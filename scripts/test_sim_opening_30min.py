"""Unit tests for sim_opening_30min_20260520.simulate_one_stock.

자체 로직 검증 (외부 fetch 없이 합성 분봉으로 시뮬레이션).
실행: python scripts/test_sim_opening_30min.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from sim_opening_30min_20260520 import (
    simulate_one_stock,
    TAKE_PROFIT_PCT, STOP_LOSS_PCT,
    SLIPPAGE_PCT, SELL_TAX_PCT,
)


def make_bar(t, o, h, l, c, v=1000):
    return {"time": t, "open": o, "high": h, "low": l, "close": c, "volume": v}


def test_no_data():
    r = simulate_one_stock("000000", "test", [])
    assert r["exit_reason"] == "no_data"
    assert r["pnl_amount"] == 0
    print("PASS: test_no_data")


def test_tp_hit():
    # 09:05 open=10000, 09:06 high reaches +5%
    bars = [
        make_bar("09:00:00", 9900, 9950, 9890, 9920),
        make_bar("09:05:00", 10000, 10050, 9990, 10030),
        make_bar("09:06:00", 10030, 10600, 10020, 10500),  # high 10600 = +6%
    ]
    r = simulate_one_stock("000000", "tp_stock", bars)
    assert r["exit_reason"] == "profit_target", f"Expected profit_target, got {r['exit_reason']}"
    assert r["entry_time"] == "09:05:00"
    # entry_raw=10000, tp_raw=10500
    assert r["entry_price_raw"] == 10000
    assert r["exit_price_raw"] == 10500
    # entry_eff = 10000 * 1.0015 = 10015, exit_eff = 10500 * 0.9985 * 0.998 ≈ 10464.27
    # pnl% ≈ (10464.27/10015 - 1) * 100 ≈ +4.49%
    assert 4.3 < r["pnl_pct"] < 4.6, f"Expected ~+4.49%, got {r['pnl_pct']}"
    print(f"PASS: test_tp_hit (pnl={r['pnl_pct']:+.2f}%)")


def test_sl_hit():
    bars = [
        make_bar("09:05:00", 10000, 10050, 9990, 10030),
        make_bar("09:06:00", 10030, 10040, 9650, 9700),  # low 9650 = -3.5%
    ]
    r = simulate_one_stock("000000", "sl_stock", bars)
    assert r["exit_reason"] == "stop_loss"
    assert r["exit_price_raw"] == 9700  # sl_price = 10000 * 0.97
    # pnl ≈ -3.48%
    assert -3.6 < r["pnl_pct"] < -3.4, f"Expected ~-3.48%, got {r['pnl_pct']}"
    print(f"PASS: test_sl_hit (pnl={r['pnl_pct']:+.2f}%)")


def test_time_cut():
    # 09:05 진입, 종일 횡보, 14:50 마감
    bars = [make_bar("09:05:00", 10000, 10100, 9900, 10000)]
    # 진입 이후 14:50까지 5분 간격으로 횡보 분봉 추가
    for h in range(9, 15):
        for m in range(0, 60, 5):
            t = f"{h:02d}:{m:02d}:00"
            if t < "09:05:00":
                continue
            if t > "14:50:00":
                break
            bars.append(make_bar(t, 10000, 10050, 9950, 10020))
    r = simulate_one_stock("000000", "time_stock", bars)
    assert r["exit_reason"] == "time_cut", f"Expected time_cut, got {r['exit_reason']}"
    assert r["exit_time"][:5] == "14:50"
    print(f"PASS: test_time_cut (pnl={r['pnl_pct']:+.2f}%)")


def test_tp_priority_over_sl_same_bar():
    # 한 봉에서 high와 low 둘 다 트리거 — 사양상 익절 우선
    bars = [
        make_bar("09:05:00", 10000, 10050, 9990, 10030),
        make_bar("09:06:00", 10030, 10600, 9600, 10000),  # high +6%, low -4%
    ]
    r = simulate_one_stock("000000", "both_stock", bars)
    assert r["exit_reason"] == "profit_target", f"Expected profit_target (priority), got {r['exit_reason']}"
    print("PASS: test_tp_priority_over_sl_same_bar")


def test_entry_after_905_if_missing():
    # 09:05 없고 09:07부터 시작
    bars = [
        make_bar("09:07:00", 10000, 10050, 9990, 10030),
        make_bar("09:08:00", 10030, 10040, 9650, 9700),
    ]
    r = simulate_one_stock("000000", "late_stock", bars)
    assert r["entry_time"] == "09:07:00"
    assert r["exit_reason"] == "stop_loss"
    print("PASS: test_entry_after_905_if_missing")


if __name__ == "__main__":
    test_no_data()
    test_tp_hit()
    test_sl_hit()
    test_time_cut()
    test_tp_priority_over_sl_same_bar()
    test_entry_after_905_if_missing()
    print("\nAll tests passed.")
