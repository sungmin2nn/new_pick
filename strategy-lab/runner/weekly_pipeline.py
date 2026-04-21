"""
Weekly Pipeline
================
Strategy Lab의 전체 파이프라인 1회 실행:

1. 전체 전략 × 선택 기간 매트릭스 백테스트
2. leaderboard_data.js 갱신
3. 승급 평가 실행 (모든 전략 × 기간)
4. 승급 결과 JSON 저장 (data/promotions/)
5. PROMOTED 전략에 대해 통합 가이드 생성
6. 요약 로그 출력

사용:
    # 수동 실행
    python3 -m runner.weekly_pipeline --periods 1w

    # schedule 스킬 / CronCreate로 매주 월요일 트리거
    (스킬 등록 별도 — docs/schedule_setup.md 참조)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from lab.promotion import (
    PromotionEvaluator,
    PromotionCriteria,
    PromotionStatus,
    evaluate_leaderboard_file,
)
from lab.integration_guide import IntegrationGuideGenerator
from runner.backtest_wrapper import StandardPeriods
from runner.matrix_runner import MatrixRunner
from runner.build_leaderboard_data import main as build_lb_main

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROMOTIONS_DIR = PROJECT_ROOT / "data" / "promotions"
LEADERBOARD_JS = PROJECT_ROOT / "data" / "leaderboard_data.js"


def load_metadata_map() -> Dict:
    """전략 메타데이터 전체 로드."""
    meta_map = {}
    meta_dir = PROJECT_ROOT / "data" / "sources" / "metadata"
    if not meta_dir.exists():
        return meta_map
    for f in meta_dir.glob("*.metadata.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            meta_map[data["id"]] = data
        except Exception:
            continue
    return meta_map


def save_promotions(results: list) -> Path:
    """승급 평가 결과를 JSON 스냅샷으로 저장."""
    PROMOTIONS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = PROMOTIONS_DIR / f"promotions_{ts}.json"

    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total_evaluated": len(results),
        "status_counts": {},
        "evaluations": [r.to_dict() for r in results],
    }
    for r in results:
        data["status_counts"][r.status] = data["status_counts"].get(r.status, 0) + 1

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_pipeline(
    periods: List[str],
    end_date: str = None,
    workers: int = 4,
    skip_backtest: bool = False,
) -> Dict:
    """
    파이프라인 전체 실행.

    Args:
        periods: ['1w', '1m', ...]
        end_date: YYYYMMDD (None이면 오늘)
        workers: 매트릭스 병렬 워커
        skip_backtest: True면 백테스트 skip, 기존 결과만 사용 (디버깅용)
    """
    start_time = time.time()
    print(f"\n{'=' * 64}")
    print(f"Strategy Lab Weekly Pipeline — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"기간: {periods} / 병렬 워커: {workers}")
    print(f"{'=' * 64}\n")

    summary = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "periods": periods,
        "steps": {},
    }

    # Step 1: 매트릭스 백테스트
    if not skip_backtest:
        print("[1/5] 매트릭스 백테스트 실행...")
        runner = MatrixRunner()
        runner.add_all_strategies()
        for p in periods:
            if p == "1w":
                runner.add_period("1w", *StandardPeriods.one_week(end_date))
            elif p == "1m":
                runner.add_period("1m", *StandardPeriods.one_month(end_date))
            elif p == "3m":
                runner.add_period("3m", *StandardPeriods.three_months(end_date))
            elif p == "1y":
                runner.add_period("1y", *StandardPeriods.one_year(end_date))

        cells = runner.run(parallel_strategies=workers, verbose=True)
        result_path = runner.save_results()
        summary["steps"]["backtest"] = {
            "cells": len(cells),
            "completed": sum(1 for c in cells if c.status == "completed"),
            "failed": sum(1 for c in cells if c.status == "failed"),
            "result_file": str(result_path.name),
        }
    else:
        print("[1/5] 백테스트 skip (기존 결과 사용)")
        summary["steps"]["backtest"] = {"skipped": True}

    # Step 2: 리더보드 데이터 재빌드
    print("\n[2/5] 리더보드 데이터 재빌드 (merge)...")
    import sys as _sys
    _sys.argv = ["build", "--merge"]
    try:
        build_lb_main()
    except SystemExit:
        pass
    summary["steps"]["leaderboard_build"] = "ok"

    # Step 3: 승급 평가
    print("\n[3/5] 승급 평가...")
    all_results = []
    for period in periods:
        results = evaluate_leaderboard_file(LEADERBOARD_JS, period=period)
        print(f"  기간 {period}: {len(results)}개 평가")
        all_results.extend(results)

    status_counts = {}
    for r in all_results:
        status_counts[r.status] = status_counts.get(r.status, 0) + 1
    print(f"  분포: {status_counts}")
    summary["steps"]["promotion"] = status_counts

    # Step 4: 승급 결과 저장
    print("\n[4/5] 승급 스냅샷 저장...")
    promo_path = save_promotions(all_results)
    print(f"  {promo_path.relative_to(PROJECT_ROOT)}")
    summary["steps"]["promotion_snapshot"] = str(promo_path.name)

    # Step 5: 통합 가이드 생성 (PROMOTED만)
    print("\n[5/5] 통합 가이드 생성...")
    meta_map = load_metadata_map()
    gen = IntegrationGuideGenerator()
    promoted_results = [r for r in all_results if r.status == PromotionStatus.PROMOTED.value]
    guides = gen.generate_batch(promoted_results, meta_map)
    print(f"  승급 전략: {len(promoted_results)}개 → 가이드 {len(guides)}개 생성")
    for p in guides:
        print(f"    - {p.name}")
    summary["steps"]["integration_guides"] = len(guides)

    # 완료
    elapsed = time.time() - start_time
    summary["elapsed_seconds"] = round(elapsed, 1)
    summary["ended_at"] = datetime.now().isoformat(timespec="seconds")

    # 최종 리더보드 TOP 요약
    print(f"\n{'=' * 64}")
    print(f"📊 Top 5 (전체 기간)")
    print(f"{'=' * 64}")
    top5 = sorted(all_results, key=lambda x: -x.score)[:5]
    for i, r in enumerate(top5, 1):
        emoji = {"promoted": "🏆", "watchlist": "⚠️", "rejected": "❌", "pending": "⏳"}.get(r.status, "❓")
        print(f"  {i}. {emoji} {r.strategy_id:<30} {r.period_label:>3}  "
              f"return={r.total_return_pct:+7.2f}%  "
              f"score={r.score:.1f}")

    print(f"\n{'=' * 64}")
    print(f"✓ 파이프라인 완료 ({elapsed:.1f}s)")
    print(f"  승급: {status_counts.get('promoted', 0)} / "
          f"관찰: {status_counts.get('watchlist', 0)} / "
          f"탈락: {status_counts.get('rejected', 0)} / "
          f"대기: {status_counts.get('pending', 0)}")
    print(f"{'=' * 64}\n")

    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--periods", default="1w",
        help="콤마 구분 기간 (1w,1m,3m,1y / default: 1w)",
    )
    parser.add_argument("--end-date", default=None, help="기준 종료일")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--skip-backtest", action="store_true",
                       help="백테스트 skip, 기존 결과만 사용 (디버깅)")
    args = parser.parse_args()

    periods = [p.strip() for p in args.periods.split(",") if p.strip()]
    summary = run_pipeline(
        periods=periods,
        end_date=args.end_date,
        workers=args.workers,
        skip_backtest=args.skip_backtest,
    )

    # 요약 저장
    log_path = PROJECT_ROOT / "data" / "pipeline_runs.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(summary, ensure_ascii=False, default=str) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
