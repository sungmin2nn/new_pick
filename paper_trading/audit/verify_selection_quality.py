"""
선정 품질 자동 검증 (ISSUE-014 monitor 후속)

각 전략의 일별 selection.json 을 검사해 다음 결함을 자동 탐지:
- top_n 미달 (5종목 풀 선정 안 됨 → 분산 부족)
- 평균/최저 점수 임계 미달 (질 낮은 후보)
- 선정 가격(price) vs 네이버 실측 전일 종가 불일치 (데이터 신선도)
- 선정 등락률(change_pct) vs 실측 불일치
- 중복 선정 카운트 (정보용)

사용:
    python -m paper_trading.audit.verify_selection_quality           # today (KST)
    python -m paper_trading.audit.verify_selection_quality 20260508  # specific date

출력:
- data/arena/audit/selection_quality_<date>.json (일별 상세)
- data/arena/audit/selection_quality_summary.json (시계열 누적 + alerts)
- GITHUB_STEP_SUMMARY (CI 환경 자동 마크다운)
"""

import sys, os, json, time
from pathlib import Path
from datetime import datetime, timezone, timedelta

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from naver_market import stock as nv

ARENA_DIR = PROJECT_ROOT / "data" / "arena"
OUT_DIR = ARENA_DIR / "audit"
OUT_DIR.mkdir(parents=True, exist_ok=True)
KST = timezone(timedelta(hours=9))

# 임계 (alert 발생 기준)
TOP_N_TARGET = 5
THRESHOLDS = {
    "min_avg_score": 50.0,         # 평균 점수 < 50 시 W_LOW_SCORE
    "max_shortfall_rate_pct": 30,   # 선정 부족 팀 비율 > 30% 시 W_SHORTFALL
    "max_price_diff_pct": 1.0,      # price 오차 평균 > 1% 시 W_STALE_PRICE
    "max_change_diff_pct": 0.5,     # change_pct 오차 평균 > 0.5%p 시 W_STALE_CHANGE
}


def collect_selections(date: str) -> dict:
    """date의 모든 team selection.json 수집"""
    teams = {}
    for tid_dir in sorted(ARENA_DIR.glob("team_*")):
        p = tid_dir / "daily" / date / "selection.json"
        if p.exists():
            with open(p) as f:
                teams[tid_dir.name] = json.load(f)
    return teams


def get_real_prices(codes, ref_date: str) -> dict:
    """ref_date(전일) 의 종가 + 등락률 (네이버)"""
    real = {}
    for code in codes:
        try:
            df = nv.get_market_ohlcv_by_date(ref_date, ref_date, code)
            for idx in df.index:
                if idx.strftime("%Y%m%d") == ref_date:
                    row = df.loc[idx]
                    close = int(row.get('종가', 0))
                    # 네이버 일별 등락률은 직접 계산 (전전일 대비) — by_date 단일일은 등락률 미지원
                    # 대신 by_ticker 시도
                    real[code] = {'close': close, 'change_pct': None}
                    break
            time.sleep(0.1)
        except Exception:
            pass

    # change_pct 보강 — by_ticker 시장 단위 fetch (1번)
    try:
        for mkt in ['KOSPI', 'KOSDAQ']:
            df = nv.get_market_ohlcv_by_ticker(ref_date, market=mkt)
            for code in codes:
                if code in df.index and code in real:
                    real[code]['change_pct'] = float(df.loc[code].get('등락률', 0))
            time.sleep(0.1)
    except Exception:
        pass
    return real


def previous_business_day(date_str: str) -> str:
    """date_str의 직전 영업일 (월 → 금 처리)"""
    d = datetime.strptime(date_str, "%Y%m%d")
    while True:
        d -= timedelta(days=1)
        if d.weekday() < 5:  # 월~금
            return d.strftime("%Y%m%d")


