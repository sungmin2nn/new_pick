"""
Promotion Evaluation
=====================
백테스트 결과를 기반으로 전략이 news-trading-bot 정식 통합 후보인지 평가.

4단계 상태:
- PROMOTED: 모든 승급 기준 통과 → 통합 후보
- WATCHLIST: 일부 기준 미달이나 가능성 있음
- REJECTED: 탈락 기준 중 하나라도 해당
- PENDING: 데이터 부족 (거래 수 너무 적음)

승급 기준 (모두 만족):
- total_return_pct >= 5.0
- sharpe_ratio >= 1.0 (현실적 샤프, 과대평가 방지 상한 적용)
- win_rate >= 0.50
- max_drawdown_pct >= -15.0 (부호: 음수가 MDD)
- num_trades >= 10
- profit_factor >= 1.5

탈락 기준 (하나라도 해당하면 REJECTED):
- total_return_pct < 0
- max_consecutive_losses >= 7
- win_rate < 0.30
- num_trades == 0

PENDING (데이터 부족):
- num_trades < 5
- trading_days < 5

설계 원칙:
- 임계값은 PromotionCriteria로 override 가능
- 평가는 순수 함수 (side effect 없음)
- 결과는 PromotionResult dataclass
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


# ============================================================
# Enums
# ============================================================

class PromotionStatus(str, Enum):
    PROMOTED = "promoted"       # 승급 후보 — 통합 가이드 생성
    WATCHLIST = "watchlist"     # 관찰 — 더 많은 데이터 필요
    REJECTED = "rejected"       # 탈락 — 아이디어 재고
    PENDING = "pending"         # 판단 불가 — 데이터 부족


class RejectionReason(str, Enum):
    NEGATIVE_RETURN = "negative_return"
    TOO_MANY_LOSSES = "too_many_consecutive_losses"
    LOW_WIN_RATE = "low_win_rate"
    NO_TRADES = "no_trades"


# ============================================================
# Criteria (튜닝 가능)
# ============================================================

@dataclass
class PromotionCriteria:
    """승급/탈락 임계값 설정. 모든 값은 override 가능."""

    # 승급 기준 (ALL must pass)
    min_return_pct: float = 5.0
    min_sharpe: float = 1.0
    max_sharpe_sanity: float = 15.0    # Sharpe > 15는 과대평가로 간주 (현실화)
    min_win_rate: float = 0.50
    max_drawdown_pct: float = -15.0    # 이보다 더 나쁜 MDD는 탈락 쪽
    min_trades: int = 10
    min_profit_factor: float = 1.5

    # 탈락 기준 (ANY triggers)
    reject_if_negative_return: bool = True
    reject_if_consecutive_losses: int = 7
    reject_if_win_rate_below: float = 0.30
    reject_if_no_trades: bool = True

    # PENDING 기준
    pending_if_trades_below: int = 5
    pending_if_days_below: int = 5

    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================
# Result
# ============================================================

@dataclass
class PromotionResult:
    """단일 전략 × 기간 평가 결과."""
    strategy_id: str
    strategy_name: str
    period_label: str
    start_date: str
    end_date: str

    status: str = ""   # 평가 중에만 빈 값, 평가 완료 후 반드시 설정됨
    passed_criteria: List[str] = field(default_factory=list)
    failed_criteria: List[str] = field(default_factory=list)
    rejection_reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # 주요 메트릭 요약
    total_return_pct: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    max_drawdown_pct: float = 0.0
    num_trades: int = 0
    profit_factor: float = 0.0
    max_consecutive_losses: int = 0
    trading_days: int = 0

    score: float = 0.0           # 0~100 종합 점수
    evaluated_at: str = ""
    criteria_snapshot: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.evaluated_at:
            self.evaluated_at = datetime.now().isoformat(timespec="seconds")

    def to_dict(self) -> dict:
        return asdict(self)

    def is_promoted(self) -> bool:
        return self.status == PromotionStatus.PROMOTED.value

    def summary(self) -> str:
        emoji = {
            "promoted": "🏆",
            "watchlist": "⚠️",
            "rejected": "❌",
            "pending": "⏳",
        }.get(self.status, "❓")
        return (
            f"{emoji} [{self.status}] {self.strategy_id} ({self.period_label}) "
            f"return={self.total_return_pct:+.2f}% "
            f"sharpe={self.sharpe_ratio:.2f} "
            f"WR={self.win_rate * 100:.0f}% "
            f"trades={self.num_trades} "
            f"score={self.score:.1f}"
        )


# ============================================================
# Evaluator
# ============================================================

class PromotionEvaluator:
    """리더보드 row / 메트릭 딕셔너리를 받아 승급 상태를 결정."""

    def __init__(self, criteria: Optional[PromotionCriteria] = None):
        self.criteria = criteria or PromotionCriteria()

    def evaluate(self, row: Dict) -> PromotionResult:
        """
        리더보드 row 1개 평가.

        Args:
            row: dict — leaderboard_data.js의 leaderboards[period] 항목
                필수 키: strategy_id, total_return_pct, sharpe_ratio, win_rate,
                         max_drawdown_pct, num_trades, profit_factor, ...
        """
        result = PromotionResult(
            strategy_id=row.get("strategy_id", "unknown"),
            strategy_name=row.get("strategy_name", ""),
            period_label=row.get("period", ""),
            start_date=row.get("start_date", ""),
            end_date=row.get("end_date", ""),
            total_return_pct=float(row.get("total_return_pct") or 0),
            sharpe_ratio=float(row.get("sharpe_ratio") or 0),
            win_rate=float(row.get("win_rate") or 0),
            max_drawdown_pct=float(row.get("max_drawdown_pct") or 0),
            num_trades=int(row.get("num_trades") or 0),
            profit_factor=float(row.get("profit_factor") or 0),
            max_consecutive_losses=int(row.get("max_consecutive_losses") or 0),
            trading_days=int(row.get("trading_days") or 0),
            criteria_snapshot=self.criteria.to_dict(),
        )

        c = self.criteria

        # 1) REJECTED 우선 체크 (가장 명확한 탈락)
        rejection = []
        if c.reject_if_no_trades and result.num_trades == 0:
            rejection.append(RejectionReason.NO_TRADES.value)
        if c.reject_if_negative_return and result.total_return_pct < 0:
            rejection.append(RejectionReason.NEGATIVE_RETURN.value)
        if (
            c.reject_if_consecutive_losses
            and result.max_consecutive_losses >= c.reject_if_consecutive_losses
        ):
            rejection.append(RejectionReason.TOO_MANY_LOSSES.value)
        if (
            result.win_rate > 0
            and result.win_rate < c.reject_if_win_rate_below
        ):
            rejection.append(RejectionReason.LOW_WIN_RATE.value)

        if rejection:
            result.status = PromotionStatus.REJECTED.value
            result.rejection_reasons = rejection
            return result

        # 2) PENDING 체크 (데이터 부족으로 평가 불가)
        is_pending = False
        if result.num_trades < c.pending_if_trades_below:
            is_pending = True
            result.warnings.append(
                f"거래 수 부족 ({result.num_trades} < {c.pending_if_trades_below})"
            )
        if result.trading_days < c.pending_if_days_below:
            is_pending = True
            result.warnings.append(
                f"거래일 부족 ({result.trading_days} < {c.pending_if_days_below})"
            )

        if is_pending:
            result.status = PromotionStatus.PENDING.value
            return result

        # 3) 승급 기준 평가 (모두 만족해야 PROMOTED)
        passed = []
        failed = []

        # return
        if result.total_return_pct >= c.min_return_pct:
            passed.append(f"return >= {c.min_return_pct}%")
        else:
            failed.append(f"return {result.total_return_pct:.2f}% < {c.min_return_pct}%")

        # sharpe (과대평가 상한 포함)
        sharpe_clipped = min(result.sharpe_ratio, c.max_sharpe_sanity)
        if result.sharpe_ratio > c.max_sharpe_sanity:
            result.warnings.append(
                f"Sharpe {result.sharpe_ratio:.1f} > {c.max_sharpe_sanity} → 짧은 기간 과대평가 의심"
            )
        if sharpe_clipped >= c.min_sharpe:
            passed.append(f"sharpe >= {c.min_sharpe}")
        else:
            failed.append(f"sharpe {result.sharpe_ratio:.2f} < {c.min_sharpe}")

        # win rate
        if result.win_rate >= c.min_win_rate:
            passed.append(f"WR >= {c.min_win_rate * 100:.0f}%")
        else:
            failed.append(f"WR {result.win_rate * 100:.1f}% < {c.min_win_rate * 100:.0f}%")

        # MDD
        if result.max_drawdown_pct >= c.max_drawdown_pct:
            passed.append(f"MDD >= {c.max_drawdown_pct}%")
        else:
            failed.append(f"MDD {result.max_drawdown_pct:.2f}% < {c.max_drawdown_pct}%")

        # trades
        if result.num_trades >= c.min_trades:
            passed.append(f"trades >= {c.min_trades}")
        else:
            failed.append(f"trades {result.num_trades} < {c.min_trades}")

        # profit factor
        if result.profit_factor >= c.min_profit_factor:
            passed.append(f"PF >= {c.min_profit_factor}")
        else:
            failed.append(f"PF {result.profit_factor:.2f} < {c.min_profit_factor}")

        result.passed_criteria = passed
        result.failed_criteria = failed

        # 4) 상태 결정
        if len(failed) == 0:
            result.status = PromotionStatus.PROMOTED.value
        elif len(failed) <= 2:
            result.status = PromotionStatus.WATCHLIST.value
        else:
            result.status = PromotionStatus.WATCHLIST.value  # 부분 실패는 관찰
            # 2개 이상 실패하면 watchlist, 실패가 3개 이상이면 여전히 watchlist
            # REJECTED는 명시적 탈락 기준만 적용

        # 5) 종합 점수 0~100 (승급이면 높음)
        result.score = self._compute_score(result)

        return result

    def _compute_score(self, r: PromotionResult) -> float:
        """
        종합 점수 (0~100).
        - 수익률 (40%)
        - Sharpe (25%)
        - 승률 (15%)
        - MDD 안정성 (10%)
        - Profit Factor (10%)
        """
        c = self.criteria

        # 수익률 40점 (5% 이상 만점, 0%는 0점)
        return_score = min(max(r.total_return_pct / 10.0, 0), 1) * 40

        # Sharpe 25점 (clipped)
        sharpe_clipped = min(r.sharpe_ratio, c.max_sharpe_sanity)
        sharpe_score = min(max(sharpe_clipped / 5.0, 0), 1) * 25

        # 승률 15점
        wr_score = r.win_rate * 15 if r.win_rate > 0 else 0

        # MDD 10점 (0%가 만점, -15%가 0점)
        mdd_score = max(1 - abs(r.max_drawdown_pct) / 15.0, 0) * 10 if r.max_drawdown_pct < 0 else 10

        # PF 10점 (1.5=0, 3.0=만점)
        pf_score = min(max((r.profit_factor - 1.0) / 2.0, 0), 1) * 10 if r.profit_factor else 0

        return round(return_score + sharpe_score + wr_score + mdd_score + pf_score, 1)

    def evaluate_batch(self, rows: List[Dict]) -> List[PromotionResult]:
        return [self.evaluate(r) for r in rows]


# ============================================================
# Convenience loader
# ============================================================

def evaluate_leaderboard_file(
    leaderboard_js_path: Path,
    criteria: Optional[PromotionCriteria] = None,
    period: Optional[str] = None,
) -> List[PromotionResult]:
    """
    leaderboard_data.js 파일을 파싱해서 평가.

    leaderboard_data.js는 `window.LEADERBOARD_DATA = {...};` 형식.
    """
    leaderboard_js_path = Path(leaderboard_js_path)
    if not leaderboard_js_path.exists():
        raise FileNotFoundError(f"리더보드 데이터 없음: {leaderboard_js_path}")

    raw = leaderboard_js_path.read_text(encoding="utf-8")
    # JS의 window.LEADERBOARD_DATA = {...}; 부분에서 JSON 객체 추출
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("leaderboard_data.js 형식 오류")
    json_str = raw[start:end + 1]
    # 끝에 세미콜론이 있을 수 있음 — rfind는 { } 찾으므로 문제 없음
    data = json.loads(json_str)

    rows = []
    leaderboards = data.get("leaderboards", {})
    for period_key, period_rows in leaderboards.items():
        if period and period_key != period:
            continue
        rows.extend(period_rows)

    evaluator = PromotionEvaluator(criteria)
    return evaluator.evaluate_batch(rows)


__all__ = [
    "PromotionStatus",
    "RejectionReason",
    "PromotionCriteria",
    "PromotionResult",
    "PromotionEvaluator",
    "evaluate_leaderboard_file",
]
