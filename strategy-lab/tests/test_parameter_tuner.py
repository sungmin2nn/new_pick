"""
Phase 7.A.3 — 파라미터 튜닝 + v0.2 생성 테스트
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lab.parameter_tuner import (  # noqa: E402
    ParameterTuner,
    VariantSpec,
    save_variants,
    load_variant,
)


def _weakness(
    stop_wall=False,
    asymmetry=1.0,
    consec_losses=0,
    low_diversity=False,
    scoring_broken=False,
    loss_concentration=0.0,
    total_trades=20,
):
    return {
        "strategy_id": "test_strategy",
        "strategy_name": "테스트 전략",
        "period_label": "1w",
        "start_date": "20260401",
        "end_date": "20260410",
        "loss_pattern": {
            "total_trades": total_trades,
            "wins": 5,
            "losses": 15,
            "avg_win_pct": 1.5,
            "avg_loss_pct": -3.0,
            "asymmetry": asymmetry,
            "max_consecutive_losses": consec_losses,
            "stop_wall_detected": stop_wall,
            "stop_wall_level_pct": -3.0 if stop_wall else None,
            "stop_wall_ratio": 0.9 if stop_wall else 0.0,
        },
        "timing_pattern": {
            "loss_concentration": loss_concentration,
        },
        "name_bias": {
            "unique_names": 3 if low_diversity else 18,
            "total_trades": 20,
            "low_diversity": low_diversity,
        },
        "score_correlation": {
            "available": True,
            "pearson_corr": -0.1 if scoring_broken else 0.6,
            "scoring_effective": not scoring_broken,
        },
        "market_context": {"available": False},
        "hypotheses": [],
    }


def test_healthy_no_variants():
    tuner = ParameterTuner()
    variants = tuner.suggest_variants(_weakness())
    assert variants == []


def test_stop_wall_generates_3_variants():
    tuner = ParameterTuner(max_variants_per_strategy=10)
    variants = tuner.suggest_variants(_weakness(stop_wall=True))
    # 손절 벽 rule만 → 3개 (loss_target -5/-7/-10)
    loss_targets = sorted(
        v.exit_rule_overrides.get("loss_target") for v in variants
        if "loss_target" in v.exit_rule_overrides
        and "profit_target" not in v.exit_rule_overrides
    )
    assert loss_targets == [-10.0, -7.0, -5.0]


def test_asymmetry_generates_profit_variants():
    tuner = ParameterTuner(max_variants_per_strategy=10)
    variants = tuner.suggest_variants(_weakness(asymmetry=2.5))
    profit_targets = sorted(
        v.exit_rule_overrides.get("profit_target") for v in variants
        if "profit_target" in v.exit_rule_overrides
        and "loss_target" not in v.exit_rule_overrides
    )
    assert profit_targets == [7.0, 10.0]


def test_combined_rule_when_both_present():
    tuner = ParameterTuner(max_variants_per_strategy=10)
    variants = tuner.suggest_variants(
        _weakness(stop_wall=True, asymmetry=2.5)
    )
    # 복합 variant (loss_target=-7 AND profit_target=+10) 존재
    combined = [
        v for v in variants
        if v.exit_rule_overrides.get("loss_target") == -7.0
        and v.exit_rule_overrides.get("profit_target") == 10.0
    ]
    assert len(combined) == 1


def test_regime_filter_on_consecutive_losses():
    tuner = ParameterTuner()
    variants = tuner.suggest_variants(_weakness(consec_losses=8))
    regime_vars = [
        v for v in variants
        if v.strategy_param_overrides.get("REGIME_FILTER_ENABLED") is True
    ]
    assert len(regime_vars) == 1


def test_low_diversity_rule():
    tuner = ParameterTuner()
    variants = tuner.suggest_variants(_weakness(low_diversity=True))
    diversity_vars = [
        v for v in variants
        if "MAX_TRADES_PER_NAME_PER_PERIOD" in v.strategy_param_overrides
    ]
    assert len(diversity_vars) == 1


def test_max_variants_cap():
    tuner = ParameterTuner(max_variants_per_strategy=3)
    variants = tuner.suggest_variants(
        _weakness(
            stop_wall=True, asymmetry=2.5, consec_losses=8, low_diversity=True
        )
    )
    assert len(variants) <= 3


def test_priority_ordering():
    # 복합 rule이 가장 먼저 나와야 함
    tuner = ParameterTuner(max_variants_per_strategy=10)
    variants = tuner.suggest_variants(
        _weakness(stop_wall=True, asymmetry=2.5)
    )
    first = variants[0]
    assert first.exit_rule_overrides.get("loss_target") == -7.0
    assert first.exit_rule_overrides.get("profit_target") == 10.0


def test_entry_relaxation_for_zero_trades():
    tuner = ParameterTuner()
    variants = tuner.suggest_variants(_weakness(total_trades=0))
    relax = [
        v for v in variants
        if v.strategy_param_overrides.get("ENTRY_RELAXATION_HINT") is True
    ]
    assert len(relax) == 1


def test_variant_id_format():
    tuner = ParameterTuner()
    variants = tuner.suggest_variants(_weakness(stop_wall=True))
    for i, v in enumerate(variants):
        expected_suffix = chr(ord("a") + i)
        assert v.variant_id.endswith(f"v0.2_{expected_suffix}")
        assert v.parent_strategy_id == "test_strategy"


def test_save_and_load_round_trip(tmp_dir=None):
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    tuner = ParameterTuner()
    variants = tuner.suggest_variants(_weakness(stop_wall=True))
    paths = save_variants(variants, tmp)
    assert len(paths) == len(variants)
    loaded = [load_variant(p) for p in paths]
    assert loaded[0].variant_id == variants[0].variant_id
    assert loaded[0].exit_rule_overrides == variants[0].exit_rule_overrides
    # cleanup
    import shutil
    shutil.rmtree(tmp)


def test_deduplication():
    # 동일 override 조합은 중복 제거돼야 함 (combined rule이 stop_wall과 다른 값이므로 정상 3+2+1=6 이 아닌 5 이하)
    tuner = ParameterTuner(max_variants_per_strategy=20)
    variants = tuner.suggest_variants(
        _weakness(stop_wall=True, asymmetry=2.5)
    )
    # 모든 override 조합이 unique한지
    keys = set()
    for v in variants:
        k = (
            frozenset(v.strategy_param_overrides.items()),
            frozenset(v.exit_rule_overrides.items()),
        )
        assert k not in keys
        keys.add(k)


TESTS = [
    test_healthy_no_variants,
    test_stop_wall_generates_3_variants,
    test_asymmetry_generates_profit_variants,
    test_combined_rule_when_both_present,
    test_regime_filter_on_consecutive_losses,
    test_low_diversity_rule,
    test_max_variants_cap,
    test_priority_ordering,
    test_entry_relaxation_for_zero_trades,
    test_variant_id_format,
    test_save_and_load_round_trip,
    test_deduplication,
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
