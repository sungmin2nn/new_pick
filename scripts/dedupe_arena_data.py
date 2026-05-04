"""
Arena 데이터 중복 누적 1회성 정정 스크립트
- ISSUE-015: leaderboard.daily_history 동일 날짜 중복
- ISSUE-018: portfolio.total_trades 와 daily/<date>/trades.json 합산 불일치

처리 방식:
1) leaderboard.daily_history 를 date 로 dedupe (마지막 entry 유지)
2) 팀별 portfolio.json 을 daily/<date>/trades.json 시계열로 재구성
3) leaderboard.teams[].{elo, rank counts, best/worst_day_return} 를 deduped history 로 재계산
4) 원본은 .backup_YYYYMMDD_HHMMSS 로 보존

사용:
  python scripts/dedupe_arena_data.py --dry-run    # 미리보기
  python scripts/dedupe_arena_data.py              # 실제 적용
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
ARENA_DIR = ROOT / "data" / "arena"

INITIAL_CAPITAL = 10_000_000
INITIAL_ELO = 1000
K_FACTOR_ADJACENT = 16
K_FACTOR_EXTREME = 32


def discover_teams() -> list[str]:
    """data/arena/team_* 디렉토리에서 팀 ID 수집"""
    return sorted(
        p.name for p in ARENA_DIR.glob("team_*")
        if p.is_dir() and (p / "daily").exists()
    )


def load_trades_per_date(team_id: str) -> dict[str, dict]:
    """team 의 daily/<date>/trades.json 을 모두 읽음 → {date: trades_data}"""
    daily_dir = ARENA_DIR / team_id / "daily"
    if not daily_dir.exists():
        return {}
    out = {}
    for d in sorted(daily_dir.iterdir()):
        if not d.is_dir():
            continue
        tj = d / "trades.json"
        if not tj.exists():
            continue
        try:
            with open(tj, encoding="utf-8") as f:
                out[d.name] = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  ⚠ {team_id}/{d.name}/trades.json 읽기 실패: {e}")
    return out


def rebuild_portfolio(team_id: str, trades_by_date: dict[str, dict],
                     existing: dict) -> dict:
    """daily trades 시계열로 portfolio 재구성

    보존: team_id, initial_capital
    재계산: current_capital, total_return_*, total_trades/wins/losses,
            trading_days, win_streak/loss_streak/max_*,
            peak_capital, max_drawdown_pct
    """
    initial_capital = existing.get("initial_capital", INITIAL_CAPITAL)
    current_capital = float(initial_capital)
    total_return_amount = 0
    total_trades = 0
    total_wins = 0
    total_losses = 0
    trading_days = 0
    win_streak = 0
    loss_streak = 0
    max_win_streak = 0
    peak_capital = float(initial_capital)
    max_drawdown_pct = 0.0
    last_date = ""

    for date in sorted(trades_by_date.keys()):
        sim = trades_by_date[date]
        ret_amt = int(sim.get("total_return_amount", 0))
        ret_pct = float(sim.get("total_return", 0))
        trades = int(sim.get("total_trades", 0))
        wins = int(sim.get("wins", 0))

        current_capital += ret_amt
        total_return_amount += ret_amt
        total_trades += trades
        total_wins += wins
        total_losses += (trades - wins)
        trading_days += 1

        if ret_pct > 0:
            win_streak += 1
            loss_streak = 0
            max_win_streak = max(max_win_streak, win_streak)
        else:
            loss_streak += 1
            win_streak = 0

        if current_capital > peak_capital:
            peak_capital = current_capital
        dd = (peak_capital - current_capital) / peak_capital * 100 if peak_capital > 0 else 0
        max_drawdown_pct = max(max_drawdown_pct, dd)
        last_date = date

    total_return_pct = round(
        (current_capital - initial_capital) / initial_capital * 100, 2
    ) if initial_capital > 0 else 0.0

    return {
        "team_id": team_id,
        "initial_capital": initial_capital,
        "current_capital": round(current_capital, 2) if isinstance(current_capital, float) else current_capital,
        "total_return_pct": total_return_pct,
        "total_return_amount": total_return_amount,
        "total_trades": total_trades,
        "total_wins": total_wins,
        "total_losses": total_losses,
        "trading_days": trading_days,
        "win_streak": win_streak,
        "max_win_streak": max_win_streak,
        "loss_streak": loss_streak,
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "peak_capital": round(peak_capital, 2) if isinstance(peak_capital, float) else peak_capital,
        "last_updated": existing.get("last_updated", "")
            or datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
    }


def dedupe_daily_history(history: list[dict],
                         exclude_dates: set[str] | None = None) -> list[dict]:
    """동일 date 는 마지막 entry 만 유지, date 오름차순 정렬.
    exclude_dates 에 포함된 일자는 결과에서 제거 (휴장일 오염 정정용)."""
    excl = exclude_dates or set()
    by_date: dict[str, dict] = {}
    for entry in history:
        date = entry.get("date", "")
        if date and date not in excl:
            by_date[date] = entry  # 뒤에 나오는 것이 덮어씀
    return [by_date[d] for d in sorted(by_date.keys())]


def replay_team_aggregates(history: list[dict], team_meta: dict[str, dict]) -> dict[str, dict]:
    """deduped history 로 팀별 ELO·rank counts·best/worst day return 재계산"""
    # 팀 초기화 (기존 메타 유지: team_name, emoji)
    teams = {}
    for tid, meta in team_meta.items():
        teams[tid] = {
            "team_id": tid,
            "team_name": meta.get("team_name", tid),
            "emoji": meta.get("emoji", ""),
            "elo": INITIAL_ELO,
            "rank": 0,
            "total_1st": 0,
            "total_2nd": 0,
            "total_3rd": 0,
            "total_4th": 0,
            "best_day_return": 0,
            "worst_day_return": 0,
        }

    rank_keys = {1: "total_1st", 2: "total_2nd", 3: "total_3rd", 4: "total_4th"}

    for entry in history:
        ranking = entry.get("ranking", [])
        # ranking 은 이미 total_return desc 로 정렬되어 저장됨
        ranked_tids = [r["team_id"] for r in ranking if r.get("team_id") in teams]

        for r in ranking:
            tid = r.get("team_id")
            if tid not in teams:
                continue
            rank = r.get("rank", 0)
            ret = r.get("total_return", 0)
            t = teams[tid]
            if rank in rank_keys:
                t[rank_keys[rank]] += 1
            t["rank"] = rank
            if ret > t["best_day_return"]:
                t["best_day_return"] = round(ret, 2)
            if ret < t["worst_day_return"]:
                t["worst_day_return"] = round(ret, 2)

        # ELO 라운드로빈 (arena_manager._update_elo 와 동일 로직)
        n = len(ranked_tids)
        for i in range(n):
            for j in range(i + 1, n):
                tid_a, tid_b = ranked_tids[i], ranked_tids[j]
                elo_a = teams[tid_a]["elo"]
                elo_b = teams[tid_b]["elo"]
                exp_a = 1 / (1 + 10 ** ((elo_b - elo_a) / 400))
                exp_b = 1 - exp_a
                gap = j - i
                k = K_FACTOR_EXTREME if gap >= 3 else K_FACTOR_ADJACENT
                teams[tid_a]["elo"] = round(elo_a + k * (1 - exp_a))
                teams[tid_b]["elo"] = round(elo_b + k * (0 - exp_b))

    return teams


def backup_file(path: Path, suffix: str) -> Path | None:
    if not path.exists():
        return None
    bak = path.with_suffix(path.suffix + f".backup_{suffix}")
    shutil.copy2(path, bak)
    return bak


def main():
    parser = argparse.ArgumentParser(description="Arena 데이터 중복 누적 정정")
    parser.add_argument("--dry-run", action="store_true",
                        help="변경 미리보기만 (파일 쓰기 없음)")
    parser.add_argument("--exclude-dates", type=str, default="",
                        help="leaderboard.daily_history 에서 제거할 일자 (콤마 구분, YYYYMMDD)")
    args = parser.parse_args()
    exclude_dates = {d.strip() for d in args.exclude_dates.split(",") if d.strip()}

    if not ARENA_DIR.exists():
        print(f"[Error] {ARENA_DIR} 없음")
        return 1

    suffix = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    teams = discover_teams()
    print(f"[1/3] 팀 {len(teams)}개 발견: {teams}")

    # ===== Phase 1: 팀별 portfolio 재구성 =====
    print("\n[2/3] 팀별 portfolio.json 재구성")
    portfolio_changes = {}
    for tid in teams:
        pf_path = ARENA_DIR / tid / "portfolio.json"
        if not pf_path.exists():
            print(f"  - {tid}: portfolio.json 없음 (skip)")
            continue
        with open(pf_path, encoding="utf-8") as f:
            existing = json.load(f)
        trades_by_date = load_trades_per_date(tid)
        if not trades_by_date:
            print(f"  - {tid}: daily trades 없음 (skip)")
            continue
        rebuilt = rebuild_portfolio(tid, trades_by_date, existing)

        diffs = []
        for k in ("total_trades", "total_wins", "total_losses", "trading_days",
                 "current_capital", "total_return_pct", "max_drawdown_pct"):
            if existing.get(k) != rebuilt.get(k):
                diffs.append(f"{k}: {existing.get(k)} → {rebuilt.get(k)}")
        if diffs:
            print(f"  ⚠ {tid}: {len(trades_by_date)}일치 재구성")
            for d in diffs:
                print(f"      {d}")
        else:
            print(f"  ✓ {tid}: 변경 없음")
        portfolio_changes[tid] = (pf_path, existing, rebuilt)

    # ===== Phase 2: leaderboard 재계산 =====
    print("\n[3/3] leaderboard.json 재계산")
    lb_path = ARENA_DIR / "leaderboard.json"
    lb_change = None
    if lb_path.exists():
        with open(lb_path, encoding="utf-8") as f:
            lb = json.load(f)
        old_history = lb.get("daily_history", [])
        new_history = dedupe_daily_history(old_history, exclude_dates=exclude_dates)
        team_meta = lb.get("teams", {})
        new_teams = replay_team_aggregates(new_history, team_meta)

        dup_count = len(old_history) - len(new_history)
        if dup_count > 0:
            print(f"  ⚠ daily_history: {len(old_history)}건 → {len(new_history)}건 (중복 {dup_count}건 제거)")
            # 중복 일자 표시
            seen, dups = set(), set()
            for e in old_history:
                d = e.get("date", "")
                if d in seen:
                    dups.add(d)
                seen.add(d)
            print(f"      중복 날짜: {sorted(dups)}")
        else:
            print(f"  ✓ daily_history: {len(old_history)}건 (중복 없음)")

        elo_diffs = []
        for tid, t in new_teams.items():
            old_elo = team_meta.get(tid, {}).get("elo", INITIAL_ELO)
            if old_elo != t["elo"]:
                elo_diffs.append(f"{tid}: ELO {old_elo} → {t['elo']}")
        if elo_diffs:
            print("  ⚠ ELO 재계산:")
            for d in elo_diffs:
                print(f"      {d}")

        new_lb = dict(lb)
        new_lb["daily_history"] = new_history
        new_lb["teams"] = new_teams
        new_lb["last_updated"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
        lb_change = (lb_path, new_lb)
    else:
        print(f"  - {lb_path} 없음 (skip)")

    # ===== Apply =====
    if args.dry_run:
        print("\n[Dry-run] 변경사항 미적용. 실제 적용은 --dry-run 없이 재실행.")
        return 0

    print("\n=== 적용 ===")
    for tid, (path, _, rebuilt) in portfolio_changes.items():
        bak = backup_file(path, suffix)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rebuilt, f, ensure_ascii=False, indent=2)
        print(f"  ✓ {tid}/portfolio.json 갱신 (backup: {bak.name if bak else '-'})")

    if lb_change:
        path, new_lb = lb_change
        bak = backup_file(path, suffix)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(new_lb, f, ensure_ascii=False, indent=2)
        print(f"  ✓ leaderboard.json 갱신 (backup: {bak.name if bak else '-'})")

    print("\n완료. 검증: python -m paper_trading.audit.verify_facts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
