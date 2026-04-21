"""
Strategy: News Catalyst Timing
================================

가설:
  DART 호재 공시가 게시된 후 1시간 이내 가격이 빠르게 반응하는 종목은
  당일 추세가 이어진다 (정보 우위 종료 전 진입).

핵심 시그널:
  당일 또는 전일 늦은 시각 DART 호재 공시
  + 시초가 갭 (또는 장 초반 급등)
  + 거래량 평소 대비 surge
  → "공시 → 가격 반응 → 추격" 단타 셋업

본 전략 vs Gamma Disclosure:
  Gamma: DART 호재 공시 종목 단순 매수 (전일 18시 ~ 당일 08:30)
         시초가 매매 — 시점이 고정
  본 전략: 공시 게시 시간 자체를 시그널로 사용
           "공시 후 빠른 반응" = 시장의 추격 매수가 들어왔다는 증거
           시간 가중치 + 가격 반응 강도 결합
  → '공시 발생' vs '공시 게시 → 즉각 반응'의 차이

데이터 의존도:
  DART OpenAPI (공시 + rcept_dt 시간)
  KRX OpenAPI (가격)
  분봉 6일 한계 — 본격 활용은 분봉 가능 범위 내에서

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
    id="news_catalyst_timing",
    name="뉴스 카탈리스트 타이밍",
    version="0.1.0",
    category=StrategyCategory.EVENT.value,
    risk_level=RiskLevel.HIGH.value,

    hypothesis="DART 호재 공시 게시 후 1시간 내 빠르게 반응한 종목은 당일 추세 지속",
    rationale=(
        "공시 자체는 정보일 뿐, 시장 참가자들이 그것을 어떻게 해석/반응하는지가 단타에 중요. "
        "공시 후 빠른 가격 반응 = 정보 우위가 빠르게 사라지고 추격 매수가 들어왔다는 증거. "
        "Gamma Disclosure가 공시 발생 자체를 본다면, 본 전략은 '공시 → 즉각 반응'을 본다."
    ),
    expected_edge="공시 후 1차 가격 반응의 추세 지속성",

    data_requirements=["DART", "KRX_OHLCV"],
    min_history_days=2,
    requires_intraday=True,  # 이상적으로는 분봉 필요 (백테스트 한계)

    target_basket_size=5,
    target_holding_days=1,
    target_market="KOSPI+KOSDAQ",

    differs_from_existing=(
        "Gamma Disclosure와 다름: Gamma는 '공시 발생 종목 = 매수 후보' (시점 무관). "
        "본 전략은 '공시 게시 시간'과 '게시 후 가격 반응 속도'를 시그널의 중심으로 사용. "
        "같은 데이터 소스를 다른 차원으로 활용 — 시간 차원 추가."
    ),
    novelty_score=7,
    notes=(
        "분봉 6일 한계로 backtest는 일봉 갭으로 근사. "
        "실전에서는 09:00~10:00 분봉 활용 가능."
    ),
)

METADATA.add_source(StrategySource(
    type=SourceType.HANDOFF_GUIDE.value,
    title="news-trading-bot-handoff.md Section 6.2 #5",
    trust_level=TrustLevel.HIGH.value,
    notes="신규 전략 후보로 명시 — 'News Catalyst Timing'.",
))
METADATA.add_source(StrategySource(
    type=SourceType.OFFICIAL_DOC.value,
    title="DART OpenAPI 공시 검색",
    url="https://opendart.fss.or.kr/intro/main.do",
    trust_level=TrustLevel.VERIFIED.value,
    notes="공식 API. dart_utils.DartFilter로 이미 검증됨.",
))


class NewsCatalystTimingStrategy(BaseStrategy):
    """DART 호재 공시 + 빠른 가격 반응 결합."""

    STRATEGY_ID = METADATA.id
    STRATEGY_NAME = METADATA.name
    DESCRIPTION = METADATA.hypothesis

    # 파라미터
    GAP_MIN_PCT: float = 1.5         # 시초가 갭 최소 (호재 반응 확인)
    MIN_PRICE: int = 2000
    MIN_MARKET_CAP: int = 50_000_000_000     # 500억
    MIN_TRADING_VALUE: int = 5_000_000_000   # 50억
    VOLUME_SURGE_MIN: float = 1.5

    WEIGHTS = {
        "disclosure_quality": 35,    # DART 점수 (호재 강도)
        "gap_reaction": 30,          # 시초가 갭 (즉각 반응)
        "volume_surge": 20,          # 거래량 (관심도)
        "trading_value": 15,         # 유동성
    }

    def __init__(self):
        super().__init__()
        self._dart_filter = None

    def _get_dart_filter(self):
        if self._dart_filter is None:
            try:
                from paper_trading.utils.dart_utils import get_dart_filter
                self._dart_filter = get_dart_filter()
            except Exception as e:
                logger.warning(f"DartFilter 초기화 실패: {e}")
                self._dart_filter = False
        return self._dart_filter if self._dart_filter else None

    def select_stocks(self, date: Optional[str] = None, top_n: int = 5) -> List[Candidate]:
        if date is None:
            date = datetime.now().strftime("%Y%m%d")
        self.selection_date = date
        print(f"\n[{self.STRATEGY_NAME}] 종목 선정 시작 ({date})")

        dart = self._get_dart_filter()
        if not dart or not dart.is_available():
            print("  DART API 사용 불가")
            return []

        krx = get_krx()
        if not krx:
            print("  KRX 사용 불가")
            return []

        # 1. DART 호재 공시 종목 (전일 18시 ~ 당일 08:30)
        try:
            positive_stocks = dart.get_positive_stocks(target_date=date)
        except Exception as e:
            print(f"  DART fetch 실패: {e}")
            return []

        if not positive_stocks:
            print("  호재 공시 없음")
            return []
        print(f"  호재 공시: {len(positive_stocks)}개 종목")

        positive_codes = {p.stock_code: p for p in positive_stocks if hasattr(p, "stock_code")}

        # 2. 당일 시장 데이터
        all_stocks = fetch_all_markets(date)
        if not all_stocks:
            return []

        # 3. 호재 공시 종목 매칭 + 갭 계산
        matched = []
        for s in all_stocks:
            if s["code"] not in positive_codes:
                continue
            prev_close = s["prev_close"]
            if prev_close <= 0:
                continue
            gap_pct = (s["open"] - prev_close) / prev_close * 100
            if gap_pct < self.GAP_MIN_PCT:
                continue
            s["gap_pct"] = gap_pct
            s["dart_info"] = positive_codes[s["code"]]
            matched.append(s)

        print(f"  공시 + 갭 매칭: {len(matched)}개")

        # 4. 기본 필터
        filtered = basic_filter(
            matched,
            min_price=self.MIN_PRICE,
            min_market_cap=self.MIN_MARKET_CAP,
            min_trading_value=self.MIN_TRADING_VALUE,
        )

        # 거래량 surge 필터 (전일 대비)
        krx_filtered = []
        for s in filtered:
            try:
                # 어제 거래량 (단순: prev_close 옆 데이터 없으므로 일봉 history fetch는 생략)
                # 거래대금 자체로 surge 근사
                if s["trading_value"] >= self.MIN_TRADING_VALUE * self.VOLUME_SURGE_MIN:
                    krx_filtered.append(s)
            except Exception:
                continue

        print(f"  거래량 surge: {len(krx_filtered)}개")

        if not krx_filtered:
            return []

        scored = self._calculate_scores(krx_filtered)
        scored.sort(key=lambda c: c.score, reverse=True)
        self.candidates = scored[:top_n]
        for i, c in enumerate(self.candidates, 1):
            c.rank = i

        print(f"  선정 완료: {len(self.candidates)}개")
        return self.candidates

    def _calculate_scores(self, stocks: List[Dict]) -> List[Candidate]:
        if not stocks:
            return []

        max_gap = max((s.get("gap_pct", 0) for s in stocks), default=1) or 1
        max_tv = max((s["trading_value"] for s in stocks), default=1) or 1

        candidates: List[Candidate] = []
        for s in stocks:
            dart_info = s.get("dart_info")
            disclosure_score = 1.0  # 기본값. 실제론 dart_info에서 카테고리/금액 점수 추출
            if dart_info and hasattr(dart_info, "category"):
                category = dart_info.category
                disclosure_score = {
                    "실적": 1.0, "계약": 0.95, "투자": 0.85,
                    "기술": 0.9, "배당": 0.7, "대형": 0.85,
                }.get(category, 0.6)

            score_detail = {
                "disclosure_quality": disclosure_score * self.WEIGHTS["disclosure_quality"],
                "gap_reaction": (s.get("gap_pct", 0) / max_gap) * self.WEIGHTS["gap_reaction"],
                "volume_surge": min(s["trading_value"] / (self.MIN_TRADING_VALUE * 4), 1) * self.WEIGHTS["volume_surge"],
                "trading_value": (s["trading_value"] / max_tv) * self.WEIGHTS["trading_value"],
            }
            total = round(sum(score_detail.values()), 2)
            candidates.append(Candidate(
                code=s["code"],
                name=s["name"],
                price=s["open"],
                change_pct=s.get("gap_pct", 0),
                score=total,
                score_detail={k: round(v, 2) for k, v in score_detail.items()},
                market_cap=s["market_cap"],
                volume=s["volume"],
                trading_value=s["trading_value"],
            ))
        return candidates

    def get_params(self) -> Dict:
        return {
            "gap_min_pct": self.GAP_MIN_PCT,
            "min_price": self.MIN_PRICE,
            "min_market_cap": self.MIN_MARKET_CAP,
            "min_trading_value": self.MIN_TRADING_VALUE,
            "volume_surge_min": self.VOLUME_SURGE_MIN,
            "weights": self.WEIGHTS,
        }
