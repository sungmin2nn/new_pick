"""
전략 백테스트 - 과거 데이터로 3개 전략 비교
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List
import time

sys.path.insert(0, str(Path(__file__).parent.parent))

from paper_trading.strategies import StrategyRegistry
from paper_trading.simulator import TradingSimulator

DATA_DIR = Path(__file__).parent.parent / "data" / "paper_trading"


def get_trading_dates(start_date: str, end_date: str) -> List[str]:
    """거래일 목록 생성 (주말 제외)"""
    dates = []
    current = datetime.strptime(start_date, '%Y%m%d')
    end = datetime.strptime(end_date, '%Y%m%d')

    while current <= end:
        # 주말 제외
        if current.weekday() < 5:
            dates.append(current.strftime('%Y%m%d'))
        current += timedelta(days=1)

    return dates


def run_strategy_backtest(strategy_id: str, dates: List[str], top_n: int = 5) -> Dict:
    """단일 전략 백테스트"""
    strategy_class = StrategyRegistry.get(strategy_id)
    if not strategy_class:
        print(f"전략 없음: {strategy_id}")
        return {}

    print(f"\n[{strategy_class.STRATEGY_NAME}] 백테스트 시작 ({len(dates)}일)")

    results = {
        'strategy_id': strategy_id,
        'strategy_name': strategy_class.STRATEGY_NAME,
        'period': f"{dates[0]} ~ {dates[-1]}",
        'total_days': len(dates),
        'daily_results': [],
        'summary': {}
    }

    total_return = 0
    total_trades = 0
    wins = 0
    losses = 0

    simulator = TradingSimulator()

    for i, date in enumerate(dates):
        try:
            # 전략 실행
            strategy = strategy_class()
            candidates = strategy.select_stocks(date=date, top_n=top_n)

            if not candidates:
                continue

            # 시뮬레이션
            sim_result = simulator.simulate_day(
                date,
                [c.to_dict() for c in candidates]
            )

            if sim_result:
                day_return = sim_result.get('total_return', 0)
                day_trades = sim_result.get('total_trades', 0)
                day_wins = sim_result.get('profit_exits', 0)
                day_losses = sim_result.get('loss_exits', 0)

                total_return += day_return
                total_trades += day_trades
                wins += day_wins
                losses += day_losses

                results['daily_results'].append({
                    'date': date,
                    'candidates': len(candidates),
                    'return': round(day_return, 2),
                    'trades': day_trades,
                    'wins': day_wins,
                    'losses': day_losses
                })

            # 진행 상황 (10일마다)
            if (i + 1) % 10 == 0:
                print(f"  {i + 1}/{len(dates)} 완료... 누적 수익률: {total_return:+.2f}%")

        except Exception as e:
            print(f"  {date} 오류: {e}")
            continue

        # API 부하 방지
        time.sleep(0.1)

    # 요약 통계
    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
    avg_return = total_return / len(results['daily_results']) if results['daily_results'] else 0

    results['summary'] = {
        'total_return': round(total_return, 2),
        'avg_daily_return': round(avg_return, 2),
        'total_trades': total_trades,
        'wins': wins,
        'losses': losses,
        'win_rate': round(win_rate, 1),
        'trading_days': len(results['daily_results'])
    }

    print(f"\n  [결과] 수익률: {total_return:+.2f}%, 승률: {win_rate:.1f}%, 거래: {total_trades}건")

    return results


def run_all_strategies_backtest(
    start_date: str = None,
    end_date: str = None,
    days: int = 60,
    top_n: int = 5
) -> Dict:
    """모든 전략 백테스트"""

    # 날짜 설정
    if end_date is None:
        end_date = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')

    if start_date is None:
        start = datetime.strptime(end_date, '%Y%m%d') - timedelta(days=days)
        start_date = start.strftime('%Y%m%d')

    print(f"\n{'='*60}")
    print(f"[Strategy Backtest] 전략 비교 백테스트")
    print(f"  기간: {start_date} ~ {end_date}")
    print(f"  종목 수: 전략당 {top_n}개")
    print(f"{'='*60}")

    # 거래일 목록
    dates = get_trading_dates(start_date, end_date)
    print(f"\n총 {len(dates)}일 백테스트 예정")

    # 모든 전략 실행
    all_results = {
        'backtest_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'period': f"{start_date} ~ {end_date}",
        'total_days': len(dates),
        'strategies': {}
    }

    strategies = StrategyRegistry.list_strategies()

    for strategy_info in strategies:
        strategy_id = strategy_info['id']
        result = run_strategy_backtest(strategy_id, dates, top_n)
        if result:
            all_results['strategies'][strategy_id] = result

    # 비교 분석
    all_results['comparison'] = compare_strategies(all_results['strategies'])

    # 결과 저장
    save_backtest_results(all_results)

    # 요약 출력
    print_comparison(all_results)

    return all_results


def compare_strategies(strategies: Dict) -> Dict:
    """전략 비교"""
    comparison = {
        'ranking_by_return': [],
        'ranking_by_winrate': [],
        'best_strategy': None
    }

    # 수익률 기준 랭킹
    returns = [(sid, s['summary']['total_return'])
               for sid, s in strategies.items() if s.get('summary')]
    returns.sort(key=lambda x: x[1], reverse=True)
    comparison['ranking_by_return'] = returns

    # 승률 기준 랭킹
    winrates = [(sid, s['summary']['win_rate'])
                for sid, s in strategies.items() if s.get('summary')]
    winrates.sort(key=lambda x: x[1], reverse=True)
    comparison['ranking_by_winrate'] = winrates

    # 최고 전략 (수익률 기준)
    if returns:
        comparison['best_strategy'] = returns[0][0]

    return comparison


def save_backtest_results(results: Dict):
    """결과 저장"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 전체 결과
    filepath = DATA_DIR / "strategy_backtest_results.json"
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n저장됨: {filepath}")

    # 요약만 별도 저장
    summary = {
        'backtest_date': results['backtest_date'],
        'period': results['period'],
        'comparison': results['comparison'],
        'strategies': {
            sid: {
                'name': s['strategy_name'],
                'summary': s['summary']
            }
            for sid, s in results['strategies'].items()
        }
    }

    summary_path = DATA_DIR / "strategy_comparison_summary.json"
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"저장됨: {summary_path}")


