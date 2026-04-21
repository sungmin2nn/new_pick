"""
Analyze Weakness CLI (Phase 7.A.2)
===================================
부진 전략에 대해 약점 구조 분석을 실행.

사용:
    python runner/analyze_weakness.py
    python runner/analyze_weakness.py --matrix data/results/matrix_xxx.json
    python runner/analyze_weakness.py --only eod_reversal_korean,news_catalyst_timing
    python runner/analyze_weakness.py --from-latest-underperformer-report

기본 동작:
    - matrix 파일: data/results/ 중 history 있는 최신 파일
    - underperformer ID: data/underperformers/ 중 최신 리포트의 부진 전략
    - 없으면 전체 전략 분석
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lab.weakness_analyzer import (  # noqa: E402
    analyze_matrix_file,
    save_weakness_reports,
)


def _latest_matrix_with_history(results_dir: Path) -> Optional[Path]:
    candidates = sorted(results_dir.glob("matrix_*.json"), reverse=True)
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for cell in data.get("cells", []):
                if cell.get("history"):
                    return path
        except (json.JSONDecodeError, OSError):
            continue
    return None


def _latest_underperformer_ids(under_dir: Path) -> List[str]:
    candidates = sorted(under_dir.glob("underperformers_*.json"), reverse=True)
    if not candidates:
        return []
    try:
        data = json.loads(candidates[0].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    ids: List[str] = []
    for m in data.get("per_strategy", []):
        if m.get("worst_severity") in ("mild", "moderate", "severe", "inactive"):
            ids.append(m["strategy_id"])
    return ids


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="부진 전략 약점 분석")
    p.add_argument("--matrix", type=Path, default=None)
    p.add_argument(
        "--under-dir",
        type=Path,
        default=REPO_ROOT / "data" / "underperformers",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "data" / "weakness_reports",
    )
    p.add_argument("--only", default=None, help="쉼표구분 전략 ID 목록만 분석")
    p.add_argument(
        "--all",
        action="store_true",
        help="underperformer 필터 무시하고 전체 분석",
    )
    p.add_argument("--quiet", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    matrix_path = args.matrix or _latest_matrix_with_history(
        REPO_ROOT / "data" / "results"
    )
    if matrix_path is None or not matrix_path.exists():
        print("[ERROR] 분석할 matrix 파일 없음 (history 포함 필요)", file=sys.stderr)
        return 2

    if args.only:
        ids = [s.strip() for s in args.only.split(",") if s.strip()]
    elif args.all:
        ids = None  # 전체
    else:
        ids = _latest_underperformer_ids(args.under_dir)
        if not ids:
            print("[INFO] 최신 underperformer 리포트 없음 → 전체 분석으로 전환")
            ids = None

    reports = analyze_matrix_file(matrix_path, underperformer_ids=ids)
    if not reports:
        print("[INFO] 분석 대상 없음 (matrix에서 찾지 못함)")
        return 0

    out_path = save_weakness_reports(reports, args.out_dir)
    print(f"약점 분석 완료: {out_path}")
    print(f"  matrix: {matrix_path.name}")
    print(f"  분석 대상 {len(reports)}개")

    if not args.quiet:
        print()
        for r in reports:
            print(f"═══ {r.strategy_id} ({r.period_label}) ═══")
            for i, h in enumerate(r.hypotheses, 1):
                print(f"  {i}. {h}")
            print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
