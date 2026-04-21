"""
strategy-lab core package.

news-trading-bot의 BaseStrategy 등을 재사용하기 위해
sys.path에 news-trading-bot 경로를 추가한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

# news-trading-bot 경로 자동 추가
NTB_ROOT = Path("/Users/kslee/Documents/kslee_ZIP/zip1/news-trading-bot")
if NTB_ROOT.exists() and str(NTB_ROOT) not in sys.path:
    sys.path.insert(0, str(NTB_ROOT))

# news-trading-bot에서 import 시도
try:
    from paper_trading.strategies.base import BaseStrategy, Candidate, StrategyResult
    from paper_trading.strategies.registry import StrategyRegistry
    NTB_AVAILABLE = True
except ImportError as e:
    BaseStrategy = None
    Candidate = None
    StrategyResult = None
    StrategyRegistry = None
    NTB_AVAILABLE = False
    _IMPORT_ERROR = str(e)


def assert_ntb_available() -> None:
    """news-trading-bot import가 가능한지 확인. 불가 시 명확한 에러."""
    if not NTB_AVAILABLE:
        raise RuntimeError(
            f"news-trading-bot을 import할 수 없습니다.\n"
            f"  경로: {NTB_ROOT}\n"
            f"  에러: {_IMPORT_ERROR}\n"
            f"  해결: news-trading-bot이 위 경로에 있고, paper_trading 패키지가 정상인지 확인하세요."
        )


__all__ = [
    "BaseStrategy",
    "Candidate",
    "StrategyResult",
    "StrategyRegistry",
    "NTB_AVAILABLE",
    "NTB_ROOT",
    "assert_ntb_available",
]
