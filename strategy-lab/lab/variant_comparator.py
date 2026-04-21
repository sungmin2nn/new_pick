"""
Variant Comparator (Phase 7.A.4)
=================================
v0.1 (원본)과 v0.2 variants를 동일 기간/규칙으로 비교하고
가장 나은 버전을 자동 채택한다.

워크플로:
    1) parent 전략 + variants 리스트 로드
    2) 각각 동일 start/end로 백테스트 실행 (exit rule override 반영)
    3) 메트릭 집계 → adoption score 계산
    4) 최고 점수 pick → AdoptionDecision 생성
    5) 리포트 JSON 영속화

설계 포인트:
    - 백테스트 실행은 주입 가능 (테스트 시 mock 가능)
    - 비교 기준은 AdoptionCriteria로 커스터마이즈 가능
    - 동점 처리: 더 단순한 variant (overrides 수 적은 쪽) 선호
    - 원본 개선 없을 시 "원본 유지" 결정
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol

from lab.parameter_tuner import VariantSpec


# ============================================================
# Protocols / Interfaces
# ============================================================

class BacktestRunner(Protocol):
    """백테스트 실행 프로토콜. 실제 구현은 backtest_wrapper, 테스트는 mock."""

    def run(
        self,
        strategy_id: str,
        start_date: str,
        end_date: str,
        strategy_param_overrides: Optional[Dict[str, Any]] = None,
        exit_rule_overrides: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        Returns:
            dict with keys: total_return_pct, sharpe_ratio, max_drawdown_pct,
                            win_rate, num_trades, profit_factor, ...
        """
        ...


# ============================================================
# Data classes
# ============================================================

@dataclass
class VariantRunResult:
    """단일 variant (또는 원본) 실행 결과 + 점수."""
    label: str                          # "v0.1 (원본)" 또는 variant_id
    variant_id: Optional[str]           # None이면 원본
    is_baseline: bool
    metrics: Dict[str, Any] = field(default_factory=dict)
    adoption_score: float = 0.0
    complexity: int = 0                 # 오버라이드 개수
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AdoptionDecision:
    """v0.1 vs v0.2 채택 결정."""
    parent_strategy_id: str
    start_date: str
    end_date: str
    winner_label: str
    winner_variant_id: Optional[str]    # None이면 원본 유지
    baseline_score: float
    winner_score: float
    improvement_pct: float              # winner 대비 baseline 개선폭
    results: List[VariantRunResult] = field(default_factory=list)
    criteria_snapshot: Dict[str, Any] = field(default_factory=dict)
    decided_at: str = ""
    notes: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.decided_at:
            self.decided_at = datetime.now().isoformat(timespec="seconds")

    @property
    def baseline_beaten(self) -> bool:
        return self.winner_variant_id is not None

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> str:
        icon = "🏆" if self.baseline_beaten else "⚪"
        return (
            f"{icon} [{self.parent_strategy_id}] {self.start_date}~{self.end_date}\n"
            f"  winner: {self.winner_label} (score {self.winner_score:.2f})\n"
            f"  baseline: {self.baseline_score:.2f} → "
            f"{'+' if self.improvement_pct >= 0 else ''}{self.improvement_pct:.2f}% 개선"
        )


# ============================================================
# Criteria & scoring
# ============================================================

@dataclass
class AdoptionCriteria:
    """채택 판정 임계값/가중치."""
    # 점수 가중치
    weight_return: float = 0.40
    weight_sharpe: float = 0.25
    weight_mdd: float = 0.15
    weight_win_rate: float = 0.10
    weight_profit_factor: float = 0.10

    # 클리핑
    max_sharpe_sanity: float = 15.0

    # 채택 최소 개선 (%) — 이 미만이면 baseline 유지 (안정성 우선)
    min_improvement_pct: float = 2.0

    # 최소 거래 수 — 이 미만 결과는 유효하지 않음으로 간주
    min_trades: int = 5

    def to_dict(self) -> dict:
        return asdict(self)


