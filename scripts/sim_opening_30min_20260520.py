#!/usr/bin/env python3
"""
opening_30min_volume_burst 전략 시뮬레이션 — 2026-05-20 (T) / 선정기준 2026-05-19 (T-1)

목적:
  - leakage 차단: 종목 선정은 2026-05-19 종가까지만 사용.
  - 시뮬레이션은 2026-05-20 분봉으로만 수행.

룰:
  - 진입: 09:05 1분봉 시가 (uptick rule 회피, domain 권고)
  - 청산 우선: ①+5% 익절 ②-3% 손절 ③14:50 강제마감
  - 슬리피지: 0.15% 단방향 (왕복 0.30%)
  - 거래세: 매도시 0.20%
  - 자본: 1000만원 / 5종목 = 종목당 200만원

산출:
  - data/sim_opening_30min_20260520.json
  - 콘솔 요약
"""

from __future__ import annotations

import json
import os
import sys
import io
from datetime import datetime
from pathlib import Path

# Windows 콘솔 UTF-8 강제 (cp949 회피)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 프로젝트 경로 셋업
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "strategy-lab"))

# .env 로드 (KIS / KRX 키)
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass


# ─────────────────────────────────────
# 파라미터
# ─────────────────────────────────────
DATE_T = "20260520"           # 시뮬 대상일
DATE_T_MINUS_1 = "20260519"   # 종목 선정 기준일 (T-1)
TOP_N = 5
CAPITAL_TOTAL = 10_000_000    # 1000만원
CAPITAL_PER_STOCK = CAPITAL_TOTAL // TOP_N  # 200만원

ENTRY_TIME = "09:05"          # 진입 시각 (HH:MM)
EXIT_DEADLINE = "14:50"       # 강제마감 시각
TAKE_PROFIT_PCT = 5.0
STOP_LOSS_PCT = -3.0
SLIPPAGE_PCT = 0.15           # 단방향
SELL_TAX_PCT = 0.20

OUT_JSON = ROOT / "data" / "sim_opening_30min_20260520.json"


# ─────────────────────────────────────
# Step 1: 종목 선정 (T-1 close 기준)
# ─────────────────────────────────────
def select_stocks_t_minus_1():
    """opening_30min_volume_burst 전략으로 5/19 close까지만 사용해 종목 선정.

    leakage 안전성:
      - Opening30MinVolumeBurstStrategy.select_stocks(date='20260519')는
        내부적으로 fetch_all_markets('20260519') + batch_get_history(start, end='20260518')
        만 호출. 5/20 데이터는 일절 fetch하지 않음.
    """
    from strategies.opening_30min_volume_burst import Opening30MinVolumeBurstStrategy

    strategy = Opening30MinVolumeBurstStrategy()
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
            "value_ratio": float(c.score_detail.get("volume_surge", 0)) > 0
                           and getattr(c, "value_ratio", None) or None,
            "score": float(c.score),
            "score_detail": c.score_detail,
            "rank": c.rank,
        })
    return selected


# ─────────────────────────────────────
# Step 2: 분봉 시뮬레이션 (T)
# ─────────────────────────────────────
def find_bar_at_or_after(bars, target_hhmm):
    """target_hhmm("09:05") 이상인 첫 분봉 반환. 없으면 None."""
    for b in bars:
        # bars time format "HH:MM:SS"
        if b["time"][:5] >= target_hhmm:
            return b
    return None


def find_last_bar_at_or_before(bars, target_hhmm):
    """target_hhmm 이하인 마지막 분봉."""
    candidate = None
    for b in bars:
        if b["time"][:5] <= target_hhmm:
            candidate = b
        else:
            break
    return candidate


