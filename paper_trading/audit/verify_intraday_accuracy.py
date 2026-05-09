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


def update_summary(results):
    """누적 시계열 summary.json 갱신 + alert 산출

    저장: data/arena/audit/accuracy_summary.json
    구조:
        {
          "last_updated": ISO,
          "history": [{date, n_trades, mismatch_rate_pct, sim_total_pct, real_total_pct, diff_pct}],
          "rolling_5d": {mismatch_rate_pct_avg, diff_pct_avg},
          "alerts": [{date, severity, message}],
          "thresholds": {single_day_warn: 30, rolling_5d_warn: 15}
        }
    """
    from datetime import datetime, timezone, timedelta
    KST = timezone(timedelta(hours=9))
    summary_path = OUT_DIR / "accuracy_summary.json"

    summary = {"history": [], "alerts": [], "thresholds": {"single_day_warn": 30, "rolling_5d_warn": 15}}
    if summary_path.exists():
        try:
            with open(summary_path) as f:
                summary = json.load(f)
        except Exception:
            pass

    # history append (중복 date는 갱신)
    history_by_date = {h['date']: h for h in summary.get('history', [])}
    for s in results:
        sim_total = round(sum(t['sim_pct'] for t in s['team_pnl'].values()), 2)
        real_total = round(sum(t['real_pct'] for t in s['team_pnl'].values()), 2)
        history_by_date[s['date']] = {
            'date': s['date'],
            'n_trades': s['n_trades'],
            'n_ok': s['n_ok'],
            'mismatch_rate_pct': s['mismatch_rate_pct'],
            'sim_total_pct': sim_total,
            'real_total_pct': real_total,
            'diff_pct': round(real_total - sim_total, 2),
        }
    summary['history'] = sorted(history_by_date.values(), key=lambda x: x['date'])

    # rolling 5거래일 평균
    recent = summary['history'][-5:]
    if recent:
        summary['rolling_5d'] = {
            'days': len(recent),
            'mismatch_rate_pct_avg': round(sum(h['mismatch_rate_pct'] for h in recent) / len(recent), 1),
            'diff_pct_avg': round(sum(h['diff_pct'] for h in recent) / len(recent), 2),
            'first_date': recent[0]['date'],
            'last_date': recent[-1]['date'],
        }

    # alert 산출
    th = summary.get('thresholds', {"single_day_warn": 30, "rolling_5d_warn": 15})
    alerts = []
    for h in summary['history']:
        if h['mismatch_rate_pct'] > th['single_day_warn']:
            alerts.append({
                'date': h['date'], 'severity': 'warn', 'code': 'W_SINGLE_DAY_DIVERGENCE',
                'message': f"부정확율 {h['mismatch_rate_pct']:.1f}% > {th['single_day_warn']}% (5팀합 차이 {h['diff_pct']:+.2f}%p)"
            })
    if 'rolling_5d' in summary and summary['rolling_5d']['mismatch_rate_pct_avg'] > th['rolling_5d_warn']:
        alerts.append({
            'date': summary['rolling_5d']['last_date'], 'severity': 'warn', 'code': 'W_ROLLING_DIVERGENCE',
            'message': f"최근 {summary['rolling_5d']['days']}거래일 평균 부정확율 {summary['rolling_5d']['mismatch_rate_pct_avg']:.1f}% > {th['rolling_5d_warn']}%"
        })
    summary['alerts'] = alerts
    summary['last_updated'] = datetime.now(KST).isoformat()

    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary


def today_kst() -> str:
    from datetime import datetime, timezone, timedelta
    return datetime.now(timezone(timedelta(hours=9))).strftime("%Y%m%d")


if __name__ == '__main__':
    # 인자 없으면 오늘(KST), 있으면 명시 일자
    dates = sys.argv[1:] if len(sys.argv) > 1 else [today_kst()]
    all_results = []
    for d in dates:
        s = verify_date(d)
        if s:
            all_results.append(s)

    if all_results:
        summary = update_summary(all_results)
        print(f"\n{'='*60}\n=== 누적 시계열 (data/arena/audit/accuracy_summary.json) ===")
        print(f"{'date':<10}{'n':>5}{'OK':>5}{'부정확%':>9}{'시뮬%':>9}{'실측%':>9}{'차이%p':>9}")
        for h in summary['history'][-10:]:
            print(f"{h['date']:<10}{h['n_trades']:>5}{h['n_ok']:>5}{h['mismatch_rate_pct']:>8.1f}%{h['sim_total_pct']:>+9.2f}{h['real_total_pct']:>+9.2f}{h['diff_pct']:>+9.2f}")
        if 'rolling_5d' in summary:
            r = summary['rolling_5d']
            print(f"\n[rolling {r['days']}거래일] 부정확율 평균 {r['mismatch_rate_pct_avg']:.1f}%, 차이 평균 {r['diff_pct_avg']:+.2f}%p")
        if summary.get('alerts'):
            print(f"\n⚠️ Alerts ({len(summary['alerts'])}건):")
            for a in summary['alerts']:
                print(f"  [{a['code']}] {a['date']}: {a['message']}")
        else:
            print("\n✅ Alerts: 없음")

        # GitHub Actions Step Summary 에도 동시 출력 (CI 환경에서 자동)
        gh_summary_path = os.environ.get('GITHUB_STEP_SUMMARY')
        if gh_summary_path:
            with open(gh_summary_path, 'a', encoding='utf-8') as gs:
                gs.write("\n## 🔍 시뮬 정합성 검증 (ISSUE-014 monitor)\n\n")
                gs.write("| 날짜 | 거래 | 정합 | 부정확율 | 시뮬% | 실측% | 차이%p |\n")
                gs.write("|---|---:|---:|---:|---:|---:|---:|\n")
                for h in summary['history'][-5:]:
                    gs.write(f"| {h['date']} | {h['n_trades']} | {h['n_ok']} | {h['mismatch_rate_pct']}% | {h['sim_total_pct']:+.2f} | {h['real_total_pct']:+.2f} | {h['diff_pct']:+.2f} |\n")
                if 'rolling_5d' in summary:
                    r = summary['rolling_5d']
                    gs.write(f"\n**Rolling {r['days']}거래일 평균**: 부정확율 {r['mismatch_rate_pct_avg']}%, 차이 {r['diff_pct_avg']:+.2f}%p  \n\n")
                alerts = summary.get('alerts', [])
                if alerts:
                    gs.write(f"### ⚠️ Alerts ({len(alerts)}건)\n")
                    for a in alerts:
                        gs.write(f"- **{a['code']}** ({a['date']}): {a['message']}\n")
                else:
                    gs.write("### ✅ Alerts: 없음\n")
