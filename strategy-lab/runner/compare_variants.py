"""
Variant Comparison CLI (Phase 7.A.4)
=====================================
data/variants/ 의 v0.2 스펙들을 원본(v0.1)과 동일 기간/규칙으로 백테스트 후 비교,
최고 성과 variant를 자동 채택하고 결정을 영속화한다.

사용:
    python runner/compare_variants.py --parent eod_reversal_korean \\
        --start 20260329 --end 20260410
    python runner/compare_variants.py --parent eod_reversal_korean --all-variants
    python runner/compare_variants.py --dry-run    # 실행 계획만 출력

주의:
    실제 백테스트는 KRX 데이터 fetch를 수반 (수 분 소요 가능).
    --dry-run으로 계획만 확인 가능.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lab import BaseStrategy, assert_ntb_available  # noqa: E402
from lab.parameter_tuner import VariantSpec, load_variant  # noqa: E402
from lab.variant_comparator import (  # noqa: E402
    AdoptionCriteria,
    VariantComparator,
    save_adoption,
)
from lab.variant_runtime import apply_strategy_overrides  # noqa: E402
from runner.backtest_wrapper import SingleStrategyBacktest  # noqa: E402
from runner.matrix_runner import DEFAULT_STRATEGY_MODULES  # noqa: E402
from runner.metrics import calculate_metrics  # noqa: E402


# ============================================================
# Strategy class loader
# ============================================================

def _find_strategy_class(strategy_id: str):
    """strategy_id로 모듈/클래스 탐색."""
    for module_path in DEFAULT_STRATEGY_MODULES:
        try:
            mod = importlib.import_module(module_path)
        except Exception:
            continue
        for name in dir(mod):
            obj = getattr(mod, name)
            if (
                isinstance(obj, type)
                and obj is not BaseStrategy
                and getattr(obj, "STRATEGY_ID", None) == strategy_id
                and obj.__module__ == module_path
            ):
                return obj
    raise ValueError(f"전략 클래스를 찾을 수 없음: {strategy_id}")


# ============================================================
# Real backtest runner (VariantComparator에 주입)
# ============================================================

def _metrics_to_dict(m) -> Dict[str, Any]:
    """MetricsResult → VariantComparator가 기대하는 dict."""
    return {
        "total_return_pct": getattr(m, "total_return_pct", 0),
        "sharpe_ratio": getattr(m, "sharpe_ratio", 0),
        "max_drawdown_pct": getattr(m, "max_drawdown_pct", 0),
        "win_rate": getattr(m, "win_rate", 0),
        "num_trades": getattr(m, "num_trades", 0),
        "profit_factor": getattr(m, "profit_factor", 0),
    }


def make_real_runner(suppress_print: bool = True):
    """실제 backtest_wrapper 기반 runner_fn."""

    def runner(
        strategy_id: str,
        start_date: str,
        end_date: str,
        strategy_param_overrides: Optional[Dict[str, Any]] = None,
        exit_rule_overrides: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        assert_ntb_available()
        base_cls = _find_strategy_class(strategy_id)
        patched_cls = apply_strategy_overrides(
            base_cls, strategy_param_overrides or {}
        )
        instance = patched_cls()

        exit_rules = exit_rule_overrides or {}
        bt = SingleStrategyBacktest(
            strategy=instance,
            profit_target=exit_rules.get("profit_target"),
            loss_target=exit_rules.get("loss_target"),
            suppress_strategy_print=suppress_print,
        )
        result = bt.run(start_date=start_date, end_date=end_date)
        metrics = calculate_metrics(result)
        return _metrics_to_dict(metrics)

    return runner


# ============================================================
# Variant loading
# ============================================================

def load_variants_for_parent(
    variants_dir: Path, parent_id: str
) -> List[VariantSpec]:
    out = []
    for path in sorted(variants_dir.glob(f"{parent_id}_v*.json")):
        try:
            out.append(load_variant(path))
        except Exception as e:
            print(f"[WARN] variant 로드 실패 {path.name}: {e}")
    return out


# ============================================================
# CLI
# ============================================================

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="v0.1 vs v0.2 비교 + 채택")
    p.add_argument("--parent", required=True, help="부모 전략 ID")
    p.add_argument("--start", required=True, help="YYYYMMDD")
    p.add_argument("--end", required=True, help="YYYYMMDD")
    p.add_argument(
        "--variants-dir",
        type=Path,
        default=REPO_ROOT / "data" / "variants",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "data" / "adoptions",
    )
    p.add_argument(
        "--min-improvement-pct",
        type=float,
        default=2.0,
        help="이 미만 개선은 안정성 우선 baseline 유지",
    )
    p.add_argument(
        "--min-trades",
        type=int,
        default=5,
        help="이 미만 거래 수 variant는 무효 처리",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="실행 계획만 출력 (백테스트 실행 안 함)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    variants = load_variants_for_parent(args.variants_dir, args.parent)

    if not variants:
        print(f"[ERROR] {args.parent}의 variant 없음 ({args.variants_dir})", file=sys.stderr)
        return 2

    print(f"Variant 비교: {args.parent} × {len(variants)} variants")
    print(f"  기간: {args.start} ~ {args.end}")
    print(f"  variants:")
    for v in variants:
        print(f"    ▸ {v.summary()}")
    print()

    if args.dry_run:
        total_runs = len(variants) + 1  # baseline + variants
        print(f"[DRY-RUN] 총 {total_runs}회 백테스트 실행 예정")
        print(f"[DRY-RUN] 실제 실행하려면 --dry-run 제거")
        return 0

    criteria = AdoptionCriteria(
        min_improvement_pct=args.min_improvement_pct,
        min_trades=args.min_trades,
    )
    runner_fn = make_real_runner()
    comparator = VariantComparator(runner_fn=runner_fn, criteria=criteria)

    print(f"백테스트 실행 중... (baseline + {len(variants)}개 variants)")
    decision = comparator.compare(
        parent_strategy_id=args.parent,
        variants=variants,
        start_date=args.start,
        end_date=args.end,
    )

    out_path = save_adoption(decision, args.out_dir)
    print(f"\n채택 결정: {out_path}")
    print()
    print(decision.summary())
    print()

    # 결과 표
    print("전체 결과:")
    sorted_results = sorted(
        decision.results, key=lambda r: -r.adoption_score
    )
    for r in sorted_results:
        icon = "★" if r.variant_id == decision.winner_variant_id else " "
        if decision.winner_variant_id is None and r.is_baseline:
            icon = "★"
        m = r.metrics
        err = f" [ERROR: {r.error}]" if r.error else ""
        print(
            f"  {icon} {r.label:<45} score={r.adoption_score:5.1f}  "
            f"ret={m.get('total_return_pct', 0):+6.2f}%  "
            f"sharpe={m.get('sharpe_ratio', 0):+5.2f}  "
            f"trades={m.get('num_trades', 0):3d}{err}"
        )

    print()
    for note in decision.notes:
        print(f"  ▸ {note}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
