"""
시뮬 trades.json vs 네이버 실측 OHLC 정합성 검증 (ISSUE-014)

분봉 collector의 first_hit 판정과 simulator의 trailing 우선 로직이
실측 일봉 OHLC 기준 재계산과 얼마나 어긋나는지 측정.

사용:
    python -m paper_trading.audit.verify_intraday_accuracy 20260508
    python -m paper_trading.audit.verify_intraday_accuracy 20260504 20260507 20260508

출력: 콘솔 표 + data/arena/audit/intraday_accuracy_<date>.json
"""

import sys, os, json, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from naver_market import stock as nv

ARENA_DIR = PROJECT_ROOT / "data" / "arena"
OUT_DIR = ARENA_DIR / "audit"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PROFIT_TARGET_PCT = 5.0
LOSS_TARGET_PCT = -3.0


def collect_trades(date: str):
    """date의 모든 team trades.json 수집"""
    teams = {}
    for tid_dir in sorted(ARENA_DIR.glob("team_*")):
        p = tid_dir / "daily" / date / "trades.json"
        if p.exists():
            with open(p) as f:
                teams[tid_dir.name] = json.load(f)
    return teams


def get_real_ohlc(codes, date: str):
    """네이버에서 date의 OHLC 수집"""
    ohlc = {}
    start = date  # YYYYMMDD
    end = date
    # ohlcv_by_date 는 단일 종목, 기간 검색
    for code in codes:
        try:
            df = nv.get_market_ohlcv_by_date(start, "20260512", code)
            for idx in df.index:
                if idx.strftime("%Y%m%d") == date:
                    row = df.loc[idx]
                    ohlc[code] = {
                        'open': int(row['시가']),
                        'high': int(row['고가']),
                        'low': int(row['저가']),
                        'close': int(row['종가']),
                    }
                    break
            time.sleep(0.15)
        except Exception:
            pass
    return ohlc


def real_simulate(real, profit_pct=PROFIT_TARGET_PCT, loss_pct=LOSS_TARGET_PCT):
    """실측 OHLC 기반 일봉 시뮬: 시초가 매수 → 손절선 → 익절선 → 종가

    한계: 일봉만 쓰므로 시간 순서 모름. 손절-익절 모두 도달했으면 손절 우선
    (전략적 보수). 실제 분봉 시간 순서가 정확한 truth지만 분봉 historical 한계.
    """
    e = real['open']
    if e == 0:
        return None
    lp = e * (1 + loss_pct / 100)
    pp = e * (1 + profit_pct / 100)
    if real['low'] <= lp:
        return {'exit': int(lp), 'type': 'loss', 'ret': loss_pct}
    if real['high'] >= pp:
        return {'exit': int(pp), 'type': 'profit', 'ret': profit_pct}
    ret = (real['close'] - e) / e * 100
    return {'exit': real['close'], 'type': 'close', 'ret': round(ret, 2)}


