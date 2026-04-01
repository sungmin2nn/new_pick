"""
종목 선정 모듈 - 대형주 역추세 전략
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, field, asdict

# 상위 디렉토리 import 설정
sys.path.insert(0, str(Path(__file__).parent.parent))

# 네이버 금융 우선, pykrx 폴백
try:
    from naver_market import stock
except ImportError:
    from pykrx import stock

import pandas as pd

# 경고 무시
import warnings
warnings.filterwarnings('ignore')


@dataclass
class StockCandidate:
    """종목 후보 데이터 클래스"""
    code: str
    name: str
    price: int
    change_pct: float
    trading_value: int
    market_cap: int
    volume: int
    avg_volume: int = 0
    score: float = 0.0
    score_detail: Dict = field(default_factory=dict)
    rank: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class StockSelector:
    """
    대형주 역추세 전략 종목 선정기

    조건:
    - 가격: 5만원 이상
    - 전일 등락률: -1% 이상 하락
    - 거래대금: 500억원 이상

    점수 배점 (총 100점):
    - 하락폭: 35점
    - 거래대금: 25점
    - 시가총액: 15점
    - 거래량 변화: 15점
    - 가격대 적합성: 10점
    """

    # 전략 파라미터
    MIN_PRICE = 50000               # 최소 주가 5만원
    MAX_PRICE = 500000              # 최대 주가 50만원
    MAX_CHANGE = -1.0               # 최대 등락률 -1% (하락만)
    MIN_TRADING_VALUE = 50_000_000_000  # 최소 거래대금 500억

    # 점수 배점
    SCORE_WEIGHTS = {
        'price_drop': 35,
        'trading_value': 25,
        'market_cap': 15,
        'volume_change': 15,
        'price_range': 10,
    }

    def __init__(self):
        self.candidates: List[StockCandidate] = []
        self.selection_date: str = ""

    def fetch_market_data(self, date: str = None) -> pd.DataFrame:
        """
        시장 데이터 수집

        Args:
            date: 조회 날짜 (YYYYMMDD), None이면 최근 거래일

        Returns:
            KOSPI + KOSDAQ 전종목 데이터
        """
        if date is None:
            # 최근 거래일 조회
            date = datetime.now().strftime("%Y%m%d")

        print(f"[Selector] 시장 데이터 수집 중... ({date})")

        try:
            # KOSPI 데이터 (get_market_ohlcv_by_date 사용)
            kospi = stock.get_market_ohlcv_by_date(date, date, "KOSPI")
            if not kospi.empty:
                kospi['market'] = 'KOSPI'

            # KOSDAQ 데이터
            kosdaq = stock.get_market_ohlcv_by_date(date, date, "KOSDAQ")
            if not kosdaq.empty:
                kosdaq['market'] = 'KOSDAQ'

            # 합치기
            df = pd.concat([kospi, kosdaq])

            if df.empty:
                print(f"[Selector] 경고: {date} 데이터가 없습니다.")
                return pd.DataFrame()

            # 시가총액 데이터 추가
            kospi_cap = stock.get_market_cap_by_date(date, date, "KOSPI")
            kosdaq_cap = stock.get_market_cap_by_date(date, date, "KOSDAQ")
            cap_df = pd.concat([kospi_cap, kosdaq_cap])

            if '시가총액' in cap_df.columns:
                df = df.join(cap_df[['시가총액']], how='left')
            else:
                df['시가총액'] = 0

            # 등락률 계산
            if '시가' in df.columns and '종가' in df.columns:
                df['등락률'] = ((df['종가'] - df['시가']) / df['시가'] * 100).fillna(0)
            else:
                df['등락률'] = 0

            print(f"[Selector] 총 {len(df)}개 종목 수집 완료")
            return df

        except Exception as e:
            print(f"[Selector] 데이터 수집 오류: {e}")
            return pd.DataFrame()

    def fetch_previous_day_data(self, date: str = None) -> pd.DataFrame:
        """
        전일 데이터 수집 (역추세 판단용)
        개별 종목 방식으로 안정적으로 수집

        Args:
            date: 기준 날짜 (YYYYMMDD)

        Returns:
            전일 종가 및 등락률 데이터
        """
        if date is None:
            date = datetime.now().strftime("%Y%m%d")

        print(f"[Selector] 전일 데이터 수집 중...")

        try:
            from datetime import timedelta
            start_dt = datetime.strptime(date, "%Y%m%d") - timedelta(days=10)
            start_date = start_dt.strftime("%Y%m%d")

            # 대형주 종목 리스트 (테스트용)
            test_stocks = [
                '005930', '000660', '005380', '035420', '051910',  # 삼성전자, SK하이닉스, 현대차, NAVER, LG화학
                '006400', '035720', '005490', '000270', '012330',  # 삼성SDI, 카카오, POSCO, 기아, 현대모비스
                '028260', '207940', '096770', '003670', '066570',  # 삼성물산, 삼성바이오, SK이노베이션, SK, LG전자
                '055550', '105560', '086790', '032830', '018260',  # 신한지주, KB금융, 하나금융, 삼성생명, 삼성중공업
                '034730', '003550', '015760', '017670', '024110',  # SK, LG, 한국전력, SK텔레콤, 기업은행
                '086280', '316140', '009150', '010950', '011200',  # 현대글로비스, 우리금융, 삼성전기, S-Oil, HMM
            ]

            results = []
            for code in test_stocks:
                try:
                    df = stock.get_market_ohlcv(start_date, date, code)
                    if df.empty or len(df) < 2:
                        continue

                    # 마지막 2일 데이터
                    curr = df.iloc[-1]
                    prev = df.iloc[-2]

                    # 전일 등락률 (전일 종가 - 전일 시가) / 전일 시가
                    prev_change = (prev['종가'] - prev['시가']) / prev['시가'] * 100 if prev['시가'] > 0 else 0

                    # 시가총액 조회
                    try:
                        cap_df = stock.get_market_cap(date, date, code)
                        market_cap = cap_df.iloc[-1]['시가총액'] if not cap_df.empty else 0
                    except:
                        market_cap = 0

                    results.append({
                        'code': code,
                        '종가': int(curr['종가']),
                        '시가': int(curr['시가']),
                        '고가': int(curr['고가']),
                        '저가': int(curr['저가']),
                        '거래량': int(curr['거래량']),
                        '거래대금': int(curr.get('거래대금', curr['거래량'] * curr['종가'])),
                        '시가총액': int(market_cap),
                        '전일등락률': round(prev_change, 2),
                        '등락률': round((curr['종가'] - curr['시가']) / curr['시가'] * 100, 2) if curr['시가'] > 0 else 0
                    })

                except Exception as e:
                    continue

            if not results:
                print("[Selector] 경고: 데이터 수집 실패")
                return pd.DataFrame()

            df = pd.DataFrame(results)
            df.set_index('code', inplace=True)

            print(f"[Selector] 전일 데이터 수집 완료 ({len(df)}개 종목)")
            return df

        except Exception as e:
            print(f"[Selector] 전일 데이터 수집 오류: {e}")
            import traceback
            traceback.print_exc()
            return pd.DataFrame()

    def apply_filters(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        역추세 전략 필터 적용

        조건:
        - 가격: 5만원 ~ 50만원
        - 전일 등락률: -1% 이하 (하락)
        - 거래대금: 500억 이상
        """
        if df.empty:
            return df

        print(f"[Selector] 필터 적용 중... (전체 {len(df)}개)")

        # 필터 통계
        stats = {'total': len(df)}

        # 1. 가격 필터
        price_col = '종가' if '종가' in df.columns else 'close'
        mask_price = (df[price_col] >= self.MIN_PRICE) & (df[price_col] <= self.MAX_PRICE)
        stats['price_fail'] = (~mask_price).sum()

        # 2. 하락 필터 (전일 등락률 기준)
        change_col = '전일등락률' if '전일등락률' in df.columns else '등락률'
        if change_col in df.columns:
            mask_change = df[change_col] <= self.MAX_CHANGE
            stats['change_fail'] = (~mask_change).sum()
        else:
            mask_change = pd.Series([True] * len(df), index=df.index)
            stats['change_fail'] = 0

        # 3. 거래대금 필터
        value_col = '거래대금' if '거래대금' in df.columns else 'trading_value'
        if value_col in df.columns:
            mask_value = df[value_col] >= self.MIN_TRADING_VALUE
            stats['value_fail'] = (~mask_value).sum()
        else:
            mask_value = pd.Series([True] * len(df), index=df.index)
            stats['value_fail'] = 0

        # 필터 적용
        filtered = df[mask_price & mask_change & mask_value].copy()

        print(f"[Selector] 필터 결과:")
        print(f"  - 가격 필터 제외: {stats['price_fail']}개")
        print(f"  - 하락 필터 제외: {stats['change_fail']}개")
        print(f"  - 거래대금 필터 제외: {stats['value_fail']}개")
        print(f"  - 통과: {len(filtered)}개")

        return filtered

    def calculate_score(self, row: pd.Series) -> tuple:
        """
        종목 점수 계산 (총 100점)

        Args:
            row: 종목 데이터 Series

        Returns:
            (총점, 점수 상세)
        """
        score = 0.0
        detail = {}

        # 데이터 추출
        price = row.get('종가', row.get('close', 0))
        change = row.get('전일등락률', row.get('등락률', 0))
        trading_value = row.get('거래대금', 0)
        market_cap = row.get('시가총액', 0)
        volume = row.get('거래량', 0)
        avg_volume = row.get('avg_volume', volume)  # 평균 거래량

        # 1. 하락폭 점수 (35점)
        # -1% = 10점, -3% = 20점, -5% 이상 = 35점
        drop_rate = abs(change)
        if drop_rate >= 5:
            drop_score = 35
        elif drop_rate >= 3:
            drop_score = 20 + (drop_rate - 3) * 7.5
        elif drop_rate >= 1:
            drop_score = 10 + (drop_rate - 1) * 5
        else:
            drop_score = 0

        score += drop_score
        detail['price_drop'] = round(drop_score, 1)

        # 2. 거래대금 점수 (25점)
        # 500억 = 5점, 1000억 = 15점, 3000억+ = 25점
        tv_billion = trading_value / 100_000_000_000
        if tv_billion >= 30:
            tv_score = 25
        elif tv_billion >= 10:
            tv_score = 15 + (tv_billion - 10) * 0.5
        elif tv_billion >= 5:
            tv_score = 5 + (tv_billion - 5) * 2
        else:
            tv_score = max(0, tv_billion)

        score += tv_score
        detail['trading_value'] = round(tv_score, 1)

        # 3. 시가총액 점수 (15점)
        # 1조 = 5점, 5조 = 10점, 10조+ = 15점
        mc_trillion = market_cap / 1_000_000_000_000
        if mc_trillion >= 10:
            mc_score = 15
        elif mc_trillion >= 5:
            mc_score = 10 + (mc_trillion - 5) * 1
        elif mc_trillion >= 1:
            mc_score = 5 + (mc_trillion - 1) * 1.25
        else:
            mc_score = max(0, mc_trillion * 5)

        score += mc_score
        detail['market_cap'] = round(mc_score, 1)

        # 4. 거래량 변화 점수 (15점)
        # 평균 대비 1.5배 = 10점, 2배+ = 15점
        if avg_volume > 0:
            volume_ratio = volume / avg_volume
        else:
            volume_ratio = 1.0

        if volume_ratio >= 2.0:
            vol_score = 15
        elif volume_ratio >= 1.5:
            vol_score = 10 + (volume_ratio - 1.5) * 10
        elif volume_ratio >= 1.0:
            vol_score = 5 + (volume_ratio - 1.0) * 10
        else:
            vol_score = max(0, volume_ratio * 5)

        score += vol_score
        detail['volume_change'] = round(vol_score, 1)

        # 5. 가격대 적합성 (10점)
        # 5만~10만원 = 10점, 10만~20만원 = 7점, 그 외 = 5점
        if 50000 <= price <= 100000:
            price_score = 10
        elif 100000 < price <= 200000:
            price_score = 7
        elif 200000 < price <= 500000:
            price_score = 5
        else:
            price_score = 3

        score += price_score
        detail['price_range'] = round(price_score, 1)

        return round(score, 1), detail

    def select_stocks(self, date: str = None, top_n: int = 5) -> List[StockCandidate]:
        """
        종목 선정 메인 함수

        Args:
            date: 기준 날짜 (YYYYMMDD)
            top_n: 상위 N개 선정

        Returns:
            선정된 종목 리스트
        """
        self.selection_date = date or datetime.now().strftime("%Y%m%d")

        print(f"\n{'='*50}")
        print(f"[Selector] 종목 선정 시작 ({self.selection_date})")
        print(f"{'='*50}")

        # 1. 데이터 수집
        df = self.fetch_previous_day_data(self.selection_date)
        if df.empty:
            df = self.fetch_market_data(self.selection_date)

        if df.empty:
            print("[Selector] 데이터 없음 - 선정 종료")
            return []

        # 2. 필터 적용
        filtered = self.apply_filters(df)
        if filtered.empty:
            print("[Selector] 필터 통과 종목 없음")
            return []

        # 3. 점수 계산
        print(f"\n[Selector] 점수 계산 중...")
        candidates = []

        for code in filtered.index:
            try:
                row = filtered.loc[code]
                name = stock.get_market_ticker_name(code)

                score, detail = self.calculate_score(row)

                candidate = StockCandidate(
                    code=code,
                    name=name or code,
                    price=int(row.get('종가', 0)),
                    change_pct=round(row.get('전일등락률', row.get('등락률', 0)), 2),
                    trading_value=int(row.get('거래대금', 0)),
                    market_cap=int(row.get('시가총액', 0)),
                    volume=int(row.get('거래량', 0)),
                    score=score,
                    score_detail=detail
                )
                candidates.append(candidate)

            except Exception as e:
                continue

        # 4. 점수순 정렬 및 상위 N개 선정
        candidates.sort(key=lambda x: x.score, reverse=True)

        for i, c in enumerate(candidates[:top_n], 1):
            c.rank = i

        self.candidates = candidates[:top_n]

        # 5. 결과 출력
        print(f"\n[Selector] 상위 {top_n}개 종목 선정 완료:")
        print("-" * 70)
        for c in self.candidates:
            print(f"  {c.rank}. {c.name} ({c.code})")
            print(f"     가격: {c.price:,}원 | 등락률: {c.change_pct:+.2f}%")
            print(f"     점수: {c.score}점 {c.score_detail}")
        print("-" * 70)

        return self.candidates

    def get_selection_summary(self) -> dict:
        """선정 결과 요약"""
        return {
            'date': self.selection_date,
            'total_candidates': len(self.candidates),
            'candidates': [c.to_dict() for c in self.candidates],
            'strategy': '대형주_역추세',
            'params': {
                'min_price': self.MIN_PRICE,
                'max_change': self.MAX_CHANGE,
                'min_trading_value': self.MIN_TRADING_VALUE,
            }
        }


# CLI 테스트
if __name__ == "__main__":
    selector = StockSelector()
    candidates = selector.select_stocks()

    print("\n[결과 요약]")
    print(selector.get_selection_summary())
