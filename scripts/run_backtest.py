"""
Backtest Runner (Phase 7D)
- 3주 day-by-day replay (2026-03-23 ~ 2026-04-10)
- 5팀 (A/B/C/D/E) 동시 실행
- 별도 디렉토리: data/backtest/ (운영 데이터 오염 방지)
- 일봉 기반 시뮬 (분봉 historical 한도 6일이라 통일)

사용법:
    python scripts/run_backtest.py [start_date] [end_date]
    python scripts/run_backtest.py 20260323 20260410
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env')

logging.basicConfig(level=logging.WARNING, format='%(message)s')
logger = logging.getLogger(__name__)

from paper_trading.utils.krx_api import KRXClient
from paper_trading.strategies import (
    MomentumStrategy, LargecapContrarianStrategy,
    DartDisclosureStrategy, ThemePolicyStrategy, FrontierGapStrategy
)

# 별도 디렉토리 (운영 데이터와 분리)
BACKTEST_DIR = PROJECT_ROOT / 'data' / 'backtest'
BACKTEST_DIR.mkdir(parents=True, exist_ok=True)

INITIAL_CAPITAL = 10_000_000
PROFIT_TARGET = 5.0    # +5%
LOSS_TARGET = -3.0     # -3%

TEAMS = [
    {'id': 'team_a', 'name': 'Alpha Momentum', 'cls': MomentumStrategy, 'color': '#EF4444'},
    {'id': 'team_b', 'name': 'Beta Contrarian', 'cls': LargecapContrarianStrategy, 'color': '#3B82F6'},
    {'id': 'team_c', 'name': 'Gamma Disclosure', 'cls': DartDisclosureStrategy, 'color': '#10B981'},
    {'id': 'team_d', 'name': 'Delta Theme', 'cls': ThemePolicyStrategy, 'color': '#F59E0B'},
    {'id': 'team_e', 'name': 'Echo Frontier', 'cls': FrontierGapStrategy, 'color': '#8B5CF6'},
]


def get_trading_days(start: str, end: str) -> List[str]:
    """KRX 지수 데이터로 거래일 필터 (가장 정확)"""
    krx = KRXClient()
    days = []
    cur = datetime.strptime(start, '%Y%m%d')
    end_dt = datetime.strptime(end, '%Y%m%d')
    while cur <= end_dt:
        if cur.weekday() < 5:  # 월~금
            d = cur.strftime('%Y%m%d')
            try:
                idx = krx.get_index_ohlcv(d, 'KOSPI')
                if not idx.empty:
                    days.append(d)
            except Exception:
                pass
        cur += timedelta(days=1)
    return days


def simulate_day(date: str, candidates: List, krx: KRXClient) -> Dict:
    """일봉 기반 매매 시뮬 (시초가 매수 → 익절/손절 → 종가 청산)

    Returns:
        {'trades': [...], 'total_return': %, 'wins': N, 'total_trades': N, 'total_return_amount': 원}
    """
    if not candidates:
        return {'trades': [], 'total_return': 0, 'wins': 0,
                'total_trades': 0, 'total_return_amount': 0, 'win_rate': 0}

    trades = []
    capital_per_trade = INITIAL_CAPITAL / max(len(candidates), 1)

    # 그날의 OHLCV 한 번에 fetch (캐시 사용)
    market_data = {}
    for market in ['KOSPI', 'KOSDAQ']:
        df = krx.get_stock_ohlcv(date, market=market)
        if not df.empty:
            for code in df.index:
                market_data[code] = df.loc[code]

    for cand in candidates:
        code = cand.code if hasattr(cand, 'code') else cand['code']
        name = cand.name if hasattr(cand, 'name') else cand['name']
        row = market_data.get(code)
        if row is None:
            continue
        try:
            open_p = int(row.get('시가', 0))
            high_p = int(row.get('고가', 0))
            low_p = int(row.get('저가', 0))
            close_p = int(row.get('종가', 0))
            if open_p == 0:
                continue

            # 익절/손절 가격
            profit_px = open_p * (1 + PROFIT_TARGET / 100)
            loss_px = open_p * (1 + LOSS_TARGET / 100)

            # 일봉 기반 체결 판정
            if low_p <= loss_px:
                # 손절 우선 (저가가 손절선 도달)
                exit_px = int(loss_px)
                exit_type = 'loss'
            elif high_p >= profit_px:
                # 익절 (고가가 익절선 도달)
                exit_px = int(profit_px)
                exit_type = 'profit'
            else:
                # 종가 청산
                exit_px = close_p
                exit_type = 'close'

            return_pct = (exit_px - open_p) / open_p * 100
            qty = int(capital_per_trade / open_p)
            return_amt = (exit_px - open_p) * qty

            trades.append({
                'code': code,
                'name': name,
                'entry_price': open_p,
                'exit_price': exit_px,
                'exit_type': exit_type,
                'return_pct': round(return_pct, 2),
                'return_amount': return_amt,
                'qty': qty,
            })
        except Exception as e:
            logger.debug(f"{code} 시뮬 실패: {e}")
            continue

    if not trades:
        return {'trades': [], 'total_return': 0, 'wins': 0,
                'total_trades': 0, 'total_return_amount': 0, 'win_rate': 0}

    avg_return = sum(t['return_pct'] for t in trades) / len(trades)
    wins = sum(1 for t in trades if t['return_pct'] > 0)
    total_return_amt = sum(t['return_amount'] for t in trades)

    return {
        'trades': trades,
        'total_return': round(avg_return, 2),
        'wins': wins,
        'total_trades': len(trades),
        'total_return_amount': total_return_amt,
        'win_rate': round(wins / len(trades) * 100, 1) if trades else 0,
    }


def run_backtest(start_date: str, end_date: str):
    """3주 backtest 메인 루프"""
    print(f"\n{'=' * 60}")
    print(f"Backtest: {start_date} ~ {end_date}")
    print(f"{'=' * 60}")

    krx = KRXClient()

    # 거래일 추출
    print("\n[1/3] 거래일 추출 중...")
    trading_days = get_trading_days(start_date, end_date)
    print(f"  거래일: {len(trading_days)}일 ({trading_days[0]} ~ {trading_days[-1]})")

    # 팀 portfolio 초기화
    portfolios = {t['id']: {
        'team_id': t['id'], 'name': t['name'],
        'capital': INITIAL_CAPITAL,
        'total_return_amount': 0, 'total_return_pct': 0,
        'total_trades': 0, 'wins': 0, 'losses': 0,
        'daily_history': [],
    } for t in TEAMS}

    # 전략 인스턴스 1번만 생성
    strategies = {t['id']: t['cls']() for t in TEAMS}

    # Day-by-day replay
    print(f"\n[2/3] Day-by-day 시뮬 ({len(trading_days)}일)")
    print("-" * 60)
    for di, date in enumerate(trading_days, 1):
        print(f"\n[{di}/{len(trading_days)}] {date}")

        for team in TEAMS:
            tid = team['id']
            strat = strategies[tid]
            try:
                # 종목 선정
                cands = strat.select_stocks(date=date, top_n=5)
                # 매매 시뮬
                result = simulate_day(date, cands, krx)
                # portfolio 업데이트
                pf = portfolios[tid]
                pf['capital'] += result['total_return_amount']
                pf['total_return_amount'] += result['total_return_amount']
                pf['total_return_pct'] = round(
                    (pf['capital'] - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100, 2
                )
                pf['total_trades'] += result['total_trades']
                pf['wins'] += result['wins']
                pf['losses'] += (result['total_trades'] - result['wins'])
                pf['daily_history'].append({
                    'date': date,
                    'candidates': len(cands),
                    'trades': result['total_trades'],
                    'wins': result['wins'],
                    'daily_return_pct': result['total_return'],
                    'daily_return_amount': result['total_return_amount'],
                    'capital_after': pf['capital'],
                })
                print(f"  {tid:8s}: 후보 {len(cands)} → 매매 {result['total_trades']} → "
                      f"{result['total_return']:+5.2f}% ({result['total_return_amount']:+,}원)")
            except Exception as e:
                logger.warning(f"  {tid} 오류: {e}")
                continue

    # 결과 저장
    print(f"\n[3/3] 결과 저장")
    print("-" * 60)
    out_path = BACKTEST_DIR / f'backtest_{start_date}_{end_date}.json'
    summary = {
        'start_date': start_date, 'end_date': end_date,
        'trading_days': len(trading_days), 'dates': trading_days,
        'initial_capital': INITIAL_CAPITAL,
        'profit_target': PROFIT_TARGET, 'loss_target': LOSS_TARGET,
        'portfolios': portfolios,
    }
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
    print(f"  저장: {out_path}")

    # 최종 리포트
    print(f"\n{'=' * 60}")
    print(f"📊 Backtest 결과 ({len(trading_days)}일)")
    print(f"{'=' * 60}")
    sorted_teams = sorted(portfolios.items(), key=lambda x: x[1]['total_return_pct'], reverse=True)
    medals = ['🥇', '🥈', '🥉', ' 4', ' 5']
    for i, (tid, pf) in enumerate(sorted_teams):
        m = medals[min(i, 4)]
        wr = round(pf['wins'] / max(pf['total_trades'], 1) * 100, 1)
        print(f"{m} {pf['name']:20s} {pf['total_return_pct']:+7.2f}%  "
              f"잔고 {pf['capital']:>11,}원  매매 {pf['wins']}/{pf['total_trades']} ({wr:.0f}%)")

    return summary


if __name__ == '__main__':
    if len(sys.argv) >= 3:
        start, end = sys.argv[1], sys.argv[2]
    else:
        start, end = '20260323', '20260410'
    run_backtest(start, end)