def print_comparison(results: Dict):
    """비교 결과 출력"""
    print(f"\n{'='*60}")
    print(f"[전략 비교 결과]")
    print(f"{'='*60}")

    print(f"\n{'전략':<20} {'수익률':>12} {'승률':>10} {'거래수':>10}")
    print("-" * 55)

    for sid, strategy in results['strategies'].items():
        summary = strategy.get('summary', {})
        name = strategy['strategy_name'][:18]
        ret = summary.get('total_return', 0)
        wr = summary.get('win_rate', 0)
        trades = summary.get('total_trades', 0)

        # 최고 전략 표시
        best = results['comparison'].get('best_strategy')
        marker = " 🏆" if sid == best else ""

        print(f"{name:<20} {ret:>+10.2f}% {wr:>9.1f}% {trades:>10}{marker}")

    print("-" * 55)

    # 랭킹
    print(f"\n📊 수익률 랭킹:")
    for i, (sid, ret) in enumerate(results['comparison']['ranking_by_return'], 1):
        name = results['strategies'][sid]['strategy_name']
        print(f"  {i}. {name}: {ret:+.2f}%")


def main():
    """CLI"""
    import argparse

    parser = argparse.ArgumentParser(description='전략 백테스트')
    parser.add_argument('--start', '-s', type=str, help='시작일 (YYYYMMDD)')
    parser.add_argument('--end', '-e', type=str, help='종료일 (YYYYMMDD)')
    parser.add_argument('--days', '-d', type=int, default=60, help='백테스트 기간 (일)')
    parser.add_argument('--top-n', '-n', type=int, default=5, help='전략당 종목 수')

    args = parser.parse_args()

    run_all_strategies_backtest(
        start_date=args.start,
        end_date=args.end,
        days=args.days,
        top_n=args.top_n
    )


if __name__ == "__main__":
    main()
