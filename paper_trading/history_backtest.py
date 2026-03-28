"""
기존 history.json 데이터 활용 백테스트
- 이미 수집된 데이터로 전략 시뮬레이션
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_DIR = DATA_DIR / "paper_trading"


def load_history_data() -> Dict:
    """history.json 로드"""
    history_file = DATA_DIR / "history.json"
    if not history_file.exists():
        print("history.json 없음")
        return {}

    with open(history_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def simulate_strategy(stocks: List[Dict], strategy_type: str) -> Dict:
    """
    전략별 시뮬레이션

    strategy_type:
    - 'largecap_contrarian': 하락 종목 (역추세)
    - 'momentum': 상승 종목 (추세추종)
    - 'theme_policy': 테마 기반 (모든 종목)
    """

    # 필터 조건
    if strategy_type == 'largecap_contrarian':
        # 하락 종목만 (entry_check에서 하락)
        filtered = [s for s in stocks if s.get('entry_check', {}).get('entry_pct', 0) < 0]
    elif strategy_type == 'momentum':
        # 상승 종목만
        filtered = [s for s in stocks if s.get('entry_check', {}).get('entry_pct', 0) > 0]
    else:
        # 모든 종목
        filtered = stocks

    if not filtered:
        return {'trades': 0, 'wins': 0, 'losses': 0, 'return': 0}

    # 결과 계산
    total_return = 0
    wins = 0
    losses = 0

    for stock in filtered[:5]:  # 상위 5개만
        result = stock.get('result', 'none')
        ret = stock.get('return_pct', 0)

        if result == 'profit':
            wins += 1
            total_return += ret if ret else 3.0  # 익절 기본 3%
        elif result == 'loss':
            losses += 1
            total_return += ret if ret else -1.5  # 손절 기본 -1.5%
        else:
            # 종가 청산
            total_return += ret if ret else 0
            if ret and ret > 0:
                wins += 1
            elif ret and ret < 0:
                losses += 1

    return {
        'trades': len(filtered[:5]),
        'wins': wins,
        'losses': losses,
        'return': round(total_return, 2)
    }


def run_history_backtest():
    """history.json 기반 백테스트"""

    print("\n" + "="*60)
    print("[History Backtest] 기존 데이터 기반 전략 비교")
    print("="*60)

    # 데이터 로드
    data = load_history_data()
    if not data:
        return

    dates = data.get('dates', [])
    by_date = data.get('data_by_date', {})

    print(f"\n기간: {min(dates)} ~ {max(dates)}")
    print(f"총 거래일: {len(dates)}일")

    # 전략별 결과
    strategies = {
        'largecap_contrarian': {'name': '대형주 역추세', 'daily': [], 'total_return': 0, 'wins': 0, 'losses': 0, 'trades': 0},
        'momentum': {'name': '모멘텀 추세', 'daily': [], 'total_return': 0, 'wins': 0, 'losses': 0, 'trades': 0},
        'theme_policy': {'name': '테마/정책', 'daily': [], 'total_return': 0, 'wins': 0, 'losses': 0, 'trades': 0}
    }

    for date in dates:
        stocks = by_date.get(date, [])
        if not stocks:
            continue

        for strategy_id, strategy in strategies.items():
            result = simulate_strategy(stocks, strategy_id)

            strategy['daily'].append({
                'date': date,
                **result
            })

            strategy['total_return'] += result['return']
            strategy['wins'] += result['wins']
            strategy['losses'] += result['losses']
            strategy['trades'] += result['trades']

    # 결과 출력
    print("\n" + "="*60)
    print("[결과] 전략별 성과 비교")
    print("="*60)

    print(f"\n{'전략':<20} {'수익률':>12} {'승률':>10} {'거래수':>10}")
    print("-" * 55)

    best_strategy = None
    best_return = -999999

    for sid, s in strategies.items():
        total = s['wins'] + s['losses']
        win_rate = (s['wins'] / total * 100) if total > 0 else 0
        s['win_rate'] = round(win_rate, 1)

        # 최고 전략 체크
        if s['total_return'] > best_return:
            best_return = s['total_return']
            best_strategy = sid

        print(f"{s['name']:<20} {s['total_return']:>+10.2f}% {win_rate:>9.1f}% {s['trades']:>10}")

    print("-" * 55)
    print(f"\n🏆 최고 전략: {strategies[best_strategy]['name']} ({best_return:+.2f}%)")

    # 일별 누적 수익률 계산
    for sid, s in strategies.items():
        cumulative = 0
        for day in s['daily']:
            cumulative += day['return']
            day['cumulative'] = round(cumulative, 2)

    # 결과 저장
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    result = {
        'backtest_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'period': f"{min(dates)} ~ {max(dates)}",
        'total_days': len(dates),
        'strategies': {
            sid: {
                'name': s['name'],
                'total_return': round(s['total_return'], 2),
                'win_rate': s['win_rate'],
                'wins': s['wins'],
                'losses': s['losses'],
                'trades': s['trades'],
                'daily': s['daily']
            }
            for sid, s in strategies.items()
        },
        'best_strategy': best_strategy,
        'comparison': {
            'ranking_by_return': sorted(
                [(sid, s['total_return']) for sid, s in strategies.items()],
                key=lambda x: x[1],
                reverse=True
            )
        }
    }

    output_file = OUTPUT_DIR / "strategy_backtest_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n저장됨: {output_file}")

    # 요약 저장
    summary = {
        'backtest_date': result['backtest_date'],
        'period': result['period'],
        'strategies': {
            sid: {
                'name': s['name'],
                'total_return': s['total_return'],
                'win_rate': s['win_rate'],
                'trades': s['trades']
            }
            for sid, s in result['strategies'].items()
        },
        'best_strategy': best_strategy
    }

    summary_file = OUTPUT_DIR / "strategy_comparison_summary.json"
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"저장됨: {summary_file}")

    return result


if __name__ == "__main__":
    run_history_backtest()