def verify_date(date: str, verbose: bool = True) -> dict:
    teams = collect_selections(date)
    if not teams:
        if verbose:
            print(f"[{date}] selection.json 없음 - 스킵")
        return None

    # 선정 시점 기준일 = selection.json 의 date 필드 (전일 종가 기반)
    # 일자 통일을 위해 첫 selection 의 date 사용
    ref_date = next(iter(teams.values())).get('date', previous_business_day(date))

    # 모든 종목 코드 모음
    all_codes = set()
    for s in teams.values():
        for c in s.get('candidates', s.get('selected', [])):
            all_codes.add(c['code'])

    real = get_real_prices(list(all_codes), ref_date)

    # 팀별 메트릭
    team_metrics = {}
    duplicate_counter = {}
    total_picks = 0
    total_shortfall = 0
    sum_avg_score = 0
    sum_price_err = 0
    sum_change_err = 0
    n_price_compared = 0
    n_change_compared = 0
    n_active_teams = 0

    rows = []  # 결함 row 만 (alert용)

    for tid, s in teams.items():
        cands = s.get('candidates') or s.get('selected', [])
        n_sel = len(cands)
        scores = [c.get('score', 0) for c in cands]
        avg_score = sum(scores) / max(len(scores), 1) if scores else 0
        min_score = min(scores) if scores else 0
        shortfall = max(0, TOP_N_TARGET - n_sel)

        # 가격/등락률 검증
        price_diffs = []
        change_diffs = []
        for c in cands:
            duplicate_counter[c['code']] = duplicate_counter.get(c['code'], 0) + 1
            r = real.get(c['code'])
            if r and r.get('close'):
                sel_price = c.get('price', 0)
                if sel_price:
                    diff_pct = abs(sel_price - r['close']) / r['close'] * 100
                    price_diffs.append(diff_pct)
                    if diff_pct > 1.0:
                        rows.append({
                            'team': tid, 'code': c['code'], 'name': c['name'],
                            'flag': 'STALE_PRICE',
                            'sel_price': sel_price, 'real_close': r['close'],
                            'diff_pct': round(diff_pct, 2),
                        })
            if r and r.get('change_pct') is not None:
                sel_chg = c.get('change_pct', 0)
                diff = abs(sel_chg - r['change_pct'])
                change_diffs.append(diff)
                if diff > 0.5:
                    rows.append({
                        'team': tid, 'code': c['code'], 'name': c['name'],
                        'flag': 'STALE_CHANGE',
                        'sel_change': sel_chg, 'real_change': r['change_pct'],
                        'diff': round(diff, 2),
                    })

        avg_price_err = sum(price_diffs) / max(len(price_diffs), 1) if price_diffs else 0
        avg_change_err = sum(change_diffs) / max(len(change_diffs), 1) if change_diffs else 0

        team_metrics[tid] = {
            'strategy_id': s.get('strategy_id', ''),
            'n_selected': n_sel,
            'shortfall': shortfall,
            'avg_score': round(avg_score, 1),
            'min_score': round(min_score, 1),
            'avg_price_err_pct': round(avg_price_err, 3),
            'avg_change_err': round(avg_change_err, 3),
            'n_price_compared': len(price_diffs),
            'n_change_compared': len(change_diffs),
        }
        total_picks += n_sel
        total_shortfall += shortfall
        sum_avg_score += avg_score
        sum_price_err += sum(price_diffs)
        sum_change_err += sum(change_diffs)
        n_price_compared += len(price_diffs)
        n_change_compared += len(change_diffs)
        n_active_teams += 1

    # 종합 통계
    duplicates = {code: cnt for code, cnt in duplicate_counter.items() if cnt > 1}

    overall = {
        'date': date,
        'reference_date': ref_date,
        'n_teams': n_active_teams,
        'total_picks': total_picks,
        'total_shortfall': total_shortfall,
        'shortfall_rate_pct': round(total_shortfall / max(n_active_teams * TOP_N_TARGET, 1) * 100, 1),
        'avg_team_avg_score': round(sum_avg_score / max(n_active_teams, 1), 1),
        'overall_avg_price_err_pct': round(sum_price_err / max(n_price_compared, 1), 3),
        'overall_avg_change_err': round(sum_change_err / max(n_change_compared, 1), 3),
        'n_real_missing': len(all_codes) - len(real),
        'n_duplicates': len(duplicates),
    }

    out = OUT_DIR / f"selection_quality_{date}.json"
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({
            'overall': overall,
            'team_metrics': team_metrics,
            'duplicates': duplicates,
            'mismatch_rows': rows,
        }, f, ensure_ascii=False, indent=2)

    if verbose:
        print(f"\n=== [{date}] 선정 품질 (전일 ref={ref_date}) ===")
        print(f"{'team':<7}{'strategy':<22}{'n_sel':>6}{'short':>6}{'avg_sc':>7}{'min_sc':>7}{'price_err%':>11}{'chg_err':>9}")
        for tid, m in team_metrics.items():
            print(f"{tid:<7}{m['strategy_id']:<22}{m['n_selected']:>6}{m['shortfall']:>6}{m['avg_score']:>7.1f}{m['min_score']:>7.1f}{m['avg_price_err_pct']:>11.3f}{m['avg_change_err']:>9.3f}")
        print(f"\n전체: 활성 {n_active_teams}팀, 선정 {total_picks}/{n_active_teams*TOP_N_TARGET}, 부족 {total_shortfall}건 ({overall['shortfall_rate_pct']}%)")
        print(f"중복 종목 {len(duplicates)}개: {list(duplicates.items())[:5]}")
        print(f"평균 가격 오차 {overall['overall_avg_price_err_pct']}%, 등락률 오차 {overall['overall_avg_change_err']}%p")

    return {
        'date': date,
        'overall': overall,
        'team_metrics': team_metrics,
        'mismatch_rows': rows,
    }


