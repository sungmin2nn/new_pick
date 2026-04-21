"""
실험 로그 시스템.

각 백테스트 실행을 "실험"으로 기록한다.
- 실험 ID, 전략 ID, 기간, 결과 메트릭, 실행 환경
- 일관된 형식으로 누적되어 리더보드의 데이터 소스가 됨
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXPERIMENTS_DIR = PROJECT_ROOT / "data" / "experiments"


# ============================================================
# Data class
# ============================================================

@dataclass
class ExperimentResult:
    """단일 실험 결과 (전략 1개 × 기간 1개)."""

    # 식별
    experiment_id: str = ""             # ULID 또는 UUID
    strategy_id: str = ""
    strategy_name: str = ""
    strategy_version: str = ""

    # 기간
    start_date: str = ""                # YYYYMMDD
    end_date: str = ""                  # YYYYMMDD
    trading_days: int = 0

    # 시뮬 설정
    initial_capital: int = 10_000_000   # 1000만원
    use_intraday: bool = False
    market: str = "KOSPI+KOSDAQ"

    # 핵심 메트릭
    final_balance: int = 0
    total_return_pct: float = 0.0       # 누적 수익률 %
    max_drawdown_pct: float = 0.0       # MDD %
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0               # 0~1
    profit_factor: float = 0.0          # 총이익 / 총손실 절댓값

    # 거래 통계
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    avg_holding_days: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    max_consecutive_losses: int = 0
    max_consecutive_wins: int = 0

    # 리스크
    volatility_pct: float = 0.0         # 일별 수익률 표준편차 (연환산)

    # 실행 환경
    executed_at: str = ""
    duration_seconds: float = 0.0
    runner: str = "strategy-lab.runner.backtest_wrapper"
    git_commit: str = ""
    notes: str = ""

    # 원본 결과 파일 (백테스트 출력)
    raw_result_path: str = ""

    def __post_init__(self):
        if not self.experiment_id:
            self.experiment_id = f"exp_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        if not self.executed_at:
            self.executed_at = datetime.now().isoformat(timespec="seconds")

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# ============================================================
# Logger
# ============================================================

class ExperimentLogger:
    """실험 결과를 JSON 파일로 누적 저장."""

    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root else DEFAULT_EXPERIMENTS_DIR
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, experiment_id: str) -> Path:
        return self.root / f"{experiment_id}.json"

    def save(self, result: ExperimentResult) -> Path:
        """단일 실험 저장."""
        path = self._path(result.experiment_id)
        path.write_text(result.to_json(), encoding="utf-8")
        return path

    def load(self, experiment_id: str) -> ExperimentResult:
        path = self._path(experiment_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        return ExperimentResult(**data)

    def list_all(self) -> list:
        """모든 실험을 로드해서 리스트로 반환 (날짜 역순)."""
        experiments = []
        for f in sorted(self.root.glob("exp_*.json"), reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                experiments.append(ExperimentResult(**data))
            except Exception:
                continue
        return experiments

    def list_by_strategy(self, strategy_id: str) -> list:
        return [e for e in self.list_all() if e.strategy_id == strategy_id]

    def latest_per_strategy(self) -> dict:
        """각 전략의 가장 최근 실험만 반환."""
        seen = {}
        for e in self.list_all():
            if e.strategy_id not in seen:
                seen[e.strategy_id] = e
        return seen

    def stats(self) -> dict:
        all_exps = self.list_all()
        unique_strategies = set(e.strategy_id for e in all_exps)
        return {
            "total_experiments": len(all_exps),
            "unique_strategies": len(unique_strategies),
            "latest_experiment": all_exps[0].executed_at if all_exps else None,
        }


__all__ = [
    "ExperimentResult",
    "ExperimentLogger",
    "DEFAULT_EXPERIMENTS_DIR",
]
