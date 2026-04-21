"""
Realistic Leaderboard Builder
==============================
3-Tier 시뮬 결과를 단일 leaderboard_data_realistic.js로 통합.

포함되는 수치 (전략당 4개):
- nominal_return_pct    : 기존 일봉 시뮬 (baseline)
- tier1_return_pct      : 분봉 실측 (Ground Truth, 6일)
- tier2_return_pct      : 확률적 일봉 (장기)
- calibrated_return_pct : Tier 2 × calibration factor
- statistics            : bootstrap p-value + walk-forward + alpha

사용:
    python3 -m runner.build_realistic_leaderboard --period 1w
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import sys
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from lab import BaseStrategy, assert_ntb_available
from lab.realistic_sim.calibrator import Calibrator, CalibrationFactor
from lab.realistic_sim.statistics import (
    bootstrap_significance,
    walk_forward_validation,
    compute_benchmark_alpha,
    get_kodex_200_returns,
)
from runner.backtest_wrapper import get_trading_days
from runner.intraday_matrix import run_intraday_matrix, save_results as save_intraday
from runner.matrix_runner import DEFAULT_STRATEGY_MODULES
from runner.probabilistic_backtest import ProbabilisticBacktest

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "data" / "results"
OUTPUT_JS = PROJECT_ROOT / "data" / "leaderboard_realistic.js"


def load_nominal_matrix() -> Dict[str, dict]:
    """기존 일봉 매트릭스 (best effort) 가장 최근."""
    files = sorted(RESULTS_DIR.glob("matrix_*.json"), reverse=True)
    if not files:
        return {}
    try:
        data = json.loads(files[0].read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {
        c["strategy_id"]: c
        for c in data.get("cells", [])
        if c.get("status") == "completed"
    }


def run_probabilistic_matrix(
    strategy_modules: List[str],
    start_date: str,
    end_date: str,
    verbose: bool = True,
) -> Dict[str, dict]:
    """확률적 일봉 매트릭스 실행."""
    assert_ntb_available()
    trading_days = get_trading_days(start_date, end_date)
    results = {}

    for i, module_path in enumerate(strategy_modules, 1):
        try:
            mod = importlib.import_module(module_path)
            strategy_cls = None
            for name in dir(mod):
                obj = getattr(mod, name)
                if (
                    isinstance(obj, type)
                    and obj is not BaseStrategy
                    and hasattr(obj, "STRATEGY_ID")
                    and obj.__module__ == module_path
                ):
                    strategy_cls = obj
                    break
            if not strategy_cls:
                continue

            strategy = strategy_cls()
            bt = ProbabilisticBacktest(strategy)
            result = bt.run(start_date, end_date, trading_days=trading_days)

            results[result.strategy_id] = {
                "strategy_id": result.strategy_id,
                "strategy_name": result.strategy_name,
                "status": "completed",
                "metrics": {
                    "total_return_pct": result.gross_return_pct,
                    "net_return_pct": result.net_return_pct,
                    "win_rate": (
                        result.total_wins / max(result.total_trades, 1)
                        if result.total_trades > 0 else 0
                    ),
                    "num_trades": result.total_trades,
                    "avg_confidence": result.avg_confidence,
                },
                "scenario_counts": result.scenario_counts,
                "duration_seconds": result.duration_seconds,
            }

            if verbose:
                print(
                    f"[{i}/{len(strategy_modules)}] ✓ {result.strategy_id} "
                    f"{result.gross_return_pct:+.2f}% "
                    f"confidence={result.avg_confidence:.2f}"
                )
        except Exception as e:
            logger.error(f"{module_path}: {e}")
            if verbose:
                print(f"[{i}/{len(strategy_modules)}] ✗ {module_path}: {e}")

    return results


def build_realistic_leaderboard(
    start_date: str,
    end_date: str,
    strategy_modules: List[str],
    intraday_path: Optional[Path] = None,
    verbose: bool = True,
) -> dict:
    """
    3-Tier 결과를 단일 dict로 통합.

    Args:
        intraday_path: 분봉 매트릭스 결과 JSON (없으면 실행)
    """
    # 1. 기존 일봉 (nominal)
    if verbose:
        print("\n[1/4] 기존 일봉 매트릭스 로드...")
    nominal = load_nominal_matrix()
    if verbose:
        print(f"  {len(nominal)}개 전략 로드")

    # 2. Tier 1: 분봉
    if verbose:
        print("\n[2/4] Tier 1 분봉 매트릭스...")
    if intraday_path and intraday_path.exists():
        intraday_data = json.loads(intraday_path.read_text(encoding="utf-8"))
        if verbose:
            print(f"  파일에서 로드: {intraday_path.name}")
    else:
        # 실행
        intraday_data = run_intraday_matrix(
            strategy_modules=strategy_modules,
            start_date=start_date,
            end_date=end_date,
            verbose=verbose,
        )
        save_intraday(intraday_data)
    intraday_cells = {
        c["strategy_id"]: c
        for c in intraday_data.get("cells", [])
        if c.get("status") == "completed"
    }

    # 3. Tier 2: 확률적 일봉
    if verbose:
        print("\n[3/4] Tier 2 확률적 일봉 매트릭스...")
    probabilistic_cells = run_probabilistic_matrix(
        strategy_modules=strategy_modules,
        start_date=start_date,
        end_date=end_date,
        verbose=verbose,
    )

    # 4. Calibration
    if verbose:
        print("\n[4/4] Calibration + 통계 검증...")

    calibrator = Calibrator()
    calibrator.intraday_data = intraday_data
    calibrator.probabilistic_data = {"cells": list(probabilistic_cells.values())}
    factors = calibrator.compute_factors()

    # 5. KODEX 200 벤치마크
    kodex_returns = get_kodex_200_returns(start_date, end_date)
    if verbose:
        print(f"  KODEX 200 데이터: {len(kodex_returns)} days")

    # 6. 통합 rows
    rows = []
    for module_path in strategy_modules:
        sid = module_path.replace("strategies.", "")

        nominal_cell = nominal.get(sid, {})
        intraday_cell = intraday_cells.get(sid, {})
        prob_cell = probabilistic_cells.get(sid, {})
        factor = factors.get(sid)

        # 수익률들
        nominal_return = (nominal_cell.get("metrics") or {}).get("total_return_pct", 0) or 0
        tier1_return = intraday_cell.get("net_return_pct", 0) or 0
        tier2_return = (prob_cell.get("metrics") or {}).get("total_return_pct", 0) or 0

        # Calibrated
        if factor:
            calibrated_return = round(tier2_return * factor.return_factor, 4)
        else:
            calibrated_return = tier2_return

        # 통계 검증 (Tier 1 분봉 실측 기준)
        daily_returns_t1 = []
        intraday_history = intraday_cell.get("daily_history", [])
        for d in intraday_history:
            daily_returns_t1.append(d.get("avg_net_return_pct", 0) or 0)

        bootstrap = bootstrap_significance(daily_returns_t1, n_iterations=500) if daily_returns_t1 else None
        walk_fwd = walk_forward_validation(daily_returns_t1, train_window=3, test_window=2) if len(daily_returns_t1) >= 5 else None

        # Benchmark alpha
        alpha_result = None
        if daily_returns_t1 and kodex_returns:
            alpha_result = compute_benchmark_alpha(
                strategy_returns=daily_returns_t1,
                benchmark_returns=kodex_returns[:len(daily_returns_t1)],
            )

        row = {
            "strategy_id": sid,
            "strategy_name": prob_cell.get("strategy_name") or intraday_cell.get("strategy_name") or sid,

            # 4가지 수익률
            "nominal_return_pct": round(nominal_return, 4),
            "tier1_intraday_return_pct": round(tier1_return, 4),
            "tier2_probabilistic_return_pct": round(tier2_return, 4),
            "calibrated_return_pct": round(calibrated_return, 4),

            # Tier 1 통계
            "tier1_win_rate": intraday_cell.get("win_rate", 0),
            "tier1_num_trades": intraday_cell.get("num_trades", 0),
            "tier1_cost_pct": intraday_cell.get("total_cost_pct", 0),

            # Tier 2 통계
            "tier2_confidence": (prob_cell.get("metrics") or {}).get("avg_confidence", 0),
            "tier2_win_rate": (prob_cell.get("metrics") or {}).get("win_rate", 0),
            "tier2_scenarios": prob_cell.get("scenario_counts", {}),

            # Calibration
            "calibration_factor": factor.return_factor if factor else None,
            "calibration_confidence": factor.confidence if factor else None,

            # Bootstrap (통계 검증)
            "bootstrap_p_value": bootstrap.p_value if bootstrap else None,
            "is_statistically_significant": bootstrap.is_significant if bootstrap else False,
            "ci_95_lower": bootstrap.confidence_interval_95[0] if bootstrap else None,
            "ci_95_upper": bootstrap.confidence_interval_95[1] if bootstrap else None,

            # Walk-forward
            "walk_forward_return": walk_fwd.avg_return if walk_fwd else None,
            "walk_forward_consistency": walk_fwd.consistency if walk_fwd else None,
            "overfitting_gap": walk_fwd.overfitting_gap if walk_fwd else None,

            # Benchmark
            "benchmark_alpha": alpha_result.alpha if alpha_result else None,
            "benchmark_beta": alpha_result.beta if alpha_result else None,
            "benchmark_return": alpha_result.benchmark_return if alpha_result else None,
        }
        rows.append(row)

    # 순 수익률 기준 정렬 (walk-forward가 가장 신뢰)
    def sort_key(r):
        # walk_forward > tier1 > calibrated > tier2 > nominal 순
        return (
            r.get("walk_forward_return") or 0,
            r.get("tier1_intraday_return_pct") or 0,
        )
    rows.sort(key=sort_key, reverse=True)

    # 최종 데이터
    data = {
        "generated_at": datetime.now().isoformat(),
        "start_date": start_date,
        "end_date": end_date,
        "period_label": f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]} ~ {end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}",
        "strategies_count": len(rows),
        "rows": rows,
        "factors": {sid: asdict(f) for sid, f in factors.items()},
        "benchmark": {
            "name": "KOSPI index (proxy for KODEX 200)",
            "avg_daily_return_pct": round(
                sum(kodex_returns) / len(kodex_returns), 4
            ) if kodex_returns else 0,
            "days": len(kodex_returns),
        },
    }

    return data


def save_as_js(data: dict, output_path: Path = OUTPUT_JS) -> None:
    """
    leaderboard HTML이 읽을 수 있는 JS 형식으로 저장.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        f"// Auto-generated by build_realistic_leaderboard.py\n"
        f"// {datetime.now().isoformat()}\n\n"
        f"window.REALISTIC_LEADERBOARD = "
        f"{json.dumps(data, ensure_ascii=False, indent=2, default=str)};\n"
    )
    output_path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strategies", default="all",
        help="콤마 구분 (default: all = 10개)",
    )
    parser.add_argument(
        "--start-date", default=None,
        help="시작일 (default: 7일 전)",
    )
    parser.add_argument(
        "--end-date", default=None,
        help="종료일 (default: 오늘)",
    )
    parser.add_argument(
        "--intraday-path",
        type=Path,
        default=None,
        help="분봉 매트릭스 파일 (없으면 실행)",
    )
    args = parser.parse_args()

    if args.strategies == "all":
        modules = DEFAULT_STRATEGY_MODULES
    else:
        ids = [s.strip() for s in args.strategies.split(",")]
        modules = [f"strategies.{sid}" for sid in ids]

    if not args.end_date:
        args.end_date = datetime.now().strftime("%Y%m%d")
    if not args.start_date:
        args.start_date = (
            datetime.strptime(args.end_date, "%Y%m%d") - timedelta(days=7)
        ).strftime("%Y%m%d")

    data = build_realistic_leaderboard(
        start_date=args.start_date,
        end_date=args.end_date,
        strategy_modules=modules,
        intraday_path=args.intraday_path,
    )

    save_as_js(data)
    print(f"\n[SAVED] {OUTPUT_JS}")
    print(f"전략: {data['strategies_count']}")

    # TOP 5 출력
    print("\n=== TOP 5 (walk-forward 기준) ===")
    for i, r in enumerate(data["rows"][:5], 1):
        print(
            f"  {i}. {r['strategy_id']:>30} "
            f"nominal {r['nominal_return_pct']:+6.2f}% "
            f"T1 {r['tier1_intraday_return_pct']:+6.2f}% "
            f"WF {r.get('walk_forward_return', 0) or 0:+6.2f}%"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
