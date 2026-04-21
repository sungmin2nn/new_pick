"""
신규 전략 템플릿.

새 전략을 만들 때 이 파일을 복사해서 작성하세요:

    cp _template.py my_strategy.py

작성 순서:
1. METADATA 정의 (출처, 가설, 카테고리)
2. check_strategy_metadata로 중복 검증
3. select_stocks() 구현
4. 백테스트로 검증

⚠️ 기존 6개 전략과 본질적으로 다른 것만 등록 가능합니다.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

# news-trading-bot에서 BaseStrategy import (lab/__init__.py가 sys.path 처리)
from lab import BaseStrategy, Candidate
from lab.metadata import (
    StrategyMetadata, StrategySource,
    StrategyCategory, RiskLevel, SourceType, TrustLevel,
)


# ============================================================
# 메타데이터 (필수)
# ============================================================

METADATA = StrategyMetadata(
    id="template_strategy",                    # snake_case 고유 ID
    name="템플릿 전략",                          # 한글 표시 이름
    version="0.1.0",
    category=StrategyCategory.OTHER.value,
    risk_level=RiskLevel.MEDIUM.value,

    hypothesis="여기에 한 문장 가설을 작성하세요.",
    rationale="더 긴 설명. 왜 이 가설이 작동할 것 같은지, 어떤 시장 비효율성을 노리는지.",
    expected_edge="기대 수익의 원천 (예: 정보 비대칭, 추세 추종, 평균 회귀)",

    data_requirements=["KRX_OHLCV"],            # 필요한 데이터 리스트
    min_history_days=30,
    requires_intraday=False,                    # True면 분봉 6일 한계

    target_basket_size=5,
    target_holding_days=1,
    target_market="KOSPI+KOSDAQ",

    differs_from_existing="기존 X 전략과 다른 점: ...",
    novelty_score=5,                            # 0~10 자체 평가
    notes="자유 메모",
)

# 출처 추가 (있다면)
METADATA.add_source(StrategySource(
    type=SourceType.SELF.value,
    title="자체 창작",
    trust_level=TrustLevel.HIGH.value,
    notes="아이디어 출처 및 검증 가능성 메모",
))


# ============================================================
# 전략 클래스
# ============================================================

class TemplateStrategy(BaseStrategy):
    """
    전략 본문.

    BaseStrategy를 상속하면 news-trading-bot의 백테스트 인프라에서
    그대로 실행 가능합니다.
    """

    STRATEGY_ID = METADATA.id
    STRATEGY_NAME = METADATA.name
    DESCRIPTION = METADATA.hypothesis

    def select_stocks(
        self,
        date: Optional[str] = None,
        top_n: int = 5,
    ) -> List[Candidate]:
        """
        종목 선정 로직.

        Args:
            date: YYYYMMDD (None이면 오늘)
            top_n: 선정할 종목 수

        Returns:
            Candidate 리스트
        """
        if date is None:
            date = datetime.now().strftime("%Y%m%d")

        candidates: List[Candidate] = []

        # ========================================
        # TODO: 여기에 전략 로직 작성
        # ========================================
        #
        # 1. 데이터 fetch
        #    from paper_trading.utils.krx_api import KRXClient
        #    krx = KRXClient()
        #    df = krx.get_stock_ohlcv(date, 'KOSPI')
        #
        # 2. 필터링
        #    filtered = df[df['volume'] > df['volume'].mean() * 2]
        #
        # 3. 점수 계산
        #    filtered['score'] = ...
        #
        # 4. 상위 N개 선정
        #    top = filtered.nlargest(top_n, 'score')
        #
        # 5. Candidate로 변환
        #    for _, row in top.iterrows():
        #        candidates.append(Candidate(
        #            code=row['code'],
        #            name=row['name'],
        #            price=int(row['close']),
        #            change_pct=float(row['change_pct']),
        #            score=float(row['score']),
        #        ))

        return candidates


# ============================================================
# 등록 (선택)
# ============================================================
#
# news-trading-bot의 StrategyRegistry에 등록하려면:
#
#     from lab import StrategyRegistry
#     StrategyRegistry.register(TemplateStrategy)
#
# 다만 strategy-lab에서는 보통 등록 없이 직접 호출하여 백테스트한다.
