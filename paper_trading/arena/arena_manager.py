"""
Arena Manager - 4팀 경쟁 트레이딩 오케스트레이터
- 팀 초기화 / 일일 실행 / 비교 / 진화 관리
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from .team import Team, TeamPortfolio, TEAM_CONFIGS, ARENA_DIR, load_teams_from_config
from .leaderboard import Leaderboard

KST = timezone(timedelta(hours=9))


class ArenaManager:
    """
    4팀 경쟁 트레이딩 매니저

    실행 흐름:
    1. 4팀 초기화 (포트폴리오 로드)
    2. 전략별 종목 선정 (각 팀 독립)
    3. 전략별 시뮬레이션 (각 팀 독립 자금)
    4. 팀별 기록 저장 + 포트폴리오 업데이트
    5. 리더보드 업데이트 (ELO + 랭킹)
    6. 팀별 분석 + 학습 노트 기록
    """

    DEFAULT_CAPITAL = 10_000_000  # 초기 1000만원

    def __init__(self, initial_capital: int = None):
        self.initial_capital = initial_capital or self.DEFAULT_CAPITAL
        ARENA_DIR.mkdir(parents=True, exist_ok=True)

        # strategy_config.json에서 동적 팀 로드
        load_teams_from_config()

        # 팀 초기화
        self.teams: Dict[str, Team] = {}
        for team_id in TEAM_CONFIGS:
            self.teams[team_id] = Team(team_id, self.initial_capital)

        # 리더보드
        self.leaderboard = Leaderboard()
        for team_id, team in self.teams.items():
            self.leaderboard.init_team(team_id, team.team_name, team.emoji)

        # 아레나 설정 저장
        self._save_config()

    def _save_config(self):
        """아레나 설정 저장"""
        config_path = ARENA_DIR / "config.json"
        config = {
            "initial_capital": self.initial_capital,
            "teams": {tid: t.get_config() for tid, t in self.teams.items()},
            "rules": {
                "profit_target_pct": 5.0,
                "loss_target_pct": -3.0,  # 기본값 (전략별 오버라이드 가능)
                "exit_deadline": "14:30",
                "max_stocks_per_team": 5,
            },
            "created_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
        }
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def run_daily(self, date: str = None, force: bool = False) -> dict:
        """
        일일 아레나 실행 (4팀 경쟁)

        Args:
            date: 실행 날짜 (YYYYMMDD)
            force: 장 종료 전이라도 강제 실행

        Returns:
            아레나 결과
        """
        if date is None:
            date = datetime.now(KST).strftime("%Y%m%d")

        print(f"\n{'#'*60}")
        print(f"# \U0001f3df  ARENA - 4팀 경쟁 트레이딩")
        print(f"# 날짜: {date}")
        print(f"# 시간: {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'#'*60}")

        # 멱등성 가드: 동일 날짜 재실행 차단 (포트폴리오/ELO/일일히스토리 이중 계산 방지)
        daily_report_path = ARENA_DIR / "daily" / date / "arena_report.json"
        if daily_report_path.exists() and not force:
            print(f"[Arena] {date} 이미 실행 완료 — skip (재실행하려면 --force)")
            print(f"        기존 리포트: {daily_report_path}")
            return {
                "status": "skipped",
                "reason": "already_run",
                "date": date,
                "report_path": str(daily_report_path),
            }
        if daily_report_path.exists() and force:
            print(f"[Arena] ⚠ --force 재실행: {date} 의 portfolio/leaderboard 누적값이 이중 계산될 수 있음")
            print(f"        클린 재실행이 필요하면 scripts/dedupe_arena_data.py 먼저 실행")

        # 장 종료 확인
        if not force and not self._is_market_closed():
            print("[Arena] 장이 아직 종료되지 않았습니다.")
            return {"status": "skipped", "reason": "market_open"}

        result = {
            "date": date,
            "status": "success",
            "teams": {},
            "leaderboard": None,
        }

        try:
            # 전략 레지스트리에서 전략 실행
            from paper_trading.strategies import StrategyRegistry
            from paper_trading.simulator import TradingSimulator
            from paper_trading.selector import StockCandidate
            from paper_trading.multi_strategy_runner import _resolve_fetch_date

            # 비거래일/미래일 → 가장 최근 거래일로 fetch (target_date는 그대로)
            today_str = datetime.now(KST).strftime("%Y%m%d")
            fetch_date = _resolve_fetch_date(min(date, today_str))
            if fetch_date != date:
                print(f"[Arena] fetch_date={fetch_date} (target={date} 비거래일/미래)")

            # 1. 전략별 종목 선정
            print("\n[Phase 1] 5팀 종목 선정")
            strategy_results = StrategyRegistry.run_all(date=fetch_date, top_n=5)

            # 2. 팀별 독립 시뮬레이션
            print("\n[Phase 2] 4팀 독립 시뮬레이션")
            team_sim_results = {}

            for team_id, team in self.teams.items():
                strategy_id = team.strategy_id
                strat_result = strategy_results.get(strategy_id)

                print(f"\n  {team.emoji} {team.team_name} ({strategy_id})")

                if not strat_result or not strat_result.candidates:
                    print(f"    선정 종목 없음 - 스킵")
                    result["teams"][team_id] = {
                        "team_id": team_id,
                        "team_name": team.team_name,
                        "strategy_id": strategy_id,
                        "status": "no_candidates",
                        "simulation": None,
                    }
                    continue

                # 팀의 현재 자금으로 시뮬레이터 생성
                # 전략 고유 손절 파라미터가 있으면 적용
                strategy_cls = StrategyRegistry.get(strategy_id)
                strategy_loss = getattr(strategy_cls, 'LOSS_TARGET', None) if strategy_cls else None
                simulator = TradingSimulator(
                    capital=int(team.portfolio.current_capital),
                    strategy_id=strategy_id,
                    strategy_name=team.team_name,
                    loss_target=strategy_loss,
                )

                # Candidate → StockCandidate 변환
                stock_candidates = [
                    StockCandidate(
                        code=c.code, name=c.name, price=c.price,
                        change_pct=c.change_pct, trading_value=c.trading_value,
                        market_cap=c.market_cap, volume=c.volume,
                        score=c.score, score_detail=c.score_detail, rank=c.rank,
                    )
                    for c in strat_result.candidates
                ]

                # 시뮬레이션
                simulator.simulate_day(stock_candidates, date)
                sim_summary = simulator.get_daily_summary()

                team_sim_results[team_id] = sim_summary

                result["teams"][team_id] = {
                    "team_id": team_id,
                    "team_name": team.team_name,
                    "strategy_id": strategy_id,
                    "status": "success",
                    "selection": strat_result.to_dict(),
                    "simulation": sim_summary,
                }

            # 3. 팀별 기록 저장 + 포트폴리오 업데이트
            print("\n[Phase 3] 팀별 기록 저장 + 포트폴리오 업데이트")
            for team_id, team in self.teams.items():
                team_data = result["teams"].get(team_id, {})
                sim = team_data.get("simulation")
                selection = team_data.get("selection", {})

                if sim and team_data.get("status") == "success":
                    # 포트폴리오 업데이트
                    team.portfolio.update_after_day(
                        daily_return_pct=sim.get("total_return", 0),
                        daily_return_amount=sim.get("total_return_amount", 0),
                        trades=sim.get("total_trades", 0),
                        wins=sim.get("wins", 0),
                    )
                    team.save_portfolio()

                    # 일일 기록 저장
                    team.save_daily_record(date, selection, sim)

                    pf = team.portfolio
                    print(f"  {team.emoji} {team.team_name}: "
                          f"자금 {pf.current_capital:,.0f}원 "
                          f"(누적 {pf.total_return_pct:+.2f}%)")

            # 4. 리더보드 업데이트
            print("\n[Phase 4] 리더보드 업데이트")
            lb_results = {}
            for team_id, team_data in result["teams"].items():
                sim = team_data.get("simulation", {})
                lb_results[team_id] = {
                    "total_return": sim.get("total_return", 0) if sim else 0,
                    "win_rate": sim.get("win_rate", 0) if sim else 0,
                    "total_trades": sim.get("total_trades", 0) if sim else 0,
                }
            self.leaderboard.update_daily(date, lb_results)

            result["leaderboard"] = self.leaderboard.get_summary()

            # 5. 일일 아레나 리포트 저장
            print("\n[Phase 5] 아레나 리포트 저장")
            self._save_daily_report(date, result)

            # 결과 출력
            self._print_result(date, result)

        except Exception as e:
            print(f"\n[Arena] 오류 발생: {e}")
            import traceback
            traceback.print_exc()
            result["status"] = "error"
            result["error"] = str(e)

        return result

    def _save_daily_report(self, date: str, result: dict):
        """일일 아레나 리포트 저장"""
        daily_dir = ARENA_DIR / "daily" / date
        daily_dir.mkdir(parents=True, exist_ok=True)

        report_path = daily_dir / "arena_report.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
        print(f"  저장: {report_path}")

    def _print_result(self, date: str, result: dict):
        """결과 출력"""
        print(f"\n{'='*60}")
        print(f"\U0001f3df  ARENA 결과 ({date})")
        print(f"{'='*60}")

        print(f"\n{'팀':<25} {'자금':>15} {'일일':>10} {'누적':>10} {'승률':>8}")
        print("-" * 70)

        for team_id, team in self.teams.items():
            td = result["teams"].get(team_id, {})
            sim = td.get("simulation", {})
            pf = team.portfolio

            name = f"{team.emoji} {team.team_name}"[:23]
            capital = f"{pf.current_capital:,.0f}"
            daily_ret = f"{sim.get('total_return', 0):+.2f}%" if sim else "-"
            cum_ret = f"{pf.total_return_pct:+.2f}%"
            wr = f"{pf.total_wins}/{pf.total_trades}" if pf.total_trades > 0 else "-"

            print(f"{name:<25} {capital:>15} {daily_ret:>10} {cum_ret:>10} {wr:>8}")

        print("-" * 70)

        # ELO 랭킹
        ranking = self.leaderboard.get_ranking()
        if ranking:
            medals = ["\U0001f947", "\U0001f948", "\U0001f949", "4\ufe0f\u20e3"]
            print(f"\n\U0001f3c6 ELO 랭킹:")
            for t in ranking:
                medal = medals[min(t["elo_rank"] - 1, 3)]
                print(f"  {medal} {t['emoji']} {t['team_name']}: ELO {t['elo']}")

        print(f"{'='*60}")

    def _is_market_closed(self) -> bool:
        now = datetime.now(KST)
        if now.weekday() >= 5:
            return True
        return now.hour >= 16

    # === 분석 & 진화 ===

    def analyze_and_evolve(self, date: str) -> dict:
        """
        팀별 일일 분석 + 학습 노트 기록

        Claude Code 세션에서 호출하여
        각 팀의 성과를 분석하고 개선 제안을 기록
        """
        print(f"\n[Arena] 분석 & 진화 ({date})")

        evolution_report = {"date": date, "teams": {}}

        for team_id, team in self.teams.items():
            records = team.get_daily_records(10)
            if not records:
                continue

            # 최근 성과 통계
            returns = [r["simulation"]["total_return"] for r in records
                       if r.get("simulation")]
            win_rates = [r["simulation"]["win_rate"] for r in records
                         if r.get("simulation")]

            avg_return = sum(returns) / len(returns) if returns else 0
            avg_win_rate = sum(win_rates) / len(win_rates) if win_rates else 0

            # 학습 노트 엔트리 생성
            pf = team.portfolio
            journal_entry = (
                f"- 일일 수익률: {returns[0]:+.2f}% (최근 {len(returns)}일 평균: {avg_return:+.2f}%)\n"
                f"- 승률: {avg_win_rate:.1f}% (누적 {pf.total_wins}/{pf.total_trades})\n"
                f"- 누적 자금: {pf.current_capital:,.0f}원 ({pf.total_return_pct:+.2f}%)\n"
                f"- ELO: {self.leaderboard.get_team_stats(team_id).get('elo', 1000)}\n"
            )

            # 트렌드 분석
            if len(returns) >= 3:
                recent_3 = returns[:3]
                trend = "상승" if all(r > 0 for r in recent_3) else \
                        "하락" if all(r < 0 for r in recent_3) else "횡보"
                journal_entry += f"- 최근 3일 트렌드: {trend}\n"

            team.append_journal(date, journal_entry)

            evolution_report["teams"][team_id] = {
                "team_name": team.team_name,
                "avg_return": round(avg_return, 2),
                "avg_win_rate": round(avg_win_rate, 1),
                "journal_updated": True,
            }

        # 진화 리포트 저장
        daily_dir = ARENA_DIR / "daily" / date
        daily_dir.mkdir(parents=True, exist_ok=True)
        evo_path = daily_dir / "evolution_report.json"
        with open(evo_path, 'w', encoding='utf-8') as f:
            json.dump(evolution_report, f, ensure_ascii=False, indent=2)

        return evolution_report

    # === 조회 ===

    def get_team(self, team_id: str) -> Optional[Team]:
        return self.teams.get(team_id)

    def get_all_status(self) -> dict:
        """전체 아레나 현황"""
        return {
            "teams": {tid: t.get_status() for tid, t in self.teams.items()},
            "leaderboard": self.leaderboard.get_summary(),
        }

    def get_comparison(self, date: str) -> Optional[dict]:
        """특정 일자 비교 결과"""
        report_path = ARENA_DIR / "daily" / date / "arena_report.json"
        if report_path.exists():
            with open(report_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def format_telegram_daily(self, date: str) -> str:
        """텔레그램 일일 결과 메시지 (Design C: 정보 풍부)

        - 팀 색깔 이모지 미사용 (방향 ▲▼─와 의미 충돌 방지)
        - 4섹션 → 1섹션 통합 (오늘 수익률 기준 정렬)
        - 1팀 = 5줄 (이름 / 금일 / 잔고 / 매매 / ELO)
        - ELO 등급 텍스트로 직관적 해석
        """
        # 날짜 포맷: 20260410 -> 2026-04-10
        date_str = f"{date[:4]}-{date[4:6]}-{date[6:8]}" if len(date) == 8 and date.isdigit() else date

        # ELO 매핑
        elo_map = {tid: tdata.get('elo', 1000)
                   for tid, tdata in self.leaderboard.data.get('teams', {}).items()}

        # ELO 등급 분류
        def elo_tier(elo):
            if elo >= 1100: return "강팀"
            if elo >= 1050: return "우수"
            if elo >= 950: return "평균"
            if elo >= 900: return "약체"
            return "부진"

        # Day N 계산 (운영 일수 = leaderboard daily_history 길이)
        day_n = len(self.leaderboard.data.get('daily_history', []))

        # 팀 데이터 수집
        team_rows = []
        for team_id, team in self.teams.items():
            pf = team.portfolio
            records = team.get_daily_records(1)
            rec = records[0] if records and records[0].get("date") == date else None
            sim = rec.get("simulation", {}) if rec else {}
            team_rows.append({
                'id': team_id,
                'name': team.team_name,
                'today_pct': sim.get('total_return', None) if rec else None,
                'today_amt': sim.get('total_return_amount', 0),
                'cum_pct': pf.total_return_pct,
                'capital': pf.current_capital,
                'wins': sim.get('wins', 0),
                'trades': sim.get('total_trades', 0),
                'win_rate': sim.get('win_rate', 0),
                'elo': elo_map.get(team_id, 1000),
            })

        # 오늘 수익률 내림차순 정렬 (결과 없는 팀은 맨 뒤)
        team_rows.sort(key=lambda r: (r['today_pct'] if r['today_pct'] is not None else float('-inf')),
                       reverse=True)

        medals = ["\U0001f947", "\U0001f948", "\U0001f949", " 4"]
        lines = [f"<b>📊 ARENA REPORT</b>", f"<i>{date_str} · Day {day_n}</i>", ""]
        lines.append("━━━━━━━━━━━━━━")

        for i, t in enumerate(team_rows):
            medal = medals[min(i, 3)]
            lines.append("")

            if t['today_pct'] is None:
                lines.append(f"{medal}  <b>{t['name']}</b>")
                lines.append(f"   금일  결과 없음")
                lines.append(f"   잔고  {t['capital']:,.0f}원")
                lines.append(f"   ELO   <b>{t['elo']}</b>  ·  {elo_tier(t['elo'])}")
                continue

            arrow = "▲" if t['today_pct'] > 0 else "▼" if t['today_pct'] < 0 else "─"
            amt_sign = "+" if t['today_amt'] >= 0 else ""
            pct_sign = "+" if t['today_pct'] >= 0 else ""
            cum_sign = "+" if t['cum_pct'] >= 0 else ""
            elo_diff = t['elo'] - 1000
            elo_arrow = "▲" if elo_diff > 0 else "▼" if elo_diff < 0 else "─"
            elo_diff_str = f"+{elo_diff}" if elo_diff > 0 else f"{elo_diff}" if elo_diff < 0 else "±0"
            losses = t['trades'] - t['wins']

            lines.append(f"{medal}  <b>{t['name']}</b>")
            lines.append(
                f"   금일  {arrow} <b>{amt_sign}{t['today_amt']:,}원</b>  "
                f"({pct_sign}{t['today_pct']:.2f}%)"
            )
            lines.append(f"   잔고  {t['capital']:,.0f}원  ({cum_sign}{t['cum_pct']:.2f}%)")
            lines.append(f"   매매  {t['wins']}승 {losses}패  ({t['win_rate']:.0f}%)")
            lines.append(
                f"   ELO   <b>{t['elo']}</b> {elo_arrow}{elo_diff_str}  ·  {elo_tier(t['elo'])}"
            )

        return "\n".join(lines)


def main():
    """CLI"""
    import argparse

    parser = argparse.ArgumentParser(description='Arena - 4팀 경쟁 트레이딩')
    parser.add_argument('command', choices=['run', 'status', 'analyze', 'history'],
                        help='명령')
    parser.add_argument('--date', '-d', type=str, default=None)
    parser.add_argument('--force', '-f', action='store_true')
    parser.add_argument('--capital', '-c', type=int, default=10_000_000)

    args = parser.parse_args()
    arena = ArenaManager(initial_capital=args.capital)

    if args.command == 'run':
        arena.run_daily(date=args.date, force=args.force)
    elif args.command == 'status':
        status = arena.get_all_status()
        print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    elif args.command == 'analyze':
        date = args.date or datetime.now(KST).strftime("%Y%m%d")
        arena.analyze_and_evolve(date)
    elif args.command == 'history':
        history = arena.leaderboard.get_daily_history()
        for entry in history:
            print(f"\n{entry['date']}:")
            for r in entry.get("ranking", []):
                print(f"  {r['rank']}위 {r['team_id']}: {r['total_return']:+.2f}%")


if __name__ == "__main__":
    main()
