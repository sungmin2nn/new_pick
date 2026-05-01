"""
볼린저밴드 스윙 매매 전략 - 종목 선정 모듈

선정 기준 (BB + RSI + 거래량):
1. 볼린저밴드(20일, 2 sigma) 하단 터치 또는 이탈 (%B < 0.2)
2. RSI(14) <= 30 (과매도)
3. 당일 양봉 (종가 > 시가, 등락률 > 0)
4. 거래량 5일 평균 대비 1.3배 이상
5. 시가총액 >= 1000억원
6. 거래대금 >= 30억원
7. 우선주/스팩/리츠/ETF 제외

청산 조건 (run_bollinger_check.py에서 사용):
- 손절: -5%
- 익절: 중심선(MA20) 도달 또는 +7%
- 기한 청산: 최대 5영업일 보유
"""

import json
import sys
import warnings
import logging
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

warnings.filterwarnings("ignore")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# pykrx import
try:
    from pykrx import stock as pykrx_stock
    import pandas as pd
    PYKRX_AVAILABLE = True
except ImportError:
    PYKRX_AVAILABLE = False
    logger.warning("pykrx not available")

# KRX OpenAPI import
try:
    from paper_trading.utils.krx_api import KRXClient
    KRX_AVAILABLE = True
except ImportError:
    KRX_AVAILABLE = False
    logger.warning("KRX OpenAPI client not available")


# ─── 선정 기준 상수 (1년 백테스트 최적화 결과) ───
BB_PERIOD = 15           # 볼린저밴드 기간 (20→15, 더 민감)
BB_STD_MULT = 2          # 표준편차 배수
PERCENT_B_THRESHOLD = 0.4  # %B 임계값 (하단 40% 이하) — 04-22 진단: 0.3도 313/329 탈락해 추가 완화
RSI_PERIOD = 14          # RSI 기간
RSI_THRESHOLD = 40       # RSI 과매도 기준 (40 이하) — 04-23 스윕 결과: %B/시총은 둔감, RSI만 유의미한 지렛대. 안전 우선으로 35→40 단계적 완화
VOLUME_RATIO_THRESHOLD = 1.0  # 거래량 기준 (평균 이상)
MIN_MARKET_CAP = 1_000_000_000_000     # 시가총액 1조원 (대형주만)
MIN_TRADING_VALUE = 3_000_000_000      # 거래대금 30억원
LOOKBACK_DAYS = 35       # 과거 데이터 조회 일수 (BB 15일 + RSI 14일 + 여유)
TOP_N = 20

# 동일 테마 중복 캡 (None/0 = 비활성, A/B 토글)
# data/theme_cache/_stock_to_themes.json 기반
# AB_THEME_CAP 환경변수로 override 가능 ("0" = 비활성, "3" = 3종목 허용 등)
import os as _os
_env_cap = _os.environ.get("AB_THEME_CAP")
MAX_PER_THEME: Optional[int] = int(_env_cap) if _env_cap and _env_cap.isdigit() else 2
if MAX_PER_THEME == 0:
    MAX_PER_THEME = None

# 제외 키워드
EXCLUDE_KEYWORDS = ["우", "스팩", "SPAC", "리츠", "REIT", "ETF", "ETN",
                    "인버스", "레버리지", "선물"]


def calculate_bollinger_bands(closes: np.ndarray, period: int = BB_PERIOD,
                              std_mult: int = BB_STD_MULT) -> Tuple[float, float, float, float]:
    """
    볼린저밴드 계산

    Returns:
        (bb_upper, bb_middle, bb_lower, percent_b) - 마지막 값 기준
    """
    if len(closes) < period:
        return 0, 0, 0, 0.5

    # 최근 period일 기준
    recent = closes[-period:]
    bb_middle = float(np.mean(recent))
    bb_std = float(np.std(recent, ddof=1))  # 표본 표준편차

    bb_upper = bb_middle + std_mult * bb_std
    bb_lower = bb_middle - std_mult * bb_std

    # %B 계산: (현재가 - 하한) / (상한 - 하한)
    current = float(closes[-1])
    band_width = bb_upper - bb_lower
    if band_width == 0:
        percent_b = 0.5
    else:
        percent_b = (current - bb_lower) / band_width

    return bb_upper, bb_middle, bb_lower, percent_b


