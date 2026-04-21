"""
Strategy: Turtle Breakout (Short-Term Adaptation)
===================================================

출처:
  Richard Dennis & Bill Eckhardt의 Turtle Trading System (1980s)
  + 현대 백테스트 검증:
    - https://www.fundedtradingplus.com/propiq/turtle-trading-strategy-the-classic-breakout-system-made-simple-donchian-channels-trend-filter/
    - https://tosindicators.com/research/modern-turtle-trading-strategy-rules-and-backtest

원본 핵심:
  System 1: 20일 신고가 돌파 long, 10일 신저가 청산
  System 2: 55일 신고가 돌파 long, 20일 신저가 청산

단타 적응:
  단타 framework에서는 20일도 너무 김 → 5일 또는 10일 단축 버전.
  N일 신고가 돌파 + 거래량 동반 = 진입.
  당일 청산 (단타 룰).

본 전략 vs Echo Frontier / Volatility BO:
  Echo: 시초가 갭 (전일 종가 → 시초가)
  VB: 전일 변동폭 K배
  Alpha Momentum: MA5 + 거래량 (5일 평균)
  본 전략: 5일 또는 10일 신고가 돌파 (절대 가격 신기록)
  → "신고가" 자체가 시그널 (모멘텀 추세의 가장 단순한 형태)

주의:
  Modern 시장에서 20일 ORB는 System 2(55일)이 더 우수.
  단축 버전(5/10일)은 알파 약화 가능 → backtest 검증 필수.

데이터 의존도:
  KRX OpenAPI (10일+ history)

작성: 2026-04-11 / Phase 2.5
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from lab import BaseStrategy, Candidate
from lab.common import get_krx, fetch_all_markets, basic_filter, batch_get_history
from lab.metadata import (
    StrategyMetadata, StrategySource,
    StrategyCategory, RiskLevel, SourceType, TrustLevel,
)

logger = logging.getLogger(__name__)


METADATA = StrategyMetadata(
    id="turtle_breakout_short",
    name="단축 터틀 돌파 (5/10일 신고가)",
    version="0.1.0",
    category=StrategyCategory.BREAKOUT.value,
    risk_level=RiskLevel.MEDIUM.value,

    hypothesis="N일 신고가 돌파 + 거래량 동반 종목은 추세 지속 가능성",
    rationale=(
        "Richard Dennis & Bill Eckhardt의 Turtle Trading System(1980s)을 단타에 적응. "
        "원본은 20/55일 신고가지만 단타에는 5/10일 단축 사용. "
        "현대 시장에서 단축 버전은 알파 약화 가능성이 있어 backtest 검증 필수. "
        "신고가 자체는 모멘텀 추세의 가장 단순하고 robust한 시그널."
    ),
    expected_edge="신고가 갱신 + 거래량 동반의 추세 추종 효과",

    data_requirements=["KRX_OHLCV"],
    min_history_days=15,
    requires_intraday=False,

    target_basket_size=5,
    target_holding_days=1,
    target_market="KOSPI+KOSDAQ",

    differs_from_existing=(
        "Echo Frontier와 다름: Echo는 시초가 갭 비율, 본 전략은 N일 신고가 돌파. "
        "Volatility BO와 다름: VB는 전일 변동폭 K배, 본 전략은 절대 신고가. "
        "Alpha Momentum과 다름: Alpha는 MA5 위 + 거래량 3배 (스무딩), "
        "본 전략은 N일 신고가 돌파 (단순 신기록). "
        "Donchian Channel 클래식 전략의 단축 버전."
    ),
    novelty_score=6,
    notes="N=5, 10 두 가지 파라미터 시험 가능. 단축 버전이라 alpha 약화 위험.",
)

METADATA.add_source(StrategySource(
    type=SourceType.BOOK.value,
    title="Way of the Turtle",
    author="Curtis Faith",
    published_date="2007",
    trust_level=TrustLevel.VERIFIED.value,
    notes="Turtle Trading System 원본 정리. Richard Dennis 시스템.",
))
METADATA.add_source(StrategySource(
    type=SourceType.BLOG_EN.value,
    title="Modern Turtle Trading Strategy: Updated Rules & Backtest",
    url="https://tosindicators.com/research/modern-turtle-trading-strategy-rules-and-backtest",
    trust_level=TrustLevel.HIGH.value,
    notes="현대 시장에서 System 2 (55일)가 System 1 (20일)보다 우수. 단축 버전 주의.",
))


class TurtleBreakoutShortStrategy(BaseStrategy):
    """단축 터틀 신고가 돌파 (5일 또는 10일)."""

    STRATEGY_ID = METADATA.id
    STRATEGY_NAME = METADATA.name
    DESCRIPTION = METADATA.hypothesis

    # 파라미터
    LOOKBACK_DAYS: int = 5             # 신고가 lookback (5/10 가능)
    HISTORY_FETCH_DAYS: int = 14
    MIN_PRICE: int = 3000
    MIN_MARKET_CAP: int = 100_000_000_000   # 1000억
    MIN_TRADING_VALUE: int = 5_000_000_000  # 50억
    VOLUME_SURGE_MIN: float = 1.5
    MIN_PRICE_INCREASE: float = 1.0    # 최소 등락률 (음봉 신고가 제외)

    WEIGHTS = {
        "breakout_freshness": 35,      # 신고가 갱신 강도
        "volume_surge": 30,            # 거래량 동반
        "trading_value": 20,           # 절대 거래대금
        "price_momentum": 15,          # 가격 모멘텀
    }

    def __init__(self):
        super().__init__()

    def select_stocks(self, date: Optional[str] = None, top_n: int = 5) -> List[Candidate]:
        if date is None:
            date = datetime.now().strftime("%Y%m%d")
        self.selection_date = date
        print(f"\n[{self.STRATEGY_NAME}] 종목 선정 시작 ({date}, lookback={self.LOOKBACK_DAYS}일)")

        krx = get_krx()
        if not krx:
            print("  KRX 사용 불가")
            return []

        all_stocks = fetch_all_markets(date)
        if not all_stocks:
            return []

        # 1. 1차 필터 (양봉 + 가격/유동성)
        filtered = basic_filter(
            all_stocks,
            min_price=self.MIN_PRICE,
            min_market_cap=self.MIN_MARKET_CAP,
            min_trading_value=self.MIN_TRADING_VALUE,
        )
        filtered = [s for s in filtered if s["change_pct"] >= self.MIN_PRICE_INCREASE]
        print(f"  1차 필터: {len(filtered)}개")

        if not filtered:
            return []

        # 2. 5일 신고가 검사
        breakouts = self._filter_n_day_high_breakout(filtered, date, krx)
        print(f"  {self.LOOKBACK_DAYS}일 신고가 돌파: {len(breakouts)}개")

        if not breakouts:
            return []

        scored = self._calculate_scores(breakouts)
        scored.sort(key=lambda c: c.score, reverse=True)
        self.candidates = scored[:top_n]
        for i, c in enumerate(self.candidates, 1):
            c.rank = i

        print(f"  선정 완료: {len(self.candidates)}개")
        return self.candidates

    def _filter_n_day_high_breakout(self, stocks: List[Dict], date: str, krx) -> List[Dict]:
        """N일 신고가를 돌파한 종목만."""
        end_dt = datetime.strptime(date, "%Y%m%d")
        start_dt = end_dt - timedelta(days=self.HISTORY_FETCH_DAYS)

        # 배치로 전종목 히스토리 한번에 가져오기 (캐시 활용)
        codes = [s["code"] for s in stocks]
        history_map = batch_get_history(
            codes,
            start_dt.strftime("%Y%m%d"),
            (end_dt - timedelta(days=1)).strftime("%Y%m%d"),
        )

        passed = []
        for s in stocks:
            try:
                df = history_map.get(s["code"])
                if df is None or df.empty or len(df) < self.LOOKBACK_DAYS:
                    continue

                highs = df["고가"].astype(float).values
                volumes = df["거래량"].astype(float).values

                # 직전 N일 최고가
                n_day_high = float(max(highs[-self.LOOKBACK_DAYS:]))
                if s["high"] <= n_day_high:
                    continue  # 신고가 돌파 안됨

                # 거래량 surge
                avg_vol = sum(volumes[-self.LOOKBACK_DAYS:]) / max(self.LOOKBACK_DAYS, 1)
                if avg_vol == 0:
                    continue
                vol_ratio = s["volume"] / avg_vol
                if vol_ratio < self.VOLUME_SURGE_MIN:
                    continue

                # 신고가 돌파 강도
                freshness = (s["high"] - n_day_high) / n_day_high

                s["n_day_high"] = int(n_day_high)
                s["breakout_freshness"] = round(freshness, 4)
                s["vol_ratio"] = round(vol_ratio, 2)
                passed.append(s)
            except Exception as e:
                logger.debug(f"history fetch 실패 {s['code']}: {e}")
                continue

        return passed

    def _calculate_scores(self, stocks: List[Dict]) -> List[Candidate]:
        if not stocks:
            return []

        max_freshness = max((s.get("breakout_freshness", 0) for s in stocks), default=1) or 1
        max_vol_ratio = max((s.get("vol_ratio", 1) for s in stocks), default=1) or 1
        max_tv = max((s["trading_value"] for s in stocks), default=1) or 1
        max_change = max((s["change_pct"] for s in stocks), default=1) or 1

        candidates: List[Candidate] = []
        for s in stocks:
            score_detail = {
                "breakout_freshness": (s.get("breakout_freshness", 0) / max_freshness) * self.WEIGHTS["breakout_freshness"],
                "volume_surge": (s.get("vol_ratio", 1) / max_vol_ratio) * self.WEIGHTS["volume_surge"],
                "trading_value": (s["trading_value"] / max_tv) * self.WEIGHTS["trading_value"],
                "price_momentum": (s["change_pct"] / max_change) * self.WEIGHTS["price_momentum"],
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
            "lookback_days": self.LOOKBACK_DAYS,
            "history_fetch_days": self.HISTORY_FETCH_DAYS,
            "min_price": self.MIN_PRICE,
            "min_market_cap": self.MIN_MARKET_CAP,
            "min_trading_value": self.MIN_TRADING_VALUE,
            "volume_surge_min": self.VOLUME_SURGE_MIN,
            "min_price_increase": self.MIN_PRICE_INCREASE,
            "weights": self.WEIGHTS,
        }
