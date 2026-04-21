"""
Probabilistic Daily Backtest (Tier 2)
========================================
기존 일봉 시뮬에 확률적 exit 모델 적용.

차이점:
- 기존 (simulate_day): "손절 우선" 보수적 가정
- 신규 (probabilistic): 추세 기반 확률 가중 기대값

장점:
- 장기 기간(1m/3m/1y) 가능 (분봉 6일 한계 없음)
- 기존 데이터 인프라 그대로 사용
- 승률/수익률 현실화

단점:
- 실측이 아닌 기대값 (confidence 지표 참고)
- 확률 모델 가정에 의존

사용:
    from runner.probabilistic_backtest import ProbabilisticBacktest
    bt = ProbabilisticBacktest(strategy)
    result = bt.run("20260310", "20260410")
"""

from __future__ import annotations

import contextlib
import io
import logging
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from lab import BaseStrategy, assert_ntb_available
from lab.common import get_krx
from lab.realistic_sim.probability_model import probabilistic_exit
from lab.realistic_sim.transaction_costs import (
    calculate_net_return,
    SLIPPAGE_MARKET_OPEN,
    SLIPPAGE_MARKET_CLOSE,
)
from runner.backtest_wrapper import (
    INITIAL_CAPITAL,
    PROFIT_TARGET,
    LOSS_TARGET,
    DEFAULT_TOP_N,
    get_trading_days,
)

logger = logging.getLogger(__name__)


@dataclass
class ProbabilisticTrade:
    code: str
    name: str
    date: str
    entry_price: int
    exit_price: int
    exit_type: str   # profit | loss | close | probabilistic
    scenario: str
    confidence: float
    gross_return_pct: float
    net_return_pct: float
    cost_pct: float
    profit_probability: Optional[float] = None
    selection_score: float = 0.0
    selection_rank: int = 0


@dataclass
class ProbabilisticDayResult:
    date: str
    candidates: int = 0
    trades: int = 0
    wins: int = 0
    losses: int = 0
    avg_gross_return_pct: float = 0.0
    avg_net_return_pct: float = 0.0
    avg_confidence: float = 0.0
    total_return_amount: int = 0
    capital_after: int = 0
    trade_details: List[ProbabilisticTrade] = field(default_factory=list)


@dataclass
class ProbabilisticBacktestResult:
    strategy_id: str
    strategy_name: str
    start_date: str
    end_date: str
    trading_days: int

    initial_capital: int = INITIAL_CAPITAL
    final_capital: int = INITIAL_CAPITAL
    total_trades: int = 0
    total_wins: int = 0
    total_losses: int = 0

    gross_return_pct: float = 0.0
    net_return_pct: float = 0.0
    total_cost_pct: float = 0.0
    avg_confidence: float = 0.0

    scenario_counts: Dict[str, int] = field(default_factory=dict)
    daily_history: List[ProbabilisticDayResult] = field(default_factory=list)

    duration_seconds: float = 0.0
    has_errors: bool = False
    error_messages: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> str:
        wr = (self.total_wins / max(self.total_trades, 1)) * 100
        return (
            f"[{self.strategy_id}] PROBABILISTIC {self.start_date}~{self.end_date} ({self.trading_days}d)\n"
            f"  명목 수익률: {self.gross_return_pct:+.2f}%\n"
            f"  순 수익률: {self.net_return_pct:+.2f}%\n"
            f"  평균 confidence: {self.avg_confidence:.2f}\n"
            f"  거래: {self.total_wins}/{self.total_trades} (승률 {wr:.1f}%)\n"
            f"  시나리오: {self.scenario_counts}\n"
            f"  소요: {self.duration_seconds:.1f}s"
        )


