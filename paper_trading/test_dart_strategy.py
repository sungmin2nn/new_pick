"""
DART 공시 전략 테스트 스크립트
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from paper_trading.utils.dart_utils import DartFilter, get_dart_filter
from paper_trading.strategies.dart_disclosure import DartDisclosureStrategy


def test_dart_api():
    """DART API 연결 테스트"""
    print("=" * 60)
    print("1. DART API 연결 테스트")
    print("=" * 60)

    dart = get_dart_filter()

    api_key = os.environ.get('DART_API_KEY', '')
    print(f"API 키 설정: {'O' if api_key else 'X'} (길이: {len(api_key)})")
    print(f"DartFilter 사용 가능: {dart.is_available()}")

    if not dart.is_available():
        print("\nDART_API_KEY 환경변수를 설정하세요.")
        return False

    return True


def test_fetch_disclosures():
    """공시 수집 테스트"""
    print("\n" + "=" * 60)
    print("2. 공시 수집 테스트")
    print("=" * 60)

    dart = get_dart_filter()
    today = datetime.now().strftime('%Y%m%d')

    disclosures = dart._fetch_disclosures(today)
    print(f"오늘({today}) 전체 공시: {len(disclosures)}개")

    if disclosures:
        print("\n샘플 공시 5개:")
        for d in disclosures[:5]:
            print(f"  - {d.get('corp_name')}: {d.get('report_nm')[:40]}...")

    return len(disclosures) > 0


def test_positive_filter():
    """긍정 공시 필터 테스트"""
    print("\n" + "=" * 60)
    print("3. 긍정 공시 필터 테스트")
    print("=" * 60)

    dart = get_dart_filter()
    today = datetime.now().strftime('%Y%m%d')

    disclosures = dart._fetch_disclosures(today)
    positive = dart._filter_positive(disclosures)

    print(f"전체 공시: {len(disclosures)}개")
    print(f"긍정 공시: {len(positive)}개")

    if positive:
        print("\n긍정 공시 목록:")
        for p in positive[:10]:
            print(f"  [{p.category}] {p.corp_name} ({p.stock_code})")
            print(f"       {p.report_nm[:50]}...")

    return True


def test_strategy_run(skip_time_filter=True):
    """전략 실행 테스트"""
    print("\n" + "=" * 60)
    print("4. DART 공시 전략 실행 테스트")
    print("=" * 60)

    if skip_time_filter:
        print("(시간 필터 비활성화 - 테스트용)\n")

        # 시간 필터 우회
        class TestDartFilter(DartFilter):
            def get_recent_disclosures(self, hours_back=14):
                today = datetime.now().strftime('%Y%m%d')
                disc_today = self._fetch_disclosures(today)
                return self._filter_positive(disc_today)

        import paper_trading.utils.dart_utils as dart_module
        original_filter = dart_module._dart_filter_instance
        dart_module._dart_filter_instance = TestDartFilter()
    else:
        original_filter = None

    # 전략 실행
    strategy = DartDisclosureStrategy()
    if skip_time_filter:
        strategy.dart_filter = get_dart_filter()

    today = datetime.now().strftime('%Y%m%d')
    candidates = strategy.select_stocks(date=today, top_n=5)

    if candidates:
        print("\n=== 선정 결과 ===")
        for c in candidates:
            print(f"{c.rank}. {c.name} ({c.code}): 점수 {c.score:.1f}")
            print(f"   등락률: {c.change_pct:+.2f}%")
            if c.score_detail.get('disclosures'):
                for d in c.score_detail['disclosures'][:2]:
                    print(f"   공시: [{d['category']}] {d['report_nm'][:40]}...")
    else:
        print("\n선정된 종목 없음")

    # 원복
    if original_filter:
        import paper_trading.utils.dart_utils as dart_module
        dart_module._dart_filter_instance = original_filter

    return True


def test_strategy_registration():
    """전략 등록 확인"""
    print("\n" + "=" * 60)
    print("5. 전략 등록 확인")
    print("=" * 60)

    from paper_trading.strategies import StrategyRegistry

    strategies = StrategyRegistry.list_strategies()
    print(f"등록된 전략: {len(strategies)}개")

    dart_registered = False
    for s in strategies:
        is_dart = s['id'] == 'dart_disclosure'
        marker = " <-- DART" if is_dart else ""
        print(f"  - {s['id']}: {s['name']}{marker}")

        if is_dart:
            dart_registered = True

    return dart_registered


if __name__ == '__main__':
    print("=" * 60)
    print("DART 공시 전략 테스트")
    print(f"실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    results = []

    # 1. API 테스트
    results.append(('API 연결', test_dart_api()))

    if results[0][1]:  # API 연결 성공시에만 계속
        # 2. 공시 수집 테스트
        results.append(('공시 수집', test_fetch_disclosures()))

        # 3. 긍정 필터 테스트
        results.append(('긍정 필터', test_positive_filter()))

        # 4. 전략 실행 테스트
        results.append(('전략 실행', test_strategy_run(skip_time_filter=True)))

    # 5. 전략 등록 확인
    results.append(('전략 등록', test_strategy_registration()))

    # 결과 요약
    print("\n" + "=" * 60)
    print("테스트 결과 요약")
    print("=" * 60)

    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")

    all_passed = all(r[1] for r in results)
    print(f"\n전체 결과: {'ALL PASSED' if all_passed else 'SOME FAILED'}")
