"""
Backtest Wrapper
================
news-trading-bot의 simulate_day 로직을 재사용하여
임의의 BaseStrategy 인스턴스를 백테스트하는 모듈.

특징:
- 단일 전략 + 임의 기간 백테스트
- ThreadPoolExecutor로 일자별 병렬 처리 (KRX 캐시 활용)
- 진행률 콜백 지원
- 일자별 실패가 전체 실행 중단시키지 않음
- 결과는 BacktestResult dataclass로 반환

사용:
    from runner.backtest_wrapper import SingleStrategyBacktest
    from strategies.volatility_breakout_lw import VolatilityBreakoutLW

    bt = SingleStrategyBacktest(VolatilityBreakoutLW())
    result = bt.run("20260323", "20260410", parallel_workers=4)
    print(result.summary())
"""

from __future__ import annotations

import logging
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional

# news-trading-bot 경로 (lab/__init__이 처리)
from lab import BaseStrategy, NTB_AVAILABLE, assert_ntb_available
from lab.common import get_krx

logger = logging.getLogger(__name__)


# ============================================================
# Configuration (news-trading-bot/scripts/run_backtest.py 동일)
# ============================================================

INITIAL_CAPITAL = 10_000_000
PROFIT_TARGET = 5.0    # +5%
LOSS_TARGET = -3.0     # -3%
DEFAULT_TOP_N = 5
DEFAULT_WORKERS = 4    # KRX rate limit (200ms) 고려


# ============================================================
# Data classes
# ============================================================

@dataclass
class DayResult:
    """단일 일자 시뮬 결과."""
    date: str
    candidates: int = 0
    trades: int = 0
    wins: int = 0
    losses: int = 0
    daily_return_pct: float = 0.0
    daily_return_amount: int = 0
    capital_after: int = 0
    selection_failed: bool = False
    error: Optional[str] = None
    trade_details: List[Dict] = field(default_factory=list)


@dataclass
class BacktestResult:
    """전체 백테스트 결과."""
    strategy_id: str
    strategy_name: str
    start_date: str
    end_date: str
    trading_days: int
    initial_capital: int
    final_capital: int
    daily_history: List[DayResult] = field(default_factory=list)

    # 집계
    total_trades: int = 0
    total_wins: int = 0
    total_losses: int = 0
    total_return_pct: float = 0.0
    total_return_amount: int = 0

    # 실행 정보
    duration_seconds: float = 0.0
    failed_days: int = 0
    parallel_workers: int = 1

    # 에러
    has_errors: bool = False
    error_messages: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["daily_history"] = [asdict(dh) for dh in self.daily_history]
        return d

    def summary(self) -> str:
        win_rate = (self.total_wins / max(self.total_trades, 1)) * 100
        return (
            f"[{self.strategy_id}] {self.start_date}~{self.end_date} ({self.trading_days}일)\n"
            f"  수익률: {self.total_return_pct:+.2f}% ({self.total_return_amount:+,}원)\n"
            f"  매매: {self.total_wins}/{self.total_trades} (승률 {win_rate:.1f}%)\n"
            f"  잔고: {self.initial_capital:,} → {self.final_capital:,}\n"
            f"  소요: {self.duration_seconds:.1f}s (workers={self.parallel_workers}, "
            f"실패일 {self.failed_days})"
        )


# ============================================================
# Day simulator (news-trading-bot의 simulate_day 재현)
# ============================================================

