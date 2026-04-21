"""
Friday Pipeline (Phase 7.A + 7.B 통합 자동 실행)
==================================================
매주 금요일 정기 실행: 개선 루프 + 앙상블을 순차 수행.

파이프라인 (월요일 weekly_pipeline.py가 먼저 백테스트+리더보드 갱신 후
금요일에 이 파이프라인이 개선/조합 관점에서 보강):

  1) identify_underperformers — 부진 전략 식별
  2) analyze_weakness        — 약점 구조 분석
  3) tune_parameters          — v0.2 VariantSpec 생성
  4) build_ensembles          — 상위 선정 + 3방식 앙상블

주의:
  * compare_variants(실제 백테스트 비교)는 기본 제외 — 시간 오래 걸림.
    --with-compare 플래그로 선택적 실행.
  * 각 단계는 독립적이며 실패해도 다음 단계로 진행.
  * 로그는 data/pipeline_runs.jsonl에 누적.

사용:
    python runner/friday_pipeline.py
    python runner/friday_pipeline.py --with-compare --parent eod_reversal_korean
    python runner/friday_pipeline.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_LOG = REPO_ROOT / "data" / "pipeline_runs.jsonl"


def _log_run(entry: Dict[str, Any]) -> None:
    PIPELINE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(PIPELINE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _run_step(
    name: str,
    command: List[str],
    dry_run: bool,
) -> Dict[str, Any]:
    print(f"\n═══ [{name}] ═══")
    print(f"  $ {' '.join(command)}")
    if dry_run:
        print("  (dry-run: 실행 생략)")
        return {"name": name, "status": "skipped", "duration_sec": 0}

    t0 = time.time()
    try:
        proc = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=1800,  # 30분
        )
        dur = round(time.time() - t0, 1)
        if proc.returncode == 0:
            print(f"  ✓ 완료 ({dur}s)")
            if proc.stdout:
                # 요약 — 마지막 10줄
                tail = "\n".join(proc.stdout.splitlines()[-10:])
                print(tail)
            return {
                "name": name,
                "status": "success",
                "duration_sec": dur,
                "stdout_tail": proc.stdout.splitlines()[-20:],
            }
        else:
            print(f"  ✗ 실패 exit={proc.returncode} ({dur}s)")
            if proc.stderr:
                print(proc.stderr[-500:])
            return {
                "name": name,
                "status": "failed",
                "duration_sec": dur,
                "returncode": proc.returncode,
                "stderr_tail": proc.stderr[-500:] if proc.stderr else "",
            }
    except subprocess.TimeoutExpired:
        return {"name": name, "status": "timeout", "duration_sec": 1800}
    except Exception as e:
        return {"name": name, "status": "error", "error": str(e)}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Friday 개선+앙상블 파이프라인")
    p.add_argument("--dry-run", action="store_true", help="실행 계획만 출력")
    p.add_argument(
        "--with-compare",
        action="store_true",
        help="v0.1 vs v0.2 실제 백테스트 비교까지 수행 (시간 오래 걸림)",
    )
    p.add_argument(
        "--parent",
        default=None,
        help="--with-compare 사용 시 비교할 부모 전략 ID",
    )
    p.add_argument("--top", type=int, default=5, help="앙상블 상위 N")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    start = datetime.now()
    print(f"Friday Pipeline 시작 — {start.isoformat(timespec='seconds')}")

    python = sys.executable
    steps_results: List[Dict[str, Any]] = []

    # 1) 부진 식별
    steps_results.append(
        _run_step(
            "1. Identify Underperformers",
            [python, "runner/identify_underperformers.py", "--quiet"],
            args.dry_run,
        )
    )

    # 2) 약점 분석
    steps_results.append(
        _run_step(
            "2. Analyze Weakness",
            [python, "runner/analyze_weakness.py", "--quiet"],
            args.dry_run,
        )
    )

    # 3) v0.2 생성
    steps_results.append(
        _run_step(
            "3. Tune Parameters (v0.2)",
            [python, "runner/tune_parameters.py", "--quiet"],
            args.dry_run,
        )
    )

    # 4) (선택) v0.1 vs v0.2 비교
    if args.with_compare:
        if not args.parent:
            print("[WARN] --with-compare 사용 시 --parent 필수. 건너뜀.")
        else:
            steps_results.append(
                _run_step(
                    "4. Compare Variants",
                    [
                        python,
                        "runner/compare_variants.py",
                        "--parent",
                        args.parent,
                        "--start",
                        "20260329",
                        "--end",
                        "20260410",
                    ],
                    args.dry_run,
                )
            )

    # 5) 앙상블
    steps_results.append(
        _run_step(
            "5. Build Ensembles",
            [python, "runner/build_ensembles.py", "--top", str(args.top), "--quiet"],
            args.dry_run,
        )
    )

    end = datetime.now()
    total_dur = round((end - start).total_seconds(), 1)

    entry = {
        "started_at": start.isoformat(timespec="seconds"),
        "ended_at": end.isoformat(timespec="seconds"),
        "total_duration_sec": total_dur,
        "dry_run": args.dry_run,
        "steps": steps_results,
        "pipeline": "friday_improvement_ensemble",
    }
    if not args.dry_run:
        _log_run(entry)

    print()
    print(f"═══ Friday Pipeline 완료 ({total_dur}s) ═══")
    for s in steps_results:
        icon = {
            "success": "✓",
            "failed": "✗",
            "skipped": "·",
            "timeout": "⏱",
            "error": "!",
        }.get(s.get("status"), "?")
        print(f"  {icon} {s['name']:<35} {s.get('status')} ({s.get('duration_sec', 0)}s)")

    # 실패 있으면 non-zero
    failed = [s for s in steps_results if s.get("status") not in ("success", "skipped")]
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
