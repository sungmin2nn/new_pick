#!/usr/bin/env python3
"""
A/B 테스트: theme_cap ON vs OFF

방식:
  1. 과거 candidates_<date>.json / bollinger_candidates_<date>.json 스냅샷 사용
     (스냅샷은 cap 도입 전이라 cap-OFF 베이스라인)
  2. cap-OFF 픽 = 스냅샷 그대로
     cap-ON  픽 = theme_cap 적용 (max_per_theme=2)
  3. 각 픽의 hold_days 영업일 후 close-to-close 수익률 계산
  4. 일자별·전략별 mean return / win rate 집계

한계:
  - 스냅샷이 이미 top_n=20 으로 잘려서, cap-ON 의 "대체 후보 진입" 효과는 못 봄
    → cap-ON 선정 수가 작을수록(2~3개) noise 큼
  - close-to-close, 슬리피지 무시
  - 테마 인덱스가 현 시점 정적 스냅샷 (이전 날짜에 대한 lookahead bias 가능)

용법:
  python -m scripts.ab_theme_cap                  # 기본 hold=5, days=10
  python -m scripts.ab_theme_cap --hold 3 --days 14
"""

import argparse
import json
import sys
import warnings
from pathlib import Path
from statistics import mean
from typing import List, Dict, Optional, Tuple

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

warnings.filterwarnings("ignore")

from paper_trading.utils.theme_cap import apply_theme_cap

DATA_DIR = PROJECT_ROOT / "data" / "bnf"

STRATEGIES = {
    "BNF":       {"prefix": "candidates_",           "code_key": "code"},
    "Bollinger": {"prefix": "bollinger_candidates_", "code_key": "code"},
}


def list_snapshot_dates(prefix: str, n: int) -> List[str]:
    files = sorted(DATA_DIR.glob(f"{prefix}*.json"))
    dates: List[str] = []
    for f in files:
        stem = f.stem.replace(prefix, "")
        if stem.isdigit() and len(stem) == 8:
            dates.append(stem)
    return dates[-n:]


def load_snapshot(prefix: str, date: str) -> List[Dict]:
    p = DATA_DIR / f"{prefix}{date}.json"
    if not p.exists():
        return []
    with open(p, "r", encoding="utf-8") as f:
        d = json.load(f)
    return d.get("candidates", []) or []


def forward_return_pct(code: str, date: str, hold_days: int) -> Optional[float]:
    """date 종가 기준, hold_days 영업일 후 종가까지의 수익률 (%)."""
    from datetime import datetime, timedelta
    from pykrx import stock as pykrx_stock

    start = datetime.strptime(date, "%Y%m%d")
    end = start + timedelta(days=hold_days * 2 + 10)  # 영업일 변환 여유
    try:
        df = pykrx_stock.get_market_ohlcv(
            start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), code
        )
    except Exception:
        return None
    if df is None or df.empty:
        return None
    df = df[df["종가"] > 0]
    if df.empty or date not in df.index.strftime("%Y%m%d").tolist():
        return None
    idx_list = df.index.strftime("%Y%m%d").tolist()
    entry_i = idx_list.index(date)
    exit_i = entry_i + hold_days
    if exit_i >= len(df):
        return None
    entry = float(df["종가"].iloc[entry_i])
    exit_ = float(df["종가"].iloc[exit_i])
    if entry <= 0:
        return None
    return (exit_ - entry) / entry * 100.0


def evaluate(picks: List[Dict], date: str, hold_days: int,
             ret_cache: Dict[Tuple[str, str], Optional[float]]) -> Tuple[Dict, List[float]]:
    """캐시 활용해 forward return 계산. (요약, 유효 returns 리스트) 반환."""
    rets: List[float] = []
    skipped = 0
    for c in picks:
        code = c.get("code")
        if not code:
            skipped += 1
            continue
        key = (code, date)
        if key not in ret_cache:
            ret_cache[key] = forward_return_pct(code, date, hold_days)
        r = ret_cache[key]
        if r is None:
            skipped += 1
            continue
        rets.append(r)
    if not rets:
        return ({"n": 0, "mean_pct": None, "win_rate": None, "skipped": skipped}, rets)
    wins = sum(1 for r in rets if r > 0)
    return ({
        "n": len(rets),
        "mean_pct": round(mean(rets), 3),
        "win_rate": round(100.0 * wins / len(rets), 1),
        "skipped": skipped,
    }, rets)


def run_strategy(label: str, prefix: str, hold_days: int, days: int,
                 max_per_theme: int) -> Tuple[List[Dict], Dict]:
    dates = list_snapshot_dates(prefix, days)
    if not dates:
        print(f"  [{label}] 스냅샷 없음")
        return [], {}

    rows = []
    agg_off: List[float] = []
    agg_on: List[float] = []
    ret_cache: Dict[Tuple[str, str], Optional[float]] = {}

    for date in dates:
        pool = load_snapshot(prefix, date)
        if not pool:
            continue
        cap_off = pool
        cap_on = apply_theme_cap(
            pool, get_code=lambda c: c["code"],
            top_n=len(pool), max_per_theme=max_per_theme,
        )
        e_off, r_off = evaluate(cap_off, date, hold_days, ret_cache)
        e_on, r_on = evaluate(cap_on, date, hold_days, ret_cache)
        rows.append({"date": date, "off": e_off, "on": e_on})
        agg_off.extend(r_off)
        agg_on.extend(r_on)

    def _summary(rets: List[float]) -> Dict:
        if not rets:
            return {"trades": 0, "mean_pct": None, "win_rate": None}
        wins = sum(1 for r in rets if r > 0)
        return {
            "trades": len(rets),
            "mean_pct": round(mean(rets), 3),
            "win_rate": round(100.0 * wins / len(rets), 1),
        }

    return rows, {"off": _summary(agg_off), "on": _summary(agg_on)}


def fmt_eval(e: Dict) -> str:
    if e.get("mean_pct") is None:
        return f"n={e.get('n', 0):2d} (skipped {e.get('skipped', 0)})"
    return f"n={e['n']:2d} mean={e['mean_pct']:+.2f}% win={e['win_rate']:.1f}%"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hold", type=int, default=5, help="보유 영업일 수")
    ap.add_argument("--days", type=int, default=10, help="최근 N영업일 스냅샷")
    ap.add_argument("--cap", type=int, default=2, help="cap-ON 시 max_per_theme")
    args = ap.parse_args()

    print(f"=== A/B theme_cap (hold={args.hold}d, days={args.days}, cap={args.cap}) ===\n")

    for label, cfg in STRATEGIES.items():
        print(f"\n[{label}]")
        rows, summary = run_strategy(
            label, cfg["prefix"], args.hold, args.days, args.cap
        )
        if not rows:
            continue
        print(f"  {'date':10s} | {'OFF':40s} | ON")
        for row in rows:
            print(f"  {row['date']:10s} | {fmt_eval(row['off']):40s} | {fmt_eval(row['on'])}")

        s_off = summary.get("off", {})
        s_on = summary.get("on", {})
        print(f"\n  [{label} 누적]")
        print(f"    OFF: {s_off}")
        print(f"    ON : {s_on}")
        if s_off.get("mean_pct") is not None and s_on.get("mean_pct") is not None:
            delta = s_on["mean_pct"] - s_off["mean_pct"]
            print(f"    Δ mean: {delta:+.3f}%p  (cap ON - OFF)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