def simulate_day(
    date: str,
    candidates: List,
    krx,
    capital_per_run: int = INITIAL_CAPITAL,
    profit_target: Optional[float] = None,
    loss_target: Optional[float] = None,
) -> Dict:
    """
    일봉 기반 매매 시뮬:
    시초가 매수 → 익절(+5%)/손절(-3%) 판정 → 종가 청산.

    news-trading-bot/scripts/run_backtest.py의 simulate_day와 동일한 로직.

    Args:
        profit_target: None이면 글로벌 PROFIT_TARGET 사용 (variant override용)
        loss_target: None이면 글로벌 LOSS_TARGET 사용 (variant override용)
    """
    _profit = PROFIT_TARGET if profit_target is None else profit_target
    _loss = LOSS_TARGET if loss_target is None else loss_target
    if not candidates:
        return {
            "trades": [],
            "total_return": 0.0,
            "wins": 0,
            "total_trades": 0,
            "total_return_amount": 0,
        }

    # 그날 OHLCV (KRX 캐시 hit 시 빠름)
    market_data = {}
    for market in ("KOSPI", "KOSDAQ"):
        try:
            df = krx.get_stock_ohlcv(date, market=market)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        for code in df.index:
            market_data[code] = df.loc[code]

    capital_per_trade = capital_per_run / max(len(candidates), 1)
    trades = []

    for cand in candidates:
        code = cand.code if hasattr(cand, "code") else cand["code"]
        name = cand.name if hasattr(cand, "name") else cand["name"]
        row = market_data.get(code)

        # 선정 정보 (백테스트 후에도 보존)
        selection = {
            "rank": int(cand.rank if hasattr(cand, "rank") else 0),
            "score": float(cand.score if hasattr(cand, "score") else 0),
            "score_detail": dict(cand.score_detail) if hasattr(cand, "score_detail") and cand.score_detail else {},
        }

        if row is None:
            # 선정됐지만 시장 데이터 없음 — 집계 제외 (기존 동작 유지)
            continue
        try:
            open_p = int(row.get("시가", 0) or 0)
            high_p = int(row.get("고가", 0) or 0)
            low_p = int(row.get("저가", 0) or 0)
            close_p = int(row.get("종가", 0) or 0)
            if open_p == 0:
                continue

            profit_px = open_p * (1 + _profit / 100)
            loss_px = open_p * (1 + _loss / 100)

            # 손절 우선 (보수적)
            if low_p <= loss_px:
                exit_px = int(loss_px)
                exit_type = "loss"
            elif high_p >= profit_px:
                exit_px = int(profit_px)
                exit_type = "profit"
            else:
                exit_px = close_p
                exit_type = "close"

            return_pct = (exit_px - open_p) / open_p * 100
            qty = int(capital_per_trade / open_p)
            return_amt = (exit_px - open_p) * qty

            trades.append({
                "code": code,
                "name": name,
                "entry_price": open_p,
                "exit_price": exit_px,
                "exit_type": exit_type,
                "return_pct": round(return_pct, 2),
                "return_amount": return_amt,
                "qty": qty,
                # 일봉 레퍼런스 (검증용)
                "high": high_p,
                "low": low_p,
                "close": close_p,
                # 선정 단계 정보
                "selection": selection,
            })
        except Exception as e:
            logger.debug(f"{code} 시뮬 실패: {e}")
            continue

    if not trades:
        return {
            "trades": [],
            "total_return": 0.0,
            "wins": 0,
            "total_trades": 0,
            "total_return_amount": 0,
        }

    avg_return = sum(t["return_pct"] for t in trades) / len(trades)
    wins = sum(1 for t in trades if t["return_pct"] > 0)
    total_return_amt = sum(t["return_amount"] for t in trades)

    return {
        "trades": trades,
        "total_return": round(avg_return, 2),
        "wins": wins,
        "total_trades": len(trades),
        "total_return_amount": total_return_amt,
    }


# ============================================================
# Trading day extractor
# ============================================================

def get_trading_days(start: str, end: str) -> List[str]:
    """KRX 지수 데이터로 실제 거래일 추출."""
    krx = get_krx()
    if not krx:
        return []
    days = []
    cur = datetime.strptime(start, "%Y%m%d")
    end_dt = datetime.strptime(end, "%Y%m%d")
    while cur <= end_dt:
        if cur.weekday() < 5:  # 월~금
            d = cur.strftime("%Y%m%d")
            try:
                idx = krx.get_index_ohlcv(d, "KOSPI")
                if idx is not None and not idx.empty:
                    days.append(d)
            except Exception:
                pass
        cur += timedelta(days=1)
    return days


# ============================================================
# Single Strategy Backtest
# ============================================================

