"""
Identify Underperformers CLI (Phase 7.A.1)
===========================================
최신 리더보드 데이터에서 부진 전략을 자동 식별해서 리포트로 저장한다.

사용:
    python runner/identify_underperformers.py
    python runner/identify_underperformers.py --leaderboard data/leaderboard_data.js
    python runner/identify_underperformers.py --period 1w
    python runner/identify_underperformers.py --return-threshold 5.0 --mdd-threshold -8.0

출력:
    data/underperformers/underperformers_{YYYYMMDD_HHMMSS}.json
    콘솔에 약점 스코어 내림차순 요약 출력
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# repo root를 sys.path에 추가 (lab/ 패키지 import 위해)
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lab.underperformer import (  # noqa: E402
    UnderperformerCriteria,
    UnderperformerDetector,
    detect_from_leaderboard_file,
    save_report,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="부진 전략 자동 식별")
    p.add_argument(
        "--leaderboard",
        type=Path,
        default=REPO_ROOT / "data" / "leaderboard_data.js",
        help="리더보드 데이터 파일 (기본: data/leaderboard_data.js)",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "data" / "underperformers",
        help="리포트 저장 디렉토리",
    )
    p.add_argument("--period", default=None, help="특정 기간만 필터 (예: 1w, 1m)")
    p.add_argument("--return-threshold", type=float, default=3.0, help="low_return_pct")
    p.add_argument("--mdd-threshold", type=float, default=-10.0, help="deep_drawdown_pct")
    p.add_argument("--wr-threshold", type=float, default=0.45, help="low_win_rate")
    p.add_argument("--pf-threshold", type=float, default=1.2, help="low_profit_factor")
    p.add_argument("--sharpe-threshold", type=float, default=0.5, help="low_sharpe")
    p.add_argument(
        "--quiet", action="store_true", help="콘솔 요약 출력을 최소화"
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()

    criteria = UnderperformerCriteria(
        low_return_pct=args.return_threshold,
        deep_drawdown_pct=args.mdd_threshold,
        low_win_rate=args.wr_threshold,
        low_profit_factor=args.pf_threshold,
        low_sharpe=args.sharpe_threshold,
    )

    if not args.leaderboard.exists():
        print(f"[ERROR] 리더보드 파일 없음: {args.leaderboard}", file=sys.stderr)
        return 2

    reports = detect_from_leaderboard_file(
        args.leaderboard, criteria=criteria, period=args.period
    )
    detector = UnderperformerDetector(criteria)
    multi = detector.aggregate_multi_period(reports)

    out_path = save_report(reports, multi, args.out_dir, criteria)

    # 콘솔 요약
    total = len(reports)
    flagged = sum(1 for r in reports if r.is_underperformer)
    severe = sum(1 for r in reports if r.severity == "severe")
    moderate = sum(1 for r in reports if r.severity == "moderate")
    mild = sum(1 for r in reports if r.severity == "mild")
    inactive = sum(1 for r in reports if r.severity == "inactive")
    multi_fail = [m for m in multi if m.multi_period_fail]

    print(f"부진 전략 식별 완료: {out_path}")
    print(
        f"  총 평가 {total}건, 부진 {flagged}건 "
        f"(severe {severe} / moderate {moderate} / mild {mild} / inactive {inactive})"
    )
    if multi_fail:
        ids = ", ".join(m.strategy_id for m in multi_fail)
        print(f"  멀티-기간 부진 (MULTI_PERIOD_FAIL): {ids}")

    if not args.quiet:
        print("\n[약점 스코어 내림차순]")
        sorted_reports = sorted(
            reports, key=lambda r: r.weakness_score, reverse=True
        )
        for r in sorted_reports:
            if r.is_underperformer:
                print("  " + r.summary())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