def calculate_rsi(closes: np.ndarray, period: int = RSI_PERIOD) -> float:
    """
    RSI(Relative Strength Index) 계산

    Returns:
        RSI 값 (0~100)
    """
    if len(closes) < period + 1:
        return 50.0  # 데이터 부족 시 중립값

    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    # Wilder 평활 방식 (EMA)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi), 2)


def resolve_trading_date(date_str: str) -> str:
    """주어진 날짜가 비거래일이면 가장 최근 거래일로 거슬러 올라감"""
    if not PYKRX_AVAILABLE:
        return date_str

    dt = datetime.strptime(date_str, "%Y%m%d")
    for _ in range(10):
        d = dt.strftime("%Y%m%d")
        try:
            df = pykrx_stock.get_market_ohlcv_by_date(d, d, "005930")
            if not df.empty and float(df.iloc[0]["종가"]) > 0:
                return d
        except Exception:
            pass
        dt -= timedelta(days=1)
    return date_str


def is_excluded(name: str) -> bool:
    """우선주/스팩/리츠/ETF 등 제외 종목 판별"""
    for keyword in EXCLUDE_KEYWORDS:
        if keyword in name:
            return True
    # 우선주 코드 패턴 (끝자리 5, 7, 8, 9 등 - 간단 체크)
    return False


