"""
Strategy: End-of-Day Reversal (Korean Adaptation)
===================================================

학술 검증 출처:
  Baltussen, G., Da, Z., & Soebhag, A. "End-of-Day Reversal".
  University of Notre Dame working paper.
  https://www3.nd.edu/~zda/EOD.pdf

핵심 발견 (논문 인용):
  미국 시장에서 인트라데이 패자(loser)가 마지막 30분에 reversal.
  Long bottom decile / Short top decile = 일평균 0.24% 수익.
  메커니즘: 전문 공매도자의 overnight margin 부담으로
  마지막 30분에 short cover → 패자 가격 상승.

한국 적용 가설:
  한국 시장은 공매도 제약이 더 강함.
  → EODR 효과가 다를 수 있으나, "당일 큰 폭 하락 종목"의 마지막 30분 (또는 다음날 시초가)
    reversal 가능성은 검증해볼 가치 있음.
  → BNF 낙폭과대 전략과 다른 시간 차원 (BNF는 3거래일, 본 전략은 1일).

주의:
  학술적으로 미국 시장에서 검증. 한국 적용은 backtest로 재검증 필요.
  long-only로 단순화 (한국 공매도 제약 회피).

본 전략 vs Beta Contrarian / BNF:
  Beta: RSI≤35 대형주 (다일 평균)
  BNF: 3거래일 -10% 이상 (다일 누적)
  본 전략: 단일일 큰 폭 하락 (장중 reversal 또는 overnight reversal)
  → 시간 차원이 본질적으로 다름

데이터 의존도:
  KRX OpenAPI (당일 OHLCV)

작성: 2026-04-11 / Phase 2.5
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
    id="eod_reversal_korean",
    name="당일 EOD 리버설 (Baltussen 한국 적용)",
    version="0.1.0",
    category=StrategyCategory.CONTRARIAN.value,
    risk_level=RiskLevel.HIGH.value,

    hypothesis="당일 큰 폭 하락 종목은 장 마감 직전 또는 다음날 시초가에 reversal 가능성",
    rationale=(
        "Baltussen, Da, Soebhag의 End-of-Day Reversal 논문 (Notre Dame)에서 "
        "미국 시장 인트라데이 패자가 마지막 30분에 평균 0.24% reversal 발생을 검증. "
        "공매도자의 overnight margin 부담으로 마지막 30분에 short cover. "
        "한국은 공매도 제약 강함 → 메커니즘 다를 수 있으나 검증 가치 있음."
    ),
    expected_edge="단기 oversold 종목의 mean reversion + 공매도 cover 추정",

    data_requirements=["KRX_OHLCV"],
    min_history_days=2,
    requires_intraday=True,  # 정확하게는 마지막 30분 분봉 필요

    target_basket_size=5,
    target_holding_days=1,
    target_market="KOSPI+KOSDAQ",

    differs_from_existing=(
        "Beta Contrarian과 다름: Beta는 RSI 다일 평균(대형주). "
        "BNF와 다름: BNF는 3거래일 -10% 누적 분할매수. "
        "본 전략은 단일일 큰 폭 하락 → 단기 reversion. "
        "시간 차원(1일 vs 3일)과 출처(학술 EODR vs 경험적 BNF)가 본질적으로 다름."
    ),
    novelty_score=8,
    notes=(
        "한국 시장 검증 필수. 미국과 메커니즘 다를 수 있음. "
        "분봉 가용 시 정확히 마지막 30분 진입, 그 외엔 종가 진입 + 다음날 시초가 청산 근사."
    ),
)

METADATA.add_source(StrategySource(
    type=SourceType.PAPER.value,
    title="End-of-Day Reversal",
    author="Baltussen, G., Da, Z., Soebhag, A.",
    url="https://www3.nd.edu/~zda/EOD.pdf",
    trust_level=TrustLevel.VERIFIED.value,
    notes="Notre Dame working paper. 미국 시장 검증, 한국 적용은 backtest 필요.",
))


class EODReversalKoreanStrategy(BaseStrategy):
    """당일 큰 폭 하락 종목의 단기 reversal 전략."""

    STRATEGY_ID = METADATA.id
    STRATEGY_NAME = METADATA.name
    DESCRIPTION = METADATA.hypothesis

    # 파라미터
    LOSS_THRESHOLD: float = -3.0          # -3% 이하 하락 종목
    MAX_LOSS: float = -8.0                 # -8% 이하는 너무 위험 (감자/공시 리스크)
    MIN_PRICE: int = 3000
    MIN_MARKET_CAP: int = 100_000_000_000   # 1000억 (안정성 ↑)
    MIN_TRADING_VALUE: int = 5_000_000_000  # 50억
    INTRADAY_RECOVERY_MIN: float = 0.3     # 저가 대비 종가 회복 (recovery 시작 신호)

    WEIGHTS = {
        "loss_magnitude": 30,            # 손실 크기 (적당한 loser)
        "intraday_recovery": 35,         # 저점 대비 회복 (reversal 신호)
        "trading_value": 20,             # 유동성
        "market_cap": 15,                # 안정성
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

        # 1. 큰 폭 하락 종목 (적당한 범위 — 너무 큰 하락은 위험)
        losers = [
            s for s in all_stocks
            if self.MAX_LOSS <= s["change_pct"] <= self.LOSS_THRESHOLD
        ]
        print(f"  큰 폭 하락: {len(losers)}개")

        # 2. 기본 필터
        filtered = basic_filter(
            losers,
            min_price=self.MIN_PRICE,
            min_market_cap=self.MIN_MARKET_CAP,
            min_trading_value=self.MIN_TRADING_VALUE,
        )
        print(f"  기본 필터: {len(filtered)}개")

        # 3. 저점 대비 회복 신호 (recovery — reversal 시작)
        # (close - low) / (high - low) >= 0.3 = 종가가 저점에서 30% 이상 회복
        recovered = []
        for s in filtered:
            high, low, close = s["high"], s["low"], s["close"]
            if high <= low:
                continue
            recovery_ratio = (close - low) / (high - low)
            if recovery_ratio >= self.INTRADAY_RECOVERY_MIN:
                s["recovery_ratio"] = round(recovery_ratio, 3)
                recovered.append(s)

        print(f"  저점 회복 신호: {len(recovered)}개")

        if not recovered:
            return []

        scored = self._calculate_scores(recovered)
        scored.sort(key=lambda c: c.score, reverse=True)
        self.candidates = scored[:top_n]
        for i, c in enumerate(self.candidates, 1):
            c.rank = i

        print(f"  선정 완료: {len(self.candidates)}개 (장 마감 또는 종가 진입)")
        return self.candidates

    def _calculate_scores(self, stocks: List[Dict]) -> List[Candidate]:
        if not stocks:
            return []

        # 손실 크기는 적당한 범위 (너무 크지도 작지도 않은) 선호
        target_loss = (self.LOSS_THRESHOLD + self.MAX_LOSS) / 2
        max_recovery = max((s.get("recovery_ratio", 0) for s in stocks), default=1) or 1
        max_tv = max((s["trading_value"] for s in stocks), default=1) or 1
        max_cap = max((s["market_cap"] for s in stocks), default=1) or 1

        candidates: List[Candidate] = []
        for s in stocks:
            # 손실 크기: 타겟에 가까울수록 만점
            distance_from_target = abs(s["change_pct"] - target_loss)
            loss_score = max(1 - distance_from_target / 5, 0)

            score_detail = {
                "loss_magnitude": loss_score * self.WEIGHTS["loss_magnitude"],
                "intraday_recovery": (s.get("recovery_ratio", 0) / max_recovery) * self.WEIGHTS["intraday_recovery"],
                "trading_value": (s["trading_value"] / max_tv) * self.WEIGHTS["trading_value"],
                "market_cap": (s["market_cap"] / max_cap) * self.WEIGHTS["market_cap"],
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
            "loss_threshold": self.LOSS_THRESHOLD,
            "max_loss": self.MAX_LOSS,
            "min_price": self.MIN_PRICE,
            "min_market_cap": self.MIN_MARKET_CAP,
            "min_trading_value": self.MIN_TRADING_VALUE,
            "intraday_recovery_min": self.INTRADAY_RECOVERY_MIN,
            "weights": self.WEIGHTS,
        }
