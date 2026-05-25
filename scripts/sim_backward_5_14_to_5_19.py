#!/usr/bin/env python3
"""
Backward 시뮬레이션 — 4일 × 2전략 × 2버전 = 16개 시뮬.

목적:
  - 5/20 단일일 결과(opening_30min -1.89%/WR20, foreign_flow -3.48%/WR0)가
    신호인지 노이즈인지 판정.
  - simulator-engineer 지적: 진입봉(09:05) 동일봉 SL은 look-ahead 의심.
    실거래에선 09:05 fill 직후 같은 봉 wick low로 즉시 매도 불가능.
  - V1 (look-ahead 포함) vs V2 (look-ahead 제거)로 보수 편향 정량화.

대상:
  T ∈ {20260514, 20260515, 20260518, 20260519}
  전략 ∈ {opening_30min_volume_burst, foreign_flow_momentum}
  버전 ∈ {V1 lookahead, V2 no-lookahead}

leakage 가드:
  - 종목 선정은 T-1 종가까지만. select_stocks(date=T-1).
  - 분봉 시뮬은 T일.
  - 5/13(T) 제외 — KIS 정합 어긋남 알려진 이슈.

산출:
  data/sim_backward_5_14_to_5_19.json
"""

from __future__ import annotations

import json
import os
import sys
import io
from datetime import datetime, timedelta
from pathlib import Path

