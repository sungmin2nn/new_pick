"""
Discovery CLI
==============
발굴된 후보를 사용자가 검토/승인/거부하는 CLI.

명령:
    list          — 모든 상태 요약
    pending       — pending 목록 (검토 대기)
    show <id>     — 단일 후보 상세
    approve <id>  — pending → approved
    reject <id>   — pending → rejected
    review        — 인터랙티브 검토 모드
    log           — 최근 발굴 이력

사용:
    python3 -m runner.discovery_cli list
    python3 -m runner.discovery_cli pending
    python3 -m runner.discovery_cli show disc_20260411_...
    python3 -m runner.discovery_cli approve disc_20260411_... --notes "가치 있음"
    python3 -m runner.discovery_cli review
"""

from __future__ import annotations

import argparse
import sys
from textwrap import shorten

from lab.discovery import DiscoveryQueue, DiscoveryStatus, DiscoveryCandidate


def _status_color(status: str) -> str:
    """ANSI 색상 코드 (짧은 표기)."""
    return {
        "pending": "⏳",
        "approved": "✅",
        "coded": "🏭",
        "rejected": "❌",
    }.get(status, "❓")


def _trust_badge(trust: str) -> str:
    return {
        "verified": "★★★★★",
        "high": "★★★★",
        "medium": "★★★",
        "low": "★★",
        "unverified": "★",
    }.get(trust, "?")


def cmd_list(args) -> int:
    q = DiscoveryQueue()
    stats = q.stats()
    total = sum(stats.values())
    print()
    print(f"=== Discovery Queue ({total} total) ===")
    for s in DiscoveryStatus:
        count = stats.get(s.value, 0)
        print(f"  {_status_color(s.value)} {s.value:>10}: {count:>3}")
    return 0


def cmd_pending(args) -> int:
    q = DiscoveryQueue()
    cands = q.list(DiscoveryStatus.PENDING)
    if not cands:
        print("(pending 큐 비어있음)")
        return 0

    print(f"\n=== Pending Queue ({len(cands)}) ===\n")
    for c in cands:
        title = shorten(c.title, width=60, placeholder="...")
        hyp = shorten(c.hypothesis, width=70, placeholder="...")
        print(f"  {c.id}")
        print(f"    제목     : {title}")
        print(f"    출처     : {c.source_type} ({_trust_badge(c.trust_level)})")
        print(f"    카테고리 : {c.category_guess}  / 리스크 {c.risk_level_guess}  / 참신성 ★{c.novelty_score}")
        print(f"    가설     : {hyp}")
        if c.source_url:
            print(f"    URL      : {c.source_url}")
        print()
    return 0


def cmd_show(args) -> int:
    q = DiscoveryQueue()
    cand = q.get(args.id)
    if not cand:
        print(f"후보를 찾을 수 없음: {args.id}", file=sys.stderr)
        return 1

    print(f"\n=== {cand.id} ({cand.status}) ===\n")
    print(f"제목                : {cand.title}")
    print(f"발굴 시각           : {cand.discovered_at}")
    print(f"발굴자              : {cand.discovered_by}")
    print()
    print(f"[출처]")
    print(f"  type              : {cand.source_type}")
    print(f"  url               : {cand.source_url}")
    print(f"  author            : {cand.source_author}")
    print(f"  published         : {cand.source_published}")
    print(f"  trust_level       : {cand.trust_level} {_trust_badge(cand.trust_level)}")
    print()
    print(f"[추정 메타]")
    print(f"  category_guess    : {cand.category_guess}")
    print(f"  risk_level_guess  : {cand.risk_level_guess}")
    print(f"  novelty_score     : {cand.novelty_score}/10")
    print(f"  holding_days      : {cand.target_holding_days}")
    print(f"  requires_intraday : {cand.requires_intraday}")
    print(f"  data_requirements : {', '.join(cand.data_requirements) or '(none)'}")
    print()
    print(f"[가설]")
    print(f"  {cand.hypothesis}")
    print()
    print(f"[근거]")
    print(f"  {cand.rationale}")
    print()
    print(f"[기대 수익 원천]")
    print(f"  {cand.expected_edge}")
    print()
    print(f"[기존 전략과의 차이]")
    print(f"  {cand.differs_from_existing_guess}")
    print()
    if cand.raw_snippet:
        print(f"[원본 발췌]")
        print(f"  {shorten(cand.raw_snippet, width=300, placeholder='...')}")
        print()
    if cand.status != DiscoveryStatus.PENDING.value:
        print(f"[리뷰]")
        print(f"  reviewed_at: {cand.reviewed_at}")
        print(f"  reviewer   : {cand.reviewer}")
        print(f"  notes      : {cand.review_notes}")
    if cand.coded_file:
        print(f"  coded_file : {cand.coded_file}")
    return 0


