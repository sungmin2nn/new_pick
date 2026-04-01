"""
외국인/기관 매매 정보 수집

데이터 소스 우선순위:
1. 네이버 금융 스크래핑 (가장 안정적)
2. pykrx 라이브러리 (폴백)
"""

from datetime import datetime, timedelta
import time
from utils import get_kst_now


class InvestorCollector:
    def __init__(self):
        self.use_naver = False
        self.use_pykrx = False
        self.naver_collector = None
        self.pykrx_stock = None

        # 1. 네이버 금융 수집기 초기화 (우선)
        try:
            from naver_investor import NaverInvestorCollector
            self.naver_collector = NaverInvestorCollector()
            self.use_naver = True
            print("  ✓ 네이버 금융 수집기 초기화")
        except Exception as e:
            print(f"  ⚠️  네이버 금융 수집기 초기화 실패: {e}")

        # 2. pykrx 폴백 준비
        try:
            from pykrx import stock
            self.pykrx_stock = stock
            self.use_pykrx = True
        except ImportError:
            print("  ⚠️  pykrx 라이브러리가 설치되지 않았습니다.")

        if not self.use_naver and not self.use_pykrx:
            print("  ⚠️  데이터 소스 없음. 투자자 데이터를 수집하지 않습니다.")

    def get_investor_data(self):
        """전일 외국인/기관 순매수 상위 종목 수집"""
        print("\n💼 외국인/기관 매매 정보 수집 중...")

        if not self.use_naver and not self.use_pykrx:
            print("  ⚠️  데이터 소스를 사용할 수 없습니다. 투자자 점수는 0점으로 처리됩니다.")
            return {}

        try:
            all_data = {}

            # 1. 네이버 금융 사용 (우선)
            if self.use_naver:
                print("  📡 네이버 금융에서 데이터 수집...")
                all_data = self._collect_via_naver()

            # 2. 네이버 실패 시 pykrx 폴백
            if not all_data and self.use_pykrx:
                print("  📡 pykrx로 데이터 수집...")
                all_data = self._collect_via_pykrx()

            print(f"  ✓ 총 {len(all_data)}개 종목의 매매 정보 수집 완료")
            return all_data

        except Exception as e:
            print(f"  ⚠️  투자자 매매 정보 수집 실패: {e}")
            return {}

    def _collect_via_naver(self):
        """네이버 금융을 통한 데이터 수집"""
        all_data = {}

        for market in ['KOSPI', 'KOSDAQ']:
            try:
                # 시가총액 상위 50개 종목의 외국인/기관 순매수 수집
                result = self.naver_collector.collect_top_investor_stocks(market, 50)
                all_data.update(result)

            except Exception as e:
                print(f"  ⚠️  네이버 {market} 수집 실패: {e}")

        return all_data

    def _collect_via_pykrx(self):
        """pykrx를 통한 데이터 수집 (폴백)"""
        all_data = {}

        # 전일 날짜 계산
        today = get_kst_now()
        yesterday = today - timedelta(days=1)

        # 주말 처리
        while yesterday.weekday() >= 5:
            yesterday = yesterday - timedelta(days=1)

        date_str = yesterday.strftime('%Y%m%d')
        print(f"  📅 조회 날짜: {date_str}")

        for market in ['KOSPI', 'KOSDAQ']:
            try:
                # 외국인 순매수 상위 종목
                foreign_df = self.pykrx_stock.get_market_net_purchases_of_equities_by_ticker(
                    date_str, date_str, market, "외국인"
                )

                if foreign_df is not None and not foreign_df.empty:
                    foreign_top = foreign_df.nlargest(30, '순매수거래량')

                    for ticker in foreign_top.index:
                        if ticker not in all_data:
                            name = self.pykrx_stock.get_market_ticker_name(ticker)
                            all_data[ticker] = {
                                'name': name,
                                'code': ticker,
                                'foreign_buy': 0,
                                'institution_buy': 0
                            }
                        all_data[ticker]['foreign_buy'] = int(foreign_top.loc[ticker, '순매수거래량'])

                time.sleep(0.5)

                # 기관 순매수 상위 종목
                inst_df = self.pykrx_stock.get_market_net_purchases_of_equities_by_ticker(
                    date_str, date_str, market, "기관"
                )

                if inst_df is not None and not inst_df.empty:
                    inst_positive = inst_df[inst_df['순매수거래량'] > 0]

                    if len(inst_positive) > 0:
                        inst_top = inst_positive.nlargest(30, '순매수거래량')

                        for ticker in inst_top.index:
                            if ticker not in all_data:
                                name = self.pykrx_stock.get_market_ticker_name(ticker)
                                all_data[ticker] = {
                                    'name': name,
                                    'code': ticker,
                                    'foreign_buy': 0,
                                    'institution_buy': 0
                                }
                            all_data[ticker]['institution_buy'] = int(inst_top.loc[ticker, '순매수거래량'])

                foreign_count = len([k for k, v in all_data.items() if v['foreign_buy'] > 0])
                inst_count = len([k for k, v in all_data.items() if v['institution_buy'] > 0])
                print(f"  ✓ {market}: 외국인 {foreign_count}개, 기관 {inst_count}개")

                time.sleep(0.5)

            except Exception as e:
                print(f"  ⚠️  pykrx {market} 수집 실패: {e}")

        return all_data

    def calculate_investor_score(self, stock_code, investor_data):
        """종목별 외국인/기관 점수 계산 (15점 만점)"""
        if stock_code not in investor_data:
            return 0

        data = investor_data[stock_code]
        foreign_buy = data.get('foreign_buy', 0)
        institution_buy = data.get('institution_buy', 0)

        score = 0

        # 외국인 순매수 점수 (최대 9점)
        if foreign_buy >= 1000000:  # 100만주 이상
            score += 9
        elif foreign_buy >= 500000:  # 50만주 이상
            score += 7
        elif foreign_buy >= 100000:  # 10만주 이상
            score += 5
        elif foreign_buy >= 50000:   # 5만주 이상
            score += 3
        elif foreign_buy > 0:         # 순매수
            score += 2

        # 기관 순매수 점수 (최대 6점)
        if institution_buy >= 1000000:  # 100만주 이상
            score += 6
        elif institution_buy >= 500000:  # 50만주 이상
            score += 5
        elif institution_buy >= 100000:  # 10만주 이상
            score += 4
        elif institution_buy >= 50000:   # 5만주 이상
            score += 2
        elif institution_buy > 0:         # 순매수
            score += 1

        # 최대 15점으로 제한
        return min(score, 15)


if __name__ == '__main__':
    # 테스트
    print("=" * 50)
    print("투자자 매매정보 수집 테스트")
    print("=" * 50)

    collector = InvestorCollector()

    print(f"\n📋 데이터 소스 상태:")
    print(f"   네이버 금융: {'✅ 활성' if collector.use_naver else '❌ 비활성'}")
    print(f"   pykrx:      {'✅ 활성' if collector.use_pykrx else '❌ 비활성'}")

    if collector.use_naver or collector.use_pykrx:
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
                print(f"   점수: {collector.calculate_investor_score(code, data)}점")
        else:
            print("\n⚠️  수집된 데이터가 없습니다.")
    else:
        print("\n⚠️  사용 가능한 데이터 소스가 없습니다.")

    print("\n" + "=" * 50)
