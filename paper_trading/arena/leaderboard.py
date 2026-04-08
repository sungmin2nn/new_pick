"""
리더보드 - ELO 레이팅, 누적 랭킹, 일일/주간/월간 성과 추적
"""

import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

KST = timezone(timedelta(hours=9))

ARENA_DIR = Path(__file__).parent.parent.parent / "data" / "arena"


class Leaderboard:
    """리더보드 시스템"""

    INITIAL_ELO = 1000
    K_FACTOR_ADJACENT = 16   # 인접 순위 대결
    K_FACTOR_EXTREME = 32    # 1위 vs 4위 대결

    def __init__(self):
        self.data_path = ARENA_DIR / "leaderboard.json"
        ARENA_DIR.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self) -> dict:
        if self.data_path.exists():
            with open(self.data_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {
            "teams": {},
            "daily_history": [],
            "last_updated": "",
        }

    def save(self):
        self.data["last_updated"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
        with open(self.data_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def init_team(self, team_id: str, team_name: str, emoji: str):
        """팀 초기 등록"""
        if team_id not in self.data["teams"]:
            self.data["teams"][team_id] = {
                "team_id": team_id,
                "team_name": team_name,
                "emoji": emoji,
                "elo": self.INITIAL_ELO,
                "rank": 0,
                "total_1st": 0,
                "total_2nd": 0,
                "total_3rd": 0,
                "total_4th": 0,
                "best_day_return": 0,
                "worst_day_return": 0,
            }

    def update_daily(self, date: str, team_results: Dict[str, dict]):
        """
        일일 결과로 리더보드 업데이트

        Args:
            date: 날짜 (YYYYMMDD)
            team_results: {team_id: {"total_return": float, "win_rate": float, ...}}
        """
        # 수익률 기준 일일 랭킹
        ranked = sorted(
            team_results.items(),
            key=lambda x: x[1].get("total_return", -999),
            reverse=True
        )

        daily_entry = {
            "date": date,
            "ranking": [],
        }

        # 순위 기록 + 베스트/워스트 갱신
        for rank_idx, (tid, result) in enumerate(ranked):
            rank = rank_idx + 1
            ret = result.get("total_return", 0)

            daily_entry["ranking"].append({
                "rank": rank,
                "team_id": tid,
                "total_return": ret,
                "win_rate": result.get("win_rate", 0),
                "trades": result.get("total_trades", 0),
            })

            if tid in self.data["teams"]:
                team = self.data["teams"][tid]
                # 순위 카운트
                rank_key = f"total_{rank}{'st' if rank == 1 else 'nd' if rank == 2 else 'rd' if rank == 3 else 'th'}"
                team[rank_key] = team.get(rank_key, 0) + 1
                team["rank"] = rank

                # 베스트/워스트
                if ret > team.get("best_day_return", 0):
                    team["best_day_return"] = round(ret, 2)
                if ret < team.get("worst_day_return", 0):
                    team["worst_day_return"] = round(ret, 2)

        # ELO 업데이트 (라운드로빈)
        self._update_elo(ranked)

        # 히스토리에 추가
        self.data["daily_history"].append(daily_entry)

        self.save()

    def _update_elo(self, ranked: list):
        """ELO 레이팅 업데이트 (라운드 로빈 방식)"""
        teams = self.data["teams"]
        n = len(ranked)

        for i in range(n):
            for j in range(i + 1, n):
                tid_a = ranked[i][0]
                tid_b = ranked[j][0]

                if tid_a not in teams or tid_b not in teams:
                    continue

                elo_a = teams[tid_a]["elo"]
                elo_b = teams[tid_b]["elo"]

                # 기대 승률
                exp_a = 1 / (1 + 10 ** ((elo_b - elo_a) / 400))
                exp_b = 1 - exp_a

                # K 팩터 (1위 vs 4위는 크게, 인접 순위는 작게)
                gap = j - i
                k = self.K_FACTOR_EXTREME if gap >= 3 else self.K_FACTOR_ADJACENT

                # i가 j보다 높은 순위 (승리)
                teams[tid_a]["elo"] = round(elo_a + k * (1 - exp_a))
                teams[tid_b]["elo"] = round(elo_b + k * (0 - exp_b))

    def get_ranking(self) -> List[dict]:
        """현재 ELO 기준 랭킹"""
        teams = list(self.data["teams"].values())
        teams.sort(key=lambda x: x["elo"], reverse=True)
        for i, t in enumerate(teams):
            t["elo_rank"] = i + 1
        return teams

    def get_daily_history(self, last_n: int = 30) -> List[dict]:
        """최근 N일 히스토리"""
        return self.data["daily_history"][-last_n:]

    def get_team_stats(self, team_id: str) -> Optional[dict]:
        """팀별 통계"""
        return self.data["teams"].get(team_id)

    def get_summary(self) -> dict:
        """리더보드 요약 (대시보드용)"""
        ranking = self.get_ranking()
        history = self.get_daily_history(5)

        return {
            "ranking": ranking,
            "recent_history": history,
            "total_days": len(self.data["daily_history"]),
            "last_updated": self.data.get("last_updated", ""),
        }

    def format_telegram(self, date: str) -> str:
        """텔레그램 알림용 포맷"""
        ranking = self.get_ranking()
        history = self.data["daily_history"]

        # 오늘 결과 찾기
        today_entry = None
        for entry in reversed(history):
            if entry["date"] == date:
                today_entry = entry
                break

        lines = [f"<b>\U0001f3c6 Arena Leaderboard ({date})</b>", ""]

        if today_entry:
            lines.append("<b>[오늘 결과]</b>")
            medals = ["\U0001f947", "\U0001f948", "\U0001f949", "4\ufe0f\u20e3"]
            for r in today_entry["ranking"]:
                medal = medals[min(r["rank"] - 1, 3)]
                tid = r["team_id"]
                team = self.data["teams"].get(tid, {})
                emoji = team.get("emoji", "")
                name = team.get("team_name", tid)
                ret = r["total_return"]
                icon = "\U0001f7e2" if ret > 0 else "\U0001f534" if ret < 0 else "\u26aa"
                lines.append(f"{medal} {emoji} {name}: {icon} {ret:+.2f}%")
            lines.append("")

        lines.append("<b>[ELO 랭킹]</b>")
        for t in ranking:
            emoji = t.get("emoji", "")
            lines.append(f"  {t['elo_rank']}. {emoji} {t['team_name']}: ELO {t['elo']}")

        return "\n".join(lines)
