"""
Matrix Runner
==============
N개 전략 × M개 기간 매트릭스를 일괄 실행하고 결과를 누적 저장.

특징:
- 전략 단위 ThreadPoolExecutor 병렬 (KRX 캐시 활용)
- 진행률 실시간 표시
- 결과를 ExperimentLogger에 자동 저장
- 리더보드 JSON 출력 (성과 순)
- 부분 실행 / resume 지원
- CLI 인터페이스

사용:
    from runner.matrix_runner import MatrixRunner
    from runner.backtest_wrapper import StandardPeriods

    runner = MatrixRunner()
    runner.add_all_strategies()
    runner.add_periods({"1w": StandardPeriods.one_week()})
    runner.run(parallel_strategies=4)

    print(runner.leaderboard())
"""

from __future__ import annotations

import importlib
import json
import logging
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from lab import BaseStrategy, NTB_AVAILABLE, assert_ntb_available
from lab.experiments import ExperimentLogger, ExperimentResult
from runner.backtest_wrapper import (
    SingleStrategyBacktest,
    StandardPeriods,
    BacktestResult,
    INITIAL_CAPITAL,
    DEFAULT_WORKERS,
)
from runner.metrics import calculate_metrics, MetricsResult

logger = logging.getLogger(__name__)


# ============================================================
# Constants
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "data" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_STRATEGY_MODULES = [
    "strategies.volatility_breakout_lw",
    "strategies.sector_rotation",
    "strategies.foreign_flow_momentum",
    "strategies.news_catalyst_timing",
    "strategies.multi_signal_hybrid",
    "strategies.kospi_intraday_momentum",
    "strategies.overnight_etf_reversal",
    "strategies.opening_30min_volume_burst",
    "strategies.eod_reversal_korean",
    "strategies.turtle_breakout_short",
]


# ============================================================
# Data
# ============================================================

@dataclass
class MatrixCell:
    """매트릭스의 한 칸 = 1개 전략 × 1개 기간."""
    strategy_id: str
    strategy_name: str
    period_label: str
    start_date: str
    end_date: str
    backtest_result: Optional[dict] = None
    metrics: Optional[dict] = None
    duration_seconds: float = 0.0
    error: Optional[str] = None
    status: str = "pending"   # pending | running | completed | failed

    def is_done(self) -> bool:
        return self.status in ("completed", "failed")


# ============================================================
# Matrix Runner
# ============================================================

