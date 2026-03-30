"""
BNF-style Trading Package
낙폭과대 역추세 전략 기반 트레이딩 시스템

모듈:
- selector: 낙폭과대 종목 선정
- simulator: 분할 매수/매도 및 트레일링 스탑 시뮬레이터
- position: 다일 포지션 관리
"""

from .selector import BNFSelector, BNFCandidate
from .simulator import (
    BNFSimulator,
    BNFTradeResult,
    EntryPoint,
    ExitPoint
)
from .position import BNFPositionManager, Position, PositionState

__all__ = [
    # Selector
    'BNFSelector',
    'BNFCandidate',
    # Simulator
    'BNFSimulator',
    'BNFTradeResult',
    'EntryPoint',
    'ExitPoint',
    # Position
    'BNFPositionManager',
    'Position',
    'PositionState',
]
