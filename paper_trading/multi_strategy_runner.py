"""
다중 전략 실행기 (전략별 독립 시뮬레이션)
- 모든 전략 동시 실행
- 전략별 독립 시뮬레이션
- 전략별 결과 저장 및 비교
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from paper_trading.strategies import StrategyRegistry
from paper_trading.simulator import TradingSimulator
from paper_trading.selector import StockCandidate
from utils import format_kst_time, is_market_day

DATA_DIR = Path(__file__).parent.parent / "data" / "paper_trading"


def _resolve_fetch_date(date_str: str) -> str:
    """주어진 날짜가 비거래일이거나 KRX에 아직 데이터가 없으면 가장 가까운 과거 거래일로 거슬러 올라감.

    평일이라도 KRX OpenAPI가 해당 일자 데이터를 업로드하기 전이면 빈 응답이 온다
    (관측 사례: 20260422). 이 경우 is_market_day만으로는 폴백이 안 되어 전략이 0건으로 죽는다.
    KRXClient.get_stock_ohlcv로 실제 데이터 유무까지 확인한다.

    Args:
        date_str: YYYYMMDD

    Returns:
        가장 최근 거래일 (YYYYMMDD)
    """
    # KRX 클라이언트는 선택적 — 키 없거나 예외 시 평일 체크로만 폴백 (기존 동작)
    try:
        from paper_trading.utils.krx_api import KRXClient
        _krx = KRXClient()
    except Exception:
        _krx = None

    dt = datetime.strptime(date_str, '%Y%m%d')
    for _ in range(10):  # 최대 10일 거슬러 올라가기
        candidate = dt.strftime('%Y%m%d')
        if is_market_day(dt):
            if _krx is None:
                return candidate
            try:
                df = _krx.get_stock_ohlcv(candidate, market='KOSPI')
                if df is not None and len(df) > 0:
                    return candidate
            except Exception:
                # KRX 호출 실패 시에도 평일 날짜는 유효로 간주 (기존 동작 유지)
                return candidate
        dt -= timedelta(days=1)
    return date_str


def run_all_strategies(date: str = None, top_n: int = 5, simulate: bool = False) -> Dict:
    """
    모든 전략 실행

    Args:
        date: 날짜 (YYYYMMDD)
              - 과거: 백테스트
              - 오늘: 라이브
              - 미래: 다음 거래일 후보 선정 (실제 데이터 fetch는 today 사용)
        top_n: 전략당 선정 종목 수
        simulate: 시뮬레이션 실행 여부

    Returns:
        전략별 결과
    """
    today = format_kst_time(format_str='%Y%m%d')
    if date is None:
        date = today

    # 미래 날짜 → 가장 최근 거래일로 fetch (DART/KRX/naver 모두 미래/주말 데이터 미보유)
    # 단, save 시에는 원래 target_date 유지하여 next-trading-day 라우팅 호환
    target_date = date
    fetch_date = _resolve_fetch_date(min(date, today))

    print(f"\n{'='*60}")
    print(f"[Multi-Strategy Runner] 다중 전략 실행")
    print(f"  Target date: {target_date}")
    if fetch_date != target_date:
        print(f"  Fetch date:  {fetch_date} (미래 날짜 → 오늘 데이터로 선정)")
    print(f"  종목 수: 전략당 {top_n}개")
    print(f"{'='*60}")

    # 등록된 전략 확인
    strategies = StrategyRegistry.list_strategies()
    print(f"\n등록된 전략: {len(strategies)}개")
    for s in strategies:
        print(f"  - {s['name']} ({s['id']}): {s['description']}")

    # 모든 전략 실행 (fetch_date 사용 - 미래일이면 오늘 데이터)
    results = StrategyRegistry.run_all(date=fetch_date, top_n=top_n)

    # 저장은 target_date로 (paper-trading.yml 라우팅 호환)
    StrategyRegistry.save_results(results, target_date)
    date = target_date  # downstream simulate/print 호환

    # 전략별 독립 시뮬레이션
    if simulate:
        print(f"\n{'='*60}")
        print(f"[Simulation] 전략별 독립 시뮬레이션")
        print(f"{'='*60}")

        for strategy_id, result in results.items():
            print(f"\n  --- {result.strategy_name} ({strategy_id}) ---")
            try:
                candidates = result.candidates
                if not candidates:
                    print(f"  [{strategy_id}] 선정 종목 없음 - 스킵")
                    continue

                # 전략별 독립 시뮬레이터
                # 3순위 진단 룰 (2026-04-29) — team_d(theme_policy)에만 09:30 추세 확인 적용
                #   다른 팀(team_a/b/c/e/f/g/h/i)은 기존 시초가 일괄 진입 유지
                strategy_kwargs = {}
                if strategy_id == 'theme_policy':
                    strategy_kwargs['entry_mode'] = 'confirm_0930'
                simulator = TradingSimulator(
                    strategy_id=strategy_id,
                    strategy_name=result.strategy_name,
                    **strategy_kwargs,
                )

                # Candidate → StockCandidate 변환
                stock_candidates = [
                    StockCandidate(
                        code=c.code, name=c.name, price=c.price,
                        change_pct=c.change_pct, trading_value=c.trading_value,
                        market_cap=c.market_cap, volume=c.volume,
                        score=c.score, score_detail=c.score_detail, rank=c.rank,
                    )
                    for c in candidates
                ]

                sim_trades = simulator.simulate_day(stock_candidates, date)
                sim_summary = simulator.get_daily_summary()
                result.simulation = sim_summary

                print(f"  [{strategy_id}] 수익률: {sim_summary.get('total_return', 0):+.2f}% "
                      f"(승률: {sim_summary.get('win_rate', 0):.1f}%)")

                # 전략별 시뮬레이션 결과 개별 저장
                _save_strategy_simulation(date, strategy_id, result, sim_summary)

            except Exception as e:
                print(f"  [{strategy_id}] 시뮬레이션 오류: {e}")

        # 시뮬레이션 결과 포함해서 다시 저장
        StrategyRegistry.save_results(results, date)

        # 비교 리포트 저장
        _save_simulation_comparison(date, results)

    # 요약 출력
    print_summary(results, date)

    return results


def _save_strategy_simulation(date: str, strategy_id: str, result, sim_summary: dict):
    """전략별 시뮬레이션 결과 개별 저장"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    file_path = DATA_DIR / f"result_{date}_{strategy_id}.json"

    data = {
        'strategy_id': strategy_id,
        'strategy_name': result.strategy_name,
        'date': date,
        'selection': result.to_dict(),
        'simulation': sim_summary,
    }

    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    print(f"  저장: {file_path.name}")


