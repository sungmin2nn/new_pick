"""
KOSPI v6 — MA200 + Squeeze@10% (DEC-005, P3-3b).

백테스트 (2024-05-01 ~ 2026-04-30, 485영업일, KOSPI Top53):
- 거래수: 81 / 승률: 65.4% / 평균 +2.40%/거래 / 누적 +194.75% / MDD 8.17% / 위험조정 23.84
- 보유기간 5일 (RECOMMENDED_HOLDING_DAYS=5)
- 출처: .claude/context/results/squeeze-play-kospi-2y-001.json + DEC-005

Universe / 보유 정책 / 필터 모두 4주 shadow 동안 고정.
"""

from .registry import StrategyRegistry
from .squeeze_play_base import SqueezePlayBaseStrategy
from ._squeeze_common import KOSPI_TOP_53


@StrategyRegistry.register
class SqueezePlayKospiV6Strategy(SqueezePlayBaseStrategy):
    STRATEGY_ID = "squeeze_play_kospi_v6"
    STRATEGY_NAME = "스퀴즈 플레이 KOSPI v6"
    DESCRIPTION = (
        "임마누엘 매매법 (MA200 우상향 + 20MA·200MA 간격 ≤10% + BB %B<0.2 + 양봉) "
        "KOSPI 시총상위 53종목, 5일 보유"
    )

    UNIVERSE = KOSPI_TOP_53
    UNIVERSE_MARKET = "KOSPI"
    MA200_FILTER_ENABLED = True
    SQUEEZE_FILTER_ENABLED = True
    SQUEEZE_MAX_SPREAD_PCT = 10.0
    RECOMMENDED_HOLDING_DAYS = 5
