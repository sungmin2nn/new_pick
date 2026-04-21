"""
Phase 7.A.2 — 약점 분석 자동화 테스트
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lab.weakness_analyzer import WeaknessAnalyzer  # noqa: E402


def _make_cell(strategy_id="test", trades_per_day=None, metrics=None):
    trades_per_day = trades_per_day or []
    history = []
    for i, day_trades in enumerate(trades_per_day):
        date = f"2026040{i + 1}"
        trades = day_trades
        wins = sum(1 for t in trades if t["return_pct"] > 0)
        losses = sum(1 for t in trades if t["return_pct"] < 0)
        daily_ret = sum(t["return_pct"] for t in trades) / 5 if trades else 0
        history.append({
            "date": date,
            "candidates": len(trades),
            "trades": len(trades),
            "wins": wins,
            "losses": losses,
            "daily_return_pct": round(daily_ret, 2),
            "daily_return_amount": 0,
            "capital_after": 10_000_000,
            "selection_failed": False,
            "error": None,
            "trade_details": trades,
        })
    return {
        "strategy_id": strategy_id,
        "strategy_name": strategy_id,
        "period_label": "1w",
        "start_date": "20260401",
        "end_date": "20260410",
        "status": "completed",
        "metrics": metrics or {"total_return_pct": 0.0, "num_trades": 0},
        "history": history,
    }


def _trade(name, ret, code="000001", exit_type="profit", score=50.0):
    return {
        "code": code,
        "name": name,
        "entry_price": 10000,
        "exit_price": int(10000 * (1 + ret / 100)),
        "exit_type": "loss" if ret < 0 else exit_type,
        "return_pct": ret,
        "return_amount": 0,
        "qty": 100,
        "high": 10500,
        "low": 9500,
        "close": int(10000 * (1 + ret / 100)),
        "selection": {"rank": 1, "score": score},
    }


def test_stop_wall_detection():
    # 모든 손실이 -3.0% 근처 → 손절 벽
    cell = _make_cell(
        trades_per_day=[
            [_trade("A", -3.0), _trade("B", -3.0), _trade("C", -3.0)],
            [_trade("D", -3.0), _trade("E", -2.95), _trade("F", -3.05)],
        ]
    )
    r = WeaknessAnalyzer().analyze(cell)
    assert r.loss_pattern["stop_wall_detected"] is True
    assert r.loss_pattern["stop_wall_ratio"] >= 0.5
    assert any("손절 벽" in h for h in r.hypotheses)


def test_asymmetry_hypothesis():
    cell = _make_cell(
        trades_per_day=[
            [_trade("A", +1.0), _trade("B", -3.0), _trade("C", -3.0)],
            [_trade("D", -3.0), _trade("E", +1.0), _trade("F", -3.0)],
        ]
    )
    r = WeaknessAnalyzer().analyze(cell)
    assert r.loss_pattern["asymmetry"] >= 2.0
    assert any("비대칭" in h or "배" in h for h in r.hypotheses)


def test_consecutive_losses():
    cell = _make_cell(
        trades_per_day=[
            [_trade(f"N{i}", -2.0) for i in range(6)],
        ]
    )
    r = WeaknessAnalyzer().analyze(cell)
    assert r.loss_pattern["max_consecutive_losses"] >= 5
    assert any("연속 손실" in h for h in r.hypotheses)


def test_low_diversity():
    # 같은 종목만 반복
    cell = _make_cell(
        trades_per_day=[
            [_trade("삼성전자", -1.0, code="005930"),
             _trade("삼성전자", -1.0, code="005930")],
            [_trade("삼성전자", -1.0, code="005930")],
        ]
    )
    r = WeaknessAnalyzer().analyze(cell)
    assert r.name_bias["low_diversity"] is True
    assert any("다양성" in h for h in r.hypotheses)


def test_score_correlation_effective():
    # 높은 score → 높은 수익률 (정상 작동)
    cell = _make_cell(
        trades_per_day=[
            [
                _trade("A", +3.0, score=90),
                _trade("B", +2.0, score=80),
                _trade("C", -1.0, score=40),
                _trade("D", -2.0, score=30),
                _trade("E", +1.0, score=60),
                _trade("F", -1.5, score=35),
            ]
        ]
    )
    r = WeaknessAnalyzer().analyze(cell)
    assert r.score_correlation["available"] is True
    assert r.score_correlation["pearson_corr"] > 0.5
    assert r.score_correlation["scoring_effective"] is True


def test_score_correlation_broken():
    # score와 수익률 무관
    cell = _make_cell(
        trades_per_day=[
            [
                _trade("A", -3.0, score=90),
                _trade("B", -3.0, score=80),
                _trade("C", -3.0, score=70),
                _trade("D", +1.0, score=40),
            ]
        ]
    )
    r = WeaknessAnalyzer().analyze(cell)
    assert r.score_correlation["available"] is True
    assert r.score_correlation["scoring_effective"] is False
    assert any("예측하지 못" in h or "scoring" in h.lower() or "스코어" in h for h in r.hypotheses)


def test_market_context_underperform():
    target = _make_cell(
        strategy_id="bad",
        metrics={"total_return_pct": -10.0, "num_trades": 10},
        trades_per_day=[[_trade("A", -3.0)]],
    )
    peers = [
        _make_cell(
            strategy_id="good1",
            metrics={"total_return_pct": +5.0, "num_trades": 10},
            trades_per_day=[[_trade("A", +1.0)]],
        ),
        _make_cell(
            strategy_id="good2",
            metrics={"total_return_pct": +8.0, "num_trades": 10},
            trades_per_day=[[_trade("A", +1.0)]],
        ),
    ]
    r = WeaknessAnalyzer().analyze(target, peer_cells=[target] + peers)
    assert r.market_context["underperformed_peers"] is True
    assert r.market_context["rank_among_peers"] == "3/3"


def test_no_trades_graceful():
    cell = _make_cell(trades_per_day=[])
    r = WeaknessAnalyzer().analyze(cell)
    assert r.hypotheses  # 최소 1개 가설 (시그널 조건 문제)
    assert any("시그널" in h or "데이터" in h for h in r.hypotheses)


def test_serialization():
    import json
    cell = _make_cell(
        trades_per_day=[[_trade("A", +1.0), _trade("B", -1.0)]]
    )
    r = WeaknessAnalyzer().analyze(cell)
    js = json.dumps(r.to_dict(), ensure_ascii=False)
    back = json.loads(js)
    assert back["strategy_id"] == r.strategy_id


TESTS = [
    test_stop_wall_detection,
    test_asymmetry_hypothesis,
    test_consecutive_losses,
    test_low_diversity,
    test_score_correlation_effective,
    test_score_correlation_broken,
    test_market_context_underperform,
    test_no_trades_graceful,
    test_serialization,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