def update_summary(results):
    """누적 시계열 + alert"""
    summary_path = OUT_DIR / "selection_quality_summary.json"
    summary = {"history": [], "alerts": [], "thresholds": THRESHOLDS}
    if summary_path.exists():
        try:
            with open(summary_path) as f:
                summary = json.load(f)
        except Exception:
            pass

    history_by_date = {h['date']: h for h in summary.get('history', [])}
    for s in results:
        history_by_date[s['date']] = s['overall']
    summary['history'] = sorted(history_by_date.values(), key=lambda x: x['date'])

    # rolling 5거래일
    recent = summary['history'][-5:]
    if recent:
        summary['rolling_5d'] = {
            'days': len(recent),
            'shortfall_rate_pct_avg': round(sum(h['shortfall_rate_pct'] for h in recent) / len(recent), 1),
            'avg_score_avg': round(sum(h['avg_team_avg_score'] for h in recent) / len(recent), 1),
            'price_err_pct_avg': round(sum(h['overall_avg_price_err_pct'] for h in recent) / len(recent), 3),
            'first_date': recent[0]['date'],
            'last_date': recent[-1]['date'],
        }

    # alert
    alerts = []
    th = summary.get('thresholds', THRESHOLDS)
    for h in summary['history']:
        if h['shortfall_rate_pct'] > th['max_shortfall_rate_pct']:
            alerts.append({'date': h['date'], 'severity': 'warn', 'code': 'W_SELECTION_SHORTFALL',
                          'message': f"선정 부족율 {h['shortfall_rate_pct']}% > {th['max_shortfall_rate_pct']}%"})
        if h['avg_team_avg_score'] < th['min_avg_score']:
            alerts.append({'date': h['date'], 'severity': 'warn', 'code': 'W_LOW_SCORE',
                          'message': f"팀 평균 점수 {h['avg_team_avg_score']} < {th['min_avg_score']}"})
        if h['overall_avg_price_err_pct'] > th['max_price_diff_pct']:
            alerts.append({'date': h['date'], 'severity': 'warn', 'code': 'W_STALE_PRICE',
                          'message': f"평균 가격 오차 {h['overall_avg_price_err_pct']}% > {th['max_price_diff_pct']}%"})
        if h['overall_avg_change_err'] > th['max_change_diff_pct']:
            alerts.append({'date': h['date'], 'severity': 'warn', 'code': 'W_STALE_CHANGE',
                          'message': f"등락률 오차 {h['overall_avg_change_err']}%p > {th['max_change_diff_pct']}%p"})
    summary['alerts'] = alerts
    summary['last_updated'] = datetime.now(KST).isoformat()

    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary


def today_kst() -> str:
    return datetime.now(KST).strftime("%Y%m%d")


if __name__ == '__main__':
    dates = sys.argv[1:] if len(sys.argv) > 1 else [today_kst()]
    all_results = []
    for d in dates:
        s = verify_date(d)
        if s:
            all_results.append(s)

    if all_results:
        summary = update_summary(all_results)

        print(f"\n{'='*60}\n=== 누적 시계열 (data/arena/audit/selection_quality_summary.json) ===")
        print(f"{'date':<10}{'팀':>4}{'선정':>6}{'부족%':>7}{'평균점수':>9}{'price_err%':>11}{'chg_err':>9}")
        for h in summary['history'][-10:]:
            print(f"{h['date']:<10}{h['n_teams']:>4}{h['total_picks']:>6}{h['shortfall_rate_pct']:>6.1f}%{h['avg_team_avg_score']:>9.1f}{h['overall_avg_price_err_pct']:>11.3f}{h['overall_avg_change_err']:>9.3f}")

        if 'rolling_5d' in summary:
            r = summary['rolling_5d']
            print(f"\n[rolling {r['days']}거래일] 부족율 {r['shortfall_rate_pct_avg']}%, 평균점수 {r['avg_score_avg']}, 가격오차 {r['price_err_pct_avg']}%")

        if summary.get('alerts'):
            print(f"\n⚠️ Alerts ({len(summary['alerts'])}건):")
            for a in summary['alerts']:
                print(f"  [{a['code']}] {a['date']}: {a['message']}")
        else:
            print("\n✅ Alerts: 없음")

        # GitHub Actions Step Summary
        gh_summary_path = os.environ.get('GITHUB_STEP_SUMMARY')
        if gh_summary_path:
            with open(gh_summary_path, 'a', encoding='utf-8') as gs:
                gs.write("\n## 🎯 선정 품질 검증\n\n")
                gs.write("| 날짜 | 팀 | 선정 | 부족율 | 평균점수 | 가격오차% | 등락률오차%p |\n")
                gs.write("|---|---:|---:|---:|---:|---:|---:|\n")
                for h in summary['history'][-5:]:
                    gs.write(f"| {h['date']} | {h['n_teams']} | {h['total_picks']} | {h['shortfall_rate_pct']}% | {h['avg_team_avg_score']} | {h['overall_avg_price_err_pct']} | {h['overall_avg_change_err']} |\n")
                if 'rolling_5d' in summary:
                    r = summary['rolling_5d']
                    gs.write(f"\n**Rolling {r['days']}거래일**: 부족율 {r['shortfall_rate_pct_avg']}%, 평균점수 {r['avg_score_avg']}, 가격오차 {r['price_err_pct_avg']}%  \n\n")
                alerts = summary.get('alerts', [])
                if alerts:
                    gs.write(f"### ⚠️ Alerts ({len(alerts)}건)\n")
                    for a in alerts:
                        gs.write(f"- **{a['code']}** ({a['date']}): {a['message']}\n")
                else:
                    gs.write("### ✅ Alerts: 없음\n")
