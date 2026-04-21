"""
Strategy: Volatility Breakout (Larry Williams K-value)
========================================================

가설:
  전일 변동폭(high - low)의 K배만큼 시초가에서 추가 상승하면
  당일 추세가 이어질 가능성이 높다 (변동성 = 모멘텀의 선행 지표).

핵심 시그널:
  trigger_price = today_open + (yesterday_high - yesterday_low) * K
  today_high >= trigger_price → 돌파 발생 (매수 시그널)

K 값:
  Larry Williams 원본은 K=0.5
  한국 시장 검증 사례에서는 0.5~0.7이 안정적

본 전략 vs Echo Frontier:
  Echo: '전일 종가 → 시초가' 갭 비율(2~5%)을 트리거
  본 전략: '전일 변동폭 × K' 절대 가격 폭을 시초가에 더한 가격을 트리거
  → 갭 없어도 발동 가능, 변동성 자체를 직접 측정

데이터 의존도:
  KRX OpenAPI (오늘 + 어제 OHLCV)
  분봉 6일 한계로 backtest는 일봉 시뮬 정확도 ~80%

작성: 2026-04-11 / Phase 2.1
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

# news-trading-bot 경로 보장 (lab/__init__이 처리)
from lab import BaseStrategy, Candidate
from lab.common import (
    get_krx, previous_trading_day, fetch_all_markets, basic_filter,
)
from lab.metadata import (
    StrategyMetadata, StrategySource,
    StrategyCategory, RiskLevel, SourceType, TrustLevel,
)

logger = logging.getLogger(__name__)


# ============================================================
# Metadata
# ============================================================

METADATA = StrategyMetadata(
    id="volatility_breakout_lw",
    name="변동성 돌파 (Larry Williams)",
    version="0.1.0",
    category=StrategyCategory.BREAKOUT.value,
    risk_level=RiskLevel.MEDIUM.value,

    hypothesis="전일 변동폭의 K배만큼 시초가에서 상승 돌파하면 당일 추세가 이어진다",
    rationale=(
        "Larry Williams가 1980년대 제안한 클래식 단타 전략. "
        "한국 시장에서도 K=0.5~0.7 범위에서 검증된 사례가 다수 있다. "
        "변동성을 모멘텀의 선행 지표로 사용한다는 점이 핵심."
    ),
    expected_edge="장중 추세 지속성, 거래량 동반 시 상승 가능성 ↑",

    data_requirements=["KRX_OHLCV"],
    min_history_days=2,
    requires_intraday=False,  # 일봉 시뮬로도 검증 가능

    target_basket_size=5,
    target_holding_days=1,
    target_market="KOSPI+KOSDAQ",

    differs_from_existing=(
        "Echo Frontier와 다름: Echo는 '전일 종가→시초가' 갭 비율(2~5%)을 트리거로 사용. "
        "본 전략은 '전일 (high-low) × K' 절대 가격폭을 시초가에 더한 가격을 트리거. "
        "갭이 거의 없는 종목에서도 발동 가능하고, 변동성 자체를 직접 측정한다는 점이 본질적으로 다름."
    ),
    novelty_score=7,
    notes="K 값 튜닝 가능. 거래량 surge 필터 추가로 정밀도 향상.",
)

METADATA.add_source(StrategySource(
    type=SourceType.BOOK.value,
    title="Long-Term Secrets to Short-Term Trading",
    author="Larry Williams",
    published_date="1999",
    trust_level=TrustLevel.VERIFIED.value,
    notes="원전. K=0.5 권장.",
))
METADATA.add_source(StrategySource(
    type=SourceType.HANDOFF_GUIDE.value,
    title="news-trading-bot-handoff.md Section 6.2",
    trust_level=TrustLevel.HIGH.value,
    notes="신규 전략 후보로 명시됨.",
))


# ============================================================
# Strategy class
# ============================================================

class VolatilityBreakoutLW(BaseStrategy):
    """변동성 돌파 (Larry Williams K-value)."""

    STRATEGY_ID = METADATA.id
    STRATEGY_NAME = METADATA.name
    DESCRIPTION = METADATA.hypothesis

    # 파라미터
    K_VALUE: float = 0.5
    MIN_PRICE: int = 3000
    MIN_TRADING_VALUE: int = 5_000_000_000  # 50억
    MIN_MARKET_CAP: int = 50_000_000_000     # 500억
    VOLUME_SURGE_MIN: float = 1.5            # 거래량 평소 대비 1.5배 이상

    # 점수 가중치 (총 100)
    WEIGHTS = {
        "breakout_strength": 45,  # 돌파 강도
        "volume_surge": 30,       # 거래량 증가
        "trading_value": 15,      # 유동성
        "price_level": 10,        # 가격대
    }

    def __init__(self):
        super().__init__()

    def select_stocks(self, date: Optional[str] = None, top_n: int = 5) -> List[Candidate]:
        """종목 선정."""
        if date is None:
            date = datetime.now().strftime("%Y%m%d")
        self.selection_date = date
        print(f"\n[{self.STRATEGY_NAME}] 종목 선정 시작 ({date})")

        krx = get_krx()
        if not krx:
            print("  KRX 사용 불가")
            return []

        # 1. 어제 영업일
        prev_date = previous_trading_day(date)
        if not prev_date:
            print("  전 영업일 데이터 없음")
            return []
        print(f"  전 영업일: {prev_date}")

        # 2. 오늘 + 어제 데이터
        today_stocks = fetch_all_markets(date)
        prev_stocks = fetch_all_markets(prev_date)
        if not today_stocks or not prev_stocks:
            print("  데이터 없음")
            return []
        print(f"  오늘: {len(today_stocks)}개 / 어제: {len(prev_stocks)}개")

        prev_map = {s["code"]: s for s in prev_stocks}

        # 3. 트리거 계산 + 1차 필터
        candidates_raw = self._compute_breakouts(today_stocks, prev_map)
        print(f"  돌파 발생: {len(candidates_raw)}개")

        # 4. 기본 필터 (가격/유동성/시총/우선주)
        filtered = basic_filter(
            candidates_raw,
            min_price=self.MIN_PRICE,
            min_market_cap=self.MIN_MARKET_CAP,
            min_trading_value=self.MIN_TRADING_VALUE,
        )
        print(f"  기본 필터 통과: {len(filtered)}개")

        if not filtered:
            return []

        # 5. 점수
        scored = self._calculate_scores(filtered)
        scored.sort(key=lambda c: c.score, reverse=True)
        self.candidates = scored[:top_n]
        for i, c in enumerate(self.candidates, 1):
            c.rank = i

        print(f"  선정 완료: {len(self.candidates)}개")
        return self.candidates

    def _compute_breakouts(self, today: List[Dict], prev_map: Dict) -> List[Dict]:
        """trigger_price 계산 후 돌파 발생 종목만 추출."""
        passed = []
        for s in today:
            prev = prev_map.get(s["code"])
            if not prev:
                continue
            prev_high = prev["high"]
            prev_low = prev["low"]
            if prev_high <= 0 or prev_low <= 0 or prev_high <= prev_low:
                continue

            range_k = (prev_high - prev_low) * self.K_VALUE
            trigger = s["open"] + range_k
            if trigger <= 0:
                continue

            if s["high"] >= trigger:
                # 거래량 surge 계산 (어제 거래량 대비)
                prev_vol = prev["volume"] or 1
                vol_ratio = s["volume"] / prev_vol if prev_vol else 0
                if vol_ratio < self.VOLUME_SURGE_MIN:
                    continue

                s["trigger_price"] = int(trigger)
                s["range_k"] = int(range_k)
                s["breakout_strength"] = (s["high"] - trigger) / trigger
                s["vol_ratio"] = vol_ratio
                passed.append(s)
        return passed

    def _calculate_scores(self, stocks: List[Dict]) -> List[Candidate]:
        if not stocks:
            return []

        max_strength = max((s["breakout_strength"] for s in stocks), default=1) or 1
        max_vol_ratio = max((s["vol_ratio"] for s in stocks), default=1) or 1
        max_value = max((s["trading_value"] for s in stocks), default=1) or 1

        candidates: List[Candidate] = []
        for s in stocks:
            score_detail = {
                "breakout_strength": (s["breakout_strength"] / max_strength) * self.WEIGHTS["breakout_strength"],
                "volume_surge": (s["vol_ratio"] / max_vol_ratio) * self.WEIGHTS["volume_surge"],
                "trading_value": (s["trading_value"] / max_value) * self.WEIGHTS["trading_value"],
                "price_level": (
                    self.WEIGHTS["price_level"]
                    if 5000 <= s["close"] <= 100_000
                    else self.WEIGHTS["price_level"] * 0.5
                ),
            }
            total = round(sum(score_detail.values()), 2)
            candidates.append(Candidate(
                code=s["code"],
                name=s["name"],
                price=s["close"],
                change_pct=s["change_pct"],
                score=total,
                score_detail={k: round(v, 2) for k, v in score_detail.items()},
                market_cap=s["market_cap"],
                volume=s["volume"],
                trading_value=s["trading_value"],
            ))
        return candidates

    def get_params(self) -> Dict:
        return {
            "k_value": self.K_VALUE,
            "min_price": self.MIN_PRICE,
            "min_trading_value": self.MIN_TRADING_VALUE,
            "min_market_cap": self.MIN_MARKET_CAP,
            "volume_surge_min": self.VOLUME_SURGE_MIN,
            "weights": self.WEIGHTS,
        }
