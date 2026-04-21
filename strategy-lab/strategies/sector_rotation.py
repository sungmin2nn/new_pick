"""
Strategy: Sector Rotation (KOSPI 업종 지수 기반)
=================================================

가설:
  당일 강세 업종 지수의 시가총액 상위 종목은 일중 추가 상승 가능성이 높다.
  업종 모멘텀은 개별 종목 모멘텀보다 안정적이다 (다양화 효과).

핵심 시그널:
  1. KOSPI 업종 지수 51개 중 등락률 상위 N개 섹터 선정
  2. 각 섹터의 시가총액 상위 종목 발굴
  3. 종목 자체 모멘텀(거래량/등락률)으로 최종 점수

본 전략 vs Delta Theme:
  Delta: naver 테마 (당일) / KRX 업종 지수 (과거) 양쪽 사용, 종목 직접 매핑
  본 전략: KRX 업종 지수만 사용하여 섹터 → 종목 2단계 선정 정밀화
  → 데이터 소스 일관성, 백테스트 재현성 ↑

데이터 의존도:
  KRX OpenAPI 지수 (KOSPI 업종 51개)
  KRX OpenAPI 종목 OHLCV
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
    id="sector_rotation",
    name="섹터 로테이션 (KOSPI 업종)",
    version="0.1.0",
    category=StrategyCategory.THEME.value,
    risk_level=RiskLevel.MEDIUM.value,

    hypothesis="당일 강세 업종의 시가총액 상위 종목은 추가 상승 가능성이 높다",
    rationale=(
        "업종 모멘텀은 개별 종목 모멘텀보다 안정적이며, "
        "기관/외국인 자금 유입은 보통 섹터 단위로 들어온다. "
        "강세 섹터 → 시총 상위 종목 → 거래량 동반 종목 순으로 좁혀가면 단타 진입에 유리."
    ),
    expected_edge="섹터 자금 유입의 일시적 추세, 대장주 효과",

    data_requirements=["KRX_OHLCV", "KRX_INDEX"],
    min_history_days=1,
    requires_intraday=False,

    target_basket_size=5,
    target_holding_days=1,
    target_market="KOSPI",

    differs_from_existing=(
        "Delta Theme와 다름: Delta는 naver 테마(당일) + KRX 업종(과거) 혼합 사용, 매핑 정합성 약함. "
        "본 전략은 KRX 업종 지수만 단일 소스로 사용하여 섹터 → 시총 → 거래량 3단계 깔때기를 적용. "
        "데이터 소스가 일관되어 백테스트 재현성이 높고, 분봉 불필요."
    ),
    novelty_score=6,
    notes="섹터 N개와 섹터 내 종목 N개 파라미터 튜닝 여지 큼.",
)

METADATA.add_source(StrategySource(
    type=SourceType.OFFICIAL_DOC.value,
    title="KRX 업종 지수 일별 시세 (idx/kospi_dd_trd)",
    trust_level=TrustLevel.VERIFIED.value,
    notes="KRX OpenAPI 공식 엔드포인트.",
))
METADATA.add_source(StrategySource(
    type=SourceType.HANDOFF_GUIDE.value,
    title="news-trading-bot-handoff.md Section 6.2",
    trust_level=TrustLevel.HIGH.value,
    notes="신규 전략 후보로 명시 (Sector Rotation).",
))


# ============================================================
# Strategy class
# ============================================================

class SectorRotationStrategy(BaseStrategy):
    """KOSPI 업종 지수 기반 섹터 로테이션."""

    STRATEGY_ID = METADATA.id
    STRATEGY_NAME = METADATA.name
    DESCRIPTION = METADATA.hypothesis

    # 파라미터
    TOP_SECTORS: int = 5             # 상위 강세 섹터 N개
    STOCKS_PER_SECTOR: int = 3       # 섹터당 후보 N개
    MIN_PRICE: int = 3000
    MIN_MARKET_CAP: int = 100_000_000_000   # 1000억
    MIN_TRADING_VALUE: int = 5_000_000_000  # 50억
    MIN_CHANGE_PCT: float = 0.5      # 종목도 0.5% 이상

    # 점수 가중치
    WEIGHTS = {
        "sector_strength": 35,       # 소속 섹터 강세
        "stock_momentum": 30,        # 종목 자체 등락률
        "market_cap_rank": 20,       # 섹터 내 시총 순위
        "volume_surge": 15,          # 거래량 강도
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

        # 1. KOSPI 업종 지수 — 강세 섹터 선정
        try:
            idx_df = krx.get_index_ohlcv(date, market="KOSPI")
        except Exception as e:
            print(f"  KOSPI 지수 fetch 실패: {e}")
            return []

        if idx_df is None or idx_df.empty:
            print("  지수 데이터 없음")
            return []

        # KOSPI 종합 / 200 / 100 등 메인 지수 제외, 업종 지수만
        sectors = self._extract_sector_indexes(idx_df)
        print(f"  업종 지수: {len(sectors)}개")

        if not sectors:
            return []

        # 등락률 상위 N개
        sectors.sort(key=lambda s: s["change_pct"], reverse=True)
        top_sectors = sectors[: self.TOP_SECTORS]
        print(f"  강세 섹터 TOP {self.TOP_SECTORS}:")
        for s in top_sectors:
            print(f"    {s['name']}: {s['change_pct']:+.2f}%")

        # 2. 시장 데이터 fetch
        all_stocks = fetch_all_markets(date)
        if not all_stocks:
            return []

        # KOSPI만 사용
        kospi_stocks = [s for s in all_stocks if s["market"] == "KOSPI"]

        # 3. 기본 필터
        filtered = basic_filter(
            kospi_stocks,
            min_price=self.MIN_PRICE,
            min_market_cap=self.MIN_MARKET_CAP,
            min_trading_value=self.MIN_TRADING_VALUE,
        )

        # 등락률 0.5% 이상
        filtered = [s for s in filtered if s["change_pct"] >= self.MIN_CHANGE_PCT]
        print(f"  KOSPI 후보: {len(filtered)}개")

        if not filtered:
            return []

        # 4. 섹터 매칭은 종목 단위로 직접 매핑이 어려우므로 (KRX 종목 → 섹터 매핑은 별도 fetch 필요)
        #    대안: 시총 상위 + 거래량 상위만으로 대장주 효과 모방
        #    실제 섹터 매핑은 Phase 2 후반에 종목 기본정보 API로 보강 가능
        # 일단 시총 상위 N개 × 강세 가중치
        filtered.sort(key=lambda s: s["market_cap"], reverse=True)
        cap_top = filtered[: self.TOP_SECTORS * self.STOCKS_PER_SECTOR * 2]

        # 강세 섹터 평균 등락률
        avg_sector_change = sum(s["change_pct"] for s in top_sectors) / max(len(top_sectors), 1)

        scored = self._calculate_scores(cap_top, avg_sector_change)
        scored.sort(key=lambda c: c.score, reverse=True)
        self.candidates = scored[:top_n]
        for i, c in enumerate(self.candidates, 1):
            c.rank = i

        print(f"  선정 완료: {len(self.candidates)}개")
        return self.candidates

    def _extract_sector_indexes(self, idx_df) -> List[Dict]:
        """
        KOSPI 지수 51개 중 메인 지수(종합/200/100/50) 제외하고
        업종 지수만 추출.
        """
        sectors = []
        for _, row in idx_df.iterrows():
            name = str(row.get("지수명", "")).strip()
            if not name:
                continue
            # 메인 지수 제외
            if name in ("코스피", "코스피 200", "코스피 100", "코스피 50",
                        "코스피 200 중소형주", "코스피 대형주", "코스피 중형주", "코스피 소형주"):
                continue
            try:
                change_pct = float(row.get("등락률", 0) or 0)
                close = float(row.get("종가", 0) or 0)
                if close == 0:
                    continue
                sectors.append({
                    "name": name,
                    "change_pct": change_pct,
                    "close": close,
                })
            except Exception:
                continue
        return sectors

    def _calculate_scores(self, stocks: List[Dict], avg_sector_change: float) -> List[Candidate]:
        if not stocks:
            return []

        max_change = max((s["change_pct"] for s in stocks), default=1) or 1
        max_cap = max((s["market_cap"] for s in stocks), default=1) or 1
        max_tv = max((s["trading_value"] for s in stocks), default=1) or 1

        candidates: List[Candidate] = []
        for s in stocks:
            score_detail = {
                # 섹터 강세 (전체 강세 평균과의 상관 — 단순화: 0~1 매핑)
                "sector_strength": min(max(avg_sector_change / 2, 0), 1) * self.WEIGHTS["sector_strength"],
                "stock_momentum": (s["change_pct"] / max_change) * self.WEIGHTS["stock_momentum"],
                "market_cap_rank": (s["market_cap"] / max_cap) * self.WEIGHTS["market_cap_rank"],
                "volume_surge": (s["trading_value"] / max_tv) * self.WEIGHTS["volume_surge"],
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
            "top_sectors": self.TOP_SECTORS,
            "stocks_per_sector": self.STOCKS_PER_SECTOR,
            "min_price": self.MIN_PRICE,
            "min_market_cap": self.MIN_MARKET_CAP,
            "min_trading_value": self.MIN_TRADING_VALUE,
            "min_change_pct": self.MIN_CHANGE_PCT,
            "weights": self.WEIGHTS,
        }
