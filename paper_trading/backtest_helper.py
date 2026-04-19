"""
백테스트 헬퍼 — 분봉 우선 + 일봉 폴백 시 경고

사용법:
    from paper_trading.backtest_helper import run_backtest
    results = run_backtest(strategy_class, dates=['20260414','20260415','20260416'])
"""

import sys
from pathlib import Path
from typing import List, Type, Optional
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from paper_trading.simulator import TradingSimulator, StockCandidate


def run_backtest(
    strategy_class,
    dates: List[str],
    capital: int = 10_000_000,
    top_n: int = 5,
    use_intraday: bool = True,
    verbose: bool = True,
) -> dict:
    """
    전략 백테스트 실행 (분봉 우선)

    Args:
        strategy_class: 전략 클래스 (BaseStrategy 상속)
        dates: 테스트 날짜 목록 ['20260414', ...]
        capital: 초기 자본
        top_n: 종목 수
        use_intraday: 분봉 사용 여부 (기본 True)

    Returns:
        {'trades': [...], 'summary': {...}}
    """
    all_results = []
    intraday_used = 0
    daily_used = 0

    for date in dates:
        try:
            strat = strategy_class()
            cands = strat.select_stocks(date=date, top_n=top_n)
            if not cands:
                if verbose:
                    print(f"  {date}: 종목 없음")
                continue

            sc_list = [StockCandidate(
                code=c.code, name=c.name, price=c.price,
                change_pct=c.change_pct, score=c.score,
                trading_value=getattr(c, 'trading_value', 0) or 0,
                market_cap=getattr(c, 'market_cap', 0) or 0,
                volume=getattr(c, 'volume', 0) or 0,
            ) for c in cands]

            sim = TradingSimulator(capital=capital)
            results = sim.simulate_day(sc_list, date=date, use_intraday=use_intraday)

            for r in results:
                r.date = date
            all_results.extend(results)

        except Exception as e:
            if verbose:
                print(f"  {date}: 오류 - {e}")

    if not all_results:
        print("⚠️ 매매 결과 없음")
        return {'trades': [], 'summary': None}

    # 분봉/일봉 사용 비율 확인
    for r in all_results:
        if hasattr(r, 'exit_type'):
            if r.exit_type in ('profit', 'loss'):
                intraday_used += 1
            else:
                daily_used += 1

    wins = sum(1 for r in all_results if r.return_pct > 0)
    total_ret = sum(r.return_pct for r in all_results)

    # ⚠️ 일봉 비율이 높으면 경고
    total_trades = len(all_results)
    if daily_used > intraday_used and total_trades > 0:
        print(f"\n⚠️ 경고: 일봉 기반 {daily_used}/{total_trades}건 — 결과 정확도 낮음")
        print(f"   분봉 데이터가 없는 날짜입니다. 최근 5~7거래일만 분봉 백테스트 가능.")

    summary = {
        'trades': total_trades,
        'wins': wins,
        'winrate': round(wins / total_trades * 100),
        'avg_ret': round(total_ret / total_trades, 2),
        'total_ret': round(total_ret, 2),
        'max_gain': round(max(r.return_pct for r in all_results), 2),
        'max_loss': round(min(r.return_pct for r in all_results), 2),
        'intraday_pct': round(intraday_used / total_trades * 100) if total_trades > 0 else 0,
    }

    if verbose:
        print(f"\n{'='*50}")
        print(f"백테스트 결과 ({strategy_class.STRATEGY_NAME})")
        print(f"{'='*50}")
        print(f"  매매: {summary['trades']}건, 승률: {summary['winrate']}%")
        print(f"  평균: {summary['avg_ret']:+.2f}%, 합계: {summary['total_ret']:+.2f}%")
        print(f"  분봉 비율: {summary['intraday_pct']}%")

    return {'trades': all_results, 'summary': summary}