# Windows 콘솔 UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "strategy-lab"))
sys.path.insert(0, str(ROOT / "scripts"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass


# ─────────────────────────────────────
# 파라미터 (5/20 시뮬과 동일)
# ─────────────────────────────────────
# (T, T-1) 쌍 — T-1 은 한국 거래일 기준
DATE_PAIRS = [
    ("20260514", "20260513"),
    ("20260515", "20260514"),
    ("20260518", "20260515"),  # 5/16·17 주말
    ("20260519", "20260518"),
]
TOP_N = 5
CAPITAL_TOTAL = 10_000_000
CAPITAL_PER_STOCK = CAPITAL_TOTAL // TOP_N  # 200만원

ENTRY_TIME = "09:05"
EXIT_DEADLINE = "14:50"
TAKE_PROFIT_PCT = 5.0
STOP_LOSS_PCT = -3.0
SLIPPAGE_PCT = 0.15
SELL_TAX_PCT = 0.20

OUT_JSON = ROOT / "data" / "sim_backward_5_14_to_5_19.json"


# ─────────────────────────────────────
# 시뮬레이션 코어 — V1 / V2 분기
# ─────────────────────────────────────
def find_bar_at_or_after(bars, target_hhmm):
    for b in bars:
        if b["time"][:5] >= target_hhmm:
            return b
    return None


def find_last_bar_at_or_before(bars, target_hhmm):
    candidate = None
    for b in bars:
        if b["time"][:5] <= target_hhmm:
            candidate = b
        else:
            break
    return candidate


def simulate_one_stock(code, name, bars, version="v1_lookahead"):
    """단일 종목 분봉 시뮬.

    Args:
        version:
          "v1_lookahead": 진입봉(09:05) 안에서 wick low ≤ SL이면 즉시 손절.
            5/20 기존 결과 재현용 (look-ahead 포함).
          "v2_no_lookahead": 진입봉은 fill만. SL/TP 평가는 t+1 (09:06) 부터.
            실거래에 가까운 보수 편향 제거 버전.
    """
    if not bars:
        return {
            "code": code, "name": name,
            "entry_time": None, "entry_price": None,
            "exit_time": None, "exit_price": None,
            "exit_reason": "no_data",
            "pnl_pct": 0.0, "pnl_amount": 0,
            "shares": 0,
            "note": "분봉 데이터 fetch 실패",
        }

    entry_bar = find_bar_at_or_after(bars, ENTRY_TIME)
    if entry_bar is None:
        return {
            "code": code, "name": name,
            "entry_time": None, "entry_price": None,
            "exit_time": None, "exit_price": None,
            "exit_reason": "no_entry_bar",
            "pnl_pct": 0.0, "pnl_amount": 0,
            "shares": 0,
            "note": "09:05 이후 분봉 없음",
        }

    raw_entry_price = entry_bar["open"]
    if raw_entry_price <= 0:
        return {
            "code": code, "name": name,
            "entry_time": entry_bar["time"], "entry_price": None,
            "exit_time": None, "exit_price": None,
            "exit_reason": "bad_entry_price",
            "pnl_pct": 0.0, "pnl_amount": 0,
            "shares": 0,
            "note": "진입가 0",
        }

    entry_price_eff = raw_entry_price * (1 + SLIPPAGE_PCT / 100.0)
    shares = int(CAPITAL_PER_STOCK // entry_price_eff)
    if shares <= 0:
        return {
            "code": code, "name": name,
            "entry_time": entry_bar["time"], "entry_price": int(entry_price_eff),
            "exit_time": None, "exit_price": None,
            "exit_reason": "insufficient_capital",
            "pnl_pct": 0.0, "pnl_amount": 0,
            "shares": 0,
            "note": f"진입가 {entry_price_eff:.0f}원에 200만원으로 0주",
        }

    tp_price = raw_entry_price * (1 + TAKE_PROFIT_PCT / 100.0)
    sl_price = raw_entry_price * (1 + STOP_LOSS_PCT / 100.0)

    entry_t = entry_bar["time"]
    exit_bar = None
    exit_reason = None
    exit_price_raw = None

    for b in bars:
        # V1: 진입봉 포함 (b["time"] >= entry_t)
        # V2: 진입봉 제외 (b["time"] > entry_t) — t+1 부터 평가
        if version == "v1_lookahead":
            if b["time"] < entry_t:
                continue
        else:  # v2_no_lookahead
            if b["time"] <= entry_t:
                continue

        if b["time"][:5] > EXIT_DEADLINE:
            break

        high = b["high"]
        low = b["low"]

        # 익절 우선 (사양: ①익절 ②손절)
        if high >= tp_price:
            exit_bar = b
            exit_reason = "profit_target"
            exit_price_raw = tp_price
            break
        if low <= sl_price:
            exit_bar = b
            exit_reason = "stop_loss"
            exit_price_raw = sl_price
            break

    if exit_bar is None:
        last_bar = find_last_bar_at_or_before(bars, EXIT_DEADLINE)
        if last_bar is None or last_bar["time"] < entry_t:
            last_bar = bars[-1]
        # V2: 진입봉이 마지막이면 진입봉 close로 시간컷
        exit_bar = last_bar
        exit_reason = "time_cut"
        exit_price_raw = last_bar["close"]

    exit_price_eff = exit_price_raw * (1 - SLIPPAGE_PCT / 100.0) * (1 - SELL_TAX_PCT / 100.0)

    gross_entry = shares * entry_price_eff
    gross_exit = shares * exit_price_eff
    pnl_amount = int(gross_exit - gross_entry)
    pnl_pct = (gross_exit / gross_entry - 1) * 100.0 if gross_entry > 0 else 0.0

    return {
        "code": code, "name": name,
        "entry_time": entry_bar["time"],
        "entry_price": int(round(entry_price_eff)),
        "entry_price_raw": int(raw_entry_price),
        "tp_price": int(round(tp_price)),
        "sl_price": int(round(sl_price)),
        "exit_time": exit_bar["time"],
        "exit_price": int(round(exit_price_eff)),
        "exit_price_raw": int(round(exit_price_raw)),
        "exit_reason": exit_reason,
        "pnl_pct": round(pnl_pct, 3),
        "pnl_amount": pnl_amount,
        "shares": shares,
        "version": version,
        "note": None,
    }


# ─────────────────────────────────────
# 종목 선정 (전략별)
# ─────────────────────────────────────
def select_opening_30min(date_t_minus_1):
    from strategies.opening_30min_volume_burst import Opening30MinVolumeBurstStrategy
    strategy = Opening30MinVolumeBurstStrategy()
    candidates = strategy.select_stocks(date=date_t_minus_1, top_n=TOP_N)
    return _serialize_candidates(candidates)


def select_foreign_flow(date_t_minus_1):
    from strategies.foreign_flow_momentum import ForeignFlowMomentumStrategy
    strategy = ForeignFlowMomentumStrategy()
    candidates = strategy.select_stocks(date=date_t_minus_1, top_n=TOP_N)
    return _serialize_candidates(candidates)


def _serialize_candidates(candidates):
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


# ─────────────────────────────────────
# 분봉 fetch + 두 버전 동시 시뮬
# ─────────────────────────────────────
def fetch_bars_for_date(selected, date_t, collector):
    """선정 종목 × T일 분봉 fetch. {code: bars} 반환."""
    bars_map = {}
    fs, ff = 0, 0
    for s in selected:
        code = s["code"]
        name = s["name"]
        print(f"  [fetch] {name}({code}) {date_t} ...")
        try:
            bars = collector.get_minute_data(code, date_t, freq="1")
        except Exception as e:
            print(f"    fetch 예외: {e}")
            bars = []
        if bars:
            fs += 1
        else:
            ff += 1
        bars_map[code] = bars
    return bars_map, fs, ff


def simulate_both_versions(selected, bars_map):
    """선정 × 분봉 → V1, V2 두 버전 trades 산출."""
    trades_v1 = []
    trades_v2 = []
    for s in selected:
        code, name = s["code"], s["name"]
        bars = bars_map.get(code, [])
        t1 = simulate_one_stock(code, name, bars, version="v1_lookahead")
        t1["rank"] = s["rank"]
        trades_v1.append(t1)
        t2 = simulate_one_stock(code, name, bars, version="v2_no_lookahead")
        t2["rank"] = s["rank"]
        trades_v2.append(t2)
    return trades_v1, trades_v2


# ─────────────────────────────────────
# 집계
# ─────────────────────────────────────
def summarize_version(trades):
    executed = [t for t in trades if t["exit_reason"] not in
                ("no_data", "no_entry_bar", "bad_entry_price", "insufficient_capital")]
    n = len(executed)
    if n == 0:
        return {
            "n": 0, "trades": [], "wr": 0.0, "avg_pnl": 0.0,
            "tp_count": 0, "sl_count": 0, "time_count": 0,
            "pnl_distribution": [],
        }
    wins = sum(1 for t in executed if t["pnl_pct"] > 0)
    tp = sum(1 for t in executed if t["exit_reason"] == "profit_target")
    sl = sum(1 for t in executed if t["exit_reason"] == "stop_loss")
    tc = sum(1 for t in executed if t["exit_reason"] == "time_cut")
    avg = sum(t["pnl_pct"] for t in executed) / n
    return {
        "n": n,
        "trades": executed,
        "wr": round(wins / n * 100, 2),
        "avg_pnl": round(avg, 3),
        "tp_count": tp,
        "sl_count": sl,
        "time_count": tc,
        "pnl_distribution": [t["pnl_pct"] for t in executed],
    }


def histogram_1pct(pnl_list, lo=-10, hi=10):
    """-10..+10% 1%pt bucket 카운트.

    bucket k는 구간 [k, k+1)% 를 의미. 즉 -3 bucket은 -3.0% ≤ p < -2.0%.
    floor 사용.
    """
    import math
    buckets = {}
    for i in range(lo, hi + 1):
        buckets[i] = 0
    overflow_lo = 0
    overflow_hi = 0
    for p in pnl_list:
        b = math.floor(p)
        if b < lo:
            overflow_lo += 1
        elif b > hi:
            overflow_hi += 1
        else:
            buckets[b] = buckets.get(b, 0) + 1
    return {"buckets": buckets, "overflow_lo": overflow_lo, "overflow_hi": overflow_hi}


# ─────────────────────────────────────
# 메인
# ─────────────────────────────────────
def main():
    print("=" * 70)
    print("Backward 시뮬 — 4일 × 2전략 × 2버전 = 16 시뮬")
    print("=" * 70)

    from intraday_collector import IntradayCollector
    collector = IntradayCollector()

    # 결과 누적 — 전략·버전별
    accum = {
        "opening_30min": {
            "v1_lookahead": {"trades": []},
            "v2_no_lookahead": {"trades": []},
        },
        "foreign_flow": {
            "v1_lookahead": {"trades": []},
            "v2_no_lookahead": {"trades": []},
        },
    }
    by_date = {}  # 일자별 detail
    fetch_stats = {"success": 0, "fail": 0}

    for date_t, date_t_minus_1 in DATE_PAIRS:
        print(f"\n>>> T={date_t} / T-1={date_t_minus_1}")
        by_date[date_t] = {"date_tminus1": date_t_minus_1, "strategies": {}}

        for strat_name, select_fn in [
            ("opening_30min", select_opening_30min),
            ("foreign_flow", select_foreign_flow),
        ]:
            print(f"\n--- {strat_name} (T-1={date_t_minus_1}) 선정")
            try:
                selected = select_fn(date_t_minus_1)
            except Exception as e:
                print(f"  선정 예외: {e}")
                selected = []

            if not selected:
                print(f"  {strat_name} 선정 0개 → 스킵")
                by_date[date_t]["strategies"][strat_name] = {
                    "selected": [], "v1_lookahead": [], "v2_no_lookahead": [],
                    "fetch_success": 0, "fetch_fail": 0,
                }
                continue

            print(f"  선정 {len(selected)}개: " +
                  ", ".join(f"{s['name']}({s['code']})" for s in selected))

            print(f"\n--- {strat_name} ({date_t}) 분봉 fetch")
            bars_map, fs, ff = fetch_bars_for_date(selected, date_t, collector)
            fetch_stats["success"] += fs
            fetch_stats["fail"] += ff

            trades_v1, trades_v2 = simulate_both_versions(selected, bars_map)
            accum[strat_name]["v1_lookahead"]["trades"].extend(trades_v1)
            accum[strat_name]["v2_no_lookahead"]["trades"].extend(trades_v2)

            by_date[date_t]["strategies"][strat_name] = {
                "selected": selected,
                "v1_lookahead": trades_v1,
                "v2_no_lookahead": trades_v2,
                "fetch_success": fs,
                "fetch_fail": ff,
            }

            # 일자별 미니 요약
            v1s = summarize_version(trades_v1)
            v2s = summarize_version(trades_v2)
            print(f"  [V1] n={v1s['n']} wr={v1s['wr']}% avg={v1s['avg_pnl']:+.2f}% "
                  f"TP={v1s['tp_count']}/SL={v1s['sl_count']}/T={v1s['time_count']}")
            print(f"  [V2] n={v2s['n']} wr={v2s['wr']}% avg={v2s['avg_pnl']:+.2f}% "
                  f"TP={v2s['tp_count']}/SL={v2s['sl_count']}/T={v2s['time_count']}")

    # 최종 집계 (4일 통합)
    results = {}
    for strat_name in ("opening_30min", "foreign_flow"):
        results[strat_name] = {}
        for vn in ("v1_lookahead", "v2_no_lookahead"):
            agg = summarize_version(accum[strat_name][vn]["trades"])
            agg["histogram"] = histogram_1pct(agg["pnl_distribution"])
            results[strat_name][vn] = agg

    out = {
        "executed_at": datetime.now().isoformat(timespec="seconds"),
        "dates_t": [d for d, _ in DATE_PAIRS],
        "params": {
            "top_n_per_day": TOP_N,
            "capital_per_stock": CAPITAL_PER_STOCK,
            "entry_time": ENTRY_TIME,
            "exit_deadline": EXIT_DEADLINE,
            "take_profit_pct": TAKE_PROFIT_PCT,
            "stop_loss_pct": STOP_LOSS_PCT,
            "slippage_pct": SLIPPAGE_PCT,
            "sell_tax_pct": SELL_TAX_PCT,
        },
        "fetch_stats": fetch_stats,
        "results": results,
        "by_date": by_date,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n\n결과 저장: {OUT_JSON}")
    print_final_report(results, fetch_stats)
    return 0


def print_final_report(results, fetch_stats):
    print("\n" + "=" * 70)
    print("최종 집계 (4일 통합)")
    print("=" * 70)
    print(f"\nfetch: success={fetch_stats['success']} / fail={fetch_stats['fail']}\n")

    for strat_name in ("opening_30min", "foreign_flow"):
        print(f"\n[{strat_name}]")
        for vn in ("v1_lookahead", "v2_no_lookahead"):
            r = results[strat_name][vn]
            label = "V1 (look-ahead 포함)" if vn == "v1_lookahead" else "V2 (look-ahead 제거)"
            print(f"  {label}: n={r['n']} / WR={r['wr']}% / avg={r['avg_pnl']:+.3f}% "
                  f"/ TP={r['tp_count']} / SL={r['sl_count']} / TIME={r['time_count']}")
            # 히스토그램 (1%pt buckets, -5..+5 위주)
            h = r["histogram"]["buckets"]
            line = "    histogram (-10..+10% 1%pt): "
            line += " ".join(f"[{k:+d}]{v}" for k, v in sorted(h.items()) if v > 0)
            print(line)


if __name__ == "__main__":
    sys.exit(main())
