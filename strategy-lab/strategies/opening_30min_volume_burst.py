"""
Strategy: Opening 30-Minute Volume Burst (한국 골든타임)
========================================================

출처:
  한국 단타 매매 관행 + 학술 검증 결합:
  - 나무위키 [주식투자/단타매매 기법]
    https://namu.wiki/w/주식투자/단타매매%20기법
  - 9시 땡 단타 노트 https://lilys.ai/ko/notes/243639
  - Park & Yang (2022) MIM 학술 논문에서도 첫 30분 시그널 강도 R² 3.3%
    (변동성 높을 때) 검증

한국 시장 고유 특성 (출처):
  "9시~9시 30분에 거래대금의 38%가 형성"
  "거래량 폭발 종목은 첫 1~2분에 일중 거래량의 40~50% 발생"
  → 한국 시장에서만 두드러지는 골든타임 효과

가설:
  당일 거래대금이 평소 대비 폭발적으로 증가하면서
  주가가 양봉을 형성한 종목은 일중 추세 지속.

본 전략 vs Echo Frontier / Volatility BO:
  Echo: 시초가 갭 +2~5% (가격 갭 자체)
  VB: 전일 변동폭 K배 돌파 (가격 변동성)
  본 전략: '거래대금 폭발 강도' 자체를 핵심 시그널로
  → 한국 단타 골든타임 효과를 정량화

분봉 6일 한계:
  '첫 30분 거래대금'은 일별 거래대금 / 거래량 비율로 근사 (불완전)
  실전에서는 분봉 활용 가능 (분봉 데이터 6일 한계 내)

데이터 의존도:
  KRX OpenAPI (당일 + 5일 이상 history)

작성: 2026-04-11 / Phase 2.4
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
    id="opening_30min_volume_burst",
    name="개장 30분 거래대금 폭발 (한국 골든타임)",
    version="0.1.0",
    category=StrategyCategory.BREAKOUT.value,
    risk_level=RiskLevel.HIGH.value,

    hypothesis="개장 직후 거래대금 폭발 + 양봉 종목은 일중 추세 지속",
    rationale=(
        "한국 시장은 09:00~09:30 거래대금이 일중 38% 형성되는 골든타임 효과가 있음. "
        "이 시간대 거래대금 폭발은 강한 시장 관심을 의미하며, 양봉 동반 시 추세 지속. "
        "관행적 지식이지만 Park & Yang (2022) MIM 논문에서도 변동성 높은 첫 30분의 "
        "예측력(R² 3.3%)이 검증됨."
    ),
    expected_edge="한국 시장 고유의 개장 골든타임 거래대금 집중 효과",

    data_requirements=["KRX_OHLCV"],
    min_history_days=5,
    requires_intraday=False,  # 일별 거래대금 surge로 근사

    target_basket_size=5,
    target_holding_days=1,
    target_market="KOSPI+KOSDAQ",

    differs_from_existing=(
        "Echo Frontier와 다름: Echo는 가격 갭(2~5%)이 시그널, 본 전략은 거래대금 surge가 시그널. "
        "Volatility BO와 다름: VB는 가격 변동폭, 본 전략은 거래량/거래대금 변동. "
        "Alpha Momentum과 다름: Alpha는 5일 평균 + 거래량 3배 (스무딩), "
        "본 전략은 단일일 거래대금 폭발 강도 자체. "
        "근거: 한국 시장 골든타임 관행 + MIM 학술."
    ),
    novelty_score=7,
    notes="분봉 데이터 사용 가능 시 정밀도 ↑ (6일 한계).",
)

METADATA.add_source(StrategySource(
    type=SourceType.BLOG_KO.value,
    title="주식투자/단타매매 기법",
    url="https://namu.wiki/w/주식투자/단타매매%20기법",
    trust_level=TrustLevel.MEDIUM.value,
    notes="나무위키. 다수 trader 검증된 단타 관행 요약.",
))
METADATA.add_source(StrategySource(
    type=SourceType.PAPER.value,
    title="Market Intraday Momentum (KOSPI evidence)",
    author="Park & Yang",
    url="https://www.mdpi.com/1911-8074/15/11/523",
    published_date="2022",
    trust_level=TrustLevel.VERIFIED.value,
    notes="첫 30분 시그널 R² 3.3% 검증 (변동성 ↑ 시).",
))


class Opening30MinVolumeBurstStrategy(BaseStrategy):
    """개장 30분 거래대금 폭발 전략."""

    STRATEGY_ID = METADATA.id
    STRATEGY_NAME = METADATA.name
    DESCRIPTION = METADATA.hypothesis

    # 파라미터
    VALUE_SURGE_MIN: float = 3.0           # 거래대금 5일 평균 대비 3배 이상
    PRICE_UP_MIN_PCT: float = 1.5          # 양봉 최소 1.5%
    MIN_PRICE: int = 2000
    MIN_MARKET_CAP: int = 50_000_000_000   # 500억
    MIN_TRADING_VALUE: int = 5_000_000_000  # 50억
    HISTORY_DAYS: int = 7

    WEIGHTS = {
        "volume_surge": 45,                # 거래대금 폭발이 핵심
        "price_momentum": 30,              # 양봉 강도
        "absolute_value": 15,              # 절대 거래대금
        "price_level": 10,
    }

    def __init__(self):
        super().__init__()

    def select_stocks(self, date: Optional[str] = None, top_n: int = 5) -> List[Candidate]:
        if date is None:
            date = datetime.now().strftime("%Y%m%d")
        self.selection_date = date
        print(f"\n[{self.STRATEGY_NAME}] 종목 선정 시작 ({date})")

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
        filtered = [s for s in filtered if s["change_pct"] >= self.PRICE_UP_MIN_PCT]
        print(f"  1차 필터: {len(filtered)}개")

        if not filtered:
            return []

        # 2. 거래대금 surge 필터 (5일 평균 대비 3배)
        surged = self._filter_value_surge(filtered, date, krx)
        print(f"  거래대금 surge: {len(surged)}개")

        if not surged:
            return []

        scored = self._calculate_scores(surged)
        scored.sort(key=lambda c: c.score, reverse=True)
        self.candidates = scored[:top_n]
        for i, c in enumerate(self.candidates, 1):
            c.rank = i

        print(f"  선정 완료: {len(self.candidates)}개")
        return self.candidates

    def _filter_value_surge(self, stocks: List[Dict], date: str, krx) -> List[Dict]:
        """거래대금이 최근 5일 평균 대비 N배 이상인 종목."""
        end_dt = datetime.strptime(date, "%Y%m%d")
        start_dt = end_dt - timedelta(days=self.HISTORY_DAYS + 3)

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
                if df is None or df.empty or len(df) < 5:
                    s["value_ratio"] = 1.0
                    passed.append(s)
                    continue

                values = df["거래대금"].astype(float).values
                avg_value = sum(values[-5:]) / 5
                if avg_value <= 0:
                    continue

                ratio = s["trading_value"] / avg_value
                if ratio < self.VALUE_SURGE_MIN:
                    continue

                s["value_ratio"] = round(ratio, 2)
                passed.append(s)
            except Exception as e:
                logger.debug(f"거래대금 fetch 실패 {s['code']}: {e}")
                continue

        return passed

    def _calculate_scores(self, stocks: List[Dict]) -> List[Candidate]:
        if not stocks:
            return []

        max_ratio = max((s.get("value_ratio", 0) for s in stocks), default=1) or 1
        max_change = max((s["change_pct"] for s in stocks), default=1) or 1
        max_tv = max((s["trading_value"] for s in stocks), default=1) or 1

        candidates: List[Candidate] = []
        for s in stocks:
            score_detail = {
                "volume_surge": (s.get("value_ratio", 1) / max_ratio) * self.WEIGHTS["volume_surge"],
                "price_momentum": (s["change_pct"] / max_change) * self.WEIGHTS["price_momentum"],
                "absolute_value": (s["trading_value"] / max_tv) * self.WEIGHTS["absolute_value"],
                "price_level": (
                    self.WEIGHTS["price_level"]
                    if 3000 <= s["close"] <= 50_000
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
            "value_surge_min": self.VALUE_SURGE_MIN,
            "price_up_min_pct": self.PRICE_UP_MIN_PCT,
            "min_price": self.MIN_PRICE,
            "min_market_cap": self.MIN_MARKET_CAP,
            "min_trading_value": self.MIN_TRADING_VALUE,
            "history_days": self.HISTORY_DAYS,
            "weights": self.WEIGHTS,
        }
