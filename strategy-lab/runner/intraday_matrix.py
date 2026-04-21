"""
Intraday Matrix Runner
=======================
10개 전략 × 최근 6일 분봉 매트릭스.

특징:
- IntradayBacktest 재사용
- 분봉 캐시 전역 공유 (Yahoo rate limit 회피)
- 결과 JSON 저장 (data/results/intraday_matrix_*.json)
- leaderboard_data.js로 변환 가능

사용:
    python3 -m runner.intraday_matrix
    python3 -m runner.intraday_matrix --strategies volatility_breakout_lw,sector_rotation
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from lab import assert_ntb_available
from lab.yahoo_minute import YahooMinuteClient
from runner.backtest_wrapper import get_trading_days
from runner.intraday_backtest import (
    IntradayBacktest,
    IntradayBacktestResult,
)
from runner.matrix_runner import DEFAULT_STRATEGY_MODULES

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "data" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def _print_progress(cell: dict, current: int, total: int) -> None:
    if cell.get("status") == "completed":
        print(
            f"[{current:>3}/{total}] ✓ {cell['strategy_id']:>30} "
            f"gross={cell['gross_return_pct']:+7.2f}% "
            f"net={cell['net_return_pct']:+7.2f}% "
            f"WR={cell['win_rate']*100:.0f}% "
            f"trades={cell['num_trades']} "
            f"({cell['duration_seconds']:.1f}s)"
        )
    else:
        print(
            f"[{current:>3}/{total}] ✗ {cell['strategy_id']:>30} "
            f"FAILED: {cell.get('error', 'unknown')[:60]}"
        )


def run_intraday_matrix(
    strategy_modules: List[str],
    start_date: str,
    end_date: str,
    shared_cache: Optional[dict] = None,
    verbose: bool = True,
) -> dict:
    """
    N개 전략 × 분봉 6일 매트릭스 실행.

    Returns:
        {
            "generated_at": "...",
            "start_date": "...",
            "end_date": "...",
            "cells": [{strategy_id, gross_return_pct, net_return_pct, ...}],
            "summary": {...},
        }
    """
    assert_ntb_available()

    start_time = time.time()
    yahoo_client = YahooMinuteClient()  # 공유 인스턴스 (캐시 공유)

    trading_days = get_trading_days(start_date, end_date)
    if not trading_days:
        raise RuntimeError("거래일 추출 실패")

    if verbose:
        print(f"\n{'=' * 60}")
        print(f"Intraday Matrix: {len(strategy_modules)}개 전략 × {len(trading_days)}일 분봉")
        print(f"기간: {trading_days[0]} ~ {trading_days[-1]}")
        print(f"{'=' * 60}\n")

    cells = []
    for i, module_path in enumerate(strategy_modules, 1):
        try:
            mod = importlib.import_module(module_path)
            # BaseStrategy 인스턴스 찾기
            from lab import BaseStrategy
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
                cells.append({
                    "status": "failed",
                    "strategy_id": module_path,
                    "error": "클래스 찾기 실패",
                    "duration_seconds": 0.0,
                })
                continue

            strategy = strategy_cls()
            bt = IntradayBacktest(strategy, yahoo_client=yahoo_client)

            result = bt.run(start_date, end_date, trading_days=trading_days, verbose=False)

            cell = {
                "strategy_id": result.strategy_id,
                "strategy_name": result.strategy_name,
                "start_date": result.start_date,
                "end_date": result.end_date,
                "trading_days": result.trading_days,
                "status": "failed" if result.has_errors and result.total_trades == 0 else "completed",
                "duration_seconds": result.duration_seconds,

                # 수익률
                "gross_return_pct": result.gross_return_pct,
                "net_return_pct": result.net_return_pct,
                "total_cost_pct": result.total_cost_pct,

                # 거래 통계
                "num_trades": result.total_trades,
                "total_wins": result.total_wins,
                "total_losses": result.total_losses,
                "win_rate": (
                    result.total_wins / max(result.total_trades, 1)
                    if result.total_trades > 0 else 0.0
                ),

                # 일별 요약
                "daily_history": [
                    {
                        "date": d.date,
                        "candidates_selected": d.candidates_selected,
                        "trades_executed": d.trades_executed,
                        "wins": d.wins,
                        "losses": d.losses,
                        "avg_gross_return_pct": d.avg_gross_return_pct,
                        "avg_net_return_pct": d.avg_net_return_pct,
                        "total_return_amount": d.total_return_amount,
                        "capital_after": d.capital_after,
                        "trades": [asdict(t) for t in d.trades],
                        "skipped_no_bars": d.skipped_no_bars,
                    }
                    for d in result.daily_history
                ],

                "error": "; ".join(result.error_messages[:3]) if result.error_messages else None,
            }
            cells.append(cell)
            if verbose:
                _print_progress(cell, i, len(strategy_modules))

        except Exception as e:
            import traceback
            cells.append({
                "status": "failed",
                "strategy_id": module_path,
                "error": f"{e}\n{traceback.format_exc()[:500]}",
                "duration_seconds": 0.0,
            })
            if verbose:
                print(f"[{i:>3}/{len(strategy_modules)}] ✗ {module_path} EXCEPTION: {e}")

    elapsed = time.time() - start_time
    completed = sum(1 for c in cells if c.get("status") == "completed")
    failed = len(cells) - completed

    # 요약
    completed_cells = [c for c in cells if c.get("status") == "completed"]
    if completed_cells:
        gross_returns = [c["gross_return_pct"] for c in completed_cells]
        net_returns = [c["net_return_pct"] for c in completed_cells]
        summary = {
            "total_cells": len(cells),
            "completed": completed,
            "failed": failed,
            "avg_gross_pct": round(sum(gross_returns) / len(gross_returns), 2),
            "avg_net_pct": round(sum(net_returns) / len(net_returns), 2),
            "best_net_pct": round(max(net_returns), 2),
            "worst_net_pct": round(min(net_returns), 2),
        }
    else:
        summary = {"total_cells": len(cells), "completed": 0, "failed": failed}

    data = {
        "generated_at": datetime.now().isoformat(),
        "start_date": start_date,
        "end_date": end_date,
        "trading_days": trading_days,
        "strategies": strategy_modules,
        "cells": cells,
        "summary": summary,
        "elapsed_seconds": round(elapsed, 2),
    }

    if verbose:
        print(f"\n{'=' * 60}")
        print(f"✓ 완료: {completed}/{len(cells)} (실패 {failed})")
        print(f"  평균 gross: {summary.get('avg_gross_pct', 0):+.2f}%")
        print(f"  평균 net:   {summary.get('avg_net_pct', 0):+.2f}%")
        print(f"  소요: {elapsed:.1f}s")
        print(f"{'=' * 60}\n")

    return data


def save_results(data: dict) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RESULTS_DIR / f"intraday_matrix_{ts}.json"
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strategies", default="all",
        help="콤마 구분 (default: all = 10개 전체)",
    )
    parser.add_argument(
        "--start-date", default=None,
        help="시작일 (기본: 7일 전)",
    )
    parser.add_argument(
        "--end-date", default=None,
        help="종료일 (기본: 오늘)",
    )
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()

    if args.strategies == "all":
        modules = DEFAULT_STRATEGY_MODULES
    else:
        ids = [s.strip() for s in args.strategies.split(",")]
        modules = [f"strategies.{sid}" for sid in ids]

    # 기간: 분봉은 최대 7일 한계
    if not args.end_date:
        args.end_date = datetime.now().strftime("%Y%m%d")
    if not args.start_date:
        args.start_date = (
            datetime.strptime(args.end_date, "%Y%m%d") - timedelta(days=7)
        ).strftime("%Y%m%d")

    data = run_intraday_matrix(
        strategy_modules=modules,
        start_date=args.start_date,
        end_date=args.end_date,
    )

    if args.save:
        path = save_results(data)
        print(f"\n[SAVED] {path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
