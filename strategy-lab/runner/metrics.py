"""
Performance Metrics
====================
백테스트 결과로부터 표준 성과 메트릭을 계산.

순수 함수 모듈 (I/O 없음).
입력: BacktestResult 또는 daily returns 시리즈
출력: dict of metrics

지원 메트릭:
- total_return_pct, cagr
- sharpe_ratio, sortino_ratio, calmar_ratio
- max_drawdown_pct, max_dd_duration_days
- win_rate, profit_factor
- avg_win_pct, avg_loss_pct, win_loss_ratio
- max_consecutive_wins, max_consecutive_losses
- volatility_pct (annualized)
- recovery_factor
- num_trades, avg_holding_days
- best_day_pct, worst_day_pct

참고:
- 무위험 수익률: 한국 3년 국채 ~3.5% (2026년 기준)
- 거래일 수: 한국 연 250일
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import List, Optional, Dict


# ============================================================
# Constants
# ============================================================

RISK_FREE_RATE = 0.035   # 한국 국채 3년 ~3.5%
TRADING_DAYS_PER_YEAR = 250


# ============================================================
# Result data class
# ============================================================

@dataclass
class MetricsResult:
    """전체 성과 메트릭."""

    # 수익
    total_return_pct: float = 0.0
    cagr_pct: float = 0.0           # 연환산 수익률

    # 위험조정수익률
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0       # 하방 변동성 기준
    calmar_ratio: float = 0.0        # 수익률 / MDD

    # 변동성
    volatility_pct: float = 0.0      # 연환산 표준편차
    downside_volatility_pct: float = 0.0

    # 드로다운
    max_drawdown_pct: float = 0.0
    max_dd_duration_days: int = 0

    # 거래 통계
    num_trades: int = 0
    win_rate: float = 0.0            # 0~1
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    win_loss_ratio: float = 0.0      # avg_win / |avg_loss|
    profit_factor: float = 0.0       # 총 이익 / |총 손실|

    # 일관성
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0

    # 일별 극단값
    best_day_pct: float = 0.0
    worst_day_pct: float = 0.0

    # 회복
    recovery_factor: float = 0.0     # total_return / |max_dd|

    # 메타
    trading_days: int = 0
    avg_trades_per_day: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================
# Core calculations
# ============================================================

def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b != 0 else default


def _stddev(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(var)


def calculate_max_drawdown(equity_curve: List[float]) -> tuple:
    """
    최대 드로다운 계산.

    Returns:
        (max_dd_pct, max_dd_duration_days)
    """
    if not equity_curve:
        return (0.0, 0)

    peak = equity_curve[0]
    peak_idx = 0
    max_dd = 0.0
    max_duration = 0
    current_duration = 0

    for i, v in enumerate(equity_curve):
        if v > peak:
            peak = v
            peak_idx = i
            current_duration = 0
        else:
            current_duration = i - peak_idx
            dd = (v - peak) / peak * 100 if peak > 0 else 0
            if dd < max_dd:
                max_dd = dd
            if current_duration > max_duration:
                max_duration = current_duration

    return (round(max_dd, 2), max_duration)


def calculate_sharpe(daily_returns: List[float], rf_annual: float = RISK_FREE_RATE) -> float:
    """일별 수익률 시리즈에서 연환산 샤프."""
    if len(daily_returns) < 2:
        return 0.0
    rf_daily = rf_annual / TRADING_DAYS_PER_YEAR
    excess_returns = [r / 100 - rf_daily for r in daily_returns]
    mean = sum(excess_returns) / len(excess_returns)
    std = _stddev(excess_returns)
    if std == 0:
        return 0.0
    daily_sharpe = mean / std
    return round(daily_sharpe * math.sqrt(TRADING_DAYS_PER_YEAR), 2)


def calculate_sortino(daily_returns: List[float], rf_annual: float = RISK_FREE_RATE) -> float:
    """하방 변동성 기준 Sortino ratio."""
    if len(daily_returns) < 2:
        return 0.0
    rf_daily = rf_annual / TRADING_DAYS_PER_YEAR
    excess_returns = [r / 100 - rf_daily for r in daily_returns]
    mean = sum(excess_returns) / len(excess_returns)

    downside = [r for r in excess_returns if r < 0]
    if not downside or len(downside) < 2:
        return 0.0
    downside_std = _stddev(downside)
    if downside_std == 0:
        return 0.0
    return round((mean / downside_std) * math.sqrt(TRADING_DAYS_PER_YEAR), 2)


def calculate_consecutive_streaks(daily_returns: List[float]) -> tuple:
    """최대 연속 승/연속 패."""
    if not daily_returns:
        return (0, 0)
    max_wins = 0
    max_losses = 0
    cur_wins = 0
    cur_losses = 0
    for r in daily_returns:
        if r > 0:
            cur_wins += 1
            cur_losses = 0
            max_wins = max(max_wins, cur_wins)
        elif r < 0:
            cur_losses += 1
            cur_wins = 0
            max_losses = max(max_losses, cur_losses)
        else:
            cur_wins = 0
            cur_losses = 0
    return (max_wins, max_losses)


# ============================================================
# Main entry — from BacktestResult
# ============================================================

def calculate_metrics(backtest_result) -> MetricsResult:
    """
    BacktestResult 객체로부터 모든 메트릭 계산.

    Args:
        backtest_result: BacktestResult 인스턴스 (또는 dict)
    """
    # dict이든 dataclass든 호환
    if isinstance(backtest_result, dict):
        daily_history = backtest_result.get("daily_history", [])
        initial = backtest_result.get("initial_capital", 0)
        final = backtest_result.get("final_capital", 0)
        total_trades = backtest_result.get("total_trades", 0)
        total_wins = backtest_result.get("total_wins", 0)
        total_losses = backtest_result.get("total_losses", 0)
        trading_days = backtest_result.get("trading_days", 0)
    else:
        daily_history = backtest_result.daily_history
        initial = backtest_result.initial_capital
        final = backtest_result.final_capital
        total_trades = backtest_result.total_trades
        total_wins = backtest_result.total_wins
        total_losses = backtest_result.total_losses
        trading_days = backtest_result.trading_days

    metrics = MetricsResult(trading_days=trading_days, num_trades=total_trades)

    if not daily_history or initial <= 0:
        return metrics

    # 일별 수익률 시리즈 (% 단위)
    daily_returns = []
    equity_curve = [initial]
    for dh in daily_history:
        if isinstance(dh, dict):
            ret_pct = dh.get("daily_return_pct", 0.0)
            cap = dh.get("capital_after", initial)
        else:
            ret_pct = dh.daily_return_pct
            cap = dh.capital_after
        daily_returns.append(float(ret_pct or 0))
        equity_curve.append(float(cap or initial))

    # 총 수익률
    metrics.total_return_pct = round((final - initial) / initial * 100, 2)

    # CAGR
    if trading_days > 0 and initial > 0 and final > 0:
        years = trading_days / TRADING_DAYS_PER_YEAR
        if years > 0:
            cagr = (final / initial) ** (1 / years) - 1
            metrics.cagr_pct = round(cagr * 100, 2)

    # 변동성 (연환산)
    daily_vol = _stddev(daily_returns)
    metrics.volatility_pct = round(daily_vol * math.sqrt(TRADING_DAYS_PER_YEAR), 2)

    # 하방 변동성
    downside = [r for r in daily_returns if r < 0]
    if len(downside) >= 2:
        ds_vol = _stddev(downside)
        metrics.downside_volatility_pct = round(ds_vol * math.sqrt(TRADING_DAYS_PER_YEAR), 2)

    # Sharpe / Sortino
    metrics.sharpe_ratio = calculate_sharpe(daily_returns)
    metrics.sortino_ratio = calculate_sortino(daily_returns)

    # MDD
    mdd_pct, mdd_duration = calculate_max_drawdown(equity_curve)
    metrics.max_drawdown_pct = mdd_pct
    metrics.max_dd_duration_days = mdd_duration

    # Calmar (CAGR / |MDD|)
    if mdd_pct < 0:
        metrics.calmar_ratio = round(metrics.cagr_pct / abs(mdd_pct), 2)

    # Recovery factor
    if mdd_pct < 0:
        metrics.recovery_factor = round(metrics.total_return_pct / abs(mdd_pct), 2)

    # 거래 단위 통계 — trade_details에서 추출
    all_trades = []
    for dh in daily_history:
        details = dh.get("trade_details", []) if isinstance(dh, dict) else dh.trade_details
        for t in details:
            t_pct = t.get("return_pct", 0) if isinstance(t, dict) else t["return_pct"]
            all_trades.append(float(t_pct))

    if all_trades:
        wins = [t for t in all_trades if t > 0]
        losses = [t for t in all_trades if t < 0]
        metrics.win_rate = round(len(wins) / len(all_trades), 4)
        metrics.avg_win_pct = round(sum(wins) / len(wins), 2) if wins else 0.0
        metrics.avg_loss_pct = round(sum(losses) / len(losses), 2) if losses else 0.0
        if metrics.avg_loss_pct < 0:
            metrics.win_loss_ratio = round(metrics.avg_win_pct / abs(metrics.avg_loss_pct), 2)
        # Profit factor
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses)) if losses else 0
        if gross_loss > 0:
            metrics.profit_factor = round(gross_profit / gross_loss, 2)
        elif gross_profit > 0:
            metrics.profit_factor = float("inf")
    else:
        # trade_details 없으면 daily 합계로 근사
        if total_trades > 0:
            metrics.win_rate = round(total_wins / total_trades, 4)

    # 연속 승/패 (일별)
    max_w, max_l = calculate_consecutive_streaks(daily_returns)
    metrics.max_consecutive_wins = max_w
    metrics.max_consecutive_losses = max_l

    # 일별 극단값
    if daily_returns:
        metrics.best_day_pct = round(max(daily_returns), 2)
        metrics.worst_day_pct = round(min(daily_returns), 2)

    # 평균 거래
    if trading_days > 0:
        metrics.avg_trades_per_day = round(total_trades / trading_days, 2)

    return metrics


# ============================================================
# Convenience: from list of daily returns
# ============================================================

def calculate_metrics_from_returns(
    daily_returns_pct: List[float],
    initial_capital: float = 10_000_000,
) -> MetricsResult:
    """
    일별 수익률 리스트(%)에서 메트릭 계산.
    트레이드 단위 통계는 제외.
    """
    if not daily_returns_pct:
        return MetricsResult()

    # equity curve 재구성
    capital = initial_capital
    equity_curve = [capital]
    for r in daily_returns_pct:
        capital = capital * (1 + r / 100)
        equity_curve.append(capital)

    fake_history = [
        {
            "daily_return_pct": r,
            "capital_after": equity_curve[i + 1],
            "trades": 0,
            "wins": 0,
            "trade_details": [],
        }
        for i, r in enumerate(daily_returns_pct)
    ]

    fake_result = {
        "daily_history": fake_history,
        "initial_capital": initial_capital,
        "final_capital": equity_curve[-1],
        "total_trades": 0,
        "total_wins": 0,
        "total_losses": 0,
        "trading_days": len(daily_returns_pct),
    }
    return calculate_metrics(fake_result)


__all__ = [
    "MetricsResult",
    "calculate_metrics",
    "calculate_metrics_from_returns",
    "calculate_max_drawdown",
    "calculate_sharpe",
    "calculate_sortino",
    "calculate_consecutive_streaks",
    "RISK_FREE_RATE",
    "TRADING_DAYS_PER_YEAR",
]