class SingleStrategyBacktest:
    """단일 전략을 임의 기간으로 백테스트."""

    def __init__(
        self,
        strategy: BaseStrategy,
        initial_capital: int = INITIAL_CAPITAL,
        top_n: int = DEFAULT_TOP_N,
        suppress_strategy_print: bool = True,
        profit_target: Optional[float] = None,
        loss_target: Optional[float] = None,
    ):
        assert_ntb_available()
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.top_n = top_n
        self.suppress_strategy_print = suppress_strategy_print
        self.profit_target = profit_target
        self.loss_target = loss_target

    def _select_quietly(self, date: str) -> List:
        """전략의 print() 출력을 숨기고 종목 선정."""
        if not self.suppress_strategy_print:
            return self.strategy.select_stocks(date=date, top_n=self.top_n)

        # stdout 임시 캡처
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                cands = self.strategy.select_stocks(date=date, top_n=self.top_n)
            except Exception as e:
                raise
        return cands

    def _process_one_day(self, date: str) -> DayResult:
        """단일 일자 처리 (병렬 실행 단위)."""
        krx = get_krx()
        try:
            cands = self._select_quietly(date)
        except Exception as e:
            return DayResult(
                date=date,
                selection_failed=True,
                error=f"select_stocks 실패: {e}",
            )

        try:
            sim = simulate_day(
                date,
                cands,
                krx,
                capital_per_run=self.initial_capital,
                profit_target=self.profit_target,
                loss_target=self.loss_target,
            )
        except Exception as e:
            return DayResult(
                date=date,
                candidates=len(cands),
                error=f"simulate_day 실패: {e}",
            )

        return DayResult(
            date=date,
            candidates=len(cands),
            trades=sim["total_trades"],
            wins=sim["wins"],
            losses=sim["total_trades"] - sim["wins"],
            daily_return_pct=sim["total_return"],
            daily_return_amount=sim["total_return_amount"],
            trade_details=sim["trades"],
        )

    def run(
        self,
        start_date: str,
        end_date: str,
        parallel_workers: int = DEFAULT_WORKERS,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> BacktestResult:
        """
        백테스트 실행.

        Args:
            start_date: YYYYMMDD
            end_date: YYYYMMDD
            parallel_workers: 일자별 병렬 워커 수 (1 = 순차, 4 = thread pool)
            progress_callback: (current, total, date) 콜백

        Returns:
            BacktestResult
        """
        start_time = time.time()
        trading_days = get_trading_days(start_date, end_date)
        if not trading_days:
            return BacktestResult(
                strategy_id=self.strategy.STRATEGY_ID,
                strategy_name=self.strategy.STRATEGY_NAME,
                start_date=start_date,
                end_date=end_date,
                trading_days=0,
                initial_capital=self.initial_capital,
                final_capital=self.initial_capital,
                has_errors=True,
                error_messages=["거래일 추출 실패"],
            )

        result = BacktestResult(
            strategy_id=self.strategy.STRATEGY_ID,
            strategy_name=self.strategy.STRATEGY_NAME,
            start_date=start_date,
            end_date=end_date,
            trading_days=len(trading_days),
            initial_capital=self.initial_capital,
            final_capital=self.initial_capital,
            parallel_workers=parallel_workers,
        )

        day_results: Dict[str, DayResult] = {}

        # 병렬 또는 순차
        if parallel_workers > 1:
            with ThreadPoolExecutor(max_workers=parallel_workers) as ex:
                futures = {ex.submit(self._process_one_day, d): d for d in trading_days}
                completed = 0
                for fut in as_completed(futures):
                    date = futures[fut]
                    try:
                        dr = fut.result()
                    except Exception as e:
                        dr = DayResult(date=date, error=f"future 실패: {e}")
                    day_results[date] = dr
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, len(trading_days), date)
        else:
            for i, date in enumerate(trading_days, 1):
                dr = self._process_one_day(date)
                day_results[date] = dr
                if progress_callback:
                    progress_callback(i, len(trading_days), date)

        # 일자 순서대로 정렬 + 누적 잔고 계산
        capital = self.initial_capital
        for date in sorted(day_results.keys()):
            dr = day_results[date]
            if dr.error:
                result.failed_days += 1
                result.has_errors = True
                result.error_messages.append(f"{date}: {dr.error}")
            capital += dr.daily_return_amount
            dr.capital_after = capital
            result.daily_history.append(dr)
            result.total_trades += dr.trades
            result.total_wins += dr.wins
            result.total_losses += dr.losses
            result.total_return_amount += dr.daily_return_amount

        result.final_capital = capital
        result.total_return_pct = round(
            (capital - self.initial_capital) / self.initial_capital * 100, 2
        )
        result.duration_seconds = round(time.time() - start_time, 2)
        return result


# ============================================================
# Standard test periods
# ============================================================

class StandardPeriods:
    """표준 백테스트 기간 정의."""

    @staticmethod
    def last_n_days(n: int, end_date: Optional[str] = None) -> tuple:
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")
        end_dt = datetime.strptime(end_date, "%Y%m%d")
        start_dt = end_dt - timedelta(days=n + 5)  # 주말 여유
        return (start_dt.strftime("%Y%m%d"), end_date)

    @classmethod
    def one_week(cls, end_date: Optional[str] = None) -> tuple:
        return cls.last_n_days(7, end_date)

    @classmethod
    def one_month(cls, end_date: Optional[str] = None) -> tuple:
        return cls.last_n_days(30, end_date)

    @classmethod
    def three_months(cls, end_date: Optional[str] = None) -> tuple:
        return cls.last_n_days(90, end_date)

    @classmethod
    def one_year(cls, end_date: Optional[str] = None) -> tuple:
        return cls.last_n_days(365, end_date)

    @classmethod
    def all(cls, end_date: Optional[str] = None) -> Dict[str, tuple]:
        return {
            "1w": cls.one_week(end_date),
            "1m": cls.one_month(end_date),
            "3m": cls.three_months(end_date),
            "1y": cls.one_year(end_date),
        }


__all__ = [
    "DayResult",
    "BacktestResult",
    "SingleStrategyBacktest",
    "StandardPeriods",
    "simulate_day",
    "get_trading_days",
    "INITIAL_CAPITAL",
    "PROFIT_TARGET",
    "LOSS_TARGET",
]
