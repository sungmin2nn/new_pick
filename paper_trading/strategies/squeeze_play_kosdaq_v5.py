"""
KOSDAQ v5 — Squeeze@15% 단독 (MA200 OFF), DEC-005, P3-3b.

백테스트 (2024-05-01 ~ 2026-04-30, 485영업일, KOSDAQ Top35):
- 거래수: 418 / 승률: 47.8% / 평균 +0.57%/거래 / 누적 +236.62% / MDD 129.4% / 위험조정 1.83
- 보유기간 5일 (RECOMMENDED_HOLDING_DAYS=5)
- KOSDAQ에서 v6 (MA200 ON) 부적합 — 18거래 -2.01%~-11.45% (DEC-005)
- 출처: .claude/context/results/squeeze-play-kosdaq-{holding,v5-holding}-001.json + DEC-005

⚠️ MDD 129% — 운영 시 자금 비중·종목 한도 별도 통제 필수 (P3-3 플랜 §5.2).
"""

from .registry import StrategyRegistry
from .squeeze_play_base import SqueezePlayBaseStrategy
from ._squeeze_common import KOSDAQ_TOP_35


@StrategyRegistry.register
class SqueezePlayKosdaqV5Strategy(SqueezePlayBaseStrategy):
    STRATEGY_ID = "squeeze_play_kosdaq_v5"
    STRATEGY_NAME = "스퀴즈 플레이 KOSDAQ v5"
    DESCRIPTION = (
        "BB 평균회귀 + 20MA·200MA 간격 ≤15% (MA200 우상향 미요구) "
        "KOSDAQ 시총상위 35종목, 5일 보유"
    )

    UNIVERSE = KOSDAQ_TOP_35
    UNIVERSE_MARKET = "KOSDAQ"
    MA200_FILTER_ENABLED = False
    SQUEEZE_FILTER_ENABLED = True
    SQUEEZE_MAX_SPREAD_PCT = 15.0
    RECOMMENDED_HOLDING_DAYS = 5
