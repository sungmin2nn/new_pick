"""
팀 관리 - 포트폴리오, 설정, 일일 기록, 학습 노트
"""

import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict

KST = timezone(timedelta(hours=9))

ARENA_DIR = Path(__file__).parent.parent.parent / "data" / "arena"

# 팀 정의 (4팀 고정)
TEAM_CONFIGS = {
    "team_a": {
        "team_id": "team_a",
        "team_name": "Alpha Momentum",
        "strategy_id": "momentum",
        "emoji": "\U0001f534",  # 🔴
        "description": "모멘텀 추세 추종 - 전일 급등주 추격 매수",
    },
    "team_b": {
        "team_id": "team_b",
        "team_name": "Beta Contrarian",
        "strategy_id": "largecap_contrarian",
        "emoji": "\U0001f535",  # 🔵
        "description": "대형주 역발상 - 낙폭과대 대형주 반등 매매",
    },
    "team_c": {
        "team_id": "team_c",
        "team_name": "Gamma Disclosure",
        "strategy_id": "dart_disclosure",
        "emoji": "\U0001f7e2",  # 🟢
        "description": "DART 공시 기반 - 호재성 공시 종목 선별",
    },
    "team_d": {
        "team_id": "team_d",
        "team_name": "Delta Theme",
        "strategy_id": "theme_policy",
        "emoji": "\U0001f7e1",  # 🟡
        "description": "테마/정책 수혜 - 시장 테마 선도주 매매",
    },
}


@dataclass
class TeamPortfolio:
    """팀 포트폴리오 (누적 자금 추적)"""
    team_id: str
    initial_capital: int = 10_000_000  # 초기 1000만원
    current_capital: float = 10_000_000
    total_return_pct: float = 0.0
    total_return_amount: int = 0
    total_trades: int = 0
    total_wins: int = 0
    total_losses: int = 0
    trading_days: int = 0
    win_streak: int = 0          # 현재 연승
    max_win_streak: int = 0      # 최대 연승
    loss_streak: int = 0         # 현재 연패
    max_drawdown_pct: float = 0  # 최대 낙폭
    peak_capital: float = 10_000_000
    last_updated: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TeamPortfolio":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def update_after_day(self, daily_return_pct: float, daily_return_amount: int,
                         trades: int, wins: int):
        """일일 결과 반영"""
        self.current_capital += daily_return_amount
        self.total_return_amount += daily_return_amount
        self.total_return_pct = round(
            (self.current_capital - self.initial_capital) / self.initial_capital * 100, 2
        )
        self.total_trades += trades
        self.total_wins += wins
        self.total_losses += (trades - wins)
        self.trading_days += 1

        # 연승/연패 추적
        day_won = daily_return_pct > 0
        if day_won:
            self.win_streak += 1
            self.loss_streak = 0
            self.max_win_streak = max(self.max_win_streak, self.win_streak)
        else:
            self.loss_streak += 1
            self.win_streak = 0

        # 최대 낙폭
        if self.current_capital > self.peak_capital:
            self.peak_capital = self.current_capital
        drawdown = (self.peak_capital - self.current_capital) / self.peak_capital * 100
        self.max_drawdown_pct = round(max(self.max_drawdown_pct, drawdown), 2)

        self.last_updated = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


