"""
Phase 7.B — 앙상블 전략 테스트
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lab.ensemble import (  # noqa: E402
    CorrelationAnalyzer,
    EnsembleBuilder,
    EnsembleMethod,
    RankingCriteria,
    StrategyDailySeries,
    StrategyRanker,
    extract_daily_series_from_cell,
)


def _series(sid, returns, dates=None, name=None,
            total_return_pct=None, sharpe=2.0, wr=0.6,
            num_trades=20, pf=2.0, mdd=-5.0):
    dates = dates or [f"2026040{i + 1}" for i in range(len(returns))]
    tr = total_return_pct if total_return_pct is not None else sum(returns)
    return StrategyDailySeries(
        strategy_id=sid,
        strategy_name=name or sid,
        dates=dates,
        daily_returns_pct=returns,
        total_return_pct=tr,
        sharpe_ratio=sharpe,
        max_drawdown_pct=mdd,
        win_rate=wr,
        num_trades=num_trades,
        profit_factor=pf,
    )


# ============================================================
# Ranker
# ============================================================

def test_ranker_filters_low_trades():
    r = StrategyRanker(RankingCriteria(min_trades=10))
    good = _series("good", [1, 2, 3], num_trades=20)
    too_few = _series("few", [1, 2, 3], num_trades=5)
    top = r.select_top([good, too_few], top_n=5)
    ids = [s.strategy_id for s, _ in top]
    assert "few" not in ids
    assert "good" in ids


def test_ranker_filters_negative_return():
    r = StrategyRanker()
    good = _series("good", [1, 2], total_return_pct=15)
    bad = _series("bad", [-5, -3], total_return_pct=-10)
    top = r.select_top([good, bad])
    ids = [s.strategy_id for s, _ in top]
    assert "bad" not in ids


def test_ranker_orders_by_score():
    r = StrategyRanker()
    low = _series("low", [], total_return_pct=5, sharpe=1, wr=0.5, pf=1.5)
    high = _series("high", [], total_return_pct=20, sharpe=5, wr=0.8, pf=3)
    top = r.select_top([low, high], top_n=2)
    assert top[0][0].strategy_id == "high"
    assert top[0][1] > top[1][1]


def test_ranker_top_n_cap():
    r = StrategyRanker()
    items = [
        _series(f"s{i}", [], total_return_pct=10 + i) for i in range(10)
    ]
    top = r.select_top(items, top_n=3)
    assert len(top) == 3


# ============================================================
# Correlation
# ============================================================

def test_correlation_identity():
    ca = CorrelationAnalyzer()
    s = _series("a", [1, -1, 2, -2, 3])
    m = ca.compute_matrix([s])
    assert m["a"]["a"] == 1.0


def test_correlation_positive_pair():
    ca = CorrelationAnalyzer()
    a = _series("a", [1, 2, 3, 4])
    b = _series("b", [2, 4, 6, 8])  # perfect positive
    m = ca.compute_matrix([a, b])
    assert m["a"]["b"] > 0.99


def test_correlation_negative_pair():
    ca = CorrelationAnalyzer()
    a = _series("a", [1, 2, 3, 4])
    b = _series("b", [4, 3, 2, 1])  # perfect negative
    m = ca.compute_matrix([a, b])
    assert m["a"]["b"] < -0.99


def test_correlation_different_date_sets():
    ca = CorrelationAnalyzer()
    a = StrategyDailySeries(
        strategy_id="a", strategy_name="a",
        dates=["20260401", "20260402", "20260403"],
        daily_returns_pct=[1, 2, 3],
    )
    b = StrategyDailySeries(
        strategy_id="b", strategy_name="b",
        dates=["20260402", "20260403", "20260404"],
        daily_returns_pct=[2, 3, 4],
    )
    m = ca.compute_matrix([a, b])
    # 공통 날짜 2개 (20260402, 20260403) → a=[2,3], b=[2,3] → corr=1
    assert m["a"]["b"] > 0.99


def test_average_correlation_low_when_diverse():
    ca = CorrelationAnalyzer()
    a = _series("a", [1, -1, 1, -1])
    b = _series("b", [-1, 1, -1, 1])  # inverse of a
    c = _series("c", [0.5, 0.5, 0.5, 0.5])  # constant (corr=0)
    matrix = ca.compute_matrix([a, b, c])
    avg = ca.average_correlation(matrix)
    # a-b는 -1, a-c 0, b-c 0 → 평균 약 -0.33
    assert avg < 0.0


# ============================================================
# Ensemble builder
# ============================================================

def test_equal_weight_simple():
    members = [
        _series("a", [1.0, 2.0, 3.0], total_return_pct=6),
        _series("b", [3.0, 2.0, 1.0], total_return_pct=6),
    ]
    eb = EnsembleBuilder()
    result = eb.build(members, EnsembleMethod.EQUAL)
    assert result.weights == {"a": 0.5, "b": 0.5}
    # 결합 시계열: (1+3)/2=2, (2+2)/2=2, (3+1)/2=2
    assert result.daily_returns_pct == [2.0, 2.0, 2.0]


def test_performance_weighted():
    members = [
        _series("a", [2.0, 2.0], total_return_pct=10),
        _series("b", [1.0, 1.0], total_return_pct=5),
    ]
    eb = EnsembleBuilder()
    r = eb.build(members, EnsembleMethod.PERFORMANCE_WEIGHTED)
    # 10:5 = 2:1 → weights 2/3, 1/3 (4자리 반올림 고려)
    assert abs(r.weights["a"] - 2 / 3) < 1e-3
    assert abs(r.weights["b"] - 1 / 3) < 1e-3


def test_performance_weighted_zero_fallback():
    # 모두 음수 수익 → equal fallback
    members = [
        _series("a", [-1, -2], total_return_pct=-3),
        _series("b", [-1, -2], total_return_pct=-3),
    ]
    eb = EnsembleBuilder()
    r = eb.build(members, EnsembleMethod.PERFORMANCE_WEIGHTED)
    assert r.weights == {"a": 0.5, "b": 0.5}


def test_volatility_scaled_inverse_vol():
    # 변동성 큰 멤버는 작은 weight
    low_vol = _series("low", [1.0, 1.0, 1.0, 1.0])  # sigma ≈ 0 → sigma ≈ very small
    high_vol = _series("high", [-5, 5, -5, 5])       # sigma 큼
    eb = EnsembleBuilder()
    r = eb.build([low_vol, high_vol], EnsembleMethod.VOLATILITY_SCALED)
    assert r.weights["low"] > r.weights["high"]


def test_ensemble_common_dates_only():
    a = StrategyDailySeries(
        strategy_id="a", strategy_name="a",
        dates=["20260401", "20260402", "20260403"],
        daily_returns_pct=[1, 2, 3],
    )
    b = StrategyDailySeries(
        strategy_id="b", strategy_name="b",
        dates=["20260402", "20260403", "20260404"],
        daily_returns_pct=[2, 3, 4],
    )
    eb = EnsembleBuilder()
    r = eb.build([a, b], EnsembleMethod.EQUAL)
    # 공통: 20260402, 20260403 → 2개
    assert len(r.dates) == 2
    assert r.dates == ["20260402", "20260403"]


def test_ensemble_metrics_reasonable():
    members = [
        _series("a", [1, 2, -1, 2, 3]),
        _series("b", [2, 1, 0, 1, 2]),
    ]
    eb = EnsembleBuilder()
    r = eb.build(members, EnsembleMethod.EQUAL)
    assert r.num_days == 5
    assert r.total_return_pct > 0
    assert r.max_drawdown_pct <= 0
    assert r.worst_day_pct <= r.best_day_pct


def test_ensemble_no_members_raises():
    eb = EnsembleBuilder()
    try:
        eb.build([], EnsembleMethod.EQUAL)
        assert False, "빈 멤버에서 ValueError 기대"
    except ValueError:
        pass


def test_ensemble_no_common_dates_raises():
    a = StrategyDailySeries(
        strategy_id="a", strategy_name="a",
        dates=["20260401"], daily_returns_pct=[1],
    )
    b = StrategyDailySeries(
        strategy_id="b", strategy_name="b",
        dates=["20260402"], daily_returns_pct=[2],
    )
    eb = EnsembleBuilder()
    try:
        eb.build([a, b], EnsembleMethod.EQUAL)
        assert False, "공통 날짜 없음에서 ValueError 기대"
    except ValueError:
        pass


# ============================================================
# Matrix cell extraction
# ============================================================

def test_extract_from_cell():
    cell = {
        "strategy_id": "test",
        "strategy_name": "테스트",
        "metrics": {
            "total_return_pct": 10.0,
            "sharpe_ratio": 2.0,
            "max_drawdown_pct": -3.0,
            "win_rate": 0.6,
            "num_trades": 20,
            "profit_factor": 2.5,
        },
        "history": [
            {"date": "20260401", "daily_return_pct": 1.0},
            {"date": "20260402", "daily_return_pct": 2.0},
        ],
    }
    s = extract_daily_series_from_cell(cell)
    assert s is not None
    assert s.strategy_id == "test"
    assert s.daily_returns_pct == [1.0, 2.0]
    assert s.total_return_pct == 10.0
    assert s.num_trades == 20


def test_extract_from_cell_no_history():
    cell = {"strategy_id": "x", "metrics": {}}
    assert extract_daily_series_from_cell(cell) is None


TESTS = [
    test_ranker_filters_low_trades,
    test_ranker_filters_negative_return,
    test_ranker_orders_by_score,
    test_ranker_top_n_cap,
    test_correlation_identity,
    test_correlation_positive_pair,
    test_correlation_negative_pair,
    test_correlation_different_date_sets,
    test_average_correlation_low_when_diverse,
    test_equal_weight_simple,
    test_performance_weighted,
    test_performance_weighted_zero_fallback,
    test_volatility_scaled_inverse_vol,
    test_ensemble_common_dates_only,
    test_ensemble_metrics_reasonable,
    test_ensemble_no_members_raises,
    test_ensemble_no_common_dates_raises,
    test_extract_from_cell,
    test_extract_from_cell_no_history,
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
