"""
임마누엘 스퀴즈 플레이 — 베이스 (P3-3b, DEC-006 코드화).

KOSPI v6 / KOSDAQ v5 변형이 공유하는 데이터 fetch + 필터 + 점수 로직.
실제 변형은 squeeze_play_kospi_v6.py / squeeze_play_kosdaq_v5.py 에서 상수 오버라이드.

데이터 소스 우선순위:
1. KRX OpenAPI (paper_trading.utils.krx_api.KRXClient) — 과거 + 당일
2. pykrx 폴백
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from .base import BaseStrategy, Candidate
from ._squeeze_common import (
    KOSPI_TOP_53,
    KOSDAQ_TOP_35,
    BB_PERIOD,
    PERCENT_B_MAX,
    MA200_PERIOD,
    compute_indicators,
    passes_variant,
    score_candidate,
)

logger = logging.getLogger(__name__)

# 데이터 소스 (momentum.py 와 동일 폴백 패턴)
try:
    from paper_trading.utils.krx_api import KRXClient
    _krx_client: "KRXClient | bool | None" = None

    def _get_krx() -> Optional["KRXClient"]:
        global _krx_client
        if _krx_client is None:
            try:
                _krx_client = KRXClient()
            except Exception as e:
                logger.warning(f"KRX OpenAPI 초기화 실패: {e}")
                _krx_client = False
        return _krx_client if _krx_client else None
except ImportError:
    def _get_krx():
        return None

try:
    from pykrx import stock as pykrx_stock
except ImportError:
    pykrx_stock = None


# ============================================================
# 베이스 클래스 — 변형별 상수만 다름
# ============================================================

class SqueezePlayBaseStrategy(BaseStrategy):
    """스퀴즈 플레이 공통 베이스. 변형은 클래스 변수만 오버라이드."""

    # ── 변형이 오버라이드해야 할 상수 ──
    STRATEGY_ID: str = "squeeze_play_base"   # 등록 안 됨 (베이스)
    STRATEGY_NAME: str = "스퀴즈 플레이 (베이스)"
    DESCRIPTION: str = "베이스 클래스 — 직접 사용 금지"

    UNIVERSE: List[Tuple[str, str]] = []   # [(code, name), ...]
    UNIVERSE_MARKET: str = "KOSPI"          # KRX API market 파라미터
    MA200_FILTER_ENABLED: bool = False
    SQUEEZE_FILTER_ENABLED: bool = False
    SQUEEZE_MAX_SPREAD_PCT: float = 10.0

    # ── 공통 ──
    RECOMMENDED_HOLDING_DAYS: int = 5     # DEC-005
    LOOKBACK_DAYS: int = MA200_PERIOD + 30   # 200MA + 5일전 비교 + buffer

    def __init__(self):
        super().__init__()

    def select_stocks(self, date: Optional[str] = None, top_n: int = 5) -> List[Candidate]:
        if date is None:
            date = datetime.now().strftime("%Y%m%d")
        self.selection_date = date

        print(f"\n[{self.STRATEGY_NAME}] 종목 선정 시작 ({date})")
        print(f"  Universe: {len(self.UNIVERSE)}종목 ({self.UNIVERSE_MARKET})")
        print(f"  필터: MA200={self.MA200_FILTER_ENABLED}, "
              f"sqz={self.SQUEEZE_FILTER_ENABLED}@{self.SQUEEZE_MAX_SPREAD_PCT}%, "
              f"권장 보유 {self.RECOMMENDED_HOLDING_DAYS}일")

        # 시그널 일자 기준 lookback 시작일
        end_dt = datetime.strptime(date, "%Y%m%d")
        start_dt = end_dt - timedelta(days=int(self.LOOKBACK_DAYS * 1.6))  # 주말/휴일 buffer

        krx = _get_krx()
        candidates: List[Candidate] = []
        skipped_no_data = 0
        for code, name in self.UNIVERSE:
            df = self._fetch_history(krx, code, start_dt.strftime("%Y%m%d"), date)
            if df is None or df.empty or len(df) < BB_PERIOD:
                skipped_no_data += 1
                continue

            # 시그널 일자 OHLC
            try:
                last_row = df.iloc[-1]
                open_price = float(last_row.get("시가") or last_row.get("Open") or 0)
                close_price = float(last_row.get("종가") or last_row.get("Close") or 0)
            except Exception:
                continue
            if close_price <= 0:
                continue

            closes = df["종가"].astype(float).values if "종가" in df.columns \
                     else df["Close"].astype(float).values

            cache = compute_indicators(closes, close_price)
            is_positive = close_price > open_price
            if not passes_variant(
                cache, close_price, is_positive,
                self.MA200_FILTER_ENABLED, self.SQUEEZE_FILTER_ENABLED,
                self.SQUEEZE_MAX_SPREAD_PCT if self.SQUEEZE_FILTER_ENABLED else None,
            ):
                continue

            score = score_candidate(
                cache, close_price, open_price,
                self.SQUEEZE_MAX_SPREAD_PCT if self.SQUEEZE_FILTER_ENABLED else None,
                use_squeeze_score=self.SQUEEZE_FILTER_ENABLED,
            )
            change_pct = (close_price - open_price) / open_price * 100 if open_price > 0 else 0.0

            # 거래대금 / 시총 / 거래량 (KRX API 응답에 있으면)
            try:
                trading_value = int(last_row.get("거래대금", 0) or 0)
            except Exception:
                trading_value = 0
            try:
                volume = int(last_row.get("거래량", 0) or 0)
            except Exception:
                volume = 0

            cand = Candidate(
                code=code,
                name=name,
                price=int(close_price),
                change_pct=round(change_pct, 2),
                score=score,
                score_detail={
                    "percent_b": round(cache.get("percent_b", 0), 4),
                    "spread_pct": round(cache.get("spread_pct"), 2)
                                  if cache.get("spread_pct") is not None else None,
                    "ma200_rising": cache.get("ma200_rising"),
                    "is_positive_candle": is_positive,
                    "recommended_holding_days": self.RECOMMENDED_HOLDING_DAYS,
                    "variant_id": self.STRATEGY_ID,
                },
                trading_value=trading_value,
                volume=volume,
            )
            candidates.append(cand)

        candidates.sort(key=lambda c: c.score, reverse=True)
        self.candidates = candidates[:top_n]
        for i, c in enumerate(self.candidates, 1):
            c.rank = i

        print(f"  데이터 부족 스킵: {skipped_no_data}/{len(self.UNIVERSE)}")
        print(f"  필터 통과: {len(candidates)}종목, top {len(self.candidates)} 선정")
        return self.candidates

    def get_params(self) -> Dict:
        return {
            "universe_market": self.UNIVERSE_MARKET,
            "universe_size": len(self.UNIVERSE),
            "ma200_filter": self.MA200_FILTER_ENABLED,
            "squeeze_filter": self.SQUEEZE_FILTER_ENABLED,
            "squeeze_max_spread_pct": self.SQUEEZE_MAX_SPREAD_PCT,
            "bb_period": BB_PERIOD,
            "percent_b_max": PERCENT_B_MAX,
            "ma200_period": MA200_PERIOD,
            "recommended_holding_days": self.RECOMMENDED_HOLDING_DAYS,
        }

    def _fetch_history(self, krx, code: str, start: str, end: str):
        """KRX OpenAPI 1차, pykrx 폴백."""
        if krx is not None:
            try:
                df = krx.get_history(code, start, end, market=self.UNIVERSE_MARKET)
                if df is not None and not df.empty:
                    return df
            except Exception as e:
                logger.debug(f"KRX get_history 실패 {code}: {e}")
        if pykrx_stock is not None:
            try:
                df = pykrx_stock.get_market_ohlcv_by_date(start, end, code)
                if df is not None and not df.empty:
                    return df
            except Exception as e:
                logger.debug(f"pykrx 폴백 실패 {code}: {e}")
        return None
