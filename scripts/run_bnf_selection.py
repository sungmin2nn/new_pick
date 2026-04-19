#!/usr/bin/env python3
"""
BNF 종목 선정 실행 스크립트 (KRX OpenAPI + pykrx 하이브리드)

- 워크플로우(bnf-selection.yml)에서 호출
- KRX OpenAPI로 KOSPI+KOSDAQ 전종목 1회 fetch (시총/거래대금 필터)
- pykrx로 필터 통과 종목 히스토리 fetch (당일 데이터 포함, 낙폭 계산)
- 결과: data/bnf/candidates.json + candidates_{date}.json
"""

import json
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import pytz
from pykrx import stock as pykrx_stock

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

warnings.filterwarnings("ignore")

from paper_trading.utils.krx_api import KRXClient

DATA_DIR = PROJECT_ROOT / "data" / "bnf"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 선정 기준
DROP_5D_THRESHOLD = 15.0
DROP_10D_THRESHOLD = 20.0
DROP_HIGH_THRESHOLD = 25.0
MIN_MARKET_CAP = 1_000_000_000_000      # 1조원
MIN_TRADING_VALUE = 10_000_000_000      # 100억
LOOKBACK_HIGH = 20  # 고점 lookback
TOP_N = 20


def resolve_trading_date(date_str: str) -> str:
    """주어진 날짜가 비거래일이면 가장 최근 거래일로 거슬러 올라감 (pykrx 사용)"""
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


def main():
    kst = pytz.timezone("Asia/Seoul")
    today = datetime.now(kst)
    iso_date = today.strftime("%Y-%m-%d")
    today_str = today.strftime("%Y%m%d")

    print(f"BNF 낙폭과대 종목 선정 - {today_str}")
    print("=" * 60)

    krx = KRXClient()

    # 1) 거래일 resolve (주말/공휴일 → 최근 거래일, pykrx 사용)
    date_str = resolve_trading_date(today_str)
    if date_str != today_str:
        print(f"비거래일 → fetch_date={date_str}")

    # 2) KOSPI + KOSDAQ 전종목 fetch (KRX OpenAPI, 당일 없으면 전일 폴백)
    fetch_date = date_str
    print(f"\n[1/3] 시장 데이터 수집 ({fetch_date})")
    all_stocks = {}  # code -> {name, price, market_cap, trading_value, market}
    for market in ("KOSPI", "KOSDAQ"):
        df = krx.get_stock_ohlcv(fetch_date, market=market)
        if df.empty:
            # 당일 데이터 없으면 전일로 폴백 (KRX OpenAPI 반영 지연)
            prev_dt = datetime.strptime(fetch_date, "%Y%m%d") - timedelta(days=1)
            for _ in range(5):
                prev_str = prev_dt.strftime("%Y%m%d")
                df = krx.get_stock_ohlcv(prev_str, market=market)
                if not df.empty:
                    if market == "KOSPI":
                        print(f"  ※ KRX API 당일 미반영 → {prev_str} 데이터 사용")
                    break
                prev_dt -= timedelta(days=1)
        if df.empty:
            print(f"  {market}: 0 (skip)")
            continue
        for code in df.index:
            try:
                row = df.loc[code]
                close = int(row.get("종가", 0))
                if close == 0:
                    continue
                all_stocks[code] = {
                    "name": str(row.get("종목명", code)),
                    "price": close,
                    "market_cap": int(row.get("시가총액", 0)),
                    "trading_value": int(row.get("거래대금", 0)),
                    "market": market,
                }
            except Exception:
                continue
        print(f"  {market}: {len([s for s in all_stocks.values() if s['market'] == market])}개")
    print(f"  전체: {len(all_stocks)}개")

    # 3) 시총 + 거래대금 필터
    filtered = {
        code: s for code, s in all_stocks.items()
        if s["market_cap"] >= MIN_MARKET_CAP and s["trading_value"] >= MIN_TRADING_VALUE
    }
    print(f"\n[2/3] 필터 (시총≥{MIN_MARKET_CAP/1e12:.0f}조 · 거래대금≥{MIN_TRADING_VALUE/1e9:.0f}억)")
    print(f"  통과: {len(filtered)}개")

    if not filtered:
        save_result(date_str, iso_date, today, [])
        print("\n⚠️ 필터 통과 없음")
        return

    # 4) 필터 통과 종목 historical fetch (drop 계산)
    print(f"\n[3/3] 낙폭 계산 ({len(filtered)}종목)")
    end_dt = datetime.strptime(date_str, "%Y%m%d")
    start_dt = end_dt - timedelta(days=LOOKBACK_HIGH + 15)  # 여유

    candidates = []
    start_str = start_dt.strftime("%Y%m%d")
    end_str = end_dt.strftime("%Y%m%d")
    for code, s in filtered.items():
        try:
            df = pykrx_stock.get_market_ohlcv_by_date(start_str, end_str, code)
            if df.empty or len(df) < 11:
                continue

            closes = df["종가"].astype(float).values
            highs = df["고가"].astype(float).values

            current = closes[-1]
            if current == 0:
                continue

            # 5일 낙폭: 6번째 뒤(오늘 기준 5거래일 전) 종가 대비
            past_5 = closes[-6] if len(closes) >= 6 else closes[0]
            drop_5d = (past_5 - current) / past_5 * 100 if past_5 > 0 else 0

            # 10일 낙폭
            past_10 = closes[-11] if len(closes) >= 11 else closes[0]
            drop_10d = (past_10 - current) / past_10 * 100 if past_10 > 0 else 0

            # 20일 고점 대비
            recent_highs = highs[-LOOKBACK_HIGH:] if len(highs) >= LOOKBACK_HIGH else highs
            high_20d = float(max(recent_highs))
            drop_high = (high_20d - current) / high_20d * 100 if high_20d > 0 else 0

            reasons = []
            if drop_5d >= DROP_5D_THRESHOLD:
                reasons.append(f"5일 {drop_5d:.1f}%")
            if drop_10d >= DROP_10D_THRESHOLD:
                reasons.append(f"10일 {drop_10d:.1f}%")
            if drop_high >= DROP_HIGH_THRESHOLD:
                reasons.append(f"고점 {drop_high:.1f}%")
            if not reasons:
                continue

            max_drop = max(drop_5d, drop_10d, drop_high)
            candidates.append({
                "code": code,
                "name": s["name"],
                "price": int(current),
                "current_price": int(current),
                "market_cap": s["market_cap"],
                "trading_value": s["trading_value"],
                "drop_5d": round(drop_5d, 2),
                "drop_10d": round(drop_10d, 2),
                "drop_from_high": round(drop_high, 2),
                "max_drop": round(max_drop, 2),
                "high_20d": int(high_20d),
                "reasons": " | ".join(reasons),
                "selection_reason": " | ".join(reasons),
            })
        except Exception as e:
            continue

    candidates.sort(key=lambda x: x["max_drop"], reverse=True)
    candidates = candidates[:TOP_N]
    for i, c in enumerate(candidates, 1):
        c["rank"] = i

    print(f"\n선정 결과: {len(candidates)}개")
    if candidates:
        for c in candidates[:10]:
            print(f"  {c['rank']:2d}. {c['name']} ({c['code']}) max_drop={c['max_drop']}%")

    save_result(date_str, iso_date, today, candidates)

    # 후보 + 보유 종목의 OHLCV 차트 데이터 저장
    save_stock_charts(candidates, start_str, end_str)