def compute_adoption_score(
    metrics: Dict[str, Any], criteria: AdoptionCriteria
) -> float:
    """
    0~100 점수.
    - 수익률 40점: 0% → 0, 20%+ → 만점
    - Sharpe 25점 (clipped): 0 → 0, 5+ → 만점
    - MDD 15점: 0% → 만점, -20% → 0
    - Win rate 10점
    - Profit factor 10점: 1.0 → 0, 3.0+ → 만점
    """
    ret = float(metrics.get("total_return_pct") or 0)
    sharpe = min(float(metrics.get("sharpe_ratio") or 0), criteria.max_sharpe_sanity)
    mdd = float(metrics.get("max_drawdown_pct") or 0)
    wr = float(metrics.get("win_rate") or 0)
    pf = float(metrics.get("profit_factor") or 0)

    return_score = min(max(ret / 20.0, -1), 1) * 100 * criteria.weight_return
    sharpe_score = min(max(sharpe / 5.0, -1), 1) * 100 * criteria.weight_sharpe
    mdd_score = max(1 - abs(mdd) / 20.0, 0) * 100 * criteria.weight_mdd
    wr_score = max(min(wr, 1.0), 0) * 100 * criteria.weight_win_rate
    pf_score = min(max((pf - 1.0) / 2.0, 0), 1) * 100 * criteria.weight_profit_factor

    return round(
        return_score + sharpe_score + mdd_score + wr_score + pf_score, 2
    )


# ============================================================
# Comparator
# ============================================================

