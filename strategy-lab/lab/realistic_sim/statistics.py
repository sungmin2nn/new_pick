"""
통계적 검증 (Tier 3)
=======================
전략 성과의 신뢰도를 측정하는 통계 도구:

1. Walk-forward validation — 과적합 방지
   과거 N일로 평가, 이후 M일 테스트. 롤링.

2. Bootstrap p-value — 운 vs 실력
   수익률을 랜덤 재샘플링해 "관찰값이 운일 확률" 계산.

3. Benchmark alpha — 초과수익률
   KODEX 200 같은 벤치마크 대비 alpha.

외부 라이브러리 의존 없이 pure Python + numpy 사용.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class BootstrapResult:
    observed_mean: float
    p_value: float
    is_significant: bool   # p < 0.05
    confidence_interval_95: tuple = (0.0, 0.0)
    n_iterations: int = 0


@dataclass
class BenchmarkAlpha:
    strategy_return: float
    benchmark_return: float
    alpha: float   # strategy - benchmark
    beta: Optional[float] = None
    information_ratio: Optional[float] = None


@dataclass
class WalkForwardResult:
    windows: int
    avg_return: float
    avg_sharpe: float
    consistency: float   # 양수 수익 윈도우 비율
    overfitting_gap: float   # 전체 평균 - walk forward 평균


# ============================================================
# Bootstrap p-value
# ============================================================

def bootstrap_significance(
    returns: List[float],
    n_iterations: int = 1000,
    confidence: float = 0.95,
) -> BootstrapResult:
    """
    수익률 시리즈의 통계적 유의성 검정.

    Null hypothesis: 실제 평균 수익률은 0 (랜덤).
    Observed mean이 부트스트랩 분포에서 얼마나 극단인지 측정.

    Args:
        returns: 일별 수익률 % 리스트
        n_iterations: 재샘플링 반복 수
        confidence: 신뢰구간 (0.95 → 95%)
    """
    if not returns or len(returns) < 5:
        return BootstrapResult(
            observed_mean=0, p_value=1.0, is_significant=False,
            n_iterations=0,
        )

    n = len(returns)
    observed = sum(returns) / n

    # 부트스트랩 평균 분포 생성
    bootstrap_means = []
    for _ in range(n_iterations):
        sample = [random.choice(returns) for _ in range(n)]
        bootstrap_means.append(sum(sample) / n)

    bootstrap_means.sort()

    # P-value: 0 이하인 샘플 비율 (양수 수익률 가설 검정)
    if observed > 0:
        p_value = sum(1 for m in bootstrap_means if m <= 0) / n_iterations
    else:
        p_value = sum(1 for m in bootstrap_means if m >= 0) / n_iterations

    # 95% CI
    lower_idx = int((1 - confidence) / 2 * n_iterations)
    upper_idx = int((1 + confidence) / 2 * n_iterations) - 1
    ci = (
        bootstrap_means[max(0, lower_idx)],
        bootstrap_means[min(n_iterations - 1, upper_idx)],
    )

    return BootstrapResult(
        observed_mean=round(observed, 4),
        p_value=round(p_value, 4),
        is_significant=p_value < 0.05,
        confidence_interval_95=(round(ci[0], 4), round(ci[1], 4)),
        n_iterations=n_iterations,
    )


# ============================================================
# Walk-Forward validation
# ============================================================

def walk_forward_validation(
    daily_returns: List[float],
    train_window: int = 15,
    test_window: int = 5,
) -> WalkForwardResult:
    """
    롤링 윈도우로 과적합 측정.

    Args:
        daily_returns: 일별 수익률 % 리스트
        train_window: 학습 기간 (일)
        test_window: 테스트 기간 (일)

    Returns:
        전체 평균 vs walk-forward 평균 차이 (과적합 gap)
    """
    if len(daily_returns) < train_window + test_window:
        return WalkForwardResult(
            windows=0, avg_return=0, avg_sharpe=0,
            consistency=0, overfitting_gap=0,
        )

    test_returns = []
    window_returns = []

    for i in range(train_window, len(daily_returns) - test_window + 1):
        # train: daily_returns[i - train_window : i]
        test = daily_returns[i: i + test_window]
        test_mean = sum(test) / len(test) if test else 0
        window_returns.append(test_mean)
        test_returns.extend(test)

    if not window_returns:
        return WalkForwardResult(
            windows=0, avg_return=0, avg_sharpe=0,
            consistency=0, overfitting_gap=0,
        )

    avg_wf_return = sum(window_returns) / len(window_returns)
    overall_mean = sum(daily_returns) / len(daily_returns)

    # Sharpe (연환산)
    if len(test_returns) >= 2:
        mean = sum(test_returns) / len(test_returns)
        var = sum((r - mean) ** 2 for r in test_returns) / (len(test_returns) - 1)
        std = math.sqrt(var)
        sharpe = (mean / std * math.sqrt(250)) if std > 0 else 0
    else:
        sharpe = 0

    # consistency: 양수 윈도우 비율
    positive_windows = sum(1 for r in window_returns if r > 0)
    consistency = positive_windows / len(window_returns)

    return WalkForwardResult(
        windows=len(window_returns),
        avg_return=round(avg_wf_return, 4),
        avg_sharpe=round(sharpe, 4),
        consistency=round(consistency, 4),
        overfitting_gap=round(overall_mean - avg_wf_return, 4),
    )


# ============================================================
# Benchmark Alpha
# ============================================================

def compute_benchmark_alpha(
    strategy_returns: List[float],
    benchmark_returns: List[float],
) -> BenchmarkAlpha:
    """
    벤치마크 대비 초과수익률 (alpha) 및 베타 계산.

    Args:
        strategy_returns: 전략 일별 수익률 %
        benchmark_returns: 벤치마크 (예: KODEX 200) 일별 수익률 %
    """
    if not strategy_returns or not benchmark_returns:
        return BenchmarkAlpha(
            strategy_return=0, benchmark_return=0, alpha=0,
        )

    n = min(len(strategy_returns), len(benchmark_returns))
    sr = strategy_returns[:n]
    br = benchmark_returns[:n]

    strategy_mean = sum(sr) / n
    benchmark_mean = sum(br) / n
    alpha = strategy_mean - benchmark_mean

    # Beta: cov(s, b) / var(b)
    if n >= 2:
        cov = sum((sr[i] - strategy_mean) * (br[i] - benchmark_mean) for i in range(n)) / (n - 1)
        var_b = sum((b - benchmark_mean) ** 2 for b in br) / (n - 1)
        beta = cov / var_b if var_b > 0 else None

        # Information Ratio: alpha / tracking_error
        tracking_errors = [sr[i] - br[i] for i in range(n)]
        te_mean = sum(tracking_errors) / n
        te_var = sum((te - te_mean) ** 2 for te in tracking_errors) / (n - 1)
        te_std = math.sqrt(te_var) if te_var > 0 else 0
        ir = alpha / te_std if te_std > 0 else None
    else:
        beta = None
        ir = None

    return BenchmarkAlpha(
        strategy_return=round(strategy_mean, 4),
        benchmark_return=round(benchmark_mean, 4),
        alpha=round(alpha, 4),
        beta=round(beta, 4) if beta is not None else None,
        information_ratio=round(ir, 4) if ir is not None else None,
    )


# ============================================================
# KODEX 200 벤치마크 fetcher
# ============================================================

def get_kodex_200_returns(
    start_date: str,
    end_date: str,
) -> List[float]:
    """
    KODEX 200 ETF 일별 수익률 fetch.
    KRX OpenAPI의 코스피 지수를 사용 (ETF와 거의 동일).
    """
    try:
        from lab.common import get_krx
        from datetime import datetime, timedelta
    except ImportError:
        return []

    krx = get_krx()
    if not krx:
        return []

    returns = []
    current = datetime.strptime(start_date, "%Y%m%d")
    end = datetime.strptime(end_date, "%Y%m%d")

    while current <= end:
        if current.weekday() >= 5:
            current += timedelta(days=1)
            continue
        date_str = current.strftime("%Y%m%d")
        try:
            change = krx.get_kospi_change(date_str)
            if change is not None:
                returns.append(float(change))
        except Exception:
            pass
        current += timedelta(days=1)

    return returns


__all__ = [
    "BootstrapResult",
    "BenchmarkAlpha",
    "WalkForwardResult",
    "bootstrap_significance",
    "walk_forward_validation",
    "compute_benchmark_alpha",
    "get_kodex_200_returns",
]