def cmd_approve(args) -> int:
    q = DiscoveryQueue()
    result = q.approve(args.id, reviewer=args.reviewer, notes=args.notes)
    if not result:
        print(f"후보를 찾을 수 없음: {args.id}", file=sys.stderr)
        return 1
    print(f"✅ Approved: {result.id}")
    return 0


def cmd_reject(args) -> int:
    q = DiscoveryQueue()
    result = q.reject(args.id, reviewer=args.reviewer, notes=args.notes)
    if not result:
        print(f"후보를 찾을 수 없음: {args.id}", file=sys.stderr)
        return 1
    print(f"❌ Rejected: {result.id}")
    return 0


def cmd_review(args) -> int:
    """pending 큐를 하나씩 인터랙티브 검토."""
    q = DiscoveryQueue()
    cands = q.list(DiscoveryStatus.PENDING)
    if not cands:
        print("(pending 큐 비어있음)")
        return 0

    print(f"\n=== Interactive Review ({len(cands)} candidates) ===")
    print("명령: [a]pprove / [r]eject / [s]kip / [q]uit\n")

    for i, c in enumerate(cands, 1):
        print(f"\n--- [{i}/{len(cands)}] ---")
        print(f"ID        : {c.id}")
        print(f"제목      : {c.title}")
        print(f"출처      : {c.source_type} ({_trust_badge(c.trust_level)})")
        print(f"카테고리  : {c.category_guess}  / 참신성 ★{c.novelty_score}")
        print(f"가설      : {c.hypothesis}")
        print(f"기대 수익 : {c.expected_edge}")
        print(f"차별점    : {c.differs_from_existing_guess}")
        if c.source_url:
            print(f"URL       : {c.source_url}")

        try:
            action = input("\n결정 [a/r/s/q]: ").strip().lower()
        except EOFError:
            break

        if action == "q":
            print("중단")
            break
        elif action == "a":
            notes = input("  승인 메모 (Enter 건너뜀): ").strip()
            q.approve(c.id, reviewer="user", notes=notes)
            print(f"  ✅ approved")
        elif action == "r":
            notes = input("  거부 사유 (Enter 건너뜀): ").strip()
            q.reject(c.id, reviewer="user", notes=notes)
            print(f"  ❌ rejected")
        elif action == "s":
            print("  ⏭  skip")
        else:
            print("  (알 수 없는 명령, skip)")

    print()
    print(f"최종 stats: {q.stats()}")
    return 0


def cmd_log(args) -> int:
    q = DiscoveryQueue()
    entries = q.get_log(limit=args.limit)
    if not entries:
        print("(로그 없음)")
        return 0

    print(f"\n=== Discovery Log (last {len(entries)}) ===\n")
    for e in entries:
        ts = e.get("timestamp", "")[:19]
        action = e.get("action", "")
        title = shorten(e.get("title", ""), width=50, placeholder="...")
        print(f"  {ts}  {action:20}  {e.get('id', '')[:22]}  {title}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Discovery Queue CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="상태 요약")
    sub.add_parser("pending", help="pending 목록")

    p_show = sub.add_parser("show", help="단일 후보 상세")
    p_show.add_argument("id")

    p_app = sub.add_parser("approve", help="pending → approved")
    p_app.add_argument("id")
    p_app.add_argument("--reviewer", default="user")
    p_app.add_argument("--notes", default="")

    p_rej = sub.add_parser("reject", help="pending → rejected")
    p_rej.add_argument("id")
    p_rej.add_argument("--reviewer", default="user")
    p_rej.add_argument("--notes", default="")

    sub.add_parser("review", help="인터랙티브 검토 모드")

    p_log = sub.add_parser("log", help="발굴 이력")
    p_log.add_argument("--limit", type=int, default=30)

    args = parser.parse_args()
    cmds = {
        "list": cmd_list,
        "pending": cmd_pending,
        "show": cmd_show,
        "approve": cmd_approve,
        "reject": cmd_reject,
        "review": cmd_review,
        "log": cmd_log,
    }
    return cmds[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