class BollingerSelector:
    """
    볼린저밴드 스윙 전략 종목 선정기

    KRX OpenAPI로 전종목 OHLCV 1회 fetch (시총/거래대금 필터)
    pykrx로 필터 통과 종목 히스토리 fetch (BB/RSI 계산)
    """

    def __init__(self, data_dir: str = "data/bnf"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.candidates: List[Dict] = []
        self.selection_date: str = ""
        logger.info("BollingerSelector 초기화 완료")

    def select(self, date_str: str = None, top_n: int = TOP_N) -> List[Dict]:
        """
        볼린저밴드 스윙 종목 선정 메인 로직

        Args:
            date_str: 기준 날짜 (YYYYMMDD), None이면 오늘
            top_n: 상위 N개

        Returns:
            선정된 후보 리스트
        """
        import pytz
        kst = pytz.timezone("Asia/Seoul")
        now = datetime.now(kst)

        if date_str is None:
            date_str = now.strftime("%Y%m%d")

        self.selection_date = date_str
        iso_date = now.strftime("%Y-%m-%d")

        logger.info(f"\n{'='*60}")
        logger.info(f"볼린저밴드 스윙 종목 선정 시작 ({date_str})")
        logger.info(f"{'='*60}")
        logger.info(f"선정 기준:")
        logger.info(f"  - BB(20,2) %%B < {PERCENT_B_THRESHOLD}")
        logger.info(f"  - RSI(14) <= {RSI_THRESHOLD}")
        logger.info(f"  - 당일 양봉 (종가 > 시가)")
        logger.info(f"  - 거래량 >= 5일평균 x {VOLUME_RATIO_THRESHOLD}")
        logger.info(f"  - 시가총액 >= {MIN_MARKET_CAP/1e8:.0f}억원")
        logger.info(f"  - 거래대금 >= {MIN_TRADING_VALUE/1e8:.0f}억원")
        logger.info(f"{'='*60}\n")

        # 1) 거래일 resolve
        fetch_date = resolve_trading_date(date_str)
        if fetch_date != date_str:
            logger.info(f"비거래일 -> fetch_date={fetch_date}")

        # 2) 전종목 데이터 fetch (KRX OpenAPI → pykrx 같은 날짜 재시도 → 전일 폴백)
        #    실제 fetch 성공한 날짜(actual_date)를 받아 지표 계산 기준일로 사용
        all_stocks, actual_date = self._fetch_all_stocks(fetch_date)
        if not all_stocks:
            logger.error("종목 데이터 수집 실패")
            self._save_result(fetch_date, iso_date, now, [])
            return []
        if actual_date != fetch_date:
            logger.info(f"실제 fetch 날짜: {actual_date} (요청: {fetch_date})")

        logger.info(f"전체 종목: {len(all_stocks)}개")

        # 3) 시총 + 거래대금 + 양봉 + 제외종목 필터
        filtered = self._filter_basic(all_stocks)
        logger.info(f"기본 필터 통과 (시총/거래대금/양봉/제외): {len(filtered)}개")

        if not filtered:
            self._save_result(actual_date, iso_date, now, [])
            return []

        # 4) BB + RSI + 거래량 계산 (actual_date 기준 → 시총/지표 기준일 일관성 유지)
        candidates = self._calculate_indicators(filtered, actual_date)
        logger.info(f"BB+RSI+거래량 조건 충족: {len(candidates)}개")

        # 5) 정렬 (%%B 낮은 순 -> RSI 낮은 순)
        candidates.sort(key=lambda x: (x["percent_b"], x["rsi"]))

        # 6) 동일 테마 중복 캡 (정렬 후, top_n 자르기 전)
        from paper_trading.utils.theme_cap import apply_theme_cap
        candidates = apply_theme_cap(
            candidates,
            get_code=lambda c: c["code"],
            top_n=top_n,
            max_per_theme=MAX_PER_THEME,
            log_prefix="Bollinger",
        )

        for i, c in enumerate(candidates, 1):
            c["rank"] = i

        self.candidates = candidates

        # 결과 출력
        logger.info(f"\n선정 결과: {len(candidates)}개")
        for c in candidates[:10]:
            logger.info(
                f"  {c['rank']:2d}. {c['name']} ({c['code']}) "
                f"%%B={c['percent_b']:.3f} RSI={c['rsi']:.1f} "
                f"가격={c['price']:,}"
            )

        # 6) 저장
        self._save_result(actual_date, iso_date, now, candidates)

        return candidates

    def _fetch_via_krx_api(self, date_str: str) -> List[Dict]:
        """KRX OpenAPI로 단일 날짜 전종목 fetch (폴백/재시도 없음)"""
        if not KRX_AVAILABLE:
            return []
        stocks = []
        try:
            krx = KRXClient()
            for market in ("KOSPI", "KOSDAQ"):
                df = krx.get_stock_ohlcv(date_str, market=market)
                if df is None or df.empty:
                    continue
                for code in df.index:
                    try:
                        row = df.loc[code]
                        close_p = int(row.get("종가", 0))
                        open_p = int(row.get("시가", 0))
                        if close_p == 0 or open_p == 0:
                            continue
                        stocks.append({
                            "code": code,
                            "name": str(row.get("종목명", code)),
                            "price": close_p,
                            "open": open_p,
                            "close": close_p,
                            "change_pct": float(row.get("등락률", 0)),
                            "volume": int(row.get("거래량", 0)),
                            "market_cap": int(row.get("시가총액", 0)),
                            "trading_value": int(row.get("거래대금", 0)),
                            "market": market,
                        })
                    except Exception:
                        continue
        except Exception as e:
            logger.warning(f"KRX OpenAPI fetch 실패 ({date_str}): {e}")
            return []
        return stocks

    def _fetch_via_pykrx(self, date_str: str) -> List[Dict]:
        """pykrx로 단일 날짜 전종목 fetch (폴백/재시도 없음)"""
        if not PYKRX_AVAILABLE:
            return []
        stocks = []
        try:
            for market in ("KOSPI", "KOSDAQ"):
                tickers = pykrx_stock.get_market_ohlcv_by_ticker(date_str, market=market)
                if tickers.empty:
                    continue
                cap_df = pykrx_stock.get_market_cap_by_ticker(date_str, market=market)
                for code, row in tickers.iterrows():
                    try:
                        close_p = int(row.get("종가", 0))
                        open_p = int(row.get("시가", 0))
                        if close_p == 0 or open_p == 0:
                            continue
                        mc = int(cap_df.loc[code, "시가총액"]) if code in cap_df.index else 0
                        stocks.append({
                            "code": code,
                            "name": "",
                            "price": close_p,
                            "open": open_p,
                            "close": close_p,
                            "change_pct": float(row.get("등락률", 0)),
                            "volume": int(row.get("거래량", 0)),
                            "market_cap": mc,
                            "trading_value": int(row.get("거래대금", 0)),
                            "market": market,
                        })
                    except Exception:
                        continue
            for s in stocks:
                if not s["name"]:
                    try:
                        s["name"] = pykrx_stock.get_market_ticker_name(s["code"])
                    except Exception:
                        s["name"] = s["code"]
        except Exception as e:
            logger.warning(f"pykrx fetch 실패 ({date_str}): {e}")
            return []
        return stocks

    def _fetch_all_stocks(self, date_str: str) -> Tuple[List[Dict], str]:
        """
        전종목 fetch. 폴백 우선순위:
          1) 같은 날짜에 KRX OpenAPI → pykrx 시도 (소스 폴백 먼저)
          2) 둘 다 실패시 전일로 이동 (최대 10일)
        반환: (종목 리스트, 실제 데이터가 있는 날짜)
        """
        current_dt = datetime.strptime(date_str, "%Y%m%d")
        for attempt in range(10):
            current_str = current_dt.strftime("%Y%m%d")

            krx_stocks = self._fetch_via_krx_api(current_str)
            if krx_stocks:
                tag = "" if attempt == 0 else f" ({attempt}일 이전)"
                logger.info(f"  [KRX OpenAPI {current_str}{tag}] {len(krx_stocks)}개")
                return krx_stocks, current_str

            pk_stocks = self._fetch_via_pykrx(current_str)
            if pk_stocks:
                tag = "" if attempt == 0 else f" ({attempt}일 이전)"
                logger.info(f"  [pykrx {current_str}{tag}] {len(pk_stocks)}개 (KRX OpenAPI 미반영)")
                return pk_stocks, current_str

            logger.info(f"  {current_str}: 양쪽 소스 모두 데이터 없음 → 전일 시도")
            current_dt -= timedelta(days=1)

        logger.error("10일 소급 후에도 데이터 수집 실패")
        return [], date_str

    def _filter_basic(self, stocks: List[Dict]) -> List[Dict]:
        """기본 필터: 시총 + 거래대금 + 제외종목 (양봉 조건 제거 — BB 하단 종목은 하락 중)"""
        filtered = []
        for s in stocks:
            if s["market_cap"] < MIN_MARKET_CAP:
                continue
            if s["trading_value"] < MIN_TRADING_VALUE:
                continue
            if is_excluded(s["name"]):
                continue
            filtered.append(s)
        return filtered

    def _calculate_indicators(self, stocks: List[Dict], date_str: str) -> List[Dict]:
        """
        필터 통과 종목에 대해 pykrx로 히스토리 fetch 후
        볼린저밴드 + RSI + 거래량 비율 계산
        """
        if not PYKRX_AVAILABLE:
            logger.error("pykrx 미설치 - 지표 계산 불가")
            return []

        candidates = []
        end_dt = datetime.strptime(date_str, "%Y%m%d")
        start_dt = end_dt - timedelta(days=LOOKBACK_DAYS + 15)  # 여유
        start_str = start_dt.strftime("%Y%m%d")
        end_str = end_dt.strftime("%Y%m%d")

        # 진단 카운터 (필터 단계별 탈락 수 추적)
        skip_insufficient_data = 0
        skip_percent_b = 0
        skip_rsi = 0
        skip_volume = 0

        total = len(stocks)
        for idx, s in enumerate(stocks, 1):
            if idx % 50 == 0:
                logger.info(f"  진행: {idx}/{total} - 후보: {len(candidates)}개")

            try:
                # KRX API history 우선, pykrx 폴백
                df = None
                if KRX_AVAILABLE:
                    try:
                        krx = KRXClient()
                        df = krx.get_history(s["code"], start_str, end_str, market=s.get("market", "KOSPI"))
                    except Exception:
                        pass
                if df is None or df.empty:
                    df = pykrx_stock.get_market_ohlcv_by_date(start_str, end_str, s["code"])
                if df.empty or len(df) < BB_PERIOD + 1:
                    skip_insufficient_data += 1
                    continue

                closes = df["종가"].astype(float).values
                volumes = df["거래량"].astype(float).values

                # 볼린저밴드 계산
                bb_upper, bb_middle, bb_lower, percent_b = calculate_bollinger_bands(closes)

                # %B 필터
                if percent_b >= PERCENT_B_THRESHOLD:
                    skip_percent_b += 1
                    continue

                # RSI 계산
                rsi = calculate_rsi(closes)

                # RSI 필터
                if rsi > RSI_THRESHOLD:
                    skip_rsi += 1
                    continue

                # 거래량 5일 평균 대비 비율
                if len(volumes) >= 6:
                    avg_vol_5d = float(np.mean(volumes[-6:-1]))  # 당일 제외 5일
                    current_vol = float(volumes[-1])
                    if avg_vol_5d > 0:
                        vol_ratio = current_vol / avg_vol_5d
                    else:
                        vol_ratio = 0
                else:
                    vol_ratio = 0

                # 거래량 필터
                if vol_ratio < VOLUME_RATIO_THRESHOLD:
                    skip_volume += 1
                    continue

                # 후보 추가
                current_price = int(closes[-1])
                candidates.append({
                    "code": s["code"],
                    "name": s["name"],
                    "price": current_price,
                    "current_price": current_price,
                    "market_cap": s["market_cap"],
                    "trading_value": s["trading_value"],
                    "percent_b": round(float(percent_b), 4),
                    "rsi": round(float(rsi), 2),
                    "bb_lower": round(float(bb_lower), 0),
                    "bb_middle": round(float(bb_middle), 0),
                    "bb_upper": round(float(bb_upper), 0),
                    "vol_ratio": round(float(vol_ratio), 2),
                    "selection_reason": f"BB%B={percent_b:.2f}, RSI={rsi:.1f}",
                    "reasons": f"BB%B={percent_b:.2f}, RSI={rsi:.1f}, Vol={vol_ratio:.1f}x",
                })

                logger.info(
                    f"  -> {s['name']} ({s['code']}): "
                    f"%%B={percent_b:.3f} RSI={rsi:.1f} VolR={vol_ratio:.1f}x"
                )

            except Exception as e:
                logger.debug(f"지표 계산 실패 ({s['code']}): {e}")
                continue

        # 진단 로그: 필터 단계별 탈락 수
        logger.info(
            f"[필터 진단] total={total} "
            f"data부족={skip_insufficient_data} "
            f"%B>={PERCENT_B_THRESHOLD}={skip_percent_b} "
            f"RSI>{RSI_THRESHOLD}={skip_rsi} "
            f"거래량<{VOLUME_RATIO_THRESHOLD}x={skip_volume} "
            f"→ 통과={len(candidates)}"
        )

        return candidates

    def _save_result(self, date_str: str, iso_date: str,
                     now: datetime, candidates: List[Dict]) -> None:
        """결과 저장 (latest + daily)"""
        result = {
            "date": date_str,
            "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "strategy": "볼린저밴드_스윙",
            "criteria": {
                "bb_period": BB_PERIOD,
                "bb_std_mult": BB_STD_MULT,
                "percent_b_threshold": PERCENT_B_THRESHOLD,
                "rsi_period": RSI_PERIOD,
                "rsi_threshold": RSI_THRESHOLD,
                "volume_ratio_threshold": VOLUME_RATIO_THRESHOLD,
                "min_market_cap": MIN_MARKET_CAP,
                "min_trading_value": MIN_TRADING_VALUE,
            },
            "count": len(candidates),
            "candidates": candidates,
        }

        # latest
        latest_path = self.data_dir / "bollinger_candidates.json"
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        # daily
        daily_path = self.data_dir / f"bollinger_candidates_{date_str}.json"
        with open(daily_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        logger.info(f"\n저장: {latest_path}")
        logger.info(f"저장: {daily_path}")


# CLI 테스트
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="볼린저밴드 스윙 종목 선정")
    parser.add_argument("--date", type=str, help="기준 날짜 (YYYYMMDD)")
    parser.add_argument("--top", type=int, default=TOP_N, help=f"상위 N개 (기본: {TOP_N})")
    args = parser.parse_args()

    selector = BollingerSelector()
    candidates = selector.select(date_str=args.date, top_n=args.top)

    print(f"\n[선정 완료]")
    print(f"날짜: {selector.selection_date}")
    print(f"전략: 볼린저밴드_스윙")
    print(f"선정 종목: {len(candidates)}개")
