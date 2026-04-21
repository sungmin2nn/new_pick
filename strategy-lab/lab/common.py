"""
전략 공통 유틸리티.

모든 신규 전략이 공유하는 헬퍼:
- KRX 클라이언트 lazy 초기화
- 전 영업일 계산
- KOSPI+KOSDAQ 통합 fetch
- 표준 필터 (우선주/스팩/리츠 제외)
- DataFrame → List[Dict] 변환

기존 5팀(news-trading-bot)의 헬퍼 패턴과 호환.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from . import NTB_AVAILABLE, assert_ntb_available

logger = logging.getLogger(__name__)


# ============================================================
# KRX 클라이언트 lazy singleton
# ============================================================

_krx_client = None


def get_krx() -> Optional["KRXClient"]:  # type: ignore  # noqa
    """KRXClient lazy 초기화. 실패 시 None."""
    global _krx_client
    if _krx_client is None:
        if not NTB_AVAILABLE:
            return None
        try:
            from paper_trading.utils.krx_api import KRXClient
            _krx_client = KRXClient()
        except Exception as e:
            logger.warning(f"KRX 초기화 실패: {e}")
            _krx_client = False
    return _krx_client if _krx_client else None


# ============================================================
# 영업일 계산
# ============================================================

def previous_trading_day(date: str, max_lookback: int = 7) -> Optional[str]:
    """
    주어진 날짜의 직전 영업일.
    KRX OpenAPI에 데이터가 있는 첫 날짜를 반환.
    """
    krx = get_krx()
    if not krx:
        return None

    d = datetime.strptime(date, "%Y%m%d")
    for delta in range(1, max_lookback + 1):
        candidate = (d - timedelta(days=delta))
        if candidate.weekday() >= 5:  # 토일 skip
            continue
        date_str = candidate.strftime("%Y%m%d")
        try:
            df = krx.get_stock_ohlcv(date_str, market="KOSPI")
            if not df.empty:
                return date_str
        except Exception:
            continue
    return None


# ============================================================
# 통합 시장 데이터 fetch
# ============================================================

def fetch_all_markets(date: str) -> List[Dict]:
    """
    KOSPI + KOSDAQ 전종목 OHLCV를 List[Dict] 형태로 반환.

    각 dict 키:
        code, name, market, open, high, low, close,
        prev_close (계산), change_pct, volume,
        trading_value, market_cap

    기존 5팀의 _fetch_market_data 패턴과 동일.
    """
    krx = get_krx()
    if not krx:
        return []

    stocks: List[Dict] = []

    for market in ("KOSPI", "KOSDAQ"):
        try:
            df = krx.get_stock_ohlcv(date, market=market)
        except Exception as e:
            logger.warning(f"KRX {market} {date} fetch 실패: {e}")
            continue

        if df is None or df.empty:
            continue

        for code, row in df.iterrows():
            try:
                close = int(row.get("종가", 0) or 0)
                if close == 0:
                    continue
                open_p = int(row.get("시가", 0) or 0)
                high = int(row.get("고가", 0) or 0)
                low = int(row.get("저가", 0) or 0)
                prev_change = int(row.get("전일대비", 0) or 0)
                prev_close = close - prev_change
                stocks.append({
                    "code": str(code),
                    "name": str(row.get("종목명", "") or ""),
                    "market": market,
                    "open": open_p,
                    "high": high,
                    "low": low,
                    "close": close,
                    "prev_close": prev_close,
                    "change_pct": float(row.get("등락률", 0) or 0),
                    "volume": int(row.get("거래량", 0) or 0),
                    "trading_value": int(row.get("거래대금", 0) or 0),
                    "market_cap": int(row.get("시가총액", 0) or 0),
                })
            except Exception:
                continue

    return stocks


def fetch_for_date_pair(today: str, yesterday: str) -> tuple:
    """
    2일치 데이터를 한 번에 가져오는 헬퍼.
    Returns: (today_stocks, yesterday_stocks_by_code)
    """
    today_stocks = fetch_all_markets(today)
    yesterday_stocks = fetch_all_markets(yesterday)
    yesterday_map = {s["code"]: s for s in yesterday_stocks}
    return today_stocks, yesterday_map


# ============================================================
# 표준 필터
# ============================================================

EXCLUDE_NAME_PATTERNS = ["우", "우B", "우C", "스팩", "SPAC", "리츠", "ETN", "ETF"]


def is_excluded_name(name: str) -> bool:
    """우선주/스팩/리츠/ETN/ETF 등 제외 종목 판정."""
    if not name:
        return True
    # '우' 단독 끝 (우선주) — '우리금융' 같은 건 제외
    if name.endswith("우") or name.endswith("우B") or name.endswith("우C"):
        return True
    if any(x in name for x in ["스팩", "SPAC", "리츠", "ETN"]):
        return True
    return False


def basic_filter(
    stocks: List[Dict],
    min_price: int = 1000,
    max_price: int = 500_000,
    min_market_cap: int = 0,
    min_trading_value: int = 0,
) -> List[Dict]:
    """기본 필터: 가격 범위, 시가총액, 거래대금, 우선주 제외."""
    filtered = []
    for s in stocks:
        if s.get("close", 0) < min_price:
            continue
        if s.get("close", 0) > max_price:
            continue
        if s.get("market_cap", 0) < min_market_cap:
            continue
        if s.get("trading_value", 0) < min_trading_value:
            continue
        if is_excluded_name(s.get("name", "")):
            continue
        filtered.append(s)
    return filtered


# ============================================================
# DataFrame index 보정
# ============================================================

def safe_get_history(code: str, start: str, end: str, market: str = "KOSPI"):
    """KRXClient.get_history 안전 래퍼."""
    krx = get_krx()
    if not krx:
        return None
    try:
        return krx.get_history(code, start, end, market=market)
    except Exception as e:
        logger.debug(f"history 실패 {code}: {e}")
        return None


# ============================================================
# 배치 히스토리 (종목별 API 루프 제거)
# ============================================================

import pandas as pd
from datetime import datetime as _dt, timedelta as _td


def batch_get_history(
    codes: List[str],
    start: str,
    end: str,
) -> Dict[str, pd.DataFrame]:
    """여러 종목의 기간 OHLCV를 캐시된 전종목 일별 데이터에서 추출.

    krx.get_history()는 종목 1개당 날짜 루프를 돌아 API를 N번 호출하지만,
    이 함수는 날짜별 전종목 OHLCV(캐시 hit)를 읽어 한번에 추출한다.
    150종목 × 10일 = get_history 기준 1,500 API → 여기선 20 캐시 read.

    Returns:
        {code: DataFrame(index=날짜str, columns=[시가,고가,저가,종가,거래량,거래대금,시가총액])}
    """
    krx = get_krx()
    if not krx:
        return {}

    start_dt = _dt.strptime(start, "%Y%m%d")
    end_dt = _dt.strptime(end, "%Y%m%d")

    code_set = set(codes)
    # {code: [{날짜, 시가, ...}, ...]}
    result_rows: Dict[str, List[Dict]] = {c: [] for c in code_set}

    cur = start_dt
    while cur <= end_dt:
        if cur.weekday() >= 5:
            cur += _td(days=1)
            continue
        date_str = cur.strftime("%Y%m%d")
        # 전종목 OHLCV (캐시 hit: ~15ms)
        for market in ("KOSPI", "KOSDAQ"):
            try:
                df = krx.get_stock_ohlcv(date_str, market=market)
            except Exception:
                continue
            if df is None or df.empty:
                continue
            # 해당 종목만 추출
            matched = code_set & set(df.index)
            for code in matched:
                row = df.loc[code]
                result_rows[code].append({
                    "날짜": date_str,
                    "시가": row.get("시가", 0),
                    "고가": row.get("고가", 0),
                    "저가": row.get("저가", 0),
                    "종가": row.get("종가", 0),
                    "거래량": row.get("거래량", 0),
                    "거래대금": row.get("거래대금", 0),
                    "시가총액": row.get("시가총액", 0),
                })
        cur += _td(days=1)

    # DataFrame 변환
    result: Dict[str, pd.DataFrame] = {}
    for code, rows in result_rows.items():
        if not rows:
            result[code] = pd.DataFrame()
        else:
            df = pd.DataFrame(rows).set_index("날짜").sort_index()
            result[code] = df

    return result


__all__ = [
    "get_krx",
    "previous_trading_day",
    "fetch_all_markets",
    "fetch_for_date_pair",
    "basic_filter",
    "is_excluded_name",
    "safe_get_history",
    "batch_get_history",
    "EXCLUDE_NAME_PATTERNS",
]
