"""
Strategy: KOSPI Intraday Momentum (MIM)
=========================================

학술 검증 출처:
  Park, J. & Yang, J. (2022). "Market Intraday Momentum with New Measures
  for Trading Cost: Evidence from KOSPI Index". Journal of Risk and Financial
  Management 15(11), 523. MDPI.
  https://www.mdpi.com/1911-8074/15/11/523

  + Gao, Han, Li, Zhou (2018). "Market Intraday Momentum". Journal of Financial
    Economics. (한국 KODEX 200 검증 본 SNU 학위논문 참조)

핵심 발견 (논문 인용):
  10년+ KOSPI 인덱스 30분 데이터 분석.
  overnight 수익률 + 첫 30분 수익률 → 마지막 30분 수익률 예측
  거래비용 반영 후도 알파 유의 (effective spread 측정)

가설 (단타 적용):
  KOSPI 인덱스 자체가 아닌 개별 종목에서도
  당일 첫 30분 강세 + 시초가 갭 양수 → 당일 종가까지 추세 지속

본 전략 vs Volatility Breakout:
  Volatility BO: 전일 변동폭 K배 가격 돌파 (절대 가격)
  본 전략: 첫 30분 수익률 부호와 강도 (수익률 자체)
  → 학술 검증된 robust 시그널

데이터 의존도:
  KRX OpenAPI (시가/고가/저가/종가)
  분봉 6일 한계로 "첫 30분"을 시초가 갭 + 시초가 대비 고가 비율로 근사

작성: 2026-04-11 / Phase 2.4
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Dict, Optional

from lab import BaseStrategy, Candidate
from lab.common import get_krx, fetch_all_markets, basic_filter
from lab.metadata import (
    StrategyMetadata, StrategySource,
    StrategyCategory, RiskLevel, SourceType, TrustLevel,
)

logger = logging.getLogger(__name__)


METADATA = StrategyMetadata(
    id="kospi_intraday_momentum",
    name="KOSPI 인트라데이 모멘텀 (학술 MIM)",
    version="0.1.0",
    category=StrategyCategory.MOMENTUM.value,
    risk_level=RiskLevel.MEDIUM.value,

    hypothesis="overnight + 첫 30분 강세 종목은 당일 추세를 종가까지 이어간다",
    rationale=(
        "Park & Yang (2022, MDPI JRFM)이 10년+ KOSPI 인덱스 30분 데이터로 검증한 "
        "Market Intraday Momentum (MIM)의 단타 종목 버전. "
        "overnight 수익률(전일종가→오늘 시초가) + 첫 30분 수익률을 결합한 시그널이 "
        "마지막 30분 수익률을 robust하게 예측. 거래비용 반영 후도 알파 유의."
    ),
    expected_edge="학술 검증된 한국 시장 인트라데이 모멘텀 효과 (정보 처리 시차)",

    data_requirements=["KRX_OHLCV"],
    min_history_days=2,
    requires_intraday=False,  # 시초가 vs 종가 근사

    target_basket_size=5,
    target_holding_days=1,
    target_market="KOSPI+KOSDAQ",

    differs_from_existing=(
        "Volatility Breakout과 다름: VB는 전일 변동폭 K배 절대 가격 돌파. "
        "본 전략은 학술적으로 검증된 '첫 30분 수익률' 시그널 (수익률 자체). "
        "Alpha Momentum과도 다름: Alpha는 5일 평균 + 거래량 3배. "
        "본 전략은 단일일 신호 (overnight + 첫 30분), 학술 검증 알파 기반."
    ),
    novelty_score=8,
    notes=(
        "분봉 6일 한계로 '첫 30분 수익률'을 (시초가 - 전일종가) + (현재가 - 시초가) × 0.5 로 근사. "
        "정밀 백테스트는 분봉 가능 범위 내에서만."
    ),
)

METADATA.add_source(StrategySource(
    type=SourceType.PAPER.value,
    title="Market Intraday Momentum with New Measures for Trading Cost: Evidence from KOSPI Index",
    author="Park, J. & Yang, J.",
    url="https://www.mdpi.com/1911-8074/15/11/523",
    published_date="2022",
    trust_level=TrustLevel.VERIFIED.value,
    notes="MDPI Journal of Risk and Financial Management. 동료심사 학술지. 10년 KOSPI 데이터 검증.",
))
METADATA.add_source(StrategySource(
    type=SourceType.PAPER.value,
    title="Intraday Momentum: The First Half-Hour Return Predicts the Last Half-Hour Return",
    author="Gao, Han, Li, Zhou",
    url="https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2552752",
    published_date="2018",
    trust_level=TrustLevel.VERIFIED.value,
    notes="Journal of Financial Economics. SNU 학위논문에서 KODEX 200으로 한국 검증.",
))


class KospiIntradayMomentumStrategy(BaseStrategy):
    """학술 검증된 KOSPI Intraday Momentum 단타 종목 버전."""

    STRATEGY_ID = METADATA.id
    STRATEGY_NAME = METADATA.name
    DESCRIPTION = METADATA.hypothesis

    # 파라미터
    OVERNIGHT_MIN_PCT: float = 0.5     # overnight 수익률 (시초가 - 전일종가) 최소
    INTRADAY_MIN_PCT: float = 0.5      # 첫 30분 근사 수익률 최소
    MIN_PRICE: int = 3000
    MIN_MARKET_CAP: int = 100_000_000_000   # 1000억
    MIN_TRADING_VALUE: int = 5_000_000_000  # 50억

    WEIGHTS = {
        "overnight_strength": 30,
        "intraday_strength": 35,
        "combined_signal": 20,
        "trading_value": 15,
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
            print("  데이터 없음")
            return []
        print(f"  전체: {len(all_stocks)}개")

        # 1. 시그널 계산
        signaled = []
        for s in all_stocks:
            prev_close = s["prev_close"]
            if prev_close <= 0 or s["open"] <= 0 or s["close"] <= 0:
                continue

            # overnight = (시초가 - 전일종가) / 전일종가
            overnight_pct = (s["open"] - prev_close) / prev_close * 100

            # 첫 30분 근사 = (고가 - 시초가) / 시초가 × 0.5
            #   (분봉 6일 한계 우회. 일봉 high가 첫 30분 안에 발생할 가능성을 가정)
            intraday_proxy = (s["high"] - s["open"]) / s["open"] * 100 * 0.5

            # 결합 시그널 (논문에서 둘 다 양수 + 합계가 일정 수준 이상)
            combined_signal = overnight_pct + intraday_proxy

            if overnight_pct < self.OVERNIGHT_MIN_PCT:
                continue
            if intraday_proxy < self.INTRADAY_MIN_PCT:
                continue

            s["overnight_pct"] = overnight_pct
            s["intraday_proxy"] = intraday_proxy
            s["combined_signal"] = combined_signal
            signaled.append(s)

        print(f"  시그널 통과: {len(signaled)}개")

        # 2. 기본 필터
        filtered = basic_filter(
            signaled,
            min_price=self.MIN_PRICE,
            min_market_cap=self.MIN_MARKET_CAP,
            min_trading_value=self.MIN_TRADING_VALUE,
        )
        print(f"  기본 필터: {len(filtered)}개")

        if not filtered:
            return []

        scored = self._calculate_scores(filtered)
        scored.sort(key=lambda c: c.score, reverse=True)
        self.candidates = scored[:top_n]
        for i, c in enumerate(self.candidates, 1):
            c.rank = i

        print(f"  선정 완료: {len(self.candidates)}개")
        return self.candidates

    def _calculate_scores(self, stocks: List[Dict]) -> List[Candidate]:
        if not stocks:
            return []

        max_overnight = max((s["overnight_pct"] for s in stocks), default=1) or 1
        max_intraday = max((s["intraday_proxy"] for s in stocks), default=1) or 1
        max_combined = max((s["combined_signal"] for s in stocks), default=1) or 1
        max_tv = max((s["trading_value"] for s in stocks), default=1) or 1

        candidates: List[Candidate] = []
        for s in stocks:
            score_detail = {
                "overnight_strength": (s["overnight_pct"] / max_overnight) * self.WEIGHTS["overnight_strength"],
                "intraday_strength": (s["intraday_proxy"] / max_intraday) * self.WEIGHTS["intraday_strength"],
                "combined_signal": (s["combined_signal"] / max_combined) * self.WEIGHTS["combined_signal"],
                "trading_value": (s["trading_value"] / max_tv) * self.WEIGHTS["trading_value"],
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
            "overnight_min_pct": self.OVERNIGHT_MIN_PCT,
            "intraday_min_pct": self.INTRADAY_MIN_PCT,
            "min_price": self.MIN_PRICE,
            "min_market_cap": self.MIN_MARKET_CAP,
            "min_trading_value": self.MIN_TRADING_VALUE,
            "weights": self.WEIGHTS,
        }