class ProbabilisticBacktest:
    """확률적 일봉 시뮬 엔진."""

    def __init__(
        self,
        strategy: BaseStrategy,
        initial_capital: int = INITIAL_CAPITAL,
        top_n: int = DEFAULT_TOP_N,
        profit_pct: float = PROFIT_TARGET,
        loss_pct: float = LOSS_TARGET,
        k_trend: float = 0.8,
    ):
        assert_ntb_available()
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.top_n = top_n
        self.profit_pct = profit_pct
        self.loss_pct = loss_pct
        self.k_trend = k_trend

    def _select_quietly(self, date: str) -> list:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                return self.strategy.select_stocks(date=date, top_n=self.top_n)
            except Exception:
                return []

    def _process_day(
        self,
        date: str,
        current_capital: int,
    ) -> ProbabilisticDayResult:
        result = ProbabilisticDayResult(date=date)
        candidates = self._select_quietly(date)
        result.candidates = len(candidates)

        if not candidates:
            return result

        krx = get_krx()
        if not krx:
            return result

        # 당일 OHLCV fetch
        market_data = {}
        for market in ("KOSPI", "KOSDAQ"):
            try:
                df = krx.get_stock_ohlcv(date, market=market)
                if df is not None and not df.empty:
                    for code in df.index:
                        market_data[code] = {
                            "row": df.loc[code],
                            "market": market,
                        }
            except Exception:
                continue

        capital_per_trade = current_capital / max(len(candidates), 1)
        total_gross = 0.0
        total_net = 0.0
        total_confidence = 0.0
        total_amount = 0

        for cand in candidates:
            code = cand.code if hasattr(cand, "code") else cand["code"]
            name = cand.name if hasattr(cand, "name") else cand.get("name", "")
            rank = cand.rank if hasattr(cand, "rank") else 0
            score = cand.score if hasattr(cand, "score") else 0

            info = market_data.get(code)
            if info is None:
                continue

            row = info["row"]
            market = info["market"]

            try:
                open_p = int(row.get("시가", 0) or 0)
                high_p = int(row.get("고가", 0) or 0)
                low_p = int(row.get("저가", 0) or 0)
                close_p = int(row.get("종가", 0) or 0)
                if open_p == 0:
                    continue

                # 확률적 exit 계산
                exit_result = probabilistic_exit(
                    open_p=open_p,
                    high_p=high_p,
                    low_p=low_p,
                    close_p=close_p,
                    profit_pct=self.profit_pct,
                    loss_pct=self.loss_pct,
                    k_trend=self.k_trend,
                )

                # 진입/청산 가격 결정
                entry_price = open_p
                if exit_result.exit_type == "profit":
                    exit_price = int(open_p * (1 + self.profit_pct / 100))
                elif exit_result.exit_type == "loss":
                    exit_price = int(open_p * (1 + self.loss_pct / 100))
                elif exit_result.exit_type == "close":
                    exit_price = close_p
                else:  # probabilistic — 기대가격은 확률 가중
                    p_high = exit_result.profit_probability or 0.5
                    exit_price = int(
                        p_high * (open_p * (1 + self.profit_pct / 100))
                        + (1 - p_high) * (open_p * (1 + self.loss_pct / 100))
                    )

                # 거래비용
                cost = calculate_net_return(
                    entry_price=entry_price,
                    exit_price=exit_price,
                    market=market,
                    entry_slippage_pct=SLIPPAGE_MARKET_OPEN,
                    exit_slippage_pct=(
                        SLIPPAGE_MARKET_CLOSE
                        if exit_result.exit_type == "close"
                        else 0.05
                    ),
                )

                trade = ProbabilisticTrade(
                    code=code,
                    name=name,
                    date=date,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    exit_type=exit_result.exit_type,
                    scenario=exit_result.scenario,
                    confidence=exit_result.confidence,
                    gross_return_pct=exit_result.gross_return_pct,
                    net_return_pct=cost.net_return_pct,
                    cost_pct=cost.total_cost_pct,
                    profit_probability=exit_result.profit_probability,
                    selection_score=float(score or 0),
                    selection_rank=int(rank or 0),
                )
                result.trade_details.append(trade)
                result.trades += 1

                if trade.net_return_pct > 0:
                    result.wins += 1
                else:
                    result.losses += 1

                total_gross += trade.gross_return_pct
                total_net += trade.net_return_pct
                total_confidence += trade.confidence

                qty = int(capital_per_trade / entry_price)
                total_amount += int(
                    (exit_price - entry_price) * qty
                    - entry_price * qty * 0.00015 * 2   # 수수료 매수/매도
                    - exit_price * qty * 0.0018          # 거래세
                )

            except Exception as e:
                logger.debug(f"{code} 시뮬 실패: {e}")
                continue

        if result.trades > 0:
            result.avg_gross_return_pct = round(total_gross / result.trades, 4)
            result.avg_net_return_pct = round(total_net / result.trades, 4)
            result.avg_confidence = round(total_confidence / result.trades, 4)

        result.total_return_amount = total_amount
        return result

    def run(
        self,
        start_date: str,
        end_date: str,
        trading_days: Optional[List[str]] = None,
        verbose: bool = False,
    ) -> ProbabilisticBacktestResult:
        start_time = time.time()
        if trading_days is None:
            trading_days = get_trading_days(start_date, end_date)

        result = ProbabilisticBacktestResult(
            strategy_id=self.strategy.STRATEGY_ID,
            strategy_name=self.strategy.STRATEGY_NAME,
            start_date=start_date,
            end_date=end_date,
            trading_days=len(trading_days),
            initial_capital=self.initial_capital,
            final_capital=self.initial_capital,
        )

        current_capital = self.initial_capital
        scenario_counts: Dict[str, int] = {}
        total_confidence = 0.0

        for date in trading_days:
            try:
                day_result = self._process_day(date, current_capital)
            except Exception as e:
                result.has_errors = True
                result.error_messages.append(f"{date}: {e}")
                continue

            current_capital += day_result.total_return_amount
            day_result.capital_after = current_capital

            result.daily_history.append(day_result)
            result.total_trades += day_result.trades
            result.total_wins += day_result.wins
            result.total_losses += day_result.losses

            for trade in day_result.trade_details:
                scenario_counts[trade.scenario] = scenario_counts.get(trade.scenario, 0) + 1
                total_confidence += trade.confidence

        result.final_capital = current_capital
        result.gross_return_pct = round(
            (current_capital - self.initial_capital) / self.initial_capital * 100, 4
        )
        result.net_return_pct = result.gross_return_pct  # 이미 비용 반영
        if result.total_trades > 0:
            result.avg_confidence = round(total_confidence / result.total_trades, 4)
        result.scenario_counts = scenario_counts
        result.duration_seconds = round(time.time() - start_time, 2)

        if verbose:
            print(result.summary())

        return result


__all__ = [
    "ProbabilisticBacktest",
    "ProbabilisticBacktestResult",
    "ProbabilisticDayResult",
    "ProbabilisticTrade",
]
