"""
대형주 역추세 전략
- 시총 상위 대형주 중 전일 하락 종목
- 기술적 과매도 + 반등 가능성
"""

import sys
import logging
from pathlib import Path
from typing import List, Dict
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from .base import BaseStrategy, Candidate
from .registry import StrategyRegistry
from utils import format_kst_time

logger = logging.getLogger(__name__)

# 네이버 금융 우선, pykrx 폴백
try:
    from naver_market import stock as naver_stock
    pykrx_stock = naver_stock
except ImportError:
    try:
        from pykrx import stock as pykrx_stock
    except ImportError:
        pykrx_stock = None

# KOSPI 지수 + RSI용 historical 데이터: KRX OpenAPI (pykrx 우회)
try:
    from paper_trading.utils.krx_api import KRXClient
    _krx_client = None
    def _get_krx() -> "KRXClient | None":
        global _krx_client
        if _krx_client is None:
            try:
                _krx_client = KRXClient()
            except Exception as e:
                logger.warning(f"KRX OpenAPI 초기화 실패: {e}")
                _krx_client = False
        return _krx_client if _krx_client else None
except ImportError:
    _get_krx = lambda: None

# pykrx fallback (KRX OpenAPI 실패 시)
try:
    from pykrx import stock as _pykrx_raw
except ImportError:
    _pykrx_raw = None


