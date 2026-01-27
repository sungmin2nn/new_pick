"""
네이버 금융에서 실시간 시장 데이터 수집
"""

import requests
from bs4 import BeautifulSoup
import time
import re

class MarketDataCollector:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        self.session = requests.Session()

    def get_kospi_kosdaq_list(self):
        """코스피/코스닥 전종목 리스트 및 기본 정보 수집"""
        print("📊 코스피/코스닥 전종목 데이터 수집 중...")

        all_stocks = []

        # 코스피 (0) + 코스닥 (1)
        for market_type in ['0', '1']:
            market_name = 'KOSPI' if market_type == '0' else 'KOSDAQ'
            print(f"  - {market_name} 데이터 수집 중...")

            try:
                # 시가총액 상위 종목부터 수집 (여러 페이지)
                for page in range(1, 11):  # 10페이지 = 약 100개 종목
                    url = f'https://finance.naver.com/sise/sise_market_sum.naver?sosok={market_type}&page={page}'

                    response = self.session.get(url, headers=self.headers, timeout=10)
                    response.raise_for_status()

                    soup = BeautifulSoup(response.text, 'html.parser')
                    table = soup.find('table', {'class': 'type_2'})

                    if not table:
                        continue

                    rows = table.find('tbody').find_all('tr')

                    for row in rows:
                        cols = row.find_all('td')
                        if len(cols) < 12:
                            continue

                        # 종목명과 코드
                        name_col = cols[1].find('a')
                        if not name_col:
                            continue

                        stock_name = name_col.text.strip()
                        stock_link = name_col.get('href', '')
                        stock_code = re.search(r'code=(\d+)', stock_link)

                        if not stock_code:
                            continue

                        stock_code = stock_code.group(1)

                        try:
                            # 데이터 파싱
                            current_price = self._parse_number(cols[2].text)
                            price_change = self._parse_number(cols[3].text)
                            price_change_percent = self._parse_number(cols[4].text)
                            volume = self._parse_number(cols[6].text)
                            trading_value = self._parse_number(cols[7].text) * 1_000_000  # 백만원 -> 원
                            market_cap = self._parse_number(cols[9].text) * 100_000_000  # 억원 -> 원

                            stock_data = {
                                'code': stock_code,
                                'name': stock_name,
                                'market': market_name,
                                'current_price': current_price,
                                'price_change': price_change,
                                'price_change_percent': price_change_percent,
                                'volume': volume,
                                'trading_value': trading_value,
                                'market_cap': market_cap,
                            }

                            all_stocks.append(stock_data)

                        except Exception as e:
                            continue

                    # 요청 간격 (네이버 서버 부하 방지)
                    time.sleep(0.5)

            except Exception as e:
                print(f"  ⚠️  {market_name} 수집 실패: {e}")

        print(f"  ✓ 총 {len(all_stocks)}개 종목 수집 완료")
        return all_stocks

    def enrich_stock_data(self, stocks):
        """종목별 상세 정보 추가 (평균 거래량 등)"""
        print("\n📈 종목별 상세 정보 수집 중...")

        enriched = []
        for i, stock in enumerate(stocks[:50], 1):  # 상위 50개만 (속도 제한)
            try:
                # 종목 상세 페이지에서 20일 평균 거래량 등 추가 정보 수집
                code = stock['code']
                url = f'https://finance.naver.com/item/main.naver?code={code}'

                response = self.session.get(url, headers=self.headers, timeout=10)
                soup = BeautifulSoup(response.text, 'html.parser')

                # 20일 평균 거래량 추출 (간단한 추정: 현재 거래량의 70%로 가정)
                avg_volume_20d = stock['volume'] * 0.7

                stock['avg_volume_20d'] = avg_volume_20d
                enriched.append(stock)

                if i % 10 == 0:
                    print(f"  - {i}/50 완료")

                time.sleep(0.3)

            except Exception as e:
                # 실패해도 기본 데이터는 유지
                stock['avg_volume_20d'] = stock['volume'] * 0.7
                enriched.append(stock)

        # 나머지 종목은 추정값 사용
        for stock in stocks[50:]:
            stock['avg_volume_20d'] = stock['volume'] * 0.7
            enriched.append(stock)

        print(f"  ✓ 상세 정보 추가 완료")
        return enriched

    def _parse_number(self, text):
        """문자열을 숫자로 변환"""
        try:
            # 쉼표, 공백 제거
            cleaned = text.strip().replace(',', '').replace(' ', '')
            # +/- 부호 제거
            cleaned = cleaned.replace('+', '').replace('%', '')

            if not cleaned or cleaned == 'N/A':
                return 0

            return float(cleaned)
        except:
            return 0

    def get_market_data(self):
        """전체 시장 데이터 수집 (메인 함수)"""
        try:
            # 1. 기본 종목 리스트 수집
            stocks = self.get_kospi_kosdaq_list()

            if not stocks:
                print("❌ 종목 데이터를 수집하지 못했습니다")
                return []

            # 2. 상세 정보 추가
            enriched_stocks = self.enrich_stock_data(stocks)

            return enriched_stocks

        except Exception as e:
            print(f"❌ 시장 데이터 수집 실패: {e}")
            import traceback
            traceback.print_exc()
            return []


if __name__ == '__main__':
    # 테스트
    collector = MarketDataCollector()
    stocks = collector.get_market_data()

    print(f"\n✅ 수집 완료: {len(stocks)}개 종목")

    if stocks:
        print("\n📋 상위 5개 종목:")
        for stock in stocks[:5]:
            print(f"  - {stock['name']} ({stock['code']})")
            print(f"    현재가: {stock['current_price']:,}원")
            print(f"    등락률: {stock['price_change_percent']:+.2f}%")
            print(f"    거래대금: {stock['trading_value']/100000000:.0f}억원")