class MatrixRunner:
    """전략 × 기간 매트릭스 일괄 실행기."""

    def __init__(
        self,
        results_dir: Path = RESULTS_DIR,
        log_to_experiments: bool = True,
    ):
        assert_ntb_available()
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)

        self.strategies: Dict[str, BaseStrategy] = {}
        self.periods: Dict[str, Tuple[str, str]] = {}
        self.cells: List[MatrixCell] = []

        self.log_to_experiments = log_to_experiments
        self._exp_logger = ExperimentLogger() if log_to_experiments else None

    # --------------------------------------------------------
    # Setup
    # --------------------------------------------------------

    def add_strategy(self, strategy: BaseStrategy) -> None:
        self.strategies[strategy.STRATEGY_ID] = strategy

    def add_strategy_by_module(self, module_path: str) -> None:
        """모듈 경로로부터 전략 클래스를 찾아 인스턴스화."""
        mod = importlib.import_module(module_path)
        # BaseStrategy를 상속한 클래스 찾기
        for name in dir(mod):
            obj = getattr(mod, name)
            if (
                isinstance(obj, type)
                and obj is not BaseStrategy
                and hasattr(obj, "STRATEGY_ID")
                and obj.__module__ == module_path
            ):
                instance = obj()
                self.add_strategy(instance)
                return
        raise ValueError(f"전략 클래스를 찾을 수 없음: {module_path}")

    def add_all_strategies(self, modules: Optional[List[str]] = None) -> None:
        """기본 10개 + 옵션으로 추가 전략 모두 추가."""
        modules = modules or DEFAULT_STRATEGY_MODULES
        for m in modules:
            try:
                self.add_strategy_by_module(m)
            except Exception as e:
                logger.warning(f"전략 추가 실패 {m}: {e}")

    def add_period(self, label: str, start: str, end: str) -> None:
        self.periods[label] = (start, end)

    def add_periods(self, periods: Dict[str, Tuple[str, str]]) -> None:
        for label, dates in periods.items():
            self.periods[label] = dates

    def _build_cells(self) -> None:
        self.cells = []
        for sid, strat in self.strategies.items():
            for label, (start, end) in self.periods.items():
                self.cells.append(MatrixCell(
                    strategy_id=sid,
                    strategy_name=strat.STRATEGY_NAME,
                    period_label=label,
                    start_date=start,
                    end_date=end,
                ))

    # --------------------------------------------------------
    # Run
    # --------------------------------------------------------

    def _run_one_cell(self, cell: MatrixCell) -> MatrixCell:
        """단일 cell 실행."""
        cell.status = "running"
        t0 = time.time()
        strat = self.strategies[cell.strategy_id]

        try:
            bt = SingleStrategyBacktest(strat, suppress_strategy_print=True)
            # 일자 단위는 순차로 (전략 단위 병렬과 충돌 방지)
            result = bt.run(
                cell.start_date,
                cell.end_date,
                parallel_workers=1,
            )
            cell.backtest_result = result.to_dict()
            metrics = calculate_metrics(result)
            cell.metrics = metrics.to_dict()
            cell.status = "completed"

            # ExperimentLogger 저장
            if self._exp_logger:
                exp = ExperimentResult(
                    strategy_id=cell.strategy_id,
                    strategy_name=cell.strategy_name,
                    start_date=cell.start_date,
                    end_date=cell.end_date,
                    trading_days=result.trading_days,
                    initial_capital=result.initial_capital,
                    final_balance=result.final_capital,
                    total_return_pct=metrics.total_return_pct,
                    max_drawdown_pct=metrics.max_drawdown_pct,
                    sharpe_ratio=metrics.sharpe_ratio,
                    win_rate=metrics.win_rate,
                    profit_factor=metrics.profit_factor if metrics.profit_factor != float("inf") else 999.0,
                    total_trades=result.total_trades,
                    winning_trades=result.total_wins,
                    losing_trades=result.total_losses,
                    avg_holding_days=1.0,
                    avg_win_pct=metrics.avg_win_pct,
                    avg_loss_pct=metrics.avg_loss_pct,
                    max_consecutive_losses=metrics.max_consecutive_losses,
                    max_consecutive_wins=metrics.max_consecutive_wins,
                    volatility_pct=metrics.volatility_pct,
                    duration_seconds=time.time() - t0,
                    notes=f"period={cell.period_label}",
                )
                self._exp_logger.save(exp)

        except Exception as e:
            cell.error = f"{e}\n{traceback.format_exc()}"
            cell.status = "failed"
            logger.error(f"cell 실패: {cell.strategy_id}/{cell.period_label}: {e}")

        cell.duration_seconds = round(time.time() - t0, 2)
        return cell

    def run(
        self,
        parallel_strategies: int = DEFAULT_WORKERS,
        verbose: bool = True,
    ) -> List[MatrixCell]:
        """매트릭스 전체 실행."""
        if not self.strategies or not self.periods:
            raise ValueError("전략 또는 기간이 비어있습니다. add_* 호출 필요.")

        self._build_cells()
        total = len(self.cells)
        if verbose:
            print(f"\n{'=' * 60}")
            print(f"Matrix Runner: {len(self.strategies)}개 전략 × {len(self.periods)}개 기간 = {total} cells")
            print(f"병렬 워커: {parallel_strategies}")
            print(f"{'=' * 60}\n")

        t0 = time.time()
        completed = 0

        if parallel_strategies > 1:
            with ThreadPoolExecutor(max_workers=parallel_strategies) as ex:
                futures = {ex.submit(self._run_one_cell, c): c for c in self.cells}
                for fut in as_completed(futures):
                    cell = fut.result()
                    completed += 1
                    if verbose:
                        self._print_cell_result(cell, completed, total)
        else:
            for cell in self.cells:
                self._run_one_cell(cell)
                completed += 1
                if verbose:
                    self._print_cell_result(cell, completed, total)

        elapsed = time.time() - t0
        if verbose:
            done = sum(1 for c in self.cells if c.status == "completed")
            failed = sum(1 for c in self.cells if c.status == "failed")
            print(f"\n{'=' * 60}")
            print(f"완료: {done}/{total} (실패 {failed})")
            print(f"소요: {elapsed:.1f}s ({elapsed / max(total, 1):.2f}s/cell 평균)")
            print(f"{'=' * 60}\n")

        return self.cells

    def _print_cell_result(self, cell: MatrixCell, current: int, total: int) -> None:
        if cell.status == "completed":
            m = cell.metrics or {}
            print(
                f"[{current:>3}/{total}] ✓ {cell.strategy_id:>30}/{cell.period_label:>4} "
                f"{m.get('total_return_pct', 0):+7.2f}%  "
                f"Sharpe {m.get('sharpe_ratio', 0):+5.2f}  "
                f"MDD {m.get('max_drawdown_pct', 0):+5.2f}%  "
                f"WR {m.get('win_rate', 0) * 100:.0f}%  "
                f"({cell.duration_seconds:.1f}s)"
            )
        else:
            print(
                f"[{current:>3}/{total}] ✗ {cell.strategy_id:>30}/{cell.period_label:>4} "
                f"FAILED: {(cell.error or 'unknown')[:60]}"
            )

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------

    def leaderboard(
        self,
        period_filter: Optional[str] = None,
        sort_by: str = "total_return_pct",
        top_n: Optional[int] = None,
    ) -> List[Dict]:
        """성과 순위표 생성."""
        rows = []
        for c in self.cells:
            if c.status != "completed":
                continue
            if period_filter and c.period_label != period_filter:
                continue
            m = c.metrics or {}
            rows.append({
                "strategy_id": c.strategy_id,
                "strategy_name": c.strategy_name,
                "period": c.period_label,
                "start_date": c.start_date,
                "end_date": c.end_date,
                "total_return_pct": m.get("total_return_pct", 0),
                "sharpe_ratio": m.get("sharpe_ratio", 0),
                "sortino_ratio": m.get("sortino_ratio", 0),
                "calmar_ratio": m.get("calmar_ratio", 0),
                "max_drawdown_pct": m.get("max_drawdown_pct", 0),
                "win_rate": m.get("win_rate", 0),
                "profit_factor": m.get("profit_factor", 0),
                "num_trades": m.get("num_trades", 0),
                "trading_days": m.get("trading_days", 0),
                "best_day_pct": m.get("best_day_pct", 0),
                "worst_day_pct": m.get("worst_day_pct", 0),
                "max_consecutive_losses": m.get("max_consecutive_losses", 0),
            })

        rows.sort(key=lambda r: r.get(sort_by, 0), reverse=True)
        if top_n:
            rows = rows[:top_n]
        return rows

    def save_results(self, filename: Optional[str] = None) -> Path:
        """매트릭스 결과를 JSON 파일로 저장."""
        if not filename:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"matrix_{ts}.json"
        path = self.results_dir / filename

        data = {
            "generated_at": datetime.now().isoformat(),
            "strategies": list(self.strategies.keys()),
            "periods": {k: list(v) for k, v in self.periods.items()},
            "cells": [],
            "leaderboards": {
                period: self.leaderboard(period_filter=period)
                for period in self.periods.keys()
            },
            "summary": self._summary_stats(),
        }

        for c in self.cells:
            # daily_history (trade_details 포함) 추출 — 대시보드 아코디언용
            history = None
            if c.backtest_result and isinstance(c.backtest_result, dict):
                history = c.backtest_result.get("daily_history")

            cell_data = {
                "strategy_id": c.strategy_id,
                "strategy_name": c.strategy_name,
                "period_label": c.period_label,
                "start_date": c.start_date,
                "end_date": c.end_date,
                "status": c.status,
                "duration_seconds": c.duration_seconds,
                "metrics": c.metrics,
                "history": history,
                "error": c.error,
            }
            data["cells"].append(cell_data)

        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return path

    def _summary_stats(self) -> Dict:
        completed = [c for c in self.cells if c.status == "completed"]
        if not completed:
            return {"completed": 0, "failed": len(self.cells)}
        returns = [c.metrics.get("total_return_pct", 0) for c in completed if c.metrics]
        return {
            "total_cells": len(self.cells),
            "completed": len(completed),
            "failed": sum(1 for c in self.cells if c.status == "failed"),
            "avg_return_pct": round(sum(returns) / len(returns), 2) if returns else 0,
            "best_return_pct": round(max(returns), 2) if returns else 0,
            "worst_return_pct": round(min(returns), 2) if returns else 0,
        }

    def print_leaderboard(self, period: Optional[str] = None, top_n: int = 20) -> None:
        """콘솔에 리더보드 출력."""
        if period:
            rows = self.leaderboard(period_filter=period, top_n=top_n)
            print(f"\n=== Leaderboard ({period}) ===")
        else:
            rows = self.leaderboard(top_n=top_n)
            print(f"\n=== Leaderboard (all periods) ===")

        if not rows:
            print("(결과 없음)")
            return

        print(f"{'Rank':>4}  {'Strategy':>30}  {'Period':>6}  {'Return':>9}  {'Sharpe':>7}  {'MDD':>7}  {'WR':>6}")
        print("-" * 90)
        for i, r in enumerate(rows, 1):
            print(
                f"{i:>4}  {r['strategy_id']:>30}  {r['period']:>6}  "
                f"{r['total_return_pct']:+7.2f}%  "
                f"{r['sharpe_ratio']:+6.2f}  "
                f"{r['max_drawdown_pct']:+6.2f}%  "
                f"{r['win_rate'] * 100:5.1f}%"
            )


