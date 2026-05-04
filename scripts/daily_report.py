"""
일일 리포트 (옵션 B 메시지 1) — 장 마감 후 매일 16:35 KST 자동 발송.

내용:
  [Arena 8팀] 누적%·MDD%·승률 표
  [BNF]       자본·누적%·승률·보유·쿨다운
  [Bollinger] 거래·승률·실현손익
  [정합성]    verify_facts 결과 ✓/⚠
  [Actions]   GitHub Actions 어제 status (현재 placeholder)
  [시장]      KOSPI/KOSDAQ (현재 placeholder — 별도 트랙)
  ⚠ 의사결정 트리거: MDD>5%, cum<-10% 등
  📌 Phase 1→2 게이트: 30일+ 표본 + cum>=5% + MDD<=3% + WR>=55%

사용:
  python scripts/daily_report.py              # 실 발송
  python scripts/daily_report.py --dry-run    # 표준출력만 (텔레그램 미발송)
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 프로젝트 루트
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from telegram_notifier import TelegramNotifier  # noqa: E402

KST = timezone(timedelta(hours=9))
ARENA_DIR = ROOT / "data" / "arena"
BNF_DIR = ROOT / "data" / "bnf"

# 활성 8팀 (team_b는 archived)
ACTIVE_TEAMS = [
    ("team_a", "a Mom"),
    ("team_c", "c DRT"),
    ("team_d", "d Thm"),
    ("team_e", "e Frt"),
    ("team_f", "f Vol"),
    ("team_g", "g Tur"),
    ("team_h", "h Sec"),
    ("team_i", "i Hyb"),
]

# Phase 1→2 게이트 임계
GATE_DAYS = 30
GATE_CUM_PCT = 5.0
GATE_MDD_PCT = 3.0
GATE_WR_PCT = 55.0

# 트리거 임계
TRIGGER_MDD_PCT = 5.0
TRIGGER_CUM_DOWN_PCT = -10.0


def load_facts() -> dict:
    """verify_facts 의 _verified_facts.json 로드"""
    path = ARENA_DIR / "_verified_facts.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} 없음 — verify_facts 먼저 실행")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def latest_arena_date(facts: dict) -> str | None:
    """모든 활성 팀의 data_health.last_date 중 가장 최근"""
    dates = []
    for tid, _ in ACTIVE_TEAMS:
        t = facts.get("arena", {}).get(tid, {})
        d = t.get("data_health", {}).get("last_date")
        if d:
            dates.append(d)
    return max(dates) if dates else None


def fmt_date_label(yyyymmdd: str) -> str:
    """20260504 → '2026-05-04 (월)'"""
    if not yyyymmdd or len(yyyymmdd) != 8:
        return yyyymmdd or "-"
    y, m, d = int(yyyymmdd[0:4]), int(yyyymmdd[4:6]), int(yyyymmdd[6:8])
    dow = ["월", "화", "수", "목", "금", "토", "일"][datetime(y, m, d).weekday()]
    return f"{yyyymmdd[0:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]} ({dow})"


def build_arena_section(facts: dict) -> list[str]:
    arena = facts.get("arena", {})
    days_max = max(
        (arena.get(tid, {}).get("operational_days", 0) for tid, _ in ACTIVE_TEAMS),
        default=0,
    )
    L = [f"<b>[Arena] 표본 {days_max}일</b>", "<pre>"]
    L.append(f"{'팀':5s} {'cum%':>7s} {'MDD%':>5s} {'WR%':>4s}")
    for tid, label in ACTIVE_TEAMS:
        t = arena.get(tid, {})
        cum = t.get("returns_capital_basis", {}).get("cumulative_pct", 0)
        mdd = t.get("drawdown", {}).get("max_pct_capital_basis", 0)
        wr = t.get("trades", {}).get("win_rate_pct", 0)
        L.append(f"{label:5s} {cum:+7.2f} {mdd:5.2f} {wr:4.0f}")
    L.append("</pre>")
    return L


def build_bnf_section(facts: dict) -> list[str]:
    bnf = facts.get("bnf", {})
    cap = bnf.get("capital_krw", {})
    ret = bnf.get("returns", {})
    tr = bnf.get("trades", {})
    L = [
        f"<b>[BNF]</b> 자본 {cap.get('current', 0):,}원 ({ret.get('cumulative_pct', 0):+.2f}%)",
        f"  거래 {tr.get('total', 0)}건 / 승률 {tr.get('win_rate_pct', 0):.0f}%",
    ]
    pos_path = BNF_DIR / "positions.json"
    if pos_path.exists():
        try:
            with open(pos_path, encoding="utf-8") as f:
                pos = json.load(f)
            active = len(pos.get("positions", []))
            cooldown = len(pos.get("cooldown_until", {}))
            L.append(f"  보유 {active} / 쿨다운 {cooldown}")
        except (json.JSONDecodeError, OSError):
            pass
    return L


def build_bollinger_section(facts: dict) -> list[str]:
    bol = facts.get("bollinger", {})
    tr = bol.get("trades", {})
    pnl = bol.get("realized_pnl_krw") or bol.get("realized_pnl") or 0
    return [
        f"<b>[Bollinger]</b> 거래 {tr.get('total', 0)} 승률 {tr.get('win_rate_pct', 0):.0f}%",
        f"  실현손익 {pnl:+,}원",
    ]


def build_integrity_section(facts: dict) -> list[str]:
    warnings = facts.get("warnings", [])
    serious = [w for w in warnings if w.get("severity") in ("warn", "error")]
    info = [w for w in warnings if w.get("severity") == "info"]
    L = ["<b>[정합성]</b>"]
    if not warnings:
        L.append("  ✓ 모든 검증 통과")
        return L
    if serious:
        L.append(f"  ⚠ 경고 {len(serious)}건")
        for w in serious[:3]:
            L.append(f"   · {w.get('code')} ({w.get('scope', '')})")
    if info:
        L.append(f"  ℹ info {len(info)}건 (자연 해소 진행)")
    return L


def build_triggers_section(facts: dict) -> list[str]:
    arena = facts.get("arena", {})
    triggered = []
    for tid, label in ACTIVE_TEAMS:
        t = arena.get(tid, {})
        mdd = t.get("drawdown", {}).get("max_pct_capital_basis", 0)
        cum = t.get("returns_capital_basis", {}).get("cumulative_pct", 0)
        if mdd > TRIGGER_MDD_PCT:
            triggered.append(f"  · {label} 자본 MDD {mdd:.2f}% 초과 {TRIGGER_MDD_PCT}%")
        if cum < TRIGGER_CUM_DOWN_PCT:
            triggered.append(f"  · {label} 누적 {cum:+.1f}% — 재설계 검토")
    L = ["<b>⚠ 의사결정 트리거</b>"]
    if not triggered:
        L.append("  (없음 — 모든 active 팀 정상)")
    else:
        L.extend(triggered)
    return L


def build_phase_gate_section(facts: dict) -> list[str]:
    arena = facts.get("arena", {})
    qualified = []
    for tid, label in ACTIVE_TEAMS:
        t = arena.get(tid, {})
        days = t.get("operational_days", 0)
        cum = t.get("returns_capital_basis", {}).get("cumulative_pct", 0)
        mdd = t.get("drawdown", {}).get("max_pct_capital_basis", 0)
        wr = t.get("trades", {}).get("win_rate_pct", 0)
        if (
            days >= GATE_DAYS
            and cum >= GATE_CUM_PCT
            and mdd <= GATE_MDD_PCT
            and wr >= GATE_WR_PCT
        ):
            qualified.append(f"  · {label}: cum={cum:+.1f}% MDD={mdd:.2f}% WR={wr:.0f}%")
    days_max = max(
        (arena.get(tid, {}).get("operational_days", 0) for tid, _ in ACTIVE_TEAMS),
        default=0,
    )
    L = ["<b>📌 다음 단계 (Phase 1→2 게이트)</b>"]
    if qualified:
        L.append("  모의투자 진입 후보:")
        L.extend(qualified)
    else:
        L.append(
            f"  표본 부족 (max {days_max}일 / 요건 {GATE_DAYS}일↑ · "
            f"cum≥{GATE_CUM_PCT:.0f}% · MDD≤{GATE_MDD_PCT:.0f}% · WR≥{GATE_WR_PCT:.0f}%)"
        )
    return L


def build_message(facts: dict) -> str:
    last_date = latest_arena_date(facts) or "-"
    date_label = fmt_date_label(last_date)
    L = [
        f"📊 <b>일일 리포트 · {date_label} 결과</b>",
        "━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    L.extend(build_arena_section(facts))
    L.extend(build_bnf_section(facts))
    L.append("")
    L.extend(build_bollinger_section(facts))
    L.append("")
    L.append("━━━━━━━━━━━━━━━━━━━")
    L.extend(build_integrity_section(facts))
    L.append("")
    L.append("<b>[Actions]</b> <i>(자동 수집 미구현)</i>")
    L.append("<b>[시장]</b> <i>(자동 수집 미구현)</i>")
    L.append("")
    L.extend(build_triggers_section(facts))
    L.append("")
    L.extend(build_phase_gate_section(facts))
    return "\n".join(L)


def main() -> int:
    parser = argparse.ArgumentParser(description="일일 리포트 (옵션 B 메시지 1)")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="표준출력만 (텔레그램 미발송)",
    )
    args = parser.parse_args()

    try:
        facts = load_facts()
    except FileNotFoundError as e:
        print(f"[Error] {e}", file=sys.stderr)
        return 1

    msg = build_message(facts)
    print(f"[daily_report] message length = {len(msg)} chars")

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
    print("[daily_report] 발송 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
