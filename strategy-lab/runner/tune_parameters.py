"""
Parameter Tuning CLI (Phase 7.A.3)
===================================
약점 분석 리포트 → v0.2 variant spec 자동 생성.

사용:
    python runner/tune_parameters.py
    python runner/tune_parameters.py --weakness data/weakness_reports/weakness_xxx.json
    python runner/tune_parameters.py --only eod_reversal_korean
    python runner/tune_parameters.py --max-variants 3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lab.parameter_tuner import (  # noqa: E402
    ParameterTuner,
    save_variants,
    suggest_from_weakness_file,
)


def _latest_weakness_file(weakness_dir: Path) -> Optional[Path]:
    files = sorted(weakness_dir.glob("weakness_*.json"), reverse=True)
    return files[0] if files else None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="부진 전략 v0.2 파라미터 튜닝")
    p.add_argument("--weakness", type=Path, default=None)
    p.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "data" / "variants",
    )
    p.add_argument("--only", default=None, help="쉼표구분 전략 ID 필터")
    p.add_argument("--max-variants", type=int, default=5)
    p.add_argument("--quiet", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    weakness_path = args.weakness or _latest_weakness_file(
        REPO_ROOT / "data" / "weakness_reports"
    )
    if weakness_path is None or not weakness_path.exists():
        print("[ERROR] 약점 리포트 파일 없음. 먼저 runner/analyze_weakness.py 실행", file=sys.stderr)
        return 2

    only_ids = None
    if args.only:
        only_ids = [s.strip() for s in args.only.split(",") if s.strip()]

    result = suggest_from_weakness_file(
        weakness_path,
        only_strategy_ids=only_ids,
        max_variants_per_strategy=args.max_variants,
    )

    if not result:
        print("[INFO] 생성된 variant 없음 (모든 전략이 건강하거나 대상 아님)")
        return 0

    total_variants = sum(len(vs) for vs in result.values())
    all_paths = []
    for sid, variants in result.items():
        paths = save_variants(variants, args.out_dir)
        all_paths.extend(paths)

    print(f"v0.2 variant 생성 완료: {len(result)}개 전략, 총 {total_variants}개 variant")
    print(f"  weakness: {weakness_path.name}")
    print(f"  저장 위치: {args.out_dir}")

    if not args.quiet:
        print()
        for sid, variants in result.items():
            print(f"═══ {sid} ═══")
            for v in variants:
                print(f"  ▸ {v.summary()}")
                for h in v.addresses_hypotheses:
                    print(f"    └─ {h}")
            print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
