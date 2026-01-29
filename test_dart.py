import os
from dotenv import load_dotenv
from disclosure_collector import DisclosureCollector

load_dotenv()

api_key = os.environ.get('DART_API_KEY', '')
print(f"API Key 존재 여부: {'있음' if api_key else '없음'}")
print(f"API Key 길이: {len(api_key) if api_key else 0}")

if api_key:
    collector = DisclosureCollector(api_key)
    disclosures = collector.get_recent_disclosures()
    print(f"\n수집된 공시: {len(disclosures)}건")
    
    if disclosures:
        print("\n첫 3개 공시:")
        for disc in disclosures[:3]:
            print(f"  - {disc.get('corp_name', 'N/A')}: {disc.get('report_nm', 'N/A')}")
else:
    print("\n.env 파일에 DART_API_KEY를 설정해주세요")
