"""
Ensemble Strategy Builder (Phase 7.B)
======================================
검증된 단일 전략들을 조합해서 "앙상블 전략"을 구성하고 백테스트한다.

접근: 사후 집계 (post-hoc aggregation)
    - 이미 실행된 matrix 결과의 일일 수익률 시계열을 가중 평균
    - 전략을 재실행하지 않음 → 빠르고 캐시 친화적
    - 각 전략은 동일한 거래일 집합에서 실행됐다고 가정

파이프라인:
    1) StrategyRanker      — 상위 N 선정 (수익률 + 일관성 가중)
    2) CorrelationAnalyzer — 일일 수익률 간 Pearson 상관계수 행렬
    3) EnsembleBuilder     — 3가지 조합 방식으로 가중치 계산 + 일일 결합
    4) EnsembleResult      — 결합된 시계열 + 메트릭 (Sharpe/MDD/win rate 등)

3가지 조합 방식:
    - equal            : 모든 멤버 1/N
    - performance      : 각 멤버 성과 점수에 비례
    - volatility_scaled: 역변동성 (1/sigma) — 위험 균등
"""

from __future__ import annotations

import math
import statistics as stats
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ============================================================
# Constants
# ============================================================

TRADING_DAYS_PER_YEAR = 252


class EnsembleMethod(str, Enum):
    EQUAL = "equal"
    PERFORMANCE_WEIGHTED = "performance_weighted"
    VOLATILITY_SCALED = "volatility_scaled"


# ============================================================
# Data
# ============================================================

@dataclass
class StrategyDailySeries:
    """한 전략의 일별 수익률 시리즈 (matrix cell로부터 추출)."""
    strategy_id: str
    strategy_name: str
    dates: List[str] = field(default_factory=list)
    daily_returns_pct: List[float] = field(default_factory=list)
    # 집계 메트릭 (matrix cell의 metrics에서 복사)
    total_return_pct: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate: float = 0.0
    num_trades: int = 0
    profit_factor: float = 0.0


@dataclass
class EnsembleResult:
    """앙상블 실행 결과."""
    ensemble_id: str
    method: str
    members: List[str]
    weights: Dict[str, float]
    dates: List[str]
    daily_returns_pct: List[float]
    equity_curve: List[float]

    # 집계 메트릭
    total_return_pct: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    volatility_pct: float = 0.0
    best_day_pct: float = 0.0
    worst_day_pct: float = 0.0
    num_days: int = 0
    trading_days: int = 0

    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat(timespec="seconds")

    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================
# Extraction helpers
# ============================================================

def extract_daily_series_from_cell(cell: Dict) -> Optional[StrategyDailySeries]:
    """matrix cell → StrategyDailySeries. history 없으면 None."""
    history = cell.get("history") or []
    if not history:
        return None

    dates = [h.get("date", "") for h in history]
    returns = [float(h.get("daily_return_pct") or 0) for h in history]
    metrics = cell.get("metrics") or {}

    return StrategyDailySeries(
        strategy_id=cell.get("strategy_id", "unknown"),
        strategy_name=cell.get("strategy_name", ""),
        dates=dates,
        daily_returns_pct=returns,
        total_return_pct=float(metrics.get("total_return_pct") or 0),
        sharpe_ratio=float(metrics.get("sharpe_ratio") or 0),
        max_drawdown_pct=float(metrics.get("max_drawdown_pct") or 0),
        win_rate=float(metrics.get("win_rate") or 0),
        num_trades=int(metrics.get("num_trades") or 0),
        profit_factor=float(metrics.get("profit_factor") or 0),
    )


# ============================================================
# Ranking (상위 전략 선정)
# ============================================================

@dataclass
class RankingCriteria:
    """상위 선정 가중치."""
    weight_return: float = 0.50
    weight_sharpe: float = 0.25
    weight_win_rate: float = 0.15
    weight_profit_factor: float = 0.10
    max_sharpe_sanity: float = 15.0
    min_trades: int = 10          # 최소 거래 수 미달은 제외
    min_return_pct: float = 0.0   # 음수 수익 전략은 제외


