"""
외국인/기관 매매 정보 수집
pykrx 라이브러리를 사용한 한국거래소(KRX) 공식 데이터 수집
"""

from datetime import datetime, timedelta
import time

class InvestorCollector:
    def __init__(self):
        self.use_pykrx = True
        try:
            from pykrx import stock
            self.pykrx_stock = stock
        except ImportError:
            print("  ⚠️  pykrx 라이브러리가 설치되지 않았습니다. 투자자 데이터를 수집하지 않습니다.")
            self.use_pykrx = False

    def get_investor_data(self):
        """전일 외국인/기관 순매수 상위 종목 수집"""
        print("\n💼 외국인/기관 매매 정보 수집 중...")

        if not self.use_pykrx:
            print("  ⚠️  pykrx를 사용할 수 없습니다. 투자자 점수는 0점으로 처리됩니다.")
            return {}

        try:
            # 전일 날짜 계산 (장 마감일 기준)
            today = datetime.now()
            yesterday = today - timedelta(days=1)

            # 주말 처리
            while yesterday.weekday() >= 5:  # 5=토요일, 6=일요일
                yesterday = yesterday - timedelta(days=1)

            date_str = yesterday.strftime('%Y%m%d')

            print(f"  📅 조회 날짜: {date_str}")

            all_data = {}

            # KOSPI + KOSDAQ 외국인/기관 순매수 데이터 수집
            for market in ['KOSPI', 'KOSDAQ']:
                try:
                    # 외국인 순매수 상위 종목
                    foreign_df = self.pykrx_stock.get_market_net_purchases_of_equities_by_ticker(
                        date_str,
                        date_str,
                        market,
                        "외국인"
                    )

                    if foreign_df is not None and not foreign_df.empty:
                        # 순매수 상위 30개 (컬럼명: 순매수거래량)
                        foreign_top = foreign_df.nlargest(30, '순매수거래량')

                        for ticker in foreign_top.index:
                            if ticker not in all_data:
                                # 종목명 조회
                                name = self.pykrx_stock.get_market_ticker_name(ticker)
                                all_data[ticker] = {
                                    'name': name,
                                    'code': ticker,
                                    'foreign_buy': 0,
                                    'institution_buy': 0
                                }

                            # 순매수거래량 (주)
                            all_data[ticker]['foreign_buy'] = int(foreign_top.loc[ticker, '순매수거래량'])

                    time.sleep(0.5)  # API 호출 간격

                    # 기관 순매수 상위 종목
                    inst_df = self.pykrx_stock.get_market_net_purchases_of_equities_by_ticker(
                        date_str,
                        date_str,
                        market,
                        "기관"
                    )

                    if inst_df is not None and not inst_df.empty:
                        # 순매수거래량이 양수인 것만 필터링
                        inst_positive = inst_df[inst_df['순매수거래량'] > 0]

                        if len(inst_positive) == 0:
                            # 순매수 종목이 없으면 스킵
                            pass
                        else:
                            # 순매수 상위 30개 (컬럼명: 순매수거래량)
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

                    time.sleep(0.5)  # API 호출 간격

                except Exception as e:
                    print(f"  ⚠️  {market} 데이터 수집 실패: {e}")

            print(f"  ✓ 총 {len(all_data)}개 종목의 매매 정보 수집 완료")

            return all_data

        except Exception as e:
            print(f"  ⚠️  투자자 매매 정보 수집 실패: {e}")
            return {}

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

    if collector.use_pykrx:
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
        print("\n⚠️  pykrx가 설치되지 않아 테스트를 실행할 수 없습니다.")