def verify_date(date: str, verbose: bool = True):
    """단일 거래일 검증"""
    teams = collect_trades(date)
    if not teams:
        print(f"[{date}] trades.json 없음 - 스킵")
        return None

    codes = set()
    for t in teams.values():
        for r in t.get("results", []):
            codes.add(r["code"])

    real = get_real_ohlc(list(codes), date)

    rows = []
    sums = {tid: {"sim": 0, "real": 0} for tid in teams}
    n = n_dir_mismatch = n_amt_mismatch = 0

    for tid, t in teams.items():
        for r in t.get("results", []):
            code = r["code"]
            if code not in real:
                continue
            rs = real_simulate(real[code])
            if rs is None:
                continue
            sim_ret = r["return_pct"]
            diff = rs['ret'] - sim_ret
            qty = r.get("quantity", 0) or 100
            sim_amt = r.get("return_amount", 0)
            real_amt = (rs['exit'] - real[code]['open']) * qty
            sums[tid]["sim"] += sim_amt
            sums[tid]["real"] += real_amt
            n += 1

            type_match = (r['exit_type'] == rs['type'])
            # 시뮬 trailing/profit 인데 실측 close 이고 차이 작으면 정합
            if not type_match and r['exit_type'] in ('trailing', 'profit') and rs['type'] == 'close' and abs(diff) <= 1.0:
                type_match = True

            if not type_match:
                n_dir_mismatch += 1
                flag = "DIR"
            elif abs(diff) > 1.0:
                n_amt_mismatch += 1
                flag = "AMT"
            else:
                flag = "OK"

            rows.append({
                'team': tid, 'code': code, 'name': r['name'],
                'sim_entry': r['entry_price'], 'real_open': real[code]['open'],
                'sim_exit': r['exit_price'], 'real_close': real[code]['close'],
                'real_high': real[code]['high'], 'real_low': real[code]['low'],
                'sim_ret_pct': sim_ret, 'real_ret_pct': rs['ret'],
                'diff_pct': round(diff, 2),
                'sim_exit_type': r['exit_type'], 'real_exit_type': rs['type'],
                'flag': flag,
                'sim_amount': sim_amt, 'real_amount': real_amt,
            })

    summary = {
        'date': date,
        'n_trades': n,
        'n_real_ohlc_missing': len(codes) - len(real),
        'n_dir_mismatch': n_dir_mismatch,
        'n_amt_mismatch': n_amt_mismatch,
        'n_ok': n - n_dir_mismatch - n_amt_mismatch,
        'mismatch_rate_pct': round((n_dir_mismatch + n_amt_mismatch) / max(n, 1) * 100, 1),
        'team_pnl': {
            tid: {
                'sim_amount': sums[tid]['sim'],
                'real_amount': sums[tid]['real'],
                'diff_amount': sums[tid]['real'] - sums[tid]['sim'],
                'sim_pct': round(sums[tid]['sim'] / 10_000_000 * 100, 2),
                'real_pct': round(sums[tid]['real'] / 10_000_000 * 100, 2),
                'diff_pct': round((sums[tid]['real'] - sums[tid]['sim']) / 10_000_000 * 100, 2),
            } for tid in sums
        },
        'rows': rows,
    }

    out = OUT_DIR / f"intraday_accuracy_{date}.json"
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    if verbose:
        print(f"\n=== [{date}] 시뮬 vs 실측 정합성 ===")
        print(f"{'team':<7}{'code':<8}{'name':<14}{'sim%':>7}{'real%':>7}{'diff%p':>7}  {'sim/real':<22} {'flag':<5}")
        for r in rows:
            print(f"{r['team']:<7}{r['code']:<8}{r['name'][:13]:<14}{r['sim_ret_pct']:>+7.2f}{r['real_ret_pct']:>+7.2f}{r['diff_pct']:>+7.2f}  {r['sim_exit_type']+'/'+r['real_exit_type']:<22} {r['flag']:<5}")
        print(f"\n총 {n} | 정합 {summary['n_ok']} | DIR불일치 {n_dir_mismatch} | AMT불일치 {n_amt_mismatch} | 부정확율 {summary['mismatch_rate_pct']}%")
        print(f"\n팀별 capital_impact:")
        for tid, tp in summary['team_pnl'].items():
            print(f"  {tid}: sim {tp['sim_pct']:+6.2f}%p  real {tp['real_pct']:+6.2f}%p  diff {tp['diff_pct']:+6.2f}%p")
        print(f"\n저장: {out}")

    return summary


if __name__ == '__main__':
    dates = sys.argv[1:] if len(sys.argv) > 1 else ['20260508']
    all_results = []
    for d in dates:
        s = verify_date(d)
        if s:
            all_results.append(s)
    if len(all_results) > 1:
        print(f"\n{'='*60}\n=== 종합 ({len(all_results)}거래일) ===")
        print(f"{'date':<10}{'n':>5}{'OK':>5}{'DIR':>5}{'AMT':>5}{'부정확%':>9}{'5팀시뮬%':>11}{'5팀실측%':>11}{'차이%p':>9}")
        for s in all_results:
            sim_total = sum(t['sim_pct'] for t in s['team_pnl'].values())
            real_total = sum(t['real_pct'] for t in s['team_pnl'].values())
            print(f"{s['date']:<10}{s['n_trades']:>5}{s['n_ok']:>5}{s['n_dir_mismatch']:>5}{s['n_amt_mismatch']:>5}{s['mismatch_rate_pct']:>8.1f}%{sim_total:>+11.2f}{real_total:>+11.2f}{real_total-sim_total:>+9.2f}")
