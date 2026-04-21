"""
확률적 일봉 시뮬 모델
========================
일봉 OHLC만으로 장중 가격 경로를 확률적으로 추정.

핵심 문제:
  일봉 시뮬에서 익절선(+5%)과 손절선(-3%) 둘 다 도달한 경우,
  어느 것이 먼저 왔는지 알 수 없음.
  현재 구조는 "손절 우선" 보수적 가정 → 50% 확률로 틀림.

해결 방법:
  일봉 O/H/L/C 네 값의 관계에서 추세를 추정 →
  "익절이 먼저 왔을 확률(p_high_first)"을 계산 →
  확률 가중 기대 수익률 반환.

근거:
  - Garman-Klass 변동성 추정기 관련 연구
  - Parkinson 변동성
  - "Close position vs open position" 상관성
  - 상승 추세 강할수록 high가 먼저 왔을 확률 ↑

공식 (추세 기반 휴리스틱):
  trend = (close - open) / open
  range_ratio = (high - low) / open

  p_high_first = 0.5 + k * (trend / range_ratio)
    where k = 0.8 (경험적 계수)

  → clip to [0.05, 0.95] to avoid over-confidence

사용:
    from lab.realistic_sim.probability_model import probabilistic_exit

    result = probabilistic_exit(
        open_p=10000, high_p=10550, low_p=9670, close_p=10100,
        profit_pct=5.0, loss_pct=-3.0
    )
    # result.expected_return_pct, result.confidence
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ProbabilisticExitResult:
    """확률 기반 exit 결정 결과."""
    exit_type: str   # 'profit' | 'loss' | 'close' | 'probabilistic'
    gross_return_pct: float
    confidence: float   # 0~1, 1 = 확실 / 0 = 50/50
    profit_probability: Optional[float] = None
    loss_probability: Optional[float] = None
    scenario: str = ""  # "high_only" | "low_only" | "neither" | "both_trend_up" | "both_trend_down" | "both_neutral"


def estimate_high_first_probability(
    open_p: float,
    high_p: float,
    low_p: float,
    close_p: float,
    k_trend: float = 0.8,
) -> float:
    """
    일봉 O/H/L/C만으로 "high가 low보다 먼저 도달했을 확률" 추정.

    원리:
    - close > open (상승): high가 먼저일 가능성 ↑
    - close < open (하락): low가 먼저일 가능성 ↑
    - close ≈ open (횡보): 50/50
    - 변동폭(range) 대비 추세 강도가 클수록 확률이 한쪽으로 치우침

    Returns:
        p_high_first ∈ [0.05, 0.95]
    """
    if open_p <= 0 or high_p == low_p:
        return 0.5

    trend = (close_p - open_p) / open_p
    range_ratio = (high_p - low_p) / open_p

    if range_ratio < 1e-6:
        return 0.5

    # 상대 추세 강도
    relative_trend = trend / range_ratio

    # 확률 공식
    p = 0.5 + k_trend * relative_trend

    # clip [0.05, 0.95] — 완전 확실은 피함
    return max(0.05, min(0.95, p))


def probabilistic_exit(
    open_p: float,
    high_p: float,
    low_p: float,
    close_p: float,
    profit_pct: float = 5.0,
    loss_pct: float = -3.0,
    k_trend: float = 0.8,
) -> ProbabilisticExitResult:
    """
    일봉 OHLC에서 확률적 exit 판정.

    시나리오:
    1. high만 익절선 도달 → 익절 (확률 100%)
    2. low만 손절선 도달 → 손절 (확률 100%)
    3. 둘 다 미도달 → 종가 청산 (확률 100%)
    4. 둘 다 도달 → 확률 가중 기대값
    """
    if open_p <= 0:
        return ProbabilisticExitResult(
            exit_type="close",
            gross_return_pct=0.0,
            confidence=1.0,
            scenario="invalid",
        )

    profit_px = open_p * (1 + profit_pct / 100)
    loss_px = open_p * (1 + loss_pct / 100)

    high_hit = high_p >= profit_px
    low_hit = low_p <= loss_px

    # 시나리오 1: high만
    if high_hit and not low_hit:
        return ProbabilisticExitResult(
            exit_type="profit",
            gross_return_pct=profit_pct,
            confidence=1.0,
            profit_probability=1.0,
            loss_probability=0.0,
            scenario="high_only",
        )

    # 시나리오 2: low만
    if low_hit and not high_hit:
        return ProbabilisticExitResult(
            exit_type="loss",
            gross_return_pct=loss_pct,
            confidence=1.0,
            profit_probability=0.0,
            loss_probability=1.0,
            scenario="low_only",
        )

    # 시나리오 3: 둘 다 미도달 → 종가
    if not high_hit and not low_hit:
        close_return = (close_p - open_p) / open_p * 100
        return ProbabilisticExitResult(
            exit_type="close",
            gross_return_pct=close_return,
            confidence=1.0,
            scenario="neither",
        )

    # 시나리오 4: 둘 다 도달 → 확률 가중
    p_high_first = estimate_high_first_probability(
        open_p, high_p, low_p, close_p, k_trend=k_trend
    )

    expected_return = (
        p_high_first * profit_pct + (1 - p_high_first) * loss_pct
    )

    # confidence: 0.5에서 멀수록 높음
    confidence = abs(p_high_first - 0.5) * 2

    # 시나리오 분류
    if p_high_first > 0.7:
        scenario = "both_trend_up"
    elif p_high_first < 0.3:
        scenario = "both_trend_down"
    else:
        scenario = "both_neutral"

    return ProbabilisticExitResult(
        exit_type="probabilistic",
        gross_return_pct=round(expected_return, 4),
        confidence=round(confidence, 4),
        profit_probability=round(p_high_first, 4),
        loss_probability=round(1 - p_high_first, 4),
        scenario=scenario,
    )


__all__ = [
    "ProbabilisticExitResult",
    "estimate_high_first_probability",
    "probabilistic_exit",
]
