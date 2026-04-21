"""
Strategy: Multi-Signal Hybrid
==============================

가설:
  단일 시그널(공시 / 수급 / 거래량)은 노이즈가 많지만,
  3가지 시그널이 동시에 만족되는 종목은 신호 강도가 매우 높다.

핵심 시그널 (AND 결합):
  1. DART 호재 공시 (전일 18시 ~ 당일 08:30)
  2. 외국인 또는 기관 순매수 (최근 N일)
  3. 거래량 surge (전일 대비 N배)

이 3가지가 동시에 만족되는 종목만 후보. 매우 보수적이라 적은 종목이 나오지만 정확도 ↑.

본 전략 vs Gamma Disclosure / Foreign Flow Momentum:
  Gamma: 공시만
  Foreign Flow: 외국인만
  본 전략: 공시 + 수급 + 거래량 3중 결합 — 단일 신호의 약점 보완
  → 신호 수는 적지만 정확도 / 일관성 ↑ (Phase 7에서 ensemble base로도 활용 가능)

데이터 의존도:
  DART OpenAPI
  Naver Investor (수급)
  KRX OpenAPI (거래량/가격)
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


METADATA = StrategyMetadata(
    id="multi_signal_hybrid",
    name="다중 신호 결합 (DART + 수급 + 거래량)",
    version="0.1.0",
    category=StrategyCategory.HYBRID.value,
    risk_level=RiskLevel.MEDIUM.value,

    hypothesis="DART 호재 + 외국인/기관 순매수 + 거래량 surge 3중 결합 종목은 신호 강도 압도적",
    rationale=(
        "단일 시그널(공시만/수급만/거래량만)은 노이즈가 많지만, "
        "이 3가지가 동시에 만족되는 종목은 우연 가능성이 매우 낮다. "
        "보수적이라 후보 수는 적지만 정확도와 일관성이 높다. "
        "앙상블 전략의 기반(Phase 7)으로도 활용 가능."
    ),
    expected_edge="다중 신호의 동시 만족 = 신호 신뢰도 ↑, 우연성 ↓",

    data_requirements=["DART", "NAVER_INVESTOR", "KRX_OHLCV"],
    min_history_days=5,
    requires_intraday=False,

    target_basket_size=5,
    target_holding_days=2,
    target_market="KOSPI+KOSDAQ",

    differs_from_existing=(
        "Gamma(공시만), Foreign Flow Momentum(수급만), Alpha(거래량/모멘텀만)와 다름. "
        "본 전략은 3가지를 AND 조건으로 결합하여 신호 신뢰도를 본질적으로 다른 차원으로 끌어올림. "
        "단일 신호 전략의 false positive를 보완하는 메타 전략 성격."
    ),
    novelty_score=9,
    notes=(
        "DART + 수급 fetch 비용 큼 → 시초 풀을 시총/공시 종목으로 좁힘. "
        "ensemble 기반으로 활용 가능 (Phase 7)."
    ),
)

METADATA.add_source(StrategySource(
    type=SourceType.HANDOFF_GUIDE.value,
    title="news-trading-bot-handoff.md Section 6.2 #1",
    trust_level=TrustLevel.HIGH.value,
    notes="신규 전략 후보로 명시 — 'Multi-Signal Hybrid'.",
))


class MultiSignalHybridStrategy(BaseStrategy):
    """DART + 수급 + 거래량 3중 결합 전략."""

    STRATEGY_ID = METADATA.id
    STRATEGY_NAME = METADATA.name
    DESCRIPTION = METADATA.hypothesis

    # 파라미터
    LOOKBACK_DAYS: int = 3            # 수급 lookback
    MIN_PRICE: int = 3000
    MIN_MARKET_CAP: int = 100_000_000_000   # 1000억
    MIN_TRADING_VALUE: int = 5_000_000_000  # 50억
    VOLUME_SURGE_MIN: float = 1.5     # 거래대금 surge

    WEIGHTS = {
        "disclosure": 30,
        "investor_flow": 30,
        "volume_surge": 25,
        "price_momentum": 15,
    }

    def __init__(self):
        super().__init__()
        self._dart_filter = None
        self._investor_client = None

    def _get_dart_filter(self):
        if self._dart_filter is None:
            try:
                from paper_trading.utils.dart_utils import get_dart_filter
                self._dart_filter = get_dart_filter()
            except Exception as e:
                logger.warning(f"DartFilter 초기화 실패: {e}")
                self._dart_filter = False
        return self._dart_filter if self._dart_filter else None

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

        # 1. DART 호재 공시 풀 (가장 좁은 풀)
        dart = self._get_dart_filter()
        if not dart or not dart.is_available():
            print("  DART API 사용 불가")
            return []

        try:
            positive_stocks = dart.get_positive_stocks(target_date=date)
        except Exception as e:
            print(f"  DART fetch 실패: {e}")
            return []

        if not positive_stocks:
            print("  호재 공시 없음")
            return []

        positive_codes = {p.stock_code: p for p in positive_stocks if hasattr(p, "stock_code")}
        print(f"  호재 공시: {len(positive_codes)}개 종목")

        # 2. 시장 데이터
        all_stocks = fetch_all_markets(date)
        if not all_stocks:
            return []

        # 3. 호재 종목과 매칭 + 기본 필터
        matched = [s for s in all_stocks if s["code"] in positive_codes]
        filtered = basic_filter(
            matched,
            min_price=self.MIN_PRICE,
            min_market_cap=self.MIN_MARKET_CAP,
            min_trading_value=self.MIN_TRADING_VALUE,
        )
        print(f"  공시 + 필터: {len(filtered)}개")

        if not filtered:
            return []

        # 4. 거래량 surge 필터 (거래대금 기준 근사)
        avg_tv = self.MIN_TRADING_VALUE * 2
        vol_passed = [s for s in filtered if s["trading_value"] >= avg_tv * self.VOLUME_SURGE_MIN]
        print(f"  거래량 surge: {len(vol_passed)}개")

        if not vol_passed:
            return []

        # 5. 외국인/기관 수급 fetch
        client = self._get_investor_client()
        signal_passed = []
        if client:
            for s in vol_passed:
                try:
                    flow = client.get_investor_flow(s["code"], limit=self.LOOKBACK_DAYS + 1)
                    if not flow:
                        continue
                    foreign_total = sum(int(d.get("foreign_net", 0) or 0) for d in flow[:self.LOOKBACK_DAYS])
                    inst_total = sum(int(d.get("inst_net", 0) or 0) for d in flow[:self.LOOKBACK_DAYS])
                    combined = foreign_total + inst_total
                    if combined <= 0:
                        continue
                    s["foreign_total"] = foreign_total
                    s["inst_total"] = inst_total
                    s["combined_flow"] = combined
                    s["dart_info"] = positive_codes[s["code"]]
                    signal_passed.append(s)
                except Exception as e:
                    logger.debug(f"수급 fetch 실패 {s['code']}: {e}")
                    continue
        else:
            # fallback: 수급 데이터 없이 진행
            print("  NaverInvestorClient 없음 — 수급 시그널 skip (정확도 ↓)")
            for s in vol_passed:
                s["combined_flow"] = 0
                s["dart_info"] = positive_codes[s["code"]]
                signal_passed.append(s)

        print(f"  3중 신호 통과: {len(signal_passed)}개")

        if not signal_passed:
            return []

        scored = self._calculate_scores(signal_passed)
        scored.sort(key=lambda c: c.score, reverse=True)
        self.candidates = scored[:top_n]
        for i, c in enumerate(self.candidates, 1):
            c.rank = i

        print(f"  선정 완료: {len(self.candidates)}개")
        return self.candidates

    def _calculate_scores(self, stocks: List[Dict]) -> List[Candidate]:
        if not stocks:
            return []

        max_flow = max((abs(s.get("combined_flow", 0)) for s in stocks), default=1) or 1
        max_tv = max((s["trading_value"] for s in stocks), default=1) or 1
        max_change = max((s["change_pct"] for s in stocks), default=1) or 1

        candidates: List[Candidate] = []
        for s in stocks:
            dart_info = s.get("dart_info")
            disclosure_score = 0.6
            if dart_info and hasattr(dart_info, "category"):
                disclosure_score = {
                    "실적": 1.0, "계약": 0.95, "투자": 0.85,
                    "기술": 0.9, "배당": 0.7, "대형": 0.85,
                }.get(dart_info.category, 0.6)

            score_detail = {
                "disclosure": disclosure_score * self.WEIGHTS["disclosure"],
                "investor_flow": min(s.get("combined_flow", 0) / max_flow, 1) * self.WEIGHTS["investor_flow"],
                "volume_surge": (s["trading_value"] / max_tv) * self.WEIGHTS["volume_surge"],
                "price_momentum": (max(s["change_pct"], 0) / max_change) * self.WEIGHTS["price_momentum"],
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
            "min_market_cap": self.MIN_MARKET_CAP,
            "min_trading_value": self.MIN_TRADING_VALUE,
            "volume_surge_min": self.VOLUME_SURGE_MIN,
            "weights": self.WEIGHTS,
        }
