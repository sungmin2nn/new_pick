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
]

# strategy_config.json 기반 추가 전략 동적 로드
try:
    from .dynamic_loader import load_enabled_strategies
    _dynamic = load_enabled_strategies()
    if _dynamic:
        print(f"[Strategies] {len(_dynamic)}개 전략 활성 (동적 로드 포함)")
except Exception as _e:
    print(f"[Strategies] 동적 로더 스킵: {_e}")
