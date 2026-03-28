"""
다중 전략 실행기
- 모든 전략 동시 실행
- 결과 저장 및 비교
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from paper_trading.strategies import StrategyRegistry
from paper_trading.simulator import TradingSimulator
from utils import format_kst_time

DATA_DIR = Path(__file__).parent.parent / "data" / "paper_trading"


def run_all_strategies(date: str = None, top_n: int = 5, simulate: bool = False) -> Dict:
    """
    모든 전략 실행

    Args:
        date: 날짜 (YYYYMMDD)
        top_n: 전략당 선정 종목 수
        simulate: 시뮬레이션 실행 여부

    Returns:
        전략별 결과
    """
    if date is None:
        date = format_kst_time(format_str='%Y%m%d')

    print(f"\n{'='*60}")
    print(f"[Multi-Strategy Runner] 다중 전략 실행")
    print(f"  날짜: {date}")
    print(f"  종목 수: 전략당 {top_n}개")
    print(f"{'='*60}")

    # 등록된 전략 확인
    strategies = StrategyRegistry.list_strategies()
    print(f"\n등록된 전략: {len(strategies)}개")
    for s in strategies:
        print(f"  - {s['name']} ({s['id']}): {s['description']}")

    # 모든 전략 실행
    results = StrategyRegistry.run_all(date=date, top_n=top_n)

    # 결과 저장
    StrategyRegistry.save_results(results, date)

    # 시뮬레이션 실행 (선택적)
    if simulate:
        print(f"\n[Simulation] 시뮬레이션 실행")
        simulator = TradingSimulator()

        for strategy_id, result in results.items():
            print(f"\n  [{result.strategy_name}] 시뮬레이션...")
            try:
                # 후보 종목으로 시뮬레이션
                candidates = result.candidates
                if candidates:
                    sim_result = simulator.simulate_day(
                        date,
                        [c.to_dict() if hasattr(c, 'to_dict') else c for c in candidates]
                    )
                    result.simulation = sim_result
                    print(f"    → 수익률: {sim_result.get('total_return', 0):+.2f}%")
            except Exception as e:
                print(f"    → 오류: {e}")

        # 시뮬레이션 결과 포함해서 다시 저장
        StrategyRegistry.save_results(results, date)

    # 요약 출력
    print_summary(results, date)

    return results


def print_summary(results: Dict, date: str):
    """결과 요약 출력"""
    print(f"\n{'='*60}")
    print(f"[Summary] 전략별 결과 요약 ({date})")
    print(f"{'='*60}")

    print(f"\n{'전략':<20} {'종목수':>8} {'총점수':>10} {'수익률':>10}")
    print("-" * 50)

    for strategy_id, result in results.items():
        name = result.strategy_name[:18]
        count = len(result.candidates)
        total_score = sum(c.score for c in result.candidates) if result.candidates else 0

        if result.simulation:
            ret = f"{result.simulation.get('total_return', 0):+.2f}%"
        else:
            ret = "-"

        print(f"{name:<20} {count:>8} {total_score:>10.1f} {ret:>10}")

    print("-" * 50)

    # 선정 종목 상세
    print(f"\n[선정 종목 상세]")
    for strategy_id, result in results.items():
        print(f"\n  📌 {result.strategy_name}:")
        for c in result.candidates[:5]:
            print(f"     {c.rank}. {c.name} ({c.code}): {c.change_pct:+.2f}%, 점수 {c.score}")


def compare_strategies(date: str) -> Dict:
    """전략 비교"""
    comparison = StrategyRegistry.get_comparison(date)

    if not comparison:
        print(f"[Compare] {date} 데이터 없음")
        return {}

    print(f"\n{'='*60}")
    print(f"[Compare] 전략 비교 ({date})")
    print(f"{'='*60}")

    for s in comparison.get('strategies', []):
        print(f"\n{s['name']}:")
        print(f"  종목 수: {s['count']}")
        if s['total_return'] is not None:
            print(f"  수익률: {s['total_return']:+.2f}%")
            print(f"  승률: {s['win_rate']:.1f}%")

    return comparison


def main():
    """CLI"""
    parser = argparse.ArgumentParser(description='다중 전략 실행기')
    parser.add_argument('command', choices=['run', 'compare', 'list'],
                       help='명령: run(실행), compare(비교), list(전략목록)')
    parser.add_argument('--date', '-d', type=str, default=None,
                       help='날짜 (YYYYMMDD)')
    parser.add_argument('--top-n', '-n', type=int, default=5,
                       help='전략당 종목 수')
    parser.add_argument('--simulate', '-s', action='store_true',
                       help='시뮬레이션 실행')

    args = parser.parse_args()

    if args.command == 'run':
        run_all_strategies(
            date=args.date,
            top_n=args.top_n,
            simulate=args.simulate
        )
    elif args.command == 'compare':
        date = args.date or format_kst_time(format_str='%Y%m%d')
        compare_strategies(date)
    elif args.command == 'list':
        strategies = StrategyRegistry.list_strategies()
        print("\n등록된 전략:")
        for s in strategies:
            print(f"  - {s['id']}: {s['name']}")
            print(f"    {s['description']}")


if __name__ == "__main__":
    main()