def simulate_one_stock(code, name, bars):
    """단일 종목 분봉 시뮬.

    Returns:
        dict: trade 결과 or None (분봉 데이터 없음)
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

    # 진입: 09:05 분봉 시가 (없으면 첫 09:05 이후 분봉)
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

    # 슬리피지 (매수: 상방)
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

    # 진입 시점 이후 분봉만 평가
    entry_t = entry_bar["time"]
    exit_bar = None
    exit_reason = None
    exit_price_raw = None

    for b in bars:
        if b["time"] < entry_t:
            continue
        if b["time"][:5] > EXIT_DEADLINE:
            break

        high = b["high"]
        low = b["low"]

        # 우선순위: 익절 → 손절 → 시간컷
        # 동일 봉 내 익절·손절 동시 충족 시 보수적으로 손절 우선 가정 (한 봉 내 순서 불가지).
        # 단 사용자 사양은 "①익절 ②손절"이므로 사양을 따라 익절 우선.
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

    # 시간컷
    if exit_bar is None:
        last_bar = find_last_bar_at_or_before(bars, EXIT_DEADLINE)
        if last_bar is None or last_bar["time"] < entry_t:
            # 진입 후 14:50 이전 데이터 없음 → 마지막 분봉으로 청산
            last_bar = bars[-1]
        exit_bar = last_bar
        exit_reason = "time_cut"
        exit_price_raw = last_bar["close"]

    # 슬리피지 (매도: 하방) + 매도세 (0.20%)
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
        "note": None,
    }


def fetch_and_simulate(selected):
    """선정 종목들 5/20 분봉 fetch → 시뮬."""
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


# ─────────────────────────────────────
# Step 3: 요약 + 저장
# ─────────────────────────────────────
def build_summary(selected, trades):
    executed = [t for t in trades if t["exit_reason"] not in ("no_data", "no_entry_bar", "bad_entry_price", "insufficient_capital")]
    wins = sum(1 for t in executed if t["pnl_pct"] > 0)
    losses = sum(1 for t in executed if t["pnl_pct"] <= 0)

    breakdown = {"profit_target": 0, "stop_loss": 0, "time_cut": 0}
    for t in executed:
        if t["exit_reason"] in breakdown:
            breakdown[t["exit_reason"]] += 1

    total_pnl = sum(t["pnl_amount"] for t in executed)
    avg_pnl_pct = (sum(t["pnl_pct"] for t in executed) / len(executed)) if executed else 0.0

    return {
        "n_selected": len(selected),
        "n_executed": len(executed),
        "total_pnl_pct_avg": round(avg_pnl_pct, 3),
        "total_pnl_amount": int(total_pnl),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / len(executed) * 100, 2) if executed else 0.0,
        "exit_reason_breakdown": breakdown,
    }


def print_report(selected, trades, summary, fetch_success, fetch_fail, strategy_name="opening_30min_volume_burst"):
    print("\n" + "=" * 70)
    print(f"{strategy_name} 시뮬 - T={DATE_T}, T-1={DATE_T_MINUS_1}")
    print("=" * 70)

    print(f"\n[선정 종목 ({len(selected)})]")
    for s in selected:
        print(f"  #{s['rank']} {s['name']}({s['code']}) "
              f"change={s['change_pct']:+.2f}% / TV={s['trading_value']/1e8:.1f}억 "
              f"/ score={s['score']:.2f}")

    print(f"\n[시뮬 결과 ({len(trades)})]")
    for t in trades:
        if t["exit_reason"] in ("no_data", "no_entry_bar"):
            print(f"  #{t['rank']} {t['name']}({t['code']}): SKIP — {t['note']}")
            continue
        print(f"  #{t['rank']} {t['name']}({t['code']}): "
              f"{t['entry_time']} @ {t['entry_price']:,}원 → "
              f"{t['exit_time']} @ {t['exit_price']:,}원 "
              f"[{t['exit_reason']}] {t['pnl_pct']:+.2f}% ({t['pnl_amount']:+,}원)")

    print(f"\n[요약]")
    print(f"  분봉 fetch: success={fetch_success} / fail={fetch_fail}")
    print(f"  n_selected={summary['n_selected']} / n_executed={summary['n_executed']}")
    print(f"  avg pnl%={summary['total_pnl_pct_avg']:+.2f}% / total pnl={summary['total_pnl_amount']:+,}원")
    print(f"  wins={summary['wins']} / losses={summary['losses']} / win_rate={summary['win_rate']:.1f}%")
    print(f"  exit breakdown: TP={summary['exit_reason_breakdown']['profit_target']} / "
          f"SL={summary['exit_reason_breakdown']['stop_loss']} / "
          f"TIME={summary['exit_reason_breakdown']['time_cut']}")


def main():
    print(f"opening_30min_volume_burst 시뮬 시작 — T={DATE_T}, T-1={DATE_T_MINUS_1}")
    print(f"종목당 자본 {CAPITAL_PER_STOCK:,}원 / TP +{TAKE_PROFIT_PCT}% / SL {STOP_LOSS_PCT}% / "
          f"deadline {EXIT_DEADLINE} / slip {SLIPPAGE_PCT}% / tax {SELL_TAX_PCT}%")

    # Step 1
    selected = select_stocks_t_minus_1()
    if not selected:
        print("선정 종목 0개 — 시뮬 종료")
        return 1

    # Step 2
    trades, fs, ff = fetch_and_simulate(selected)

    # Step 3
    summary = build_summary(selected, trades)

    out = {
        "date_t": DATE_T,
        "date_tminus1": DATE_T_MINUS_1,
        "strategy": "opening_30min_volume_burst",
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

    print_report(selected, trades, summary, fs, ff)
    return 0


if __name__ == "__main__":
    sys.exit(main())
