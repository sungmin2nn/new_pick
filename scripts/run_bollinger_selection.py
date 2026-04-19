#!/usr/bin/env python3
"""
볼린저밴드 스윙 종목 선정 실행 스크립트

- 워크플로우(bollinger-swing.yml)에서 호출
- KRX OpenAPI로 전종목 fetch (시총/거래대금/양봉 필터)
- pykrx로 필터 통과 종목 히스토리 fetch (BB/RSI/거래량 계산)
- 결과: data/bnf/bollinger_candidates.json + bollinger_candidates_{date}.json
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from paper_trading.bnf.bollinger_selector import BollingerSelector


def main():
    print("=" * 60)
    print("볼린저밴드 스윙 종목 선정")
    print("=" * 60)

    selector = BollingerSelector(data_dir="data/bnf")
    candidates = selector.select()

    print("\n" + "=" * 60)
    print(f"선정 완료: {len(candidates)}개")
    if candidates:
        for c in candidates[:10]:
            print(
                f"  {c['rank']:2d}. {c['name']} ({c['code']}) "
                f"%%B={c['percent_b']:.3f} RSI={c['rsi']:.1f} "
                f"가격={c['price']:,}"
            )
    else:
        print("  조건 충족 종목 없음")
    print("=" * 60)

    # 후보 종목 OHLCV 차트 데이터 저장
    save_bb_stock_charts(candidates)


def save_bb_stock_charts(candidates):
    """볼린저 후보 종목 OHLCV 저장 (BNF와 동일 디렉토리)"""
    import json
    import warnings
    from datetime import datetime, timedelta
    warnings.filterwarnings("ignore")

    try:
        from pykrx import stock as pykrx_stock
    except ImportError:
        print("[차트 데이터] pykrx 없음, 스킵")
        return

    chart_dir = PROJECT_ROOT / "data" / "bnf" / "stock_charts"
    chart_dir.mkdir(parents=True, exist_ok=True)

    codes = {c["code"]: c["name"] for c in candidates}

    # 볼린저 보유 종목도 추가
    pos_file = PROJECT_ROOT / "data" / "bnf" / "bollinger_positions.json"
    if pos_file.exists():
        try:
            with open(pos_file, "r", encoding="utf-8") as f:
                pos_data = json.load(f)
            for p in pos_data.get("positions", []):
                if p.get("state") != "CLOSED":
                    codes[p["code"]] = p["name"]
        except Exception:
            pass

    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=45)
    start_str = start_dt.strftime("%Y%m%d")
    end_str = end_dt.strftime("%Y%m%d")

    print(f"\n[차트 데이터] {len(codes)}종목 OHLCV 저장")
    for code, name in codes.items():
        # BNF 선정에서 이미 저장했으면 스킵
        if (chart_dir / f"{code}.json").exists():
            continue
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
            with open(chart_dir / f"{code}.json", "w", encoding="utf-8") as f:
                json.dump({"code": code, "name": name, "ohlcv": ohlcv}, f, ensure_ascii=False)
            print(f"  {name}({code}): {len(ohlcv)}일")
        except Exception as e:
            print(f"  {name}({code}): 실패 - {e}")


if __name__ == "__main__":
    main()
