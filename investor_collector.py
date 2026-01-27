"""
외국인/기관 매매 정보 수집
네이버 금융에서 전일 외국인/기관 순매수 정보 크롤링
"""

import requests
from bs4 import BeautifulSoup
import time

class InvestorCollector:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        self.session = requests.Session()

    def get_investor_data(self):
        """전일 외국인/기관 순매수 상위 종목 수집"""
        print("\n💼 외국인/기관 매매 정보 수집 중...")

        all_data = {}

        try:
            # 외국인 순매수 상위
            self._collect_foreign_buy('ALL', all_data)
            time.sleep(0.3)

            # 기관 순매수 상위
            self._collect_institution_buy('ALL', all_data)

            print(f"  ✓ 총 {len(all_data)}개 종목의 매매 정보 수집 완료")

            return all_data

        except Exception as e:
            print(f"  ⚠️  매매 정보 수집 실패: {e}")
            return {}

    def _collect_foreign_buy(self, market, data_dict):
        """외국인 순매수 상위 종목"""
        try:
            # 페이지 번호 1 (상위 30개만)
            page = 1

            url = f'https://finance.naver.com/sise/sise_group_detail.naver?type=foreign&no=0&page={page}'
            response = self.session.get(url, headers=self.headers, timeout=5)

            if response.status_code != 200:
                print(f"  ⚠️  {market} 외국인 순매수 접근 실패: HTTP {response.status_code}")
                return

            soup = BeautifulSoup(response.text, 'html.parser')

            # 테이블 파싱
            table = soup.find('table', {'class': 'type_2'})
            if not table:
                return

            rows = table.find('tbody').find_all('tr')

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 10:
                    continue

                try:
                    # 종목명
                    name_tag = cols[1].find('a')
                    if not name_tag:
                        continue

                    stock_name = name_tag.text.strip()
                    stock_code = name_tag.get('href', '').split('code=')[-1] if 'code=' in name_tag.get('href', '') else ''

                    # 외국인 순매수량
                    foreign_buy = cols[9].text.strip().replace(',', '')
                    if not foreign_buy or foreign_buy == '':
                        continue

                    foreign_buy_value = int(foreign_buy) if foreign_buy.replace('-', '').isdigit() else 0

                    # 순매수인 경우만 (양수)
                    if foreign_buy_value > 0:
                        if stock_code not in data_dict:
                            data_dict[stock_code] = {
                                'name': stock_name,
                                'code': stock_code,
                                'foreign_buy': 0,
                                'institution_buy': 0
                            }

                        data_dict[stock_code]['foreign_buy'] = foreign_buy_value

                except Exception:
                    continue

            print(f"  ✓ {market} 외국인 순매수: {len([k for k, v in data_dict.items() if v['foreign_buy'] > 0])}개 종목")

        except Exception as e:
            print(f"  ⚠️  {market} 외국인 순매수 수집 실패: {e}")

    def _collect_institution_buy(self, market, data_dict):
        """기관 순매수 상위 종목"""
        try:
            # 페이지 번호 1 (상위 30개만)
            page = 1

            url = f'https://finance.naver.com/sise/sise_group_detail.naver?type=institution&no=0&page={page}'
            response = self.session.get(url, headers=self.headers, timeout=5)

            if response.status_code != 200:
                print(f"  ⚠️  {market} 기관 순매수 접근 실패: HTTP {response.status_code}")
                return

            soup = BeautifulSoup(response.text, 'html.parser')

            # 테이블 파싱
            table = soup.find('table', {'class': 'type_2'})
            if not table:
                return

            rows = table.find('tbody').find_all('tr')

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 10:
                    continue

                try:
                    # 종목명
                    name_tag = cols[1].find('a')
                    if not name_tag:
                        continue

                    stock_name = name_tag.text.strip()
                    stock_code = name_tag.get('href', '').split('code=')[-1] if 'code=' in name_tag.get('href', '') else ''

                    # 기관 순매수량
                    institution_buy = cols[9].text.strip().replace(',', '')
                    if not institution_buy or institution_buy == '':
                        continue

                    institution_buy_value = int(institution_buy) if institution_buy.replace('-', '').isdigit() else 0

                    # 순매수인 경우만 (양수)
                    if institution_buy_value > 0:
                        if stock_code not in data_dict:
                            data_dict[stock_code] = {
                                'name': stock_name,
                                'code': stock_code,
                                'foreign_buy': 0,
                                'institution_buy': 0
                            }

                        data_dict[stock_code]['institution_buy'] = institution_buy_value

                except Exception:
                    continue

            print(f"  ✓ {market} 기관 순매수: {len([k for k, v in data_dict.items() if v['institution_buy'] > 0])}개 종목")

        except Exception as e:
            print(f"  ⚠️  {market} 기관 순매수 수집 실패: {e}")

    def calculate_investor_score(self, stock_code, investor_data):
        """종목별 외국인/기관 점수 계산 (10점)"""
        if stock_code not in investor_data:
            return 0

        data = investor_data[stock_code]
        foreign_buy = data.get('foreign_buy', 0)
        institution_buy = data.get('institution_buy', 0)

        score = 0

        # 외국인 순매수 점수 (최대 6점)
        if foreign_buy >= 1000000:  # 100만주 이상
            score += 6
        elif foreign_buy >= 500000:  # 50만주 이상
            score += 5
        elif foreign_buy >= 100000:  # 10만주 이상
            score += 4
        elif foreign_buy >= 50000:   # 5만주 이상
            score += 3
        elif foreign_buy > 0:         # 순매수
            score += 2

        # 기관 순매수 점수 (최대 4점)
        if institution_buy >= 1000000:  # 100만주 이상
            score += 4
        elif institution_buy >= 500000:  # 50만주 이상
            score += 3
        elif institution_buy >= 100000:  # 10만주 이상
            score += 2
        elif institution_buy > 0:         # 순매수
            score += 1

        # 최대 10점으로 제한
        return min(score, 10)


if __name__ == '__main__':
    # 테스트
    collector = InvestorCollector()
    data = collector.get_investor_data()

    print(f"\n✅ 수집 완료: {len(data)}개 종목")

    if data:
        print("\n💼 외국인/기관 순매수 상위 10개:")
        sorted_stocks = sorted(
            data.items(),
            key=lambda x: x[1]['foreign_buy'] + x[1]['institution_buy'],
            reverse=True
        )

        for i, (code, info) in enumerate(sorted_stocks[:10], 1):
            print(f"{i}. {info['name']} ({code})")
            print(f"   외국인: {info['foreign_buy']:,}주 | 기관: {info['institution_buy']:,}주")