# ============================================================
# CLI
# ============================================================

def _cli() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Strategy Lab Matrix Runner")
    parser.add_argument(
        "--strategies", default="all",
        help="콤마 구분 ID (default: all = 10개 전체)",
    )
    parser.add_argument(
        "--periods", default="1w",
        help="콤마 구분 기간 라벨 (1w/1m/3m/1y, default: 1w)",
    )
    parser.add_argument(
        "--end-date", default=None,
        help="기준 종료일 YYYYMMDD (default: 오늘)",
    )
    parser.add_argument(
        "--workers", type=int, default=4,
        help="병렬 워커 수 (default: 4)",
    )
    parser.add_argument(
        "--save", action="store_true",
        help="결과를 data/results/에 JSON 저장",
    )
    parser.add_argument(
        "--top", type=int, default=20,
        help="리더보드 상위 N개",
    )
    args = parser.parse_args()

    runner = MatrixRunner()

    # 전략 추가
    if args.strategies == "all":
        runner.add_all_strategies()
    else:
        ids = [s.strip() for s in args.strategies.split(",") if s.strip()]
        # ID → 모듈 매핑
        for sid in ids:
            module_path = f"strategies.{sid}"
            try:
                runner.add_strategy_by_module(module_path)
            except Exception as e:
                print(f"전략 추가 실패: {sid} ({e})")

    # 기간 추가
    period_labels = [p.strip() for p in args.periods.split(",")]
    for label in period_labels:
        if label == "1w":
            runner.add_period("1w", *StandardPeriods.one_week(args.end_date))
        elif label == "1m":
            runner.add_period("1m", *StandardPeriods.one_month(args.end_date))
        elif label == "3m":
            runner.add_period("3m", *StandardPeriods.three_months(args.end_date))
        elif label == "1y":
            runner.add_period("1y", *StandardPeriods.one_year(args.end_date))
        else:
            print(f"알 수 없는 기간: {label}")

    runner.run(parallel_strategies=args.workers)
    runner.print_leaderboard(top_n=args.top)

    if args.save:
        path = runner.save_results()
        print(f"\n[SAVED] {path}")

    return 0


if __name__ == "__main__":
    sys.exit(_cli())