class StrategyRanker:
    """StrategyDailySeries 리스트를 점수 기반으로 정렬."""

    def __init__(self, criteria: Optional[RankingCriteria] = None):
        self.criteria = criteria or RankingCriteria()

    def score(self, s: StrategyDailySeries) -> float:
        c = self.criteria
        # 수익률 (0~20% → 0~만점)
        return_score = min(max(s.total_return_pct / 20.0, 0), 1) * 100 * c.weight_return
        # Sharpe clipped
        sh = min(s.sharpe_ratio, c.max_sharpe_sanity)
        sharpe_score = min(max(sh / 5.0, 0), 1) * 100 * c.weight_sharpe
        # Win rate
        wr_score = max(min(s.win_rate, 1.0), 0) * 100 * c.weight_win_rate
        # PF
        pf_score = min(max((s.profit_factor - 1.0) / 2.0, 0), 1) * 100 * c.weight_profit_factor
        return round(return_score + sharpe_score + wr_score + pf_score, 2)

    def select_top(
        self, series_list: List[StrategyDailySeries], top_n: int = 5
    ) -> List[Tuple[StrategyDailySeries, float]]:
        """
        상위 N개 + 점수. 필터(min_trades, min_return)를 먼저 적용.
        """
        c = self.criteria
        valid = [
            s for s in series_list
            if s.num_trades >= c.min_trades
            and s.total_return_pct >= c.min_return_pct
        ]
        scored = [(s, self.score(s)) for s in valid]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_n]


# ============================================================
# Correlation
# ============================================================

def _pearson(xs: List[float], ys: List[float]) -> float:
    if len(xs) < 2 or len(xs) != len(ys):
        return 0.0
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)


class CorrelationAnalyzer:
    """전략 × 전략 Pearson 상관계수 행렬."""

    def compute_matrix(
        self, series_list: List[StrategyDailySeries]
    ) -> Dict[str, Dict[str, float]]:
        """공통 날짜 기반 상관계수 행렬."""
        ids = [s.strategy_id for s in series_list]
        # id → (date → return)
        by_id: Dict[str, Dict[str, float]] = {}
        for s in series_list:
            by_id[s.strategy_id] = dict(zip(s.dates, s.daily_returns_pct))

        matrix: Dict[str, Dict[str, float]] = {}
        for i, id_a in enumerate(ids):
            matrix[id_a] = {}
            for j, id_b in enumerate(ids):
                if i == j:
                    matrix[id_a][id_b] = 1.0
                    continue
                common = sorted(
                    set(by_id[id_a].keys()) & set(by_id[id_b].keys())
                )
                xs = [by_id[id_a][d] for d in common]
                ys = [by_id[id_b][d] for d in common]
                matrix[id_a][id_b] = round(_pearson(xs, ys), 3)
        return matrix

    def average_correlation(
        self, matrix: Dict[str, Dict[str, float]], exclude_self: bool = True
    ) -> float:
        """멤버 전체의 평균 상관계수 (다양성 지표)."""
        vals = []
        ids = list(matrix.keys())
        for i, a in enumerate(ids):
            for j, b in enumerate(ids):
                if exclude_self and i == j:
                    continue
                if j <= i:
                    continue
                vals.append(matrix[a][b])
        if not vals:
            return 0.0
        return round(sum(vals) / len(vals), 3)


# ============================================================
# Ensemble builder
# ============================================================

