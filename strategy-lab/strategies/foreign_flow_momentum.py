"""
Strategy: Foreign Flow Momentum
=================================

가설:
  외국인 순매수가 N일 연속 증가 + 가격도 상승 추세 = "Smart money following"
  외국인은 펀더멘털 분석 후 매수하므로 그 흐름을 따라가면 정보 비대칭을 줄일 수 있다.

핵심 시그널:
  최근 5일 외국인 순매수 합계 > 0
  + 최근 3일 연속 외국인 순매수
  + 가격 5일 평균 상승 추세
  → 외국인 매수 강도 + 가격 모멘텀 결합 점수

본 전략 vs Beta Contrarian / Alpha Momentum:
  Alpha: 단순 가격 모멘텀 (MA5 + 거래량)
  Beta: RSI 역추세 (대형주)
  본 전략: 외국인 수급 + 가격 모멘텀 결합 — 데이터 소스(naver_investor)가 다름
  → "왜 오르는가"의 근거가 더 명확함 (외국인 매수)

데이터 의존도:
  KRX OpenAPI (가격)
  Naver investor (외국인 수급, 종목당 ~0.2초)
  분봉 불필요

작성: 2026-04-11 / Phase 2.1
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


# ============================================================
# Metadata
# ============================================================

METADATA = StrategyMetadata(
    id="foreign_flow_momentum",
    name="외국인 수급 모멘텀",
    version="0.1.0",
    category=StrategyCategory.FLOW.value,
    risk_level=RiskLevel.MEDIUM.value,

    hypothesis="외국인이 N일 연속 순매수 + 가격 상승 = 추세 지속 신뢰도 ↑",
    rationale=(
        "외국인 투자자는 일반적으로 펀더멘털 분석 후 진입한다. "
        "그들의 연속 순매수는 단순 차트 신호보다 정보 비대칭이 적은 시그널. "
        "가격 모멘텀과 결합하면 단타 진입 시점 정확도를 높일 수 있다."
    ),
    expected_edge="기관/외국인 자금 흐름의 1~2일 시차 추종",

    data_requirements=["KRX_OHLCV", "NAVER_INVESTOR"],
    min_history_days=5,
    requires_intraday=False,

    target_basket_size=5,
    target_holding_days=2,
    target_market="KOSPI+KOSDAQ",

    differs_from_existing=(
        "Alpha/Beta와 다름: 두 전략은 가격/거래량만 본다. "
        "본 전략은 외국인 순매수 (naver_investor)를 1순위 시그널로 사용. "
        "데이터 소스 자체가 새로 추가되며, '왜 오르는가'의 근거가 더 명확함."
    ),
    novelty_score=8,
    notes=(
        "Naver investor는 종목당 ~0.2초 → 초기 풀을 시총/거래대금으로 좁혀서 "
        "Top 50~100 종목만 수급 fetch."
    ),
)

METADATA.add_source(StrategySource(
    type=SourceType.HANDOFF_GUIDE.value,
    title="news-trading-bot-handoff.md Section 6.2 #4",
    trust_level=TrustLevel.HIGH.value,
    notes="신규 전략 후보로 명시 — 'Smart money following'.",
))
METADATA.add_source(StrategySource(
    type=SourceType.OFFICIAL_DOC.value,
    title="Naver Finance 종목별 외국인/기관 매매동향",
    url="https://finance.naver.com/item/frgn.naver",
    trust_level=TrustLevel.VERIFIED.value,
    notes="공개 페이지, news-trading-bot의 NaverInvestorClient로 이미 검증됨.",
))


# ============================================================
# Strategy class
# ============================================================

class ForeignFlowMomentumStrategy(BaseStrategy):
    """외국인 순매수 모멘텀 전략."""

    STRATEGY_ID = METADATA.id
    STRATEGY_NAME = METADATA.name
    DESCRIPTION = METADATA.hypothesis

    # 파라미터
    POOL_SIZE: int = 100             # 1차 풀 (시총 상위 종목 수)
    LOOKBACK_DAYS: int = 5           # 외국인 순매수 lookback
    CONSECUTIVE_DAYS: int = 3        # 연속 순매수 요건
    MIN_PRICE: int = 3000
    MIN_MARKET_CAP: int = 200_000_000_000   # 2000억
    MIN_TRADING_VALUE: int = 10_000_000_000  # 100억
    MIN_CHANGE_PCT: float = 0.0      # 음봉 제외

    WEIGHTS = {
        "foreign_consistency": 35,   # 연속 순매수 일수
        "foreign_magnitude": 30,     # 순매수 규모
        "price_momentum": 20,        # 가격 모멘텀
        "trading_value": 15,         # 유동성
    }

    def __init__(self):
        super().__init__()
        self._investor_client = None

    def _get_investor_client(self):
        if self._investor_client is None:
            try:
                from paper_trading.utils.naver_investor import NaverInvestorClient
                self._investor_client = NaverInvestorClient()
            except Exception as e:
                logger.warning(f"NaverInvestorClient 초기화 실패: {e}")
                self._investor_client = False
        return self._investor_client if self._investor_client else None

    def select_stocks(self, date: Optional[str] = None, top_n: int = 5) -> List[Candidate]:
        if date is None:
            date = datetime.now().strftime("%Y%m%d")
        self.selection_date = date
        print(f"\n[{self.STRATEGY_NAME}] 종목 선정 시작 ({date})")

        krx = get_krx()
        if not krx:
            print("  KRX 사용 불가")
            return []

        # 1. 시장 데이터 fetch
        all_stocks = fetch_all_markets(date)
        if not all_stocks:
            return []

        # 2. 기본 필터
        filtered = basic_filter(
            all_stocks,
            min_price=self.MIN_PRICE,
            min_market_cap=self.MIN_MARKET_CAP,
            min_trading_value=self.MIN_TRADING_VALUE,
        )
        filtered = [s for s in filtered if s["change_pct"] >= self.MIN_CHANGE_PCT]
        print(f"  기본 필터 통과: {len(filtered)}개")

        # 3. 시총 상위 풀로 좁힘 (수급 fetch 비용 ↓)
        filtered.sort(key=lambda s: s["market_cap"], reverse=True)
        pool = filtered[: self.POOL_SIZE]
        print(f"  수급 fetch 풀: {len(pool)}개")

        # 4. 외국인 수급 fetch (각 종목)
        client = self._get_investor_client()
        if not client:
            print("  NaverInvestorClient 없음 — 가격 모멘텀만 사용")
            scored = self._fallback_score(pool)
        else:
            scored_stocks = []
            for i, s in enumerate(pool, 1):
                if i % 20 == 0:
                    print(f"    수급 fetch 진행: {i}/{len(pool)}")
                try:
                    flow = client.get_investor_flow(s["code"], limit=self.LOOKBACK_DAYS + 2)
                    if not flow:
                        continue
                    foreign_nets = [int(d.get("foreign_net", 0) or 0) for d in flow[:self.LOOKBACK_DAYS]]
                    if not foreign_nets:
                        continue

                    # 연속 순매수 검사 (최근 N일)
                    consecutive = sum(1 for v in foreign_nets[:self.CONSECUTIVE_DAYS] if v > 0)
                    if consecutive < self.CONSECUTIVE_DAYS:
                        continue

                    # 5일 합계
                    total_net = sum(foreign_nets)
                    if total_net <= 0:
                        continue

                    s["foreign_consecutive"] = consecutive
                    s["foreign_total"] = total_net
                    scored_stocks.append(s)
                except Exception as e:
                    logger.debug(f"수급 fetch 실패 {s['code']}: {e}")
                    continue

            print(f"  수급 통과: {len(scored_stocks)}개")
            if not scored_stocks:
                return []

            scored = self._calculate_scores(scored_stocks)

        scored.sort(key=lambda c: c.score, reverse=True)
        self.candidates = scored[:top_n]
        for i, c in enumerate(self.candidates, 1):
            c.rank = i

        print(f"  선정 완료: {len(self.candidates)}개")
        return self.candidates

    def _calculate_scores(self, stocks: List[Dict]) -> List[Candidate]:
        if not stocks:
            return []

        max_total = max((s.get("foreign_total", 0) for s in stocks), default=1) or 1
        max_change = max((s["change_pct"] for s in stocks), default=1) or 1
        max_tv = max((s["trading_value"] for s in stocks), default=1) or 1

        candidates: List[Candidate] = []
        for s in stocks:
            score_detail = {
                "foreign_consistency": (s.get("foreign_consecutive", 0) / self.CONSECUTIVE_DAYS) * self.WEIGHTS["foreign_consistency"],
                "foreign_magnitude": (s.get("foreign_total", 0) / max_total) * self.WEIGHTS["foreign_magnitude"],
                "price_momentum": (max(s["change_pct"], 0) / max_change) * self.WEIGHTS["price_momentum"],
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

    def _fallback_score(self, stocks: List[Dict]) -> List[Candidate]:
        """수급 데이터 없을 때 가격 모멘텀만 사용."""
        if not stocks:
            return []
        max_change = max((s["change_pct"] for s in stocks), default=1) or 1
        max_tv = max((s["trading_value"] for s in stocks), default=1) or 1
        return [
            Candidate(
                code=s["code"],
                name=s["name"],
                price=s["close"],
                change_pct=s["change_pct"],
                score=round((s["change_pct"] / max_change) * 50 + (s["trading_value"] / max_tv) * 50, 2),
                score_detail={"fallback": True},
                market_cap=s["market_cap"],
                volume=s["volume"],
                trading_value=s["trading_value"],
            )
            for s in stocks
        ]

    def get_params(self) -> Dict:
        return {
            "pool_size": self.POOL_SIZE,
            "lookback_days": self.LOOKBACK_DAYS,
            "consecutive_days": self.CONSECUTIVE_DAYS,
            "min_market_cap": self.MIN_MARKET_CAP,
            "min_trading_value": self.MIN_TRADING_VALUE,
            "weights": self.WEIGHTS,
        }
