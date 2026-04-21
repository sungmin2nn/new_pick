"""
전략 메타데이터 스키마.

각 전략은 코드 외에 출처/가설/리스크 등을 명시한 메타데이터를 가진다.
이 메타데이터는 리더보드, 검증 로그, 승급 판단에 사용된다.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


# ============================================================
# Enums
# ============================================================

class StrategyCategory(str, Enum):
    """전략 분류."""
    MOMENTUM = "momentum"           # 추세 추종
    CONTRARIAN = "contrarian"       # 역추세
    BREAKOUT = "breakout"           # 돌파
    EVENT = "event"                 # 이벤트 (공시/뉴스)
    THEME = "theme"                 # 테마/섹터 로테이션
    FLOW = "flow"                   # 수급 (외국인/기관)
    PATTERN = "pattern"             # 차트 패턴
    STATISTICAL = "statistical"     # 통계적 차익
    HYBRID = "hybrid"               # 다중 신호 복합
    OTHER = "other"


class RiskLevel(str, Enum):
    """리스크 등급."""
    LOW = "low"           # 안정형 (저변동/대형주)
    MEDIUM = "medium"     # 중간 (혼합)
    HIGH = "high"         # 공격형 (소형주/높은 변동성)
    EXTREME = "extreme"   # 초고위험 (테마주/단타 단발)


class SourceType(str, Enum):
    """출처 유형."""
    SELF = "self"                       # 자체 창작
    BLOG_KO = "blog_ko"                 # 한국 블로그
    BLOG_EN = "blog_en"                 # 영어 블로그
    YOUTUBE = "youtube"
    PAPER = "paper"                     # 학술 논문 (SSRN/arXiv 등)
    BOOK = "book"
    COMMUNITY = "community"             # Reddit/X/디시 등
    OFFICIAL_DOC = "official_doc"       # KRX/금감원/증권사 리서치
    HANDOFF_GUIDE = "handoff_guide"     # handoff.md 후보
    OTHER = "other"


class TrustLevel(str, Enum):
    """출처 신뢰성 (검증 결과)."""
    VERIFIED = "verified"               # 동료심사 / 권위 있는 출처
    HIGH = "high"                       # 검증 가능한 저자
    MEDIUM = "medium"                   # 일반적 출처
    LOW = "low"                         # 익명 / 검증 불가
    UNVERIFIED = "unverified"           # 미검증


# ============================================================
# Source citation
# ============================================================

@dataclass
class StrategySource:
    """전략 출처 정보."""
    type: str                           # SourceType value
    title: str = ""
    author: str = ""
    url: str = ""
    published_date: str = ""
    accessed_date: str = ""
    trust_level: str = "unverified"     # TrustLevel value
    notes: str = ""

    def __post_init__(self):
        if not self.accessed_date:
            self.accessed_date = datetime.now().strftime("%Y-%m-%d")


# ============================================================
# Strategy metadata
# ============================================================

@dataclass
class StrategyMetadata:
    """전략 전체 메타데이터."""

    # 식별
    id: str                             # 고유 ID (snake_case)
    name: str                           # 표시 이름 (한글 OK)
    version: str = "0.1.0"

    # 분류
    category: str = StrategyCategory.OTHER.value
    risk_level: str = RiskLevel.MEDIUM.value

    # 가설
    hypothesis: str = ""                # 한 문장 가설
    rationale: str = ""                 # 더 긴 설명
    expected_edge: str = ""             # 기대 수익 원천

    # 출처
    sources: list = field(default_factory=list)  # list[StrategySource]

    # 데이터 의존도
    data_requirements: list = field(default_factory=list)  # ["KRX_OHLCV", "DART", ...]
    min_history_days: int = 30          # 백테스트에 필요한 최소 과거 일수
    requires_intraday: bool = False     # 분봉 필요 여부 (true면 6일 한계)

    # 매매 파라미터
    target_basket_size: int = 5         # 한 번에 보유 종목 수
    target_holding_days: int = 1        # 평균 보유일 (1=당일 청산)
    target_market: str = "KOSPI+KOSDAQ" # KOSPI / KOSDAQ / KOSPI+KOSDAQ

    # 중복 검증
    differs_from_existing: str = ""     # 기존 6개 전략과 어떻게 다른가
    novelty_score: int = 0              # 0~10 (내부 평가)

    # 상태
    status: str = "draft"               # draft | tested | promoted | rejected
    created_at: str = ""
    updated_at: str = ""
    author: str = "claude-code-session"

    # 자유 메모
    notes: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat(timespec="seconds")
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def save(self, dir_path: Path) -> Path:
        dir_path = Path(dir_path)
        dir_path.mkdir(parents=True, exist_ok=True)
        file_path = dir_path / f"{self.id}.metadata.json"
        file_path.write_text(self.to_json(), encoding="utf-8")
        return file_path

    @classmethod
    def load(cls, file_path: Path) -> "StrategyMetadata":
        file_path = Path(file_path)
        data = json.loads(file_path.read_text(encoding="utf-8"))
        # sources는 dict 리스트로 들어오므로 그대로 둠 (직렬화/역직렬화 단순화)
        return cls(**data)

    def add_source(self, source: StrategySource) -> None:
        self.sources.append(asdict(source))
        self.updated_at = datetime.now().isoformat(timespec="seconds")


# ============================================================
# Helpers
# ============================================================

def list_categories() -> list:
    return [c.value for c in StrategyCategory]


def list_risk_levels() -> list:
    return [r.value for r in RiskLevel]


def list_source_types() -> list:
    return [s.value for s in SourceType]


__all__ = [
    "StrategyCategory",
    "RiskLevel",
    "SourceType",
    "TrustLevel",
    "StrategySource",
    "StrategyMetadata",
    "list_categories",
    "list_risk_levels",
    "list_source_types",
]
