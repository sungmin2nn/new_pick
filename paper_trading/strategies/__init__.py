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

__all__ = [
    'BaseStrategy',
    'StrategyResult',
    'Candidate',
    'StrategyRegistry',
    'LargecapContrarianStrategy',
    'MomentumStrategy',
    'ThemePolicyStrategy',
    'DartDisclosureStrategy',
]