class EnsembleBuilder:
    """가중치 계산 + 일별 결합."""

    def build(
        self,
        members: List[StrategyDailySeries],
        method: EnsembleMethod,
        ensemble_id: Optional[str] = None,
    ) -> EnsembleResult:
        if not members:
            raise ValueError("멤버 전략 없음")

        weights = self._compute_weights(members, method)

        # 공통 날짜
        date_sets = [set(m.dates) for m in members]
        common_dates = sorted(set.intersection(*date_sets))
        if not common_dates:
            raise ValueError("멤버 간 공통 거래일 없음")

        # id → (date → return)
        by_id: Dict[str, Dict[str, float]] = {
            m.strategy_id: dict(zip(m.dates, m.daily_returns_pct))
            for m in members
        }

        combined = []
        for d in common_dates:
            weighted_sum = 0.0
            for m in members:
                r = by_id[m.strategy_id].get(d, 0.0)
                weighted_sum += r * weights[m.strategy_id]
            combined.append(round(weighted_sum, 4))

        equity = [100.0]
        for r in combined:
            equity.append(round(equity[-1] * (1 + r / 100), 4))

        total_return = round((equity[-1] - 100.0), 4)
        metrics = self._compute_metrics(combined, equity)

        eid = ensemble_id or f"ensemble_{method.value}_{len(members)}"
        return EnsembleResult(
            ensemble_id=eid,
            method=method.value,
            members=[m.strategy_id for m in members],
            weights={k: round(v, 4) for k, v in weights.items()},
            dates=common_dates,
            daily_returns_pct=combined,
            equity_curve=equity,
            total_return_pct=total_return,
            sharpe_ratio=metrics["sharpe"],
            max_drawdown_pct=metrics["mdd"],
            volatility_pct=metrics["volatility"],
            best_day_pct=metrics["best"],
            worst_day_pct=metrics["worst"],
            num_days=len(combined),
            trading_days=len(combined),
        )

    # --------------------------------------------------------

    def _compute_weights(
        self, members: List[StrategyDailySeries], method: EnsembleMethod
    ) -> Dict[str, float]:
        if method == EnsembleMethod.EQUAL:
            n = len(members)
            return {m.strategy_id: 1.0 / n for m in members}

        if method == EnsembleMethod.PERFORMANCE_WEIGHTED:
            # 각 멤버의 total_return_pct를 floor 0으로 클리핑 후 정규화
            raw = {m.strategy_id: max(m.total_return_pct, 0.0) for m in members}
            total = sum(raw.values())
            if total == 0:
                # 모두 0이면 equal fallback
                n = len(members)
                return {m.strategy_id: 1.0 / n for m in members}
            return {k: v / total for k, v in raw.items()}

        if method == EnsembleMethod.VOLATILITY_SCALED:
            # 역변동성 — sigma가 작을수록 weight 큼
            vols: Dict[str, float] = {}
            for m in members:
                if len(m.daily_returns_pct) >= 2:
                    sigma = _stddev(m.daily_returns_pct)
                else:
                    sigma = 0.0
                vols[m.strategy_id] = sigma if sigma > 0 else 1e-6
            inv = {k: 1.0 / v for k, v in vols.items()}
            total = sum(inv.values())
            return {k: v / total for k, v in inv.items()}

        raise ValueError(f"알 수 없는 method: {method}")

    def _compute_metrics(
        self, daily_returns: List[float], equity_curve: List[float]
    ) -> Dict[str, float]:
        if not daily_returns:
            return {
                "sharpe": 0.0, "mdd": 0.0, "volatility": 0.0,
                "best": 0.0, "worst": 0.0,
            }

        # Sharpe (일 평균 / 일 stddev × sqrt(252))
        sigma = _stddev(daily_returns)
        mean = sum(daily_returns) / len(daily_returns)
        sharpe = (mean / sigma * math.sqrt(TRADING_DAYS_PER_YEAR)) if sigma > 0 else 0.0
        vol = sigma * math.sqrt(TRADING_DAYS_PER_YEAR)

        # MDD from equity curve
        peak = equity_curve[0]
        mdd = 0.0
        for v in equity_curve:
            if v > peak:
                peak = v
            dd = (v - peak) / peak * 100 if peak > 0 else 0
            if dd < mdd:
                mdd = dd

        return {
            "sharpe": round(sharpe, 2),
            "mdd": round(mdd, 2),
            "volatility": round(vol, 2),
            "best": round(max(daily_returns), 2),
            "worst": round(min(daily_returns), 2),
        }


def _stddev(vals: List[float]) -> float:
    if len(vals) < 2:
        return 0.0
    return stats.stdev(vals)


__all__ = [
    "EnsembleMethod",
    "StrategyDailySeries",
    "EnsembleResult",
    "RankingCriteria",
    "StrategyRanker",
    "CorrelationAnalyzer",
    "EnsembleBuilder",
    "extract_daily_series_from_cell",
]
