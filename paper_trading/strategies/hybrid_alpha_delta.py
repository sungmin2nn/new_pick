"""
Alpha-Delta 하이브리드 전략
- 모멘텀(Alpha) + 테마/정책(Delta) 전략의 가중평균 조합
- 양쪽 모두 선택된 종목에 시너지 보너스 부여
"""

import logging
from typing import List, Dict

from .base import BaseStrategy, Candidate
from .registry import StrategyRegistry

logger = logging.getLogger(__name__)


@StrategyRegistry.register
class HybridAlphaDeltaStrategy(BaseStrategy):
    """Alpha-Delta 하이브리드 전략"""

    STRATEGY_ID = "hybrid_alpha_delta"
    STRATEGY_NAME = "Alpha-Delta 하이브리드"
    CATEGORY = "hybrid"
    DESCRIPTION = "모멘텀 + 테마 전략의 가중평균 조합"

    # 가중치 설정
    WEIGHT_ALPHA = 0.65
    WEIGHT_DELTA = 0.35

    # 양쪽 모두 선택된 종목 보너스
    OVERLAP_BONUS = 10.0

    # 서브 전략 후보 풀 크기
    SUB_TOP_N = 10

    def __init__(self):
        super().__init__()
        self._alpha_strategy = None
        self._delta_strategy = None

    def _get_alpha_strategy(self):
        """MomentumStrategy 지연 로드 (순환 import 방지)"""
        if self._alpha_strategy is None:
            from .momentum import MomentumStrategy
            self._alpha_strategy = MomentumStrategy()
        return self._alpha_strategy

    def _get_delta_strategy(self):
        """ThemePolicyStrategy 지연 로드 (순환 import 방지)"""
        if self._delta_strategy is None:
            from .theme_policy import ThemePolicyStrategy
            self._delta_strategy = ThemePolicyStrategy()
        return self._delta_strategy

    def select_stocks(self, date: str = None, top_n: int = 5) -> List[Candidate]:
        """종목 선정: Alpha + Delta 가중평균"""
        from utils import format_kst_time

        if date is None:
            date = format_kst_time(format_str='%Y%m%d')

        self.selection_date = date
        print(f"\n[{self.STRATEGY_NAME}] 종목 선정 시작 ({date})")

        # 1. 두 전략을 각각 실행 (넓은 후보 풀)
        alpha_candidates = self._run_sub_strategy(
            self._get_alpha_strategy(), date, self.SUB_TOP_N, "Alpha"
        )
        delta_candidates = self._run_sub_strategy(
            self._get_delta_strategy(), date, self.SUB_TOP_N, "Delta"
        )

        print(f"  Alpha 후보: {len(alpha_candidates)}개, Delta 후보: {len(delta_candidates)}개")

        # 2. Union: 모든 후보를 합침
        alpha_map: Dict[str, Candidate] = {c.code: c for c in alpha_candidates}
        delta_map: Dict[str, Candidate] = {c.code: c for c in delta_candidates}

        all_codes = set(alpha_map.keys()) | set(delta_map.keys())
        overlap_codes = set(alpha_map.keys()) & set(delta_map.keys())

        print(f"  총 후보: {len(all_codes)}개 (중복: {len(overlap_codes)}개)")

        # 3. 가중평균 점수 계산
        merged: List[Candidate] = []

        for code in all_codes:
            alpha_c = alpha_map.get(code)
            delta_c = delta_map.get(code)

            # 점수 계산
            alpha_score = alpha_c.score if alpha_c else 0.0
            delta_score = delta_c.score if delta_c else 0.0

            weighted_score = (alpha_score * self.WEIGHT_ALPHA) + (delta_score * self.WEIGHT_DELTA)

            # 4. 양쪽 모두 선택된 종목에 보너스
            source = []
            if alpha_c:
                source.append("alpha")
            if delta_c:
                source.append("delta")

            if code in overlap_codes:
                weighted_score += self.OVERLAP_BONUS

            weighted_score = round(weighted_score, 1)

            # 기본 정보는 존재하는 쪽에서 가져옴 (alpha 우선)
            ref = alpha_c or delta_c

            score_detail = {
                'alpha_score': round(alpha_score, 1),
                'delta_score': round(delta_score, 1),
                'alpha_weighted': round(alpha_score * self.WEIGHT_ALPHA, 1),
                'delta_weighted': round(delta_score * self.WEIGHT_DELTA, 1),
                'overlap_bonus': self.OVERLAP_BONUS if code in overlap_codes else 0,
                'source': source,
            }

            merged.append(Candidate(
                code=ref.code,
                name=ref.name,
                price=ref.price,
                change_pct=ref.change_pct,
                score=weighted_score,
                score_detail=score_detail,
                market_cap=ref.market_cap,
                volume=ref.volume,
                trading_value=ref.trading_value,
            ))

        # 5. 점수 상위 top_n 선정
        merged.sort(key=lambda x: x.score, reverse=True)
        self.candidates = merged[:top_n]

        for i, c in enumerate(self.candidates, 1):
            c.rank = i

        print(f"  선정 완료: {len(self.candidates)}개")
        for c in self.candidates:
            src = ', '.join(c.score_detail.get('source', []))
            bonus = " +BONUS" if c.score_detail.get('overlap_bonus', 0) > 0 else ""
            print(f"    {c.rank}. {c.name}({c.code}) = {c.score}점 [{src}{bonus}]")

        return self.candidates

    def _run_sub_strategy(
        self, strategy: BaseStrategy, date: str, top_n: int, label: str
    ) -> List[Candidate]:
        """서브 전략 실행 (에러 시 빈 리스트 반환)"""
        try:
            return strategy.select_stocks(date=date, top_n=top_n)
        except Exception as e:
            logger.warning(f"[{self.STRATEGY_NAME}] {label} 전략 실행 실패: {e}")
            print(f"  ⚠ {label} 전략 실패: {e} - 나머지로 계속 진행")
            return []

    def get_params(self) -> Dict:
        return {
            'weight_alpha': self.WEIGHT_ALPHA,
            'weight_delta': self.WEIGHT_DELTA,
            'overlap_bonus': self.OVERLAP_BONUS,
            'sub_top_n': self.SUB_TOP_N,
            'alpha_strategy': 'momentum',
            'delta_strategy': 'theme_policy',
        }
