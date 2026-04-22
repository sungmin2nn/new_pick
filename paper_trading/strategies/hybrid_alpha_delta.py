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

    # 가중치 설정 (alpha/delta 각각 min-max 정규화된 0~100 점수에 적용)
    WEIGHT_ALPHA = 0.65
    WEIGHT_DELTA = 0.35

    # 양쪽 모두 선택된 종목 보너스
    OVERLAP_BONUS = 10.0

    # 서브 전략 후보 풀 크기
    SUB_TOP_N = 10

    # 최종 편성 슬롯: Alpha 슬롯 + Delta 슬롯 = top_n
    # Alpha/Delta 한쪽이 부족하면 나머지로 백필. 겹치는 후보는 Alpha 슬롯에 먼저 배치.
    ALPHA_SLOT = 3
    DELTA_SLOT = 2

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

        # 3. 점수 정규화 (min-max, 각 전략 top 점수를 100으로): 스케일 불균형 제거
        alpha_max = max((c.score for c in alpha_candidates), default=1.0) or 1.0
        delta_max = max((c.score for c in delta_candidates), default=1.0) or 1.0

        # 4. 가중평균 점수 계산 (정규화된 0~100 스케일 기준)
        merged: List[Candidate] = []

        for code in all_codes:
            alpha_c = alpha_map.get(code)
            delta_c = delta_map.get(code)

            alpha_raw = alpha_c.score if alpha_c else 0.0
            delta_raw = delta_c.score if delta_c else 0.0
            alpha_norm = (alpha_raw / alpha_max) * 100 if alpha_c else 0.0
            delta_norm = (delta_raw / delta_max) * 100 if delta_c else 0.0

            weighted_score = (alpha_norm * self.WEIGHT_ALPHA) + (delta_norm * self.WEIGHT_DELTA)

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
                'alpha_score': round(alpha_raw, 1),
                'delta_score': round(delta_raw, 1),
                'alpha_norm': round(alpha_norm, 1),
                'delta_norm': round(delta_norm, 1),
                'alpha_weighted': round(alpha_norm * self.WEIGHT_ALPHA, 1),
                'delta_weighted': round(delta_norm * self.WEIGHT_DELTA, 1),
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

        # 5. 슬롯 기반 편성 (Alpha 슬롯 + Delta 슬롯): 정렬 상태에서 양쪽 다양성 보장
        merged.sort(key=lambda x: x.score, reverse=True)

        alpha_pool = [c for c in merged if 'alpha' in c.score_detail['source']]
        delta_pool = [c for c in merged if 'delta' in c.score_detail['source']]

        # Alpha 슬롯: alpha-only + overlap 상위 N
        alpha_picks = alpha_pool[:self.ALPHA_SLOT]
        picked_codes = {c.code for c in alpha_picks}

        # Delta 슬롯: delta source 후보 중 Alpha에 이미 뽑힌 것 제외, 상위 N
        delta_picks = [c for c in delta_pool if c.code not in picked_codes][:self.DELTA_SLOT]

        # 한쪽이 부족하면 반대쪽으로 백필하여 top_n 보장
        shortfall = top_n - (len(alpha_picks) + len(delta_picks))
        if shortfall > 0:
            used = {c.code for c in alpha_picks + delta_picks}
            backfill = [c for c in merged if c.code not in used][:shortfall]
            alpha_picks = alpha_picks + backfill  # 순서만 유지, 슬롯은 논리 구분

        selected = alpha_picks + delta_picks
        # 최종 순서는 종합 점수 기준
        selected.sort(key=lambda x: x.score, reverse=True)
        self.candidates = selected[:top_n]

        for i, c in enumerate(self.candidates, 1):
            c.rank = i

        print(f"  선정 완료: {len(self.candidates)}개 (Alpha슬롯 {len(alpha_picks)} + Delta슬롯 {len(delta_picks)})")
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
            'alpha_slot': self.ALPHA_SLOT,
            'delta_slot': self.DELTA_SLOT,
            'score_normalization': 'min-max per-strategy (0~100)',
            'alpha_strategy': 'momentum',
            'delta_strategy': 'theme_policy',
        }
