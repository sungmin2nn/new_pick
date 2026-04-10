"""
페이퍼 트레이딩 시스템
- selector: StockCandidate dataclass + StockSelector (Arena strategies + simulator가 사용)
- simulator: 가상 매매 시뮬레이션
- arena: 4팀 경쟁 시스템
- bnf: BNF 낙폭과대 분할매수
"""

from .selector import StockSelector, StockCandidate
from .simulator import TradingSimulator

__all__ = ['StockSelector', 'StockCandidate', 'TradingSimulator']
