"""
전략 베이스 클래스
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from datetime import datetime


@dataclass
class Candidate:
    """선정 종목"""
    code: str
    name: str
    price: int
    change_pct: float
    score: float
    score_detail: Dict = field(default_factory=dict)
    rank: int = 0

    # 추가 정보
    market_cap: int = 0
    volume: int = 0
    trading_value: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StrategyResult:
    """전략 실행 결과"""
    strategy_id: str
    strategy_name: str
    date: str
    selected_at: str
    candidates: List[Candidate]
    params: Dict = field(default_factory=dict)

    # 시뮬레이션 결과 (나중에 채워짐)
    simulation: Optional[Dict] = None

    def to_dict(self) -> dict:
        return {
            'strategy_id': self.strategy_id,
            'strategy_name': self.strategy_name,
            'date': self.date,
            'selected_at': self.selected_at,
            'count': len(self.candidates),
            'candidates': [c.to_dict() if hasattr(c, 'to_dict') else c for c in self.candidates],
            'params': self.params,
            'simulation': self.simulation
        }


class BaseStrategy(ABC):
    """전략 베이스 클래스"""

    # 각 전략에서 오버라이드
    STRATEGY_ID: str = "base"
    STRATEGY_NAME: str = "기본 전략"
    DESCRIPTION: str = "전략 설명"

    def __init__(self):
        self.candidates: List[Candidate] = []
        self.selection_date: str = ""

    @abstractmethod
    def select_stocks(self, date: str = None, top_n: int = 5) -> List[Candidate]:
        """
        종목 선정 (각 전략에서 구현)

        Args:
            date: 선정 날짜 (YYYYMMDD)
            top_n: 상위 N개 선정

        Returns:
            선정된 종목 리스트
        """
        pass

    def get_result(self) -> StrategyResult:
        """전략 실행 결과 반환"""
        return StrategyResult(
            strategy_id=self.STRATEGY_ID,
            strategy_name=self.STRATEGY_NAME,
            date=self.selection_date,
            selected_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            candidates=self.candidates,
            params=self.get_params()
        )

    def get_params(self) -> Dict:
        """전략 파라미터 (각 전략에서 오버라이드)"""
        return {}

    def __repr__(self):
        return f"<{self.STRATEGY_NAME} ({self.STRATEGY_ID})>"
