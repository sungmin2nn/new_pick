"""
다중 전략 시스템
- 여러 전략을 동시에 실행하고 결과 비교
"""

from .base import BaseStrategy, StrategyResult, Candidate
from .registry import StrategyRegistry

# 전략 import (자동 등록됨)
from .largecap_contrarian import LargecapContrarianStrategy
from .momentum import MomentumStrategy
from .theme_policy import ThemePolicyStrategy
from .dart_disclosure import DartDisclosureStrategy
from .frontier_gap import FrontierGapStrategy
from .hybrid_alpha_delta import HybridAlphaDeltaStrategy
# P3-3b: 스퀴즈 플레이 (DEC-005/006). 4주 shadow 운영용, 트레일링 미사용 5일 보유.
from .squeeze_play_kospi_v6 import SqueezePlayKospiV6Strategy
from .squeeze_play_kosdaq_v5 import SqueezePlayKosdaqV5Strategy

__all__ = [
    'BaseStrategy',
    'StrategyResult',
    'Candidate',
    'StrategyRegistry',
    'LargecapContrarianStrategy',
    'MomentumStrategy',
    'ThemePolicyStrategy',
    'DartDisclosureStrategy',
    'FrontierGapStrategy',
    'HybridAlphaDeltaStrategy',
    'SqueezePlayKospiV6Strategy',
    'SqueezePlayKosdaqV5Strategy',
]

# strategy_config.json 기반 추가 전략 동적 로드
try:
    from .dynamic_loader import load_enabled_strategies
    _dynamic = load_enabled_strategies()
    if _dynamic:
        print(f"[Strategies] {len(_dynamic)}개 전략 활성 (동적 로드 포함)")
except Exception as _e:
    print(f"[Strategies] 동적 로더 스킵: {_e}")
