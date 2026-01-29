"""
DART API 설정 및 동작 확인 스크립트
"""

import os
from dotenv import load_dotenv
from disclosure_collector import DisclosureCollector
from datetime import datetime

# .env 파일 로드
load_dotenv()

def check_api_key():
    """API 키 확인"""
    api_key = os.environ.get('DART_API_KEY', '')

    if not api_key:
        print("❌ DART_API_KEY가 설정되지 않았습니다.")
        print("\n해결 방법:")
        print("1. .env 파일에 다음과 같이 추가하세요:")
        print("   DART_API_KEY=your_api_key_here")
        print("\n2. 또는 환경변수로 설정하세요:")
        print("   export DART_API_KEY='your_api_key_here'")
        print("\n3. API 키는 https://opendart.fss.or.kr/ 에서 발급받을 수 있습니다.")
        return None

    print(f"✅ DART_API_KEY가 설정되어 있습니다. (길이: {len(api_key)}자)")
    return api_key

def test_api_connection(api_key):
    """API 연결 테스트"""
    print("\n" + "="*60)
    print("DART API 연결 테스트")
    print("="*60)

    collector = DisclosureCollector(api_key)

    # 오늘 날짜로 테스트
    today = datetime.now().strftime('%Y%m%d')
    print(f"\n오늘({today}) 공시를 조회합니다...")

    disclosures = collector._fetch_disclosures(today)

    if disclosures:
        print(f"✅ API 연결 성공! 오늘 공시 {len(disclosures)}건 조회됨")
        print("\n최근 공시 5개:")
        for i, disc in enumerate(disclosures[:5], 1):
            print(f"{i}. {disc.get('corp_name', 'N/A')}: {disc.get('report_nm', 'N/A')}")
    else:
        print("⚠️  오늘 공시가 없거나 API 호출에 실패했습니다.")

    return len(disclosures) > 0

def test_recent_disclosures(api_key):
    """최근 긍정적 공시 조회 테스트"""
    print("\n" + "="*60)
    print("전일 18:00 ~ 당일 08:30 긍정적 공시 조회")
    print("="*60)

    collector = DisclosureCollector(api_key)
    disclosures = collector.get_recent_disclosures()

    if disclosures:
        print(f"✅ 긍정적 공시 {len(disclosures)}건 발견!")
        print("\n긍정적 공시 목록:")
        for i, disc in enumerate(disclosures, 1):
            category = disc.get('disclosure_category', '기타')
            amount = disc.get('amount', 0)
            print(f"{i}. {disc.get('corp_name', 'N/A')}")
            print(f"   - 공시: {disc.get('report_nm', 'N/A')}")
            print(f"   - 카테고리: {category}")
            if amount > 0:
                print(f"   - 금액: {amount:,}억원")
    else:
        print("⚠️  해당 시간대에 긍정적 공시가 없습니다.")
        print("\n이는 정상적인 상황일 수 있습니다:")
        print("- 공시는 매일 발생하는 것이 아닙니다.")
        print("- 전일 18:00 ~ 당일 08:30 사이에 긍정적인 공시가 없었을 수 있습니다.")
        print("- 부정적 키워드(횡령, 소송 등)가 포함된 공시는 제외됩니다.")

if __name__ == '__main__':
    print("="*60)
    print("DART API 진단 도구")
    print("="*60)

    # 1. API 키 확인
    api_key = check_api_key()

    if not api_key:
        exit(1)

    # 2. API 연결 테스트
    is_connected = test_api_connection(api_key)

    if not is_connected:
        print("\n❌ API 연결에 문제가 있습니다. API 키를 확인해주세요.")
        exit(1)

    # 3. 최근 긍정적 공시 조회
    test_recent_disclosures(api_key)

    print("\n" + "="*60)
    print("진단 완료")
    print("="*60)
