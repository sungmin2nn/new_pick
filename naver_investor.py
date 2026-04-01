"""
네이버 금융 외국인/기관 순매매 수집기
pykrx 대체용 - 네이버 금융에서 직접 스크래핑
"""

import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime
import re


class NaverInvestorCollector:
    """네이버 금융 외국인/기관 순매매 수집"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })

    def get_market_cap_top(self, market='kospi', limit=100):
        """시가총액 상위 종목 코드 수집

        Args:
            market: 'kospi' 또는 'kosdaq'
            limit: 수집할 종목 수

        Returns:
            list: [(종목코드, 종목명), ...]
        """
        sosok = '0' if market.lower() == 'kospi' else '1'
        stocks = []
        page = 1

        while len(stocks) < limit:
            url = f'https://finance.naver.com/sise/sise_market_sum.naver?sosok={sosok}&page={page}'

            try:
                response = self.session.get(url, timeout=10)
                response.encoding = 'euc-kr'

                if response.status_code != 200:
                    break

                soup = BeautifulSoup(response.text, 'html.parser')
                table = soup.find('table', class_='type_2')

                if not table:
                    break

                rows = table.find_all('tr')
                found_in_page = 0

                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) < 2:
                        continue

                    # 종목 링크에서 코드 추출
                    link = cols[1].find('a')
                    if link and 'href' in link.attrs:
                        href = link['href']
                        match = re.search(r'code=(\d{6})', href)
                        if match:
                            code = match.group(1)
                            name = link.get_text(strip=True)
                            stocks.append((code, name))
                            found_in_page += 1

                            if len(stocks) >= limit:
                                break

                if found_in_page == 0:
                    break

                page += 1
                time.sleep(0.3)

            except Exception as e:
                print(f"  ⚠️  페이지 {page} 수집 실패: {e}")
                break

        return stocks

    def get_investor_trading(self, code):
        """종목별 외국인/기관 순매매량 조회

        Args:
            code: 종목코드 (6자리)

        Returns:
            dict: {'foreign': 외국인순매매, 'institution': 기관순매매, 'date': 날짜}
        """
        url = f'https://finance.naver.com/item/frgn.naver?code={code}'

        try:
            response = self.session.get(url, timeout=10)
            response.encoding = 'euc-kr'

            if response.status_code != 200:
                return None

            soup = BeautifulSoup(response.text, 'html.parser')

            # 테이블 찾기 (외국인/기관 일별 매매)
            tables = soup.find_all('table')

            for table in tables:
                rows = table.find_all('tr')
                if len(rows) < 3:
                    continue

                # 헤더 확인
                header_row = rows[0]
                headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]

                if '기관' in headers and '외국인' in headers:
                    # 첫 번째 데이터 행 (가장 최근)
                    for data_row in rows[2:]:  # 헤더 2줄 건너뛰기
                        cols = data_row.find_all('td')
                        if len(cols) >= 7:
                            date_str = cols[0].get_text(strip=True)
                            inst_text = cols[5].get_text(strip=True).replace(',', '').replace('+', '')
                            frgn_text = cols[6].get_text(strip=True).replace(',', '').replace('+', '')

                            try:
                                institution = int(inst_text) if inst_text and inst_text != '-' else 0
                                foreign = int(frgn_text) if frgn_text and frgn_text != '-' else 0

                                return {
                                    'date': date_str,
                                    'foreign': foreign,
                                    'institution': institution
                                }
                            except ValueError:
                                continue

            return None

        except Exception as e:
            return None

    def collect_top_investor_stocks(self, market='KOSPI', top_n=50):
        """시가총액 상위 종목들의 외국인/기관 순매수 수집

        Args:
            market: 'KOSPI' 또는 'KOSDAQ'
            top_n: 수집할 종목 수

        Returns:
            dict: {종목코드: {'name': 이름, 'foreign_buy': 외국인순매수, 'institution_buy': 기관순매수}}
        """
        print(f"  📡 네이버 금융에서 {market} 상위 {top_n}개 종목 수집...")

        # 1. 시가총액 상위 종목 가져오기
        stocks = self.get_market_cap_top(market.lower(), top_n)
        print(f"  ✓ {len(stocks)}개 종목 코드 수집")

        result = {}
        foreign_positive = 0
        inst_positive = 0

        # 2. 각 종목별 외국인/기관 순매매 조회
        for i, (code, name) in enumerate(stocks):
            data = self.get_investor_trading(code)

            if data:
                foreign = data['foreign']
                institution = data['institution']

                # 순매수 양수인 종목만 저장
                if foreign > 0 or institution > 0:
                    result[code] = {
                        'name': name,
                        'code': code,
                        'foreign_buy': max(foreign, 0),
                        'institution_buy': max(institution, 0)
                    }

                    if foreign > 0:
                        foreign_positive += 1
                    if institution > 0:
                        inst_positive += 1

            # 진행 표시
            if (i + 1) % 20 == 0:
                print(f"    ... {i + 1}/{len(stocks)} 완료")

            time.sleep(0.2)  # 요청 간격

        print(f"  ✓ {market}: 외국인 순매수 {foreign_positive}개, 기관 순매수 {inst_positive}개")
        return result


# 테스트
if __name__ == '__main__':
    print("=" * 50)
    print("네이버 금융 외국인/기관 순매매 수집 테스트")
    print("=" * 50)

    collector = NaverInvestorCollector()

    # 삼성전자 테스트
    print("\n1. 삼성전자 외국인/기관 순매매:")
    data = collector.get_investor_trading('005930')
    if data:
        print(f"   날짜: {data['date']}")
        print(f"   외국인: {data['foreign']:,}주")
        print(f"   기관: {data['institution']:,}주")
    else:
        print("   데이터 없음")

    # KOSPI 상위 30개 테스트
    print("\n2. KOSPI 상위 30개 종목 순매수:")
    result = collector.collect_top_investor_stocks('KOSPI', 30)

    if result:
        print(f"\n   순매수 종목 {len(result)}개:")
        sorted_result = sorted(result.items(),
                               key=lambda x: x[1]['foreign_buy'] + x[1]['institution_buy'],
                               reverse=True)
        for code, info in sorted_result[:10]:
            print(f"   - {info['name']}: 외국인 {info['foreign_buy']:,} / 기관 {info['institution_buy']:,}")

    print("\n" + "=" * 50)