@StrategyRegistry.register
class LargecapContrarianStrategy(BaseStrategy):
    """대형주 역추세 전략"""

    STRATEGY_ID = "largecap_contrarian"
    STRATEGY_NAME = "대형주 역추세"
    DESCRIPTION = "시총 상위 대형주 중 전일 하락 종목에서 반등 기회 포착"

    # 필터 조건
    MIN_PRICE = 5000          # 최소 가격
    MAX_CHANGE = -1.5         # 최대 등락률 (하락만)
    MIN_TRADING_VALUE = 50    # 최소 거래대금 (억)
    MIN_MARKET_CAP = 1_000_000_000_000  # 최소 시가총액 (1조원)
    KOSPI_DROP_THRESHOLD = -2.0  # KOSPI 급락 시 매수 차단 (%)
    RSI_PERIOD = 14           # RSI 계산 기간
    RSI_OVERSOLD = 35         # RSI 과매도 임계 (≤이면 진입 후보)
    RSI_LOOKBACK_DAYS = 20    # RSI 계산용 과거 데이터 일수

    # 점수 가중치
    WEIGHTS = {
        'market_cap': 30,      # 시가총액 (대형주)
        'change_pct': 25,      # 하락폭 (클수록)
        'trading_value': 20,   # 거래대금
        'price_level': 15,     # 가격대
        'volatility': 10       # 변동성
    }

    def __init__(self):
        super().__init__()

    def select_stocks(self, date: str = None, top_n: int = 5) -> List[Candidate]:
        """종목 선정"""
        if date is None:
            date = format_kst_time(format_str='%Y%m%d')

        self.selection_date = date
        print(f"\n[{self.STRATEGY_NAME}] 종목 선정 시작 ({date})")

        # 0. KOSPI 시장 상태 확인 (위험 차단)
        kospi_change = self._get_kospi_change(date)
        if kospi_change is not None and kospi_change <= self.KOSPI_DROP_THRESHOLD:
            logger.warning(
                f"[{self.STRATEGY_NAME}] KOSPI 급락 ({kospi_change:+.2f}%) "
                f"≤ {self.KOSPI_DROP_THRESHOLD}% → 매수 차단"
            )
            print(f"  ⛔ KOSPI {kospi_change:+.2f}% 급락 → 진입 차단 (Phase 2B 손실 방지)")
            return []

        if kospi_change is not None:
            print(f"  KOSPI: {kospi_change:+.2f}% (정상)")

        # 1. 전체 종목 데이터 수집
        all_stocks = self._fetch_market_data(date)
        if not all_stocks:
            print(f"  데이터 없음")
            return []

        print(f"  전체 종목: {len(all_stocks)}개")

        # 2. 1차 필터링 (가격/시총/거래대금/하락률)
        filtered = self._filter_stocks(all_stocks)
        print(f"  1차 필터 통과: {len(filtered)}개")

        # 3. 2차 필터링 (RSI 과매도) - 비싸므로 1차 통과한 것만
        rsi_filtered = self._filter_by_rsi(filtered, date)
        print(f"  RSI 필터 통과: {len(rsi_filtered)}개 (RSI≤{self.RSI_OVERSOLD})")

        # 4. 점수 계산
        scored = self._calculate_scores(rsi_filtered)

        # 5. 상위 N개 선정
        scored.sort(key=lambda x: x.score, reverse=True)
        self.candidates = scored[:top_n]

        for i, c in enumerate(self.candidates, 1):
            c.rank = i

        print(f"  선정 완료: {len(self.candidates)}개")
        return self.candidates

    def _fetch_market_data(self, date: str) -> List[Dict]:
        """시장 데이터 수집"""
        if pykrx_stock is None:
            print("  pykrx 없음")
            return []

        stocks = []

        try:
            # 코스피 + 코스닥
            for market in ['KOSPI', 'KOSDAQ']:
                df = pykrx_stock.get_market_ohlcv_by_ticker(date, market=market)
                cap_df = pykrx_stock.get_market_cap_by_ticker(date, market=market)

                if df.empty:
                    continue

                for code in df.index:
                    try:
                        row = df.loc[code]
                        cap_row = cap_df.loc[code] if code in cap_df.index else None

                        close = int(row['종가'])
                        if close == 0:
                            continue

                        change = float(row['등락률']) if '등락률' in row else 0
                        volume = int(row['거래량'])
                        trading_value = int(row['거래대금']) if '거래대금' in row else 0

                        market_cap = int(cap_row['시가총액']) if cap_row is not None else 0

                        name = pykrx_stock.get_market_ticker_name(code)

                        stocks.append({
                            'code': code,
                            'name': name,
                            'price': close,
                            'change_pct': change,
                            'volume': volume,
                            'trading_value': trading_value,
                            'market_cap': market_cap,
                            'market': market
                        })
                    except Exception as e:
                        logger.debug(f"종목 {code} 데이터 처리 오류: {e}")
                        continue

        except Exception as e:
            print(f"  데이터 수집 오류: {e}")

        return stocks

    def _get_kospi_change(self, date: str) -> float | None:
        """KOSPI 종합지수 일일 등락률 (KRX OpenAPI 우선, pykrx 폴백)"""
        # 1차: KRX OpenAPI (안정적)
        krx = _get_krx() if callable(_get_krx) else None
        if krx:
            chg = krx.get_kospi_change(date)
            if chg is not None:
                return chg

        # 2차: pykrx 폴백
        if _pykrx_raw is None:
            logger.debug("pykrx 미설치 - KOSPI 지수 조회 불가")
            return None

        try:
            end_dt = datetime.strptime(date, "%Y%m%d")
            start_dt = end_dt - timedelta(days=10)
            df = _pykrx_raw.get_index_ohlcv(
                start_dt.strftime("%Y%m%d"), date, "1001"
            )
            if df is not None and len(df) >= 2:
                prev_close = df['종가'].iloc[-2]
                curr_close = df['종가'].iloc[-1]
                if prev_close > 0:
                    return round((curr_close - prev_close) / prev_close * 100, 2)
        except Exception as e:
            logger.warning(f"KOSPI 지수 조회 오류 (pykrx 폴백): {e}")

        return None

    def _filter_by_rsi(self, stocks: List[Dict], date: str) -> List[Dict]:
        """RSI(14) ≤ 임계값 필터 (과매도 종목만)

        KRX OpenAPI로 최근 20거래일 종가 fetch → RSI 계산.
        KRX 호출 실패 시 필터 통과(보수적).
        """
        krx = _get_krx() if callable(_get_krx) else None
        if not krx:
            logger.warning(f"[{self.STRATEGY_NAME}] KRX OpenAPI 사용 불가 - RSI 필터 skip")
            return stocks

        passed = []
        for s in stocks:
            try:
                rsi = self._calc_rsi(s['code'], date, krx, market=s.get('market', 'KOSPI'))
                if rsi is None:
                    # 데이터 부족 시 보수적으로 통과
                    passed.append(s)
                    continue
                if rsi <= self.RSI_OVERSOLD:
                    s['rsi'] = round(rsi, 1)
                    passed.append(s)
            except Exception as e:
                logger.debug(f"RSI 계산 실패 {s['code']}: {e}")
                passed.append(s)  # 보수적
        return passed

    def _calc_rsi(self, code: str, date: str, krx, market: str = 'KOSPI') -> float | None:
        """단일 종목 RSI(14) 계산 - KRX OpenAPI historical fetch

        Args:
            code: 종목코드
            date: 기준 날짜 (YYYYMMDD) — 이 날짜의 종가 포함하여 RSI 계산
            krx: KRXClient 인스턴스
            market: 시장
        """
        end_dt = datetime.strptime(date, "%Y%m%d")
        start_dt = end_dt - timedelta(days=self.RSI_LOOKBACK_DAYS + 7)  # 주말 여유

        try:
            df = krx.get_history(
                code,
                start_dt.strftime("%Y%m%d"),
                end_dt.strftime("%Y%m%d"),
                market=market
            )
        except Exception as e:
            logger.debug(f"history fetch 실패 {code}: {e}")
            return None

        if df.empty or '종가' not in df.columns or len(df) < self.RSI_PERIOD + 1:
            return None

        closes = df['종가'].astype(float).values
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]

        # 단순 평균 RSI (Wilder's smoothing은 과도)
        period = self.RSI_PERIOD
        if len(gains) < period:
            return None
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def _filter_stocks(self, stocks: List[Dict]) -> List[Dict]:
        """필터링"""
        filtered = []

        for s in stocks:
            # 시가총액 조건 (대형주만)
            if s['market_cap'] < self.MIN_MARKET_CAP:
                continue

            # 가격 조건
            if s['price'] < self.MIN_PRICE:
                continue

            # 하락 조건
            if s['change_pct'] > self.MAX_CHANGE:
                continue

            # 거래대금 조건 (억 단위)
            if s['trading_value'] < self.MIN_TRADING_VALUE * 100000000:
                continue

            # 우선주/스팩 제외
            name = s.get('name', '')
            if any(x in name for x in ['우', '스팩', 'SPAC', '리츠']):
                continue

            filtered.append(s)

        return filtered

    def _calculate_scores(self, stocks: List[Dict]) -> List[Candidate]:
        """점수 계산"""
        if not stocks:
            return []

        # 정규화를 위한 최대/최소값
        max_cap = max(s['market_cap'] for s in stocks) or 1
        max_change = max(abs(s['change_pct']) for s in stocks) or 1
        max_value = max(s['trading_value'] for s in stocks) or 1

        candidates = []

        for s in stocks:
            scores = {}

            # 시가총액 점수 (대형주 우대)
            scores['market_cap'] = (s['market_cap'] / max_cap) * self.WEIGHTS['market_cap']

            # 하락폭 점수 (많이 하락할수록)
            scores['change_pct'] = (abs(s['change_pct']) / max_change) * self.WEIGHTS['change_pct']

            # 거래대금 점수
            scores['trading_value'] = (s['trading_value'] / max_value) * self.WEIGHTS['trading_value']

            # 가격대 점수 (중간 가격대 우대)
            if 10000 <= s['price'] <= 100000:
                scores['price_level'] = self.WEIGHTS['price_level']
            elif 5000 <= s['price'] < 10000:
                scores['price_level'] = self.WEIGHTS['price_level'] * 0.7
            else:
                scores['price_level'] = self.WEIGHTS['price_level'] * 0.5

            total_score = sum(scores.values())

            candidates.append(Candidate(
                code=s['code'],
                name=s['name'],
                price=s['price'],
                change_pct=s['change_pct'],
                score=round(total_score, 1),
                score_detail=scores,
                market_cap=s['market_cap'],
                volume=s['volume'],
                trading_value=s['trading_value']
            ))

        return candidates

    def get_params(self) -> Dict:
        return {
            'min_price': self.MIN_PRICE,
            'max_change': self.MAX_CHANGE,
            'min_trading_value': self.MIN_TRADING_VALUE,
            'min_market_cap': self.MIN_MARKET_CAP,
            'kospi_drop_threshold': self.KOSPI_DROP_THRESHOLD,
            'weights': self.WEIGHTS
        }
