"""
중복 검사 로직.

신규 전략이 news-trading-bot의 기존 전략(5팀 + BNF)과
본질적으로 중복되는지 검사한다.

3가지 검사:
1. ID 중복 (즉시 실패)
2. 카테고리 + 핵심 시그널 중복 (자동 경고)
3. 가설 의미 유사도 (수동 리뷰 필요 — 자연어, Claude 보조)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ============================================================
# 기존 전략 정의 (handoff.md 기반)
# ============================================================

EXISTING_STRATEGIES = [
    {
        "id": "alpha_momentum",
        "team": "team_a",
        "name": "Alpha Momentum",
        "category": "momentum",
        "core_signals": ["MA5_breakout", "volume_3x", "trend_following"],
        "data": ["KRX_OHLCV"],
        "summary": "5일 이동평균 돌파 + 거래량 3배 증가 추세 추종",
    },
    {
        "id": "beta_contrarian",
        "team": "team_b",
        "name": "Beta Contrarian",
        "category": "contrarian",
        "core_signals": ["RSI_oversold", "kospi_filter", "largecap_only"],
        "data": ["KRX_OHLCV", "KRX_INDEX"],
        "summary": "RSI ≤ 35 대형주 역추세, KOSPI 모드 필터",
    },
    {
        "id": "gamma_disclosure",
        "team": "team_c",
        "name": "Gamma Disclosure",
        "category": "event",
        "core_signals": ["dart_positive_disclosure", "phase_2c_filter"],
        "data": ["DART"],
        "summary": "DART 호재 공시 (Phase 2C 정제)",
    },
    {
        "id": "delta_theme",
        "team": "team_d",
        "name": "Delta Theme",
        "category": "theme",
        "core_signals": ["naver_theme_today", "krx_sector_historical"],
        "data": ["NAVER_THEME", "KRX_SECTOR_INDEX"],
        "summary": "당일 naver 테마 / 과거 KRX 업종 지수 기반",
    },
    {
        "id": "echo_frontier",
        "team": "team_e",
        "name": "Echo Frontier",
        "category": "breakout",
        "core_signals": ["opening_gap_2_5", "volume_surge"],
        "data": ["KRX_OHLCV"],
        "summary": "시초가 갭 +2~5% + 거래량 surge",
    },
    {
        "id": "bnf_fall",
        "team": "bnf",
        "name": "BNF 낙폭과대",
        "category": "contrarian",
        "core_signals": ["3day_drop_10pct", "split_buy", "trailing_stop"],
        "data": ["KRX_OHLCV"],
        "summary": "3거래일 -10% 이상 종목 분할매수 + 트레일링 스탑",
    },
]


# ============================================================
# 결과 데이터 클래스
# ============================================================

@dataclass
class DuplicateCheckResult:
    """중복 검사 결과."""
    passed: bool
    severity: str  # "ok" | "warning" | "fail"
    matches: list  # list of dict {strategy_id, reason, score}
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "severity": self.severity,
            "matches": self.matches,
            "message": self.message,
        }


# ============================================================
# 검사 함수들
# ============================================================

def check_id_collision(new_id: str) -> Optional[dict]:
    """ID가 정확히 같은지."""
    for s in EXISTING_STRATEGIES:
        if s["id"].lower() == new_id.lower():
            return {
                "strategy_id": s["id"],
                "reason": "id_exact_match",
                "score": 1.0,
            }
    return None


def check_category_signal_overlap(
    new_category: str,
    new_signals: list,
    threshold: float = 0.6,
) -> list:
    """
    같은 카테고리 + 핵심 시그널 겹침 검사.

    겹침 점수: |교집합| / |합집합|
    threshold 이상이면 매치로 판단.
    """
    matches = []
    new_signals_set = set(s.lower() for s in new_signals)

    for s in EXISTING_STRATEGIES:
        if s["category"] != new_category:
            continue

        existing_signals = set(sig.lower() for sig in s["core_signals"])
        if not new_signals_set or not existing_signals:
            continue

        intersection = new_signals_set & existing_signals
        union = new_signals_set | existing_signals
        overlap_score = len(intersection) / len(union) if union else 0

        if overlap_score >= threshold:
            matches.append({
                "strategy_id": s["id"],
                "reason": "category_signal_overlap",
                "category": s["category"],
                "overlap_signals": list(intersection),
                "score": round(overlap_score, 2),
            })

    return matches


def check_data_pattern(new_data_reqs: list) -> list:
    """동일 데이터 + 단순 시그널 = 의심스러움 (참고용)."""
    matches = []
    new_set = set(d.upper() for d in new_data_reqs)

    for s in EXISTING_STRATEGIES:
        existing_set = set(d.upper() for d in s["data"])
        if new_set == existing_set:
            matches.append({
                "strategy_id": s["id"],
                "reason": "identical_data_dependency",
                "data": list(new_set),
                "score": 0.5,
            })
    return matches


# ============================================================
# 통합 검사
# ============================================================

def check_duplicate(
    new_id: str,
    new_category: str,
    new_signals: list,
    new_data: list,
    differs_from_existing: str = "",
) -> DuplicateCheckResult:
    """
    신규 전략이 기존과 중복되는지 종합 검사.

    Returns:
        DuplicateCheckResult
    """
    matches = []

    # 1. ID 충돌 (즉시 fail)
    id_match = check_id_collision(new_id)
    if id_match:
        return DuplicateCheckResult(
            passed=False,
            severity="fail",
            matches=[id_match],
            message=f"전략 ID '{new_id}'가 기존 '{id_match['strategy_id']}'와 동일합니다.",
        )

    # 2. 카테고리 + 시그널 겹침 (warning)
    overlap_matches = check_category_signal_overlap(new_category, new_signals)
    matches.extend(overlap_matches)

    # 3. 데이터 패턴 동일 (참고)
    data_matches = check_data_pattern(new_data)
    matches.extend(data_matches)

    # 판정
    if not matches:
        return DuplicateCheckResult(
            passed=True,
            severity="ok",
            matches=[],
            message="기존 전략과 중복 없음.",
        )

    # 시그널 겹침이 있는데 differs_from_existing이 비어있으면 fail
    has_overlap = any(m["reason"] == "category_signal_overlap" for m in matches)
    if has_overlap and not differs_from_existing.strip():
        return DuplicateCheckResult(
            passed=False,
            severity="fail",
            matches=matches,
            message=(
                f"기존 전략과 시그널 겹침 ({len(overlap_matches)}건). "
                f"metadata.differs_from_existing 필드에 차이점을 명시하세요."
            ),
        )

    # 겹침 있지만 차이점 설명 있으면 warning
    if has_overlap:
        return DuplicateCheckResult(
            passed=True,
            severity="warning",
            matches=matches,
            message=(
                f"기존 전략과 시그널 겹침이 있으나 차이점이 명시되어 있습니다. "
                f"수동 검토 권장."
            ),
        )

    # 데이터만 같은 경우는 통과 (정보 제공만)
    return DuplicateCheckResult(
        passed=True,
        severity="ok",
        matches=matches,
        message="동일 데이터 사용 (참고). 시그널이 다르면 문제 없음.",
    )


def check_strategy_metadata(metadata) -> DuplicateCheckResult:
    """
    StrategyMetadata 객체로부터 중복 검사를 실행하는 헬퍼.
    metadata.notes 또는 별도 필드에서 core_signals를 추출한다.
    """
    # 메타데이터에 core_signals가 직접 없으므로
    # 일단 hypothesis + rationale에서 단어를 추출하는 단순 방식
    text = (metadata.hypothesis + " " + metadata.rationale).lower()
    # 단순 토큰화 (실제 신호는 사용자가 직접 명시하는 게 좋음)
    return check_duplicate(
        new_id=metadata.id,
        new_category=metadata.category,
        new_signals=text.split(),  # placeholder
        new_data=metadata.data_requirements,
        differs_from_existing=metadata.differs_from_existing,
    )


__all__ = [
    "EXISTING_STRATEGIES",
    "DuplicateCheckResult",
    "check_id_collision",
    "check_category_signal_overlap",
    "check_data_pattern",
    "check_duplicate",
    "check_strategy_metadata",
]
