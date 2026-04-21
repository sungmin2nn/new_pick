"""
Phase 7.A.4 — v0.1 vs v0.2 비교 + 채택 테스트
(실제 KRX 네트워크 호출 없이 mock runner로 검증)
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lab.parameter_tuner import VariantSpec  # noqa: E402
from lab.variant_comparator import (  # noqa: E402
    AdoptionCriteria,
    VariantComparator,
    compute_adoption_score,
)
from lab.variant_runtime import (  # noqa: E402
    apply_strategy_overrides,
    describe_variant_effects,
    resolve_exit_rules,
)


# ============================================================
# Mock runner infrastructure
# ============================================================

def make_mock_runner(outcome_map):
    """
    outcome_map: dict {variant_key: metrics_dict}
        variant_key:
          - None → baseline
          - tuple of sorted (exit_rule_overrides.items()) for variants
    """
    def runner(
        strategy_id,
        start_date,
        end_date,
        strategy_param_overrides=None,
        exit_rule_overrides=None,
    ):
        # 키 생성
        if not (strategy_param_overrides or exit_rule_overrides):
            key = None
        else:
            key = (
                tuple(sorted((strategy_param_overrides or {}).items())),
                tuple(sorted((exit_rule_overrides or {}).items())),
            )
        return outcome_map.get(key, {
            "total_return_pct": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "win_rate": 0.0,
            "num_trades": 0,
            "profit_factor": 0.0,
        })
    return runner


def _make_variant(spec_exit=None, spec_strat=None, vid="test_v0.2_a"):
    return VariantSpec(
        variant_id=vid,
        parent_strategy_id="test",
        version="0.2.0",
        label="test variant",
        strategy_param_overrides=spec_strat or {},
        exit_rule_overrides=spec_exit or {},
        addresses_hypotheses=[],
        tuning_rationale="",
    )


# ============================================================
# Tests: scoring
# ============================================================

def test_score_positive_for_good_metrics():
    score = compute_adoption_score(
        {
            "total_return_pct": 20.0,
            "sharpe_ratio": 5.0,
            "max_drawdown_pct": -2.0,
            "win_rate": 0.70,
            "profit_factor": 3.0,
            "num_trades": 50,
        },
        AdoptionCriteria(),
    )
    assert score >= 80, f"good metrics → score >= 80, got {score}"


def test_score_low_for_bad_metrics():
    score = compute_adoption_score(
        {
            "total_return_pct": -10.0,
            "sharpe_ratio": -2.0,
            "max_drawdown_pct": -20.0,
            "win_rate": 0.20,
            "profit_factor": 0.5,
            "num_trades": 50,
        },
        AdoptionCriteria(),
    )
    assert score < 30, f"bad metrics → score < 30, got {score}"


def test_sharpe_clipped():
    # 과대평가 Sharpe가 만점을 넘지 않아야
    score1 = compute_adoption_score(
        {"total_return_pct": 0, "sharpe_ratio": 5, "max_drawdown_pct": 0,
         "win_rate": 0, "profit_factor": 0, "num_trades": 50},
        AdoptionCriteria(),
    )
    score2 = compute_adoption_score(
        {"total_return_pct": 0, "sharpe_ratio": 50, "max_drawdown_pct": 0,
         "win_rate": 0, "profit_factor": 0, "num_trades": 50},
        AdoptionCriteria(),
    )
    assert abs(score1 - score2) < 1.0  # 클리핑 덕분에 거의 같아야


# ============================================================
# Tests: comparator decision
# ============================================================

def test_variant_beats_baseline():
    baseline_metrics = {
        "total_return_pct": -19.0, "sharpe_ratio": -2.0,
        "max_drawdown_pct": -18.0, "win_rate": 0.21,
        "num_trades": 48, "profit_factor": 0.13,
    }
    improved_metrics = {
        "total_return_pct": 8.0, "sharpe_ratio": 2.0,
        "max_drawdown_pct": -5.0, "win_rate": 0.55,
        "num_trades": 45, "profit_factor": 2.1,
    }
    v = _make_variant(spec_exit={"loss_target": -7.0, "profit_target": 10.0})
    key = (
        tuple(),
        tuple(sorted({"loss_target": -7.0, "profit_target": 10.0}.items())),
    )
    runner = make_mock_runner({
        None: baseline_metrics,
        key: improved_metrics,
    })
    cmp_ = VariantComparator(runner_fn=runner)
    d = cmp_.compare("test", [v], "20260401", "20260410")
    assert d.baseline_beaten is True
    assert d.winner_variant_id == "test_v0.2_a"
    assert d.winner_score > d.baseline_score


def test_baseline_kept_when_variants_worse():
    good_baseline = {
        "total_return_pct": 15.0, "sharpe_ratio": 3.0,
        "max_drawdown_pct": -5.0, "win_rate": 0.65,
        "num_trades": 40, "profit_factor": 2.5,
    }
    bad_variant = {
        "total_return_pct": -5.0, "sharpe_ratio": 0.5,
        "max_drawdown_pct": -12.0, "win_rate": 0.30,
        "num_trades": 40, "profit_factor": 0.8,
    }
    v = _make_variant(spec_exit={"loss_target": -10.0})
    key = (tuple(), tuple(sorted({"loss_target": -10.0}.items())))
    runner = make_mock_runner({None: good_baseline, key: bad_variant})
    d = VariantComparator(runner_fn=runner).compare(
        "test", [v], "20260401", "20260410"
    )
    assert d.baseline_beaten is False
    assert d.winner_variant_id is None


def test_minimal_improvement_not_adopted():
    # variant가 아주 조금만 나으면 안정성 우선으로 baseline 유지
    base = {
        "total_return_pct": 10.0, "sharpe_ratio": 2.0,
        "max_drawdown_pct": -5.0, "win_rate": 0.55,
        "num_trades": 40, "profit_factor": 2.0,
    }
    marginal = {
        "total_return_pct": 10.1, "sharpe_ratio": 2.01,
        "max_drawdown_pct": -5.0, "win_rate": 0.56,
        "num_trades": 40, "profit_factor": 2.01,
    }
    v = _make_variant(spec_exit={"loss_target": -4.0})
    key = (tuple(), tuple(sorted({"loss_target": -4.0}.items())))
    runner = make_mock_runner({None: base, key: marginal})
    d = VariantComparator(
        runner_fn=runner,
        criteria=AdoptionCriteria(min_improvement_pct=2.0),
    ).compare("test", [v], "20260401", "20260410")
    assert d.baseline_beaten is False
    assert "안정성" in " ".join(d.notes)


def test_tie_breaking_by_complexity():
    # 동점이면 더 단순한 variant (overrides 적은)
    base = {
        "total_return_pct": 0.0, "sharpe_ratio": 0.0,
        "max_drawdown_pct": -5.0, "win_rate": 0.50,
        "num_trades": 30, "profit_factor": 1.0,
    }
    same = {
        "total_return_pct": 10.0, "sharpe_ratio": 2.0,
        "max_drawdown_pct": -5.0, "win_rate": 0.60,
        "num_trades": 30, "profit_factor": 2.0,
    }
    simple = _make_variant(spec_exit={"loss_target": -5.0}, vid="simple")
    complex_ = _make_variant(
        spec_exit={"loss_target": -5.0, "profit_target": 10.0},
        vid="complex",
    )
    key_simple = (tuple(), tuple(sorted({"loss_target": -5.0}.items())))
    key_complex = (
        tuple(),
        tuple(sorted({"loss_target": -5.0, "profit_target": 10.0}.items())),
    )
    runner = make_mock_runner({
        None: base,
        key_simple: same,
        key_complex: same,
    })
    d = VariantComparator(runner_fn=runner).compare(
        "test", [simple, complex_], "20260401", "20260410"
    )
    assert d.winner_variant_id == "simple"


def test_low_trade_count_disqualified():
    base = {
        "total_return_pct": 1.0, "sharpe_ratio": 0.3,
        "max_drawdown_pct": -3.0, "win_rate": 0.55,
        "num_trades": 20, "profit_factor": 1.2,
    }
    too_few = {
        "total_return_pct": 100.0, "sharpe_ratio": 10.0,  # 거짓 대박
        "max_drawdown_pct": 0.0, "win_rate": 1.0,
        "num_trades": 2, "profit_factor": 99.0,
    }
    v = _make_variant(spec_exit={"loss_target": -10.0})
    key = (tuple(), tuple(sorted({"loss_target": -10.0}.items())))
    runner = make_mock_runner({None: base, key: too_few})
    d = VariantComparator(runner_fn=runner).compare(
        "test", [v], "20260401", "20260410"
    )
    # 적은 거래 수 variant는 score=0 처리되어 baseline이 winner
    assert d.baseline_beaten is False


def test_negative_baseline_improvement_sign():
    """음수 baseline에서 variant가 덜 나쁘면 양의 개선폭이어야 함."""
    bad_base = {
        "total_return_pct": -20.0, "sharpe_ratio": -3.0,
        "max_drawdown_pct": -20.0, "win_rate": 0.21,
        "num_trades": 48, "profit_factor": 0.1,
    }
    slightly_less_bad = {
        "total_return_pct": -15.0, "sharpe_ratio": -2.0,
        "max_drawdown_pct": -15.0, "win_rate": 0.25,
        "num_trades": 48, "profit_factor": 0.3,
    }
    v = _make_variant(spec_exit={"loss_target": -10.0})
    key = (tuple(), tuple(sorted({"loss_target": -10.0}.items())))
    runner = make_mock_runner({None: bad_base, key: slightly_less_bad})
    d = VariantComparator(
        runner_fn=runner,
        criteria=AdoptionCriteria(min_improvement_pct=1.0),
    ).compare("test", [v], "20260401", "20260410")
    # variant가 덜 나쁘면 improvement_pct > 0
    assert d.improvement_pct > 0, (
        f"음수 baseline에서 덜 나쁜 variant는 양의 개선폭 필요, got {d.improvement_pct}"
    )


def test_runner_exception_handled():
    def bad_runner(**kwargs):
        raise RuntimeError("network down")
    v = _make_variant(spec_exit={"loss_target": -5.0})
    d = VariantComparator(runner_fn=bad_runner).compare(
        "test", [v], "20260401", "20260410"
    )
    # 모든 결과에 error, baseline 유지
    assert d.winner_variant_id is None
    assert all(r.error for r in d.results)


# ============================================================
# Tests: variant_runtime
# ============================================================

def test_apply_strategy_overrides_subclass():
    class Base:
        LOSS_THRESHOLD = -3.0
        WEIGHTS = {"a": 10, "b": 20}

    Patched = apply_strategy_overrides(
        Base,
        {"LOSS_THRESHOLD": -5.0, "WEIGHTS": {"a": 50}},
    )
    # 원본 불변
    assert Base.LOSS_THRESHOLD == -3.0
    assert Base.WEIGHTS == {"a": 10, "b": 20}
    # 서브클래스 override
    assert Patched.LOSS_THRESHOLD == -5.0
    # dict 병합 (a만 덮어쓰고 b 유지)
    assert Patched.WEIGHTS == {"a": 50, "b": 20}


def test_apply_overrides_empty_returns_original():
    class Base:
        X = 1
    result = apply_strategy_overrides(Base, {})
    assert result is Base


def test_resolve_exit_rules():
    v = _make_variant(spec_exit={"loss_target": -7.0, "profit_target": 10.0})
    profit, loss = resolve_exit_rules(v)
    assert profit == 10.0
    assert loss == -7.0


def test_describe_variant_hint_separation():
    v = _make_variant(
        spec_strat={"ENTRY_RELAXATION_HINT": True, "LOSS_THRESHOLD": -5.0},
    )
    effects = describe_variant_effects(v)
    assert "ENTRY_RELAXATION_HINT" in effects["runtime_hints"]
    assert "LOSS_THRESHOLD" in effects["real_strategy_overrides"]
    assert effects["is_noop"] is False


TESTS = [
    test_score_positive_for_good_metrics,
    test_score_low_for_bad_metrics,
    test_sharpe_clipped,
    test_variant_beats_baseline,
    test_baseline_kept_when_variants_worse,
    test_minimal_improvement_not_adopted,
    test_tie_breaking_by_complexity,
    test_low_trade_count_disqualified,
    test_negative_baseline_improvement_sign,
    test_runner_exception_handled,
    test_apply_strategy_overrides_subclass,
    test_apply_overrides_empty_returns_original,
    test_resolve_exit_rules,
    test_describe_variant_hint_separation,
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