def _save_simulation_comparison(date: str, results: Dict):
    """시뮬레이션 비교 리포트 저장"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    file_path = DATA_DIR / f"result_{date}_comparison.json"

    strategies = []
    for strategy_id, result in results.items():
        sim = result.simulation or {}
        strategies.append({
            'strategy_id': strategy_id,
            'strategy_name': result.strategy_name,
            'candidate_count': len(result.candidates),
            'total_trades': sim.get('total_trades', 0),
            'wins': sim.get('wins', 0),
            'win_rate': sim.get('win_rate', 0),
            'total_return': sim.get('total_return', 0),
            'avg_return': sim.get('avg_return', 0),
            'total_return_amount': sim.get('total_return_amount', 0),
        })

    # 수익률 기준 랭킹
    ranked = sorted(strategies, key=lambda x: x['total_return'], reverse=True)

    comparison = {
        'date': date,
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'strategy_count': len(strategies),
        'strategies': strategies,
        'ranking': [
            {'rank': i + 1, 'strategy_id': s['strategy_id'],
             'strategy_name': s['strategy_name'], 'total_return': s['total_return']}
            for i, s in enumerate(ranked)
        ],
    }

    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(comparison, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n  비교 리포트 저장: {file_path.name}")


def print_summary(results: Dict, date: str):
    """결과 요약 출력"""
    print(f"\n{'='*60}")
    print(f"[Summary] 전략별 결과 요약 ({date})")
    print(f"{'='*60}")

    print(f"\n{'전략':<20} {'종목수':>8} {'총점수':>10} {'수익률':>10} {'승률':>8}")
    print("-" * 60)

    for strategy_id, result in results.items():
        name = result.strategy_name[:18]
        count = len(result.candidates)
        total_score = sum(c.score for c in result.candidates) if result.candidates else 0

        if result.simulation:
            ret = f"{result.simulation.get('total_return', 0):+.2f}%"
            wr = f"{result.simulation.get('win_rate', 0):.1f}%"
        else:
            ret = "-"
            wr = "-"

        print(f"{name:<20} {count:>8} {total_score:>10.1f} {ret:>10} {wr:>8}")

    print("-" * 60)

    # 선정 종목 상세
    print(f"\n[선정 종목 상세]")
    for strategy_id, result in results.items():
        print(f"\n  {result.strategy_name}:")
        for c in result.candidates[:5]:
            print(f"     {c.rank}. {c.name} ({c.code}): {c.change_pct:+.2f}%, 점수 {c.score}")


def compare_strategies(date: str) -> Dict:
    """전략 비교 (저장된 결과 기반)"""
    # 비교 파일 먼저 확인
    comp_file = DATA_DIR / f"result_{date}_comparison.json"
    if comp_file.exists():
        with open(comp_file, 'r', encoding='utf-8') as f:
            comparison = json.load(f)
        _print_comparison(comparison)
        return comparison

    # 없으면 candidates_all에서 비교
    comparison = StrategyRegistry.get_comparison(date)
    if not comparison:
        print(f"[Compare] {date} 데이터 없음")
        return {}

    _print_comparison(comparison)
    return comparison


def _print_comparison(comparison: dict):
    """비교 결과 출력"""
    print(f"\n{'='*60}")
    print(f"[Compare] 전략 비교 ({comparison.get('date', '')})")
    print(f"{'='*60}")

    for s in comparison.get('strategies', []):
        name = s.get('strategy_name', s.get('name', ''))
        print(f"\n{name}:")
        print(f"  종목 수: {s.get('candidate_count', s.get('count', 0))}")
        total_return = s.get('total_return')
        if total_return is not None and total_return != 0:
            print(f"  수익률: {total_return:+.2f}%")
            print(f"  승률: {s.get('win_rate', 0):.1f}%")

    ranking = comparison.get('ranking', [])
    if ranking:
        print(f"\n[랭킹]")
        for r in ranking:
            print(f"  {r['rank']}위: {r['strategy_name']} ({r['total_return']:+.2f}%)")


def main():
    """CLI"""
    parser = argparse.ArgumentParser(description='다중 전략 실행기 (전략별 독립 시뮬레이션)')
    parser.add_argument('command', choices=['run', 'compare', 'list'],
                       help='명령: run(실행), compare(비교), list(전략목록)')
    parser.add_argument('--date', '-d', type=str, default=None,
                       help='날짜 (YYYYMMDD)')
    parser.add_argument('--top-n', '-n', type=int, default=5,
                       help='전략당 종목 수')
    parser.add_argument('--simulate', '-s', action='store_true',
                       help='시뮬레이션 실행')

    args = parser.parse_args()

    if args.command == 'run':
        run_all_strategies(
            date=args.date,
            top_n=args.top_n,
            simulate=args.simulate
        )
    elif args.command == 'compare':
        date = args.date or format_kst_time(format_str='%Y%m%d')
        compare_strategies(date)
    elif args.command == 'list':
        strategies = StrategyRegistry.list_strategies()
        print("\n등록된 전략:")
        for s in strategies:
            print(f"  - {s['id']}: {s['name']}")
            print(f"    {s['description']}")


if __name__ == "__main__":
    main()
