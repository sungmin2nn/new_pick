"""
매수 가이드 (옵션 B 메시지 2) — 다음 거래일 08:00 KST 자동 발송 (영업일만).

내용:
  Arena 8전략별 후보 종목 (각 상위 3)
  BNF 후보
  Bollinger 후보 (스윙 — 신규 신호 있을 때만)
  진입 시점 / 리스크 한도 / 자본 배분

사용:
  python scripts/morning_guide.py              # 실 발송 (오늘 = 영업일일 때)
  python scripts/morning_guide.py --dry-run    # 표준출력만
  python scripts/morning_guide.py --force      # 휴장일이어도 발송
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from telegram_notifier import TelegramNotifier  # noqa: E402
from utils import is_market_day  # noqa: E402

KST = timezone(timedelta(hours=9))
DATA_PT = ROOT / "data" / "paper_trading"
DATA_BNF = ROOT / "data" / "bnf"

STRATEGY_LABEL = {
    "momentum": "a Momentum",
    "dart_disclosure": "c DART",
    "theme_policy": "d Theme",
    "frontier_gap": "e Frontier",
    "volatility_breakout_lw": "f Volatility",
    "turtle_breakout_short": "g Turtle",
    "sector_rotation": "h Sector",
    "hybrid_alpha_delta": "i Hybrid",
}

TOP_N_PER_STRATEGY = 3
TOP_N_BNF = 3
TOP_N_BOLLINGER = 3


def fmt_date_label(yyyymmdd: str) -> str:
    if not yyyymmdd or len(yyyymmdd) != 8:
        return yyyymmdd or "-"
    y, m, d = int(yyyymmdd[0:4]), int(yyyymmdd[4:6]), int(yyyymmdd[6:8])
    dow = ["월", "화", "수", "목", "금", "토", "일"][datetime(y, m, d).weekday()]
    return f"{yyyymmdd[0:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]} ({dow})"


def latest_strategies_file(target_date: str) -> Path | None:
    """target_date의 candidates_<date>_all.json. 없으면 가장 최근."""
    target = DATA_PT / f"candidates_{target_date}_all.json"
    if target.exists():
        return target
    files = sorted(DATA_PT.glob("candidates_*_all.json"))
    return files[-1] if files else None


def latest_bnf_file(target_date: str) -> Path | None:
    target = DATA_BNF / f"candidates_{target_date}.json"
    if target.exists():
        return target
    files = sorted(
        f for f in DATA_BNF.glob("candidates_2[0-9]*.json") if f.name != "candidates.json"
    )
    return files[-1] if files else None


def latest_bollinger_file(target_date: str) -> Path | None:
    target = DATA_BNF / f"bollinger_candidates_{target_date}.json"
    if target.exists():
        return target
    files = sorted(DATA_BNF.glob("bollinger_candidates_2[0-9]*.json"))
    return files[-1] if files else None


def build_arena_section(target_date: str) -> tuple[list[str], str | None]:
    """(lines, used_file_date or None)"""
    f = latest_strategies_file(target_date)
    if not f:
        return ["<b>[Arena]</b> 후보 파일 없음"], None
    used_date = f.stem.split("_")[1]  # candidates_YYYYMMDD_all
    L: list[str] = []
    if used_date != target_date:
        L.append(f"<i>※ {target_date} 후보 미생성 — {used_date} 사용</i>")
    with open(f, encoding="utf-8") as fp:
        data = json.load(fp)
    strats = data.get("strategies", {})
    for sid, label in STRATEGY_LABEL.items():
        info = strats.get(sid, {})
        cands = info.get("candidates", [])[:TOP_N_PER_STRATEGY]
        if not cands:
            continue
        L.append(f"<b>{label}</b>")
        L.append("<pre>")
        for c in cands:
            code = c.get("code", "")
            name = (c.get("name", "") or "")[:7]
            price = c.get("price", 0)
            score = c.get("score", 0)
            L.append(f"{code} {name:7s} {price:>7,} ({score:.0f})")
        L.append("</pre>")
    return L, used_date


def build_bnf_section(target_date: str) -> list[str]:
    f = latest_bnf_file(target_date)
    L = ["<b>[BNF 후보]</b>"]
    if not f:
        L.append("  (파일 없음)")
        return L
    used_date = f.stem.split("_")[1] if "_" in f.stem else "?"
    if used_date != target_date:
        L.append(f"  <i>※ {used_date} 사용</i>")
    with open(f, encoding="utf-8") as fp:
        data = json.load(fp)
    cands = data.get("candidates", [])[:TOP_N_BNF]
    if not cands:
        L.append("  (선정 없음)")
        return L
    L.append("<pre>")
    for c in cands:
        code = c.get("code", "")
        name = (c.get("name", "") or "")[:7]
        ch = c.get("change_pct", 0)
        L.append(f"{code} {name:7s} {ch:+6.2f}%")
    L.append("</pre>")
    return L


def build_bollinger_section(target_date: str) -> list[str]:
    f = latest_bollinger_file(target_date)
    L = ["<b>[Bollinger 후보]</b>"]
    if not f:
        L.append("  (파일 없음)")
        return L
    with open(f, encoding="utf-8") as fp:
        data = json.load(fp)
    cands = data.get("candidates", [])[:TOP_N_BOLLINGER]
    if not cands:
        L.append("  (신호 없음)")
        return L
    L.append("<pre>")
    for c in cands:
        code = c.get("code", "")
        name = (c.get("name", "") or "")[:7]
        L.append(f"{code} {name:7s}")
    L.append("</pre>")
    return L


def build_message(target_date: str) -> str:
    date_label = fmt_date_label(target_date)
    L = [
        f"📋 <b>매수 가이드 · {date_label}</b>",
        "━━━━━━━━━━━━━━━━━━━",
    ]
    arena_lines, _ = build_arena_section(target_date)
    L.extend(arena_lines)
    L.extend(build_bnf_section(target_date))
    L.extend(build_bollinger_section(target_date))
    L.append("━━━━━━━━━━━━━━━━━━━")
    L.append("<b>[진입]</b> 09:00~09:05 시초가")
    L.append("<b>[리스크]</b> 손절 -3% / 익절 +5%")
    L.append("<b>[자본]</b> Arena 8팀 × 5종목 × 20만원")
    return "\n".join(L)


def main() -> int:
    parser = argparse.ArgumentParser(description="매수 가이드 (옵션 B 메시지 2)")
    parser.add_argument("--dry-run", action="store_true", help="표준출력만")
    parser.add_argument("--force", action="store_true",
                        help="휴장일에도 발송")
    parser.add_argument("--date", type=str, default="",
                        help="대상 날짜 (YYYYMMDD). 미지정 시 오늘 KST")
    args = parser.parse_args()

    today = datetime.now(KST)
    if args.date:
        target_date = args.date
    else:
        target_date = today.strftime("%Y%m%d")

    if not args.force:
        # 오늘이 휴장일이면 skip (단, --date 명시 시엔 그 날짜 기준)
        check_dt = datetime.strptime(target_date, "%Y%m%d")
        if not is_market_day(check_dt):
            print(f"[morning_guide] {target_date} 는 휴장일 — skip (강제 발송: --force)")
            return 0

    msg = build_message(target_date)
    print(f"[morning_guide] target={target_date}, length={len(msg)} chars")

    if args.dry_run:
        print("---")
        print(msg)
        return 0

    notifier = TelegramNotifier()
    if not notifier.is_configured():
        print("[Error] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 미설정", file=sys.stderr)
        return 1
    ok = notifier.send_message(msg, parse_mode="HTML")
    if not ok:
        print("[Error] 텔레그램 발송 실패", file=sys.stderr)
        return 1
    print("[morning_guide] 발송 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