class Team:
    """팀 클래스 - 설정, 포트폴리오, 일일 기록, 학습 노트 관리"""

    def __init__(self, team_id: str, initial_capital: int = 10_000_000):
        config = TEAM_CONFIGS.get(team_id)
        if not config:
            raise ValueError(f"Unknown team: {team_id}. Available: {list(TEAM_CONFIGS.keys())}")

        self.team_id = team_id
        self.team_name = config["team_name"]
        self.strategy_id = config["strategy_id"]
        self.emoji = config["emoji"]
        self.description = config["description"]

        # 디렉토리 설정
        self.team_dir = ARENA_DIR / team_id
        self.daily_dir = self.team_dir / "daily"
        self.team_dir.mkdir(parents=True, exist_ok=True)
        self.daily_dir.mkdir(parents=True, exist_ok=True)

        # 포트폴리오 로드 또는 신규 생성
        self.portfolio = self._load_portfolio(initial_capital)

    def _load_portfolio(self, initial_capital: int) -> TeamPortfolio:
        """포트폴리오 로드 (없으면 새로 생성)"""
        pf_path = self.team_dir / "portfolio.json"
        if pf_path.exists():
            with open(pf_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return TeamPortfolio.from_dict(data)
        return TeamPortfolio(team_id=self.team_id, initial_capital=initial_capital,
                             current_capital=initial_capital, peak_capital=initial_capital)

    def save_portfolio(self):
        """포트폴리오 저장"""
        pf_path = self.team_dir / "portfolio.json"
        with open(pf_path, 'w', encoding='utf-8') as f:
            json.dump(self.portfolio.to_dict(), f, ensure_ascii=False, indent=2)

    def save_daily_record(self, date: str, selection: dict, simulation: dict,
                          analysis: Optional[dict] = None):
        """일일 기록 저장"""
        day_dir = self.daily_dir / date
        day_dir.mkdir(parents=True, exist_ok=True)

        # 종목 선정 기록
        with open(day_dir / "selection.json", 'w', encoding='utf-8') as f:
            json.dump(selection, f, ensure_ascii=False, indent=2, default=str)

        # 매매 기록
        with open(day_dir / "trades.json", 'w', encoding='utf-8') as f:
            json.dump(simulation, f, ensure_ascii=False, indent=2, default=str)

        # 일일 요약
        summary = {
            "team_id": self.team_id,
            "team_name": self.team_name,
            "strategy_id": self.strategy_id,
            "date": date,
            "saved_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
            "selection_count": selection.get("count", 0),
            "simulation": {
                "total_trades": simulation.get("total_trades", 0),
                "wins": simulation.get("wins", 0),
                "win_rate": simulation.get("win_rate", 0),
                "total_return": simulation.get("total_return", 0),
                "total_return_amount": simulation.get("total_return_amount", 0),
            },
            "portfolio_after": {
                "current_capital": self.portfolio.current_capital,
                "total_return_pct": self.portfolio.total_return_pct,
                "trading_days": self.portfolio.trading_days,
            },
        }
        with open(day_dir / "summary.json", 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        # 분석 기록 (있으면)
        if analysis:
            with open(day_dir / "analysis.json", 'w', encoding='utf-8') as f:
                json.dump(analysis, f, ensure_ascii=False, indent=2, default=str)

    def append_journal(self, date: str, entry: str):
        """팀 학습 노트에 엔트리 추가"""
        journal_path = self.team_dir / "journal.md"

        header = f"\n## {date}\n"
        content = f"{header}{entry}\n"

        with open(journal_path, 'a', encoding='utf-8') as f:
            if not journal_path.exists() or journal_path.stat().st_size == 0:
                f.write(f"# {self.team_name} - 팀 학습 노트\n\n")
            f.write(content)

    def save_param_change(self, date: str, change: dict):
        """파라미터 변경 이력 저장"""
        history_path = self.team_dir / "param_history.json"

        history = []
        if history_path.exists():
            with open(history_path, 'r', encoding='utf-8') as f:
                history = json.load(f)

        change["date"] = date
        change["changed_at"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
        history.append(change)

        with open(history_path, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

    def get_daily_records(self, last_n: int = 10) -> List[dict]:
        """최근 N일 기록 로드"""
        records = []
        if not self.daily_dir.exists():
            return records

        date_dirs = sorted(self.daily_dir.iterdir(), reverse=True)
        for d in date_dirs[:last_n]:
            if not d.is_dir():
                continue
            summary_path = d / "summary.json"
            if summary_path.exists():
                with open(summary_path, 'r', encoding='utf-8') as f:
                    records.append(json.load(f))

        return records

    def get_journal(self) -> str:
        """학습 노트 전체 읽기"""
        journal_path = self.team_dir / "journal.md"
        if journal_path.exists():
            return journal_path.read_text(encoding='utf-8')
        return ""

    def get_param_history(self) -> List[dict]:
        """파라미터 변경 이력 읽기"""
        history_path = self.team_dir / "param_history.json"
        if history_path.exists():
            with open(history_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []

    def get_config(self) -> dict:
        """팀 설정 반환"""
        return {
            "team_id": self.team_id,
            "team_name": self.team_name,
            "strategy_id": self.strategy_id,
            "emoji": self.emoji,
            "description": self.description,
        }

    def get_status(self) -> dict:
        """팀 현재 상태 (대시보드용)"""
        pf = self.portfolio
        win_rate = round(pf.total_wins / pf.total_trades * 100, 1) if pf.total_trades > 0 else 0

        return {
            **self.get_config(),
            "portfolio": pf.to_dict(),
            "win_rate": win_rate,
            "recent_records": self.get_daily_records(5),
        }
