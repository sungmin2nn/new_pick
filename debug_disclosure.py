"""
공시 종목이 왜 상위에 안 오는지 디버깅
"""

import os
from dotenv import load_dotenv
from disclosure_collector import DisclosureCollector
from market_data import MarketDataCollector

load_dotenv()

# 1. 공시 수집
api_key = os.environ.get('DART_API_KEY', '')
collector = DisclosureCollector(api_key)
disclosures = collector.get_recent_disclosures()

print("="*60)
print("공시가 있는 종목 리스트")
print("="*60)

disclosure_stocks = {}
for disc in disclosures:
    corp_name = disc.get('corp_name', 'N/A')
    stock_code = disc.get('stock_code', '').replace('A', '')  # A 접두사 제거

    if stock_code not in disclosure_stocks:
        disclosure_stocks[stock_code] = {
            'name': corp_name,
            'code': stock_code,
            'disclosures': []
        }

    disclosure_stocks[stock_code]['disclosures'].append(disc)

print(f"\n공시가 있는 종목 수: {len(disclosure_stocks)}개\n")
for code, info in disclosure_stocks.items():
    print(f"- {info['name']} ({code}): {len(info['disclosures'])}건")

# 2. 시장 데이터 수집
print("\n" + "="*60)
print("시장 데이터에서 공시 종목 찾기")
print("="*60)

market_collector = MarketDataCollector()
stocks = market_collector.get_market_data()

print(f"\n수집된 전체 종목: {len(stocks)}개")

# 공시 종목이 시장 데이터에 있는지 확인
found_stocks = []
not_found_stocks = []

for code, info in disclosure_stocks.items():
    found = False
    for stock in stocks:
        if stock['code'] == code:
            found = True
            found_stocks.append({
                'code': code,
                'name': info['name'],
                'stock_data': stock,
                'disclosure_count': len(info['disclosures'])
            })
            break

    if not found:
        not_found_stocks.append(info)

print(f"\n✅ 시장 데이터에서 발견된 공시 종목: {len(found_stocks)}개")
for item in found_stocks:
    stock = item['stock_data']
    print(f"\n- {item['name']} ({item['code']})")
    print(f"  공시: {item['disclosure_count']}건")
    print(f"  현재가: {stock['current_price']:,}원")
    print(f"  거래대금: {stock['trading_value']/100000000:.1f}억원")
    print(f"  시가총액: {stock['market_cap']/100000000:.1f}억원")

print(f"\n❌ 시장 데이터에 없는 공시 종목: {len(not_found_stocks)}개")
for info in not_found_stocks:
    print(f"- {info['name']} ({info['code']})")

print("\n" + "="*60)
print("결론")
print("="*60)
print(f"공시 종목 {len(disclosure_stocks)}개 중:")
print(f"  - 시장 데이터에 포함: {len(found_stocks)}개")
print(f"  - 시장 데이터에 없음: {len(not_found_stocks)}개")
print("\n시장 데이터에 없는 종목은 1000개 수집 범위 밖이므로")
print("아무리 공시 점수가 높아도 선정될 수 없습니다.")
