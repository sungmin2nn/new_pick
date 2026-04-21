"""
Yahoo Finance 1분봉 크롤러 (yfinance 기반)
============================================
한국 주식의 1분봉 OHLC + volume을 yfinance 라이브러리로 수집.

특징:
- yfinance 라이브러리 (TLS fingerprint 우회 내장)
- 한국 종목 suffix: KOSPI → .KS, KOSDAQ → .KQ
- 최근 5~7일 1분봉 (Yahoo 제한)
- 디스크 캐시 (data/minute_cache/)
- Rate limit 보수적 (2s between fetches)

반환 형식:
    {
        "20260407": [
            {"time": "09:00", "open": 83200, "high": 83300, "low": 83100,
             "close": 83200, "volume": 234567},
            ...
        ],
        "20260408": [...],
        ...
    }

사용:
    from lab.yahoo_minute import YahooMinuteClient
    client = YahooMinuteClient()
    bars_by_date = client.get_minute_bars("005930", market="KOSPI")
"""

from __future__ import annotations

import json
import logging
import time
import warnings
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# yfinance 경고 억제
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

import yfinance as yf

logger = logging.getLogger(__name__)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = PROJECT_ROOT / "data" / "minute_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

KST = timezone(timedelta(hours=9))


class YahooMinuteClient:
    """yfinance 기반 한국 주식 1분봉 크롤러."""

    RATE_LIMIT_SLEEP = 2.0   # 종목 간 최소 간격
    CACHE_TTL_SECONDS = 2 * 3600   # 2시간 캐시

    def __init__(self, use_cache: bool = True):
        self.use_cache = use_cache
        self._last_call_at = 0.0

    # ─────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────

    def get_minute_bars(
        self,
        code: str,
        market: str = "KOSPI",
        days: int = 5,
    ) -> Dict[str, List[Dict]]:
        """
        한국 종목의 1분봉을 날짜별로 그룹화해 반환.
        """
        cache_key = f"{code}_{market}_{days}d"
        cache_path = CACHE_DIR / f"{cache_key}.json"

        if self.use_cache and cache_path.exists():
            age = time.time() - cache_path.stat().st_mtime
            if age < self.CACHE_TTL_SECONDS:
                try:
                    return json.loads(cache_path.read_text(encoding="utf-8"))
                except Exception:
                    pass

        bars_by_date = self._fetch_via_yfinance(code, market, days)

        if bars_by_date:
            try:
                cache_path.write_text(
                    json.dumps(bars_by_date, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception as e:
                logger.warning(f"캐시 저장 실패: {e}")

        return bars_by_date

    def get_minute_bars_for_date(
        self,
        code: str,
        date: str,
        market: str = "KOSPI",
    ) -> List[Dict]:
        """특정 날짜의 1분봉만 반환."""
        bars_by_date = self.get_minute_bars(code, market=market, days=7)
        return bars_by_date.get(date, [])

    def prefetch(
        self,
        codes_markets: List[tuple],
        days: int = 5,
        progress_callback=None,
    ) -> Dict[str, Dict[str, List[Dict]]]:
        """
        여러 종목을 한 번에 prefetch (병렬 없음 — rate limit 회피).

        Args:
            codes_markets: [(code, market), ...]
            progress_callback: (i, total, code) 콜백

        Returns:
            {code: {date: [bars]}}
        """
        results = {}
        total = len(codes_markets)
        for i, (code, market) in enumerate(codes_markets, 1):
            if progress_callback:
                progress_callback(i, total, code)
            bars = self.get_minute_bars(code, market=market, days=days)
            results[code] = bars
        return results

    # ─────────────────────────────────────────────────────────
    # Internal
    # ─────────────────────────────────────────────────────────

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_call_at
        if elapsed < self.RATE_LIMIT_SLEEP:
            time.sleep(self.RATE_LIMIT_SLEEP - elapsed)
        self._last_call_at = time.time()

    def _code_to_ticker(self, code: str, market: str) -> str:
        suffix = ".KS" if market.upper() == "KOSPI" else ".KQ"
        return f"{code}{suffix}"

    def _fetch_via_yfinance(
        self,
        code: str,
        market: str,
        days: int,
    ) -> Dict[str, List[Dict]]:
        ticker_str = self._code_to_ticker(code, market)
        self._rate_limit()

        try:
            ticker = yf.Ticker(ticker_str)
            period = f"{min(days, 7)}d"
            hist = ticker.history(period=period, interval="1m", auto_adjust=False)
        except Exception as e:
            logger.warning(f"[{code}] yfinance error: {e}")
            return {}

        if hist is None or hist.empty:
            return {}

        return self._dataframe_to_bars_by_date(hist)

    def _dataframe_to_bars_by_date(self, hist) -> Dict[str, List[Dict]]:
        """yfinance DataFrame → date별 bars dict."""
        bars_by_date: Dict[str, List[Dict]] = {}

        for ts, row in hist.iterrows():
            # ts는 pandas Timestamp (timezone-aware)
            try:
                # KST로 변환
                kst_ts = ts.tz_convert(KST) if ts.tz is not None else ts.tz_localize(KST)
            except Exception:
                continue

            date_str = kst_ts.strftime("%Y%m%d")
            time_str = kst_ts.strftime("%H:%M")

            # 한국 장 시간(09:00~15:30)만
            hm = kst_ts.hour * 60 + kst_ts.minute
            if hm < 9 * 60 or hm > 15 * 60 + 30:
                continue

            o = row.get("Open")
            h = row.get("High")
            l = row.get("Low")
            c = row.get("Close")
            v = row.get("Volume", 0)

            # NaN 체크 (pandas NaN은 != 자기 자신)
            if any(
                x is None or (isinstance(x, float) and x != x)
                for x in (o, h, l, c)
            ):
                continue

            bar = {
                "time": time_str,
                "open": int(round(float(o))),
                "high": int(round(float(h))),
                "low": int(round(float(l))),
                "close": int(round(float(c))),
                "volume": int(v) if v and v == v else 0,
            }
            bars_by_date.setdefault(date_str, []).append(bar)

        # 시간 순 정렬
        for date in bars_by_date:
            bars_by_date[date].sort(key=lambda b: b["time"])

        return bars_by_date


# ─────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────

_market_cache: Dict[str, str] = {}


def guess_market(code: str) -> str:
    """종목 코드로 KOSPI/KOSDAQ 판별 (KRXClient 당일 데이터에서 조회)."""
    global _market_cache
    if code in _market_cache:
        return _market_cache[code]

    try:
        from lab.common import get_krx
        krx = get_krx()
        if not krx:
            return "KOSPI"

        today = datetime.now(KST).strftime("%Y%m%d")
        try:
            df = krx.get_stock_ohlcv(today, market="KOSPI")
            if df is not None and not df.empty and code in df.index:
                _market_cache[code] = "KOSPI"
                return "KOSPI"
        except Exception:
            pass

        try:
            df = krx.get_stock_ohlcv(today, market="KOSDAQ")
            if df is not None and not df.empty and code in df.index:
                _market_cache[code] = "KOSDAQ"
                return "KOSDAQ"
        except Exception:
            pass
    except Exception:
        pass

    return "KOSPI"


__all__ = [
    "YahooMinuteClient",
    "guess_market",
    "CACHE_DIR",
]
