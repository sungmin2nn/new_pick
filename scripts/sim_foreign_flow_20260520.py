#!/usr/bin/env python3
"""
foreign_flow_momentum 전략 시뮬레이션 — 2026-05-20 (T) / 선정 2026-05-19 (T-1).

opening_30min 시뮬과 동일 룰. 차이는 선정 전략만 다름.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "strategy-lab"))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

# opening 시뮬의 핵심 함수 재사용
sys.path.insert(0, str(ROOT / "scripts"))
from sim_opening_30min_20260520 import (
    DATE_T, DATE_T_MINUS_1, TOP_N,
    CAPITAL_TOTAL, CAPITAL_PER_STOCK,
    ENTRY_TIME, EXIT_DEADLINE,
    TAKE_PROFIT_PCT, STOP_LOSS_PCT,
    SLIPPAGE_PCT, SELL_TAX_PCT,
    simulate_one_stock, build_summary, print_report,
)

OUT_JSON = ROOT / "data" / "sim_foreign_flow_20260520.json"


def select_stocks_foreign_flow():
    from strategies.foreign_flow_momentum import ForeignFlowMomentumStrategy

    strategy = ForeignFlowMomentumStrategy()
    candidates = strategy.select_stocks(date=DATE_T_MINUS_1, top_n=TOP_N)

    selected = []
    for c in candidates:
        selected.append({
            "code": c.code,
            "name": c.name,
            "price_t_minus_1": int(c.price),
            "change_pct": round(float(c.change_pct), 2),
            "trading_value": int(c.trading_value),
            "market_cap": int(c.market_cap),
            "score": float(c.score),
            "score_detail": c.score_detail,
            "rank": c.rank,
        })
    return selected


def fetch_and_simulate(selected):
    from intraday_collector import IntradayCollector
    collector = IntradayCollector()

    trades = []
    fetch_success = 0
    fetch_fail = 0

    for s in selected:
        code = s["code"]
        name = s["name"]
        print(f"\n[fetch] {name}({code}) 5/20 분봉 ...")
        try:
            bars = collector.get_minute_data(code, DATE_T, freq="1")
        except Exception as e:
            print(f"  fetch 예외: {e}")
            bars = []

        if bars:
            fetch_success += 1
        else:
            fetch_fail += 1

        trade = simulate_one_stock(code, name, bars)
        trade["rank"] = s["rank"]
        trades.append(trade)

        if trade["exit_reason"] in ("no_data", "no_entry_bar"):
            print(f"  -> SKIP ({trade['exit_reason']})")
        else:
            print(f"  -> entry {trade['entry_time']} @ {trade['entry_price']}원 "
                  f"/ exit {trade['exit_time']} @ {trade['exit_price']}원 "
                  f"/ {trade['exit_reason']} / pnl {trade['pnl_pct']:+.2f}%")

    return trades, fetch_success, fetch_fail


def main():
    print(f"foreign_flow_momentum 시뮬 시작 - T={DATE_T}, T-1={DATE_T_MINUS_1}")

    selected = select_stocks_foreign_flow()
    if not selected:
        print("선정 종목 0개 - 시뮬 종료")
        return 1

    trades, fs, ff = fetch_and_simulate(selected)
    summary = build_summary(selected, trades)

    out = {
        "date_t": DATE_T,
        "date_tminus1": DATE_T_MINUS_1,
        "strategy": "foreign_flow_momentum",
        "params": {
            "capital_total": CAPITAL_TOTAL,
            "capital_per_stock": CAPITAL_PER_STOCK,
            "entry_time": ENTRY_TIME,
            "exit_deadline": EXIT_DEADLINE,
            "take_profit_pct": TAKE_PROFIT_PCT,
            "stop_loss_pct": STOP_LOSS_PCT,
            "slippage_pct": SLIPPAGE_PCT,
            "sell_tax_pct": SELL_TAX_PCT,
        },
        "fetch_stats": {"success": fs, "fail": ff},
        "selected": selected,
        "trades": trades,
        "summary": summary,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n결과 저장: {OUT_JSON}")

    print_report(selected, trades, summary, fs, ff, strategy_name="foreign_flow_momentum")
    return 0


if __name__ == "__main__":
    sys.exit(main())