class VariantComparator:
    """
    v0.1 (원본) + List[VariantSpec] → AdoptionDecision.

    백테스트 실행은 `runner_fn` callable로 주입 (테스트 시 mock 가능).
    runner_fn 시그니처:
        runner_fn(strategy_id, start, end, strategy_param_overrides, exit_rule_overrides)
            -> dict of metrics
    """

    def __init__(
        self,
        runner_fn: Callable[..., Dict[str, Any]],
        criteria: Optional[AdoptionCriteria] = None,
    ):
        self.runner_fn = runner_fn
        self.criteria = criteria or AdoptionCriteria()

    def compare(
        self,
        parent_strategy_id: str,
        variants: List[VariantSpec],
        start_date: str,
        end_date: str,
    ) -> AdoptionDecision:
        results: List[VariantRunResult] = []

        # 1) baseline (v0.1 원본)
        baseline_result = self._run_single(
            label=f"{parent_strategy_id} (v0.1 원본)",
            variant_id=None,
            is_baseline=True,
            strategy_id=parent_strategy_id,
            start=start_date,
            end=end_date,
            strategy_overrides=None,
            exit_overrides=None,
            complexity=0,
        )
        results.append(baseline_result)
        baseline_score = baseline_result.adoption_score

        # 2) variants
        for spec in variants:
            complexity = len(spec.strategy_param_overrides or {}) + len(
                spec.exit_rule_overrides or {}
            )
            r = self._run_single(
                label=spec.variant_id,
                variant_id=spec.variant_id,
                is_baseline=False,
                strategy_id=parent_strategy_id,
                start=start_date,
                end=end_date,
                strategy_overrides=spec.strategy_param_overrides,
                exit_overrides=spec.exit_rule_overrides,
                complexity=complexity,
            )
            results.append(r)

        # 3) 승자 결정
        decision = self._decide(
            parent_strategy_id=parent_strategy_id,
            start_date=start_date,
            end_date=end_date,
            results=results,
            baseline_score=baseline_score,
        )
        return decision

    # --------------------------------------------------------

    def _run_single(
        self,
        label: str,
        variant_id: Optional[str],
        is_baseline: bool,
        strategy_id: str,
        start: str,
        end: str,
        strategy_overrides: Optional[Dict[str, Any]],
        exit_overrides: Optional[Dict[str, float]],
        complexity: int,
    ) -> VariantRunResult:
        try:
            metrics = self.runner_fn(
                strategy_id=strategy_id,
                start_date=start,
                end_date=end,
                strategy_param_overrides=strategy_overrides,
                exit_rule_overrides=exit_overrides,
            )
        except Exception as e:
            return VariantRunResult(
                label=label,
                variant_id=variant_id,
                is_baseline=is_baseline,
                metrics={},
                adoption_score=0.0,
                complexity=complexity,
                error=str(e),
            )

        # 최소 거래 수 미달은 0점
        num_trades = int(metrics.get("num_trades") or 0)
        if num_trades < self.criteria.min_trades:
            return VariantRunResult(
                label=label,
                variant_id=variant_id,
                is_baseline=is_baseline,
                metrics=metrics,
                adoption_score=0.0,
                complexity=complexity,
                error=f"거래 수 부족 ({num_trades} < {self.criteria.min_trades})",
            )

        score = compute_adoption_score(metrics, self.criteria)
        return VariantRunResult(
            label=label,
            variant_id=variant_id,
            is_baseline=is_baseline,
            metrics=metrics,
            adoption_score=score,
            complexity=complexity,
        )

    def _decide(
        self,
        parent_strategy_id: str,
        start_date: str,
        end_date: str,
        results: List[VariantRunResult],
        baseline_score: float,
    ) -> AdoptionDecision:
        c = self.criteria
        notes: List[str] = []

        # 유효한 결과 (error 없고 점수 > 0)
        valid = [r for r in results if not r.error]

        # 점수 높은 순, 동점이면 복잡도 낮은 순 (baseline 우선: complexity=0)
        valid.sort(key=lambda r: (-r.adoption_score, r.complexity))

        if not valid:
            notes.append("유효한 결과 없음 — 원본 유지")
            baseline = next((r for r in results if r.is_baseline), results[0])
            return AdoptionDecision(
                parent_strategy_id=parent_strategy_id,
                start_date=start_date,
                end_date=end_date,
                winner_label=baseline.label,
                winner_variant_id=None,
                baseline_score=baseline_score,
                winner_score=baseline_score,
                improvement_pct=0.0,
                results=results,
                criteria_snapshot=c.to_dict(),
                notes=notes,
            )

        top = valid[0]

        # 원본이 1등 → 유지
        if top.is_baseline:
            notes.append("원본이 최고 점수 — 변형 채택 안 함")
            return AdoptionDecision(
                parent_strategy_id=parent_strategy_id,
                start_date=start_date,
                end_date=end_date,
                winner_label=top.label,
                winner_variant_id=None,
                baseline_score=baseline_score,
                winner_score=top.adoption_score,
                improvement_pct=0.0,
                results=results,
                criteria_snapshot=c.to_dict(),
                notes=notes,
            )

        # 개선폭 계산 (baseline 대비 상대 %)
        # 음수 baseline에서 부호가 뒤집히지 않도록 abs() 사용
        if baseline_score > 0:
            improvement = (top.adoption_score - baseline_score) / baseline_score * 100
        elif baseline_score < 0:
            improvement = (top.adoption_score - baseline_score) / abs(baseline_score) * 100
        else:
            # baseline = 0: 절대 차이를 그대로 %로 간주
            improvement = top.adoption_score

        # 최소 개선폭 미달 → 원본 유지 (안정성 우선)
        if improvement < c.min_improvement_pct:
            notes.append(
                f"variant 우위이나 개선폭 {improvement:.2f}% < 최소 "
                f"{c.min_improvement_pct}% — 안정성 우선 원본 유지"
            )
            return AdoptionDecision(
                parent_strategy_id=parent_strategy_id,
                start_date=start_date,
                end_date=end_date,
                winner_label=f"{parent_strategy_id} (v0.1 원본)",
                winner_variant_id=None,
                baseline_score=baseline_score,
                winner_score=baseline_score,
                improvement_pct=improvement,
                results=results,
                criteria_snapshot=c.to_dict(),
                notes=notes,
            )

        # 채택!
        notes.append(
            f"variant 채택: {top.label} score {top.adoption_score:.2f} vs "
            f"baseline {baseline_score:.2f} ({improvement:+.2f}% 개선)"
        )
        return AdoptionDecision(
            parent_strategy_id=parent_strategy_id,
            start_date=start_date,
            end_date=end_date,
            winner_label=top.label,
            winner_variant_id=top.variant_id,
            baseline_score=baseline_score,
            winner_score=top.adoption_score,
            improvement_pct=improvement,
            results=results,
            criteria_snapshot=c.to_dict(),
            notes=notes,
        )


# ============================================================
# Persistence
# ============================================================

def save_adoption(decision: AdoptionDecision, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"adoption_{decision.parent_strategy_id}_{ts}.json"
    path.write_text(
        json.dumps(decision.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


__all__ = [
    "VariantRunResult",
    "AdoptionDecision",
    "AdoptionCriteria",
    "VariantComparator",
    "compute_adoption_score",
    "save_adoption",
]
