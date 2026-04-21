"""
Strategy: Overnight ETF Reversal (Korean Market)
==================================================

학술 검증 출처:
  "Intraday Return Reversals: Empirical Evidence from the Korean ETF Market"
  Preprints, 2019. https://www.preprints.org/manuscript/201905.0306/v1

핵심 발견 (논문 인용):
  한국 KOSPI 200 ETF의 overnight 수익률은 유의하게 양수,
  intraday 수익률은 유의하게 음수.
  → 종가 매수 → 다음날 시초가 매도 (overnight long) 알파 존재.
  공매도 제약 + disagreement hypothesis로 설명.

본 전략은 단타가 아니라 "1일 보유 (종가→다음날 시초가)" 으로
엄밀히는 단타 framework의 경계에 있음. 그러나 보유 시간이 짧고
(약 16시간), 한국 시장 고유 비효율을 활용한다는 점에서 가치 있음.

가설:
  KOSPI 200 ETF 종가 매수 → 다음날 시초가 매도
  Overnight 수익률 양수 effect를 정량적으로 활용

본 전략 vs 모든 기존:
  - 기존 6개 + 신규 5개는 모두 일중 진입/청산 (또는 다음날 시초가 진입)
  - 본 전략은 종가 진입 → 다음날 시초가 청산 (역방향)
  - 학술 검증된 한국 시장 고유 비효율 (공매도 제약)

데이터 의존도:
  KRX OpenAPI (ETF OHLCV)
  KRX 종목 기본정보 (ETF 식별)

작성: 2026-04-11 / Phase 2.4
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Dict, Optional

from lab import BaseStrategy, Candidate
from lab.common import get_krx, fetch_all_markets
from lab.metadata import (
    StrategyMetadata, StrategySource,
    StrategyCategory, RiskLevel, SourceType, TrustLevel,
)

logger = logging.getLogger(__name__)


METADATA = StrategyMetadata(
    id="overnight_etf_reversal",
    name="ETF Overnight 리버설 (학술 검증)",
    version="0.1.0",
    category=StrategyCategory.STATISTICAL.value,
    risk_level=RiskLevel.LOW.value,

    hypothesis="한국 KOSPI 200 ETF는 종가 매수 → 다음날 시초가 매도가 양의 알파를 낳는다",
    rationale=(
        "한국 ETF 시장의 overnight 수익률이 유의하게 양수, intraday는 음수라는 "
        "학술 발견(Preprints 2019)을 활용. 한국 시장 공매도 제약과 disagreement "
        "hypothesis로 설명되는 robust한 비효율. 단타 framework 경계에 있지만 "
        "보유 시간 ~16시간, 위험 관리 용이, 학술 검증."
    ),
    expected_edge="공매도 제약 + 정보 비대칭에서 발생하는 한국 ETF overnight 프리미엄",

    data_requirements=["KRX_OHLCV", "KRX_BASE_INFO"],
    min_history_days=20,  # ETF만 골라내기 위해 충분한 데이터
    requires_intraday=False,

    target_basket_size=3,            # ETF는 종목 다양성 적음
    target_holding_days=1,           # 종가 → 다음날 시초가
    target_market="KOSPI",           # ETF는 KOSPI

    differs_from_existing=(
        "기존 6 + 신규 5개와 본질적으로 다름: "
        "1) 진입/청산 시점이 역방향 (종가 진입 → 다음날 시초가 청산) "
        "2) 단타가 아닌 overnight (~16h) "
        "3) 개별 종목이 아닌 ETF 대상 "
        "4) 학술적으로 한국 시장 고유 비효율로 검증됨"
    ),
    novelty_score=9,
    notes=(
        "ETF 식별이 핵심. KRX 종목 기본정보 API로 ISU_KIND가 'EF'인 종목만 추출. "
        "현재 단순화 버전: 종목명에 '코덱스/타이거/킨덱스/아리랑' 포함 + KOSPI 200 시총 큰 ETF만."
    ),
)

METADATA.add_source(StrategySource(
    type=SourceType.PAPER.value,
    title="Intraday Return Reversals: Empirical Evidence from the Korean ETF Market",
    url="https://www.preprints.org/manuscript/201905.0306/v1",
    published_date="2019",
    trust_level=TrustLevel.HIGH.value,
    notes="Preprint. 한국 KOSPI 200 ETF 대상 overnight positive / intraday negative 검증.",
))


class OvernightETFReversalStrategy(BaseStrategy):
    """한국 ETF의 overnight 양수 효과를 활용한 1일 보유 전략."""

    STRATEGY_ID = METADATA.id
    STRATEGY_NAME = METADATA.name
    DESCRIPTION = METADATA.hypothesis

    # ETF 브랜드 키워드 (이름 기반 식별)
    ETF_BRAND_KEYWORDS = [
        "KODEX", "코덱스", "TIGER", "타이거", "KINDEX", "킨덱스",
        "ARIRANG", "아리랑", "HANARO", "하나로", "KBSTAR", "KB스타", "ACE",
    ]

    # 파라미터
    MIN_PRICE: int = 5000
    MIN_MARKET_CAP: int = 100_000_000_000   # 1000억
    MIN_TRADING_VALUE: int = 5_000_000_000  # 50억
    MIN_INTRADAY_DROP: float = -0.3         # 당일 하락 폭이 일정 수준 (overnight 상승 가능성 ↑)

    WEIGHTS = {
        "intraday_weakness": 35,        # 당일 약세 = overnight reversal 후보
        "trading_value": 25,            # 유동성
        "market_cap": 20,               # 안정성
        "kospi_correlation": 20,        # KOSPI 200 추종
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

        # 1. KOSPI ETF 후보만 (이름 기반)
        etf_candidates = [
            s for s in all_stocks
            if s["market"] == "KOSPI"
            and any(kw in s["name"].upper() or kw in s["name"] for kw in self.ETF_BRAND_KEYWORDS)
        ]
        print(f"  ETF 후보: {len(etf_candidates)}개")

        if not etf_candidates:
            return []

        # 2. 필터 (가격/유동성/시총)
        filtered = [
            s for s in etf_candidates
            if s["close"] >= self.MIN_PRICE
            and s["market_cap"] >= self.MIN_MARKET_CAP
            and s["trading_value"] >= self.MIN_TRADING_VALUE
        ]

        # 3. 당일 약세 ETF (overnight reversal 후보 — 논문의 core)
        weak = [s for s in filtered if s["change_pct"] <= self.MIN_INTRADAY_DROP]
        print(f"  약세 ETF: {len(weak)}개")

        if not weak:
            return []

        scored = self._calculate_scores(weak)
        scored.sort(key=lambda c: c.score, reverse=True)
        self.candidates = scored[:top_n]
        for i, c in enumerate(self.candidates, 1):
            c.rank = i

        print(f"  선정 완료: {len(self.candidates)}개 (종가 매수 → 다음날 시초가 매도)")
        return self.candidates

    def _calculate_scores(self, stocks: List[Dict]) -> List[Candidate]:
        if not stocks:
            return []

        max_drop = min((s["change_pct"] for s in stocks), default=-1) or -1
        max_tv = max((s["trading_value"] for s in stocks), default=1) or 1
        max_cap = max((s["market_cap"] for s in stocks), default=1) or 1

        candidates: List[Candidate] = []
        for s in stocks:
            # KOSPI 200 추종 우선 (이름에 200 포함)
            kospi_corr = 1.0 if "200" in s["name"] else 0.5

            score_detail = {
                "intraday_weakness": (s["change_pct"] / max_drop) * self.WEIGHTS["intraday_weakness"] if max_drop else 0,
                "trading_value": (s["trading_value"] / max_tv) * self.WEIGHTS["trading_value"],
                "market_cap": (s["market_cap"] / max_cap) * self.WEIGHTS["market_cap"],
                "kospi_correlation": kospi_corr * self.WEIGHTS["kospi_correlation"],
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
            "etf_brand_keywords": self.ETF_BRAND_KEYWORDS,
            "min_price": self.MIN_PRICE,
            "min_market_cap": self.MIN_MARKET_CAP,
            "min_trading_value": self.MIN_TRADING_VALUE,
            "min_intraday_drop": self.MIN_INTRADAY_DROP,
            "weights": self.WEIGHTS,
        }