def save_result(date_str: str, iso_date: str, today: datetime, candidates: list):
    """결과 저장 (latest + daily)"""
    result = {
        "date": iso_date,
        "generated_at": today.strftime("%Y-%m-%d %H:%M:%S"),
        "strategy": "BNF_낙폭과대",
        "criteria": {
            "drop_5d_threshold": DROP_5D_THRESHOLD,
            "drop_10d_threshold": DROP_10D_THRESHOLD,
            "drop_high_threshold": DROP_HIGH_THRESHOLD,
            "min_market_cap": MIN_MARKET_CAP,
            "min_trading_value": MIN_TRADING_VALUE,
        },
        "count": len(candidates),
        "candidates": candidates,
    }

    latest_path = DATA_DIR / "candidates.json"
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    daily_path = DATA_DIR / f"candidates_{date_str}.json"
    with open(daily_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n저장: {latest_path}")
    print(f"저장: {daily_path}")


def save_stock_charts(candidates, start_str, end_str):
    """후보 + 보유 종목의 OHLCV를 개별 JSON으로 저장"""
    chart_dir = DATA_DIR / "stock_charts"
    chart_dir.mkdir(parents=True, exist_ok=True)

    # 후보 종목 코드
    codes = {c["code"]: c["name"] for c in candidates}

    # 보유 종목도 추가
    pos_file = DATA_DIR / "positions.json"
    if pos_file.exists():
        try:
            with open(pos_file, "r", encoding="utf-8") as f:
                pos_data = json.load(f)
            for p in pos_data.get("positions", []):
                if p.get("state") != "CLOSED":
                    codes[p["code"]] = p["name"]
        except Exception:
            pass

    print(f"\n[차트 데이터] {len(codes)}종목 OHLCV 저장")
    for code, name in codes.items():
        try:
            df = pykrx_stock.get_market_ohlcv_by_date(start_str, end_str, code)
            if df.empty:
                continue
            ohlcv = []
            for idx, row in df.iterrows():
                ohlcv.append({
                    "date": idx.strftime("%Y-%m-%d"),
                    "open": int(row["시가"]),
                    "high": int(row["고가"]),
                    "low": int(row["저가"]),
                    "close": int(row["종가"]),
                    "volume": int(row["거래량"]),
                })
            chart_data = {"code": code, "name": name, "ohlcv": ohlcv}
            with open(chart_dir / f"{code}.json", "w", encoding="utf-8") as f:
                json.dump(chart_data, f, ensure_ascii=False)
            print(f"  {name}({code}): {len(ohlcv)}일")
        except Exception as e:
            print(f"  {name}({code}): 실패 - {e}")


if __name__ == "__main__":
    main()
