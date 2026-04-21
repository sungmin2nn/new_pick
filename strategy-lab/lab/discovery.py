"""
Discovery Queue System
=======================
외부 자료에서 발굴된 전략 후보를 큐로 관리.

4단계 상태:
- pending  : 발굴 직후 (사용자 검토 대기)
- approved : 사용자가 승인 (코드화 대기)
- coded    : Claude Code 세션이 전략 파일 생성 완료
- rejected : 사용자가 거부 또는 중복/저품질

각 후보 = 1개 JSON 파일 (data/discovery/{status}/{id}.json)
발굴 이력 = 누적 로그 (data/discovery_log.jsonl)

큐 엔트리 최소 스키마:
    id, title, source_type, source_url, trust_level,
    category_guess, hypothesis, differs_from_existing_guess,
    data_requirements, discovered_at, status, reviewer, notes
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DISCOVERY_ROOT = PROJECT_ROOT / "data" / "discovery"
DISCOVERY_LOG = PROJECT_ROOT / "data" / "discovery_log.jsonl"


class DiscoveryStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    CODED = "coded"
    REJECTED = "rejected"


# ============================================================
# Candidate data class
# ============================================================

@dataclass
class DiscoveryCandidate:
    """발굴된 전략 후보."""
    id: str = ""
    title: str = ""

    # 출처
    source_type: str = "other"          # blog_ko/blog_en/youtube/paper/book/community/official_doc/handoff_guide/other
    source_url: str = ""
    source_author: str = ""
    source_published: str = ""
    trust_level: str = "unverified"     # verified/high/medium/low/unverified

    # 추정 메타 (Claude가 추론)
    category_guess: str = "other"       # momentum/contrarian/breakout/event/theme/flow/pattern/statistical/hybrid/other
    risk_level_guess: str = "medium"
    hypothesis: str = ""                # 한 문장
    rationale: str = ""                 # 긴 설명
    expected_edge: str = ""
    differs_from_existing_guess: str = ""
    data_requirements: list = field(default_factory=list)
    requires_intraday: bool = False
    target_holding_days: int = 1

    # 추정 novelty (Claude가 1~10)
    novelty_score: int = 5

    # 원시 발췌 (프롬프트 재생성 가능하도록)
    raw_snippet: str = ""

    # 상태 관리
    status: str = DiscoveryStatus.PENDING.value
    discovered_at: str = ""
    discovered_by: str = "claude-code-session"
    reviewed_at: str = ""
    reviewer: str = ""
    review_notes: str = ""
    coded_at: str = ""
    coded_file: str = ""                # 생성된 strategies/{id}.py 경로

    def __post_init__(self):
        if not self.id:
            self.id = f"disc_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        if not self.discovered_at:
            self.discovered_at = datetime.now().isoformat(timespec="seconds")

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# ============================================================
# Queue manager
# ============================================================

class DiscoveryQueue:
    """발굴된 후보의 상태 전환을 관리."""

    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root else DISCOVERY_ROOT
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        for s in DiscoveryStatus:
            (self.root / s.value).mkdir(parents=True, exist_ok=True)

    def _path(self, status: DiscoveryStatus, id: str) -> Path:
        return self.root / status.value / f"{id}.json"

    # --------------------------------------------------------
    # CRUD
    # --------------------------------------------------------

    def add(self, candidate: DiscoveryCandidate) -> Path:
        """신규 후보를 pending 큐에 추가 + 로그 누적."""
        candidate.status = DiscoveryStatus.PENDING.value
        path = self._path(DiscoveryStatus.PENDING, candidate.id)
        path.write_text(candidate.to_json(), encoding="utf-8")
        self._append_log("add", candidate)
        return path

    def add_batch(self, candidates: List[DiscoveryCandidate]) -> List[Path]:
        paths = []
        for c in candidates:
            paths.append(self.add(c))
        return paths

    def list(self, status: DiscoveryStatus) -> List[DiscoveryCandidate]:
        dir_path = self.root / status.value
        out = []
        if not dir_path.exists():
            return out
        for f in sorted(dir_path.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                out.append(DiscoveryCandidate(**data))
            except Exception:
                continue
        return out

    def get(self, id: str) -> Optional[DiscoveryCandidate]:
        for status in DiscoveryStatus:
            path = self._path(status, id)
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                return DiscoveryCandidate(**data)
        return None

    def _find_current_path(self, id: str) -> Optional[tuple]:
        for status in DiscoveryStatus:
            path = self._path(status, id)
            if path.exists():
                return (status, path)
        return None

    # --------------------------------------------------------
    # Transitions
    # --------------------------------------------------------

    def approve(self, id: str, reviewer: str = "user", notes: str = "") -> Optional[DiscoveryCandidate]:
        return self._transition(id, DiscoveryStatus.APPROVED, reviewer, notes)

    def reject(self, id: str, reviewer: str = "user", notes: str = "") -> Optional[DiscoveryCandidate]:
        return self._transition(id, DiscoveryStatus.REJECTED, reviewer, notes)

    def mark_coded(self, id: str, coded_file: str) -> Optional[DiscoveryCandidate]:
        cand = self.get(id)
        if not cand:
            return None
        cand.status = DiscoveryStatus.CODED.value
        cand.coded_at = datetime.now().isoformat(timespec="seconds")
        cand.coded_file = coded_file
        return self._move_to(cand, DiscoveryStatus.CODED)

    def _transition(
        self,
        id: str,
        target: DiscoveryStatus,
        reviewer: str,
        notes: str,
    ) -> Optional[DiscoveryCandidate]:
        cand = self.get(id)
        if not cand:
            return None
        cand.status = target.value
        cand.reviewed_at = datetime.now().isoformat(timespec="seconds")
        cand.reviewer = reviewer
        cand.review_notes = notes
        moved = self._move_to(cand, target)
        if moved:
            self._append_log(f"transition:{target.value}", moved)
        return moved

    def _move_to(self, cand: DiscoveryCandidate, target: DiscoveryStatus) -> DiscoveryCandidate:
        """기존 위치 파일 삭제 + 새 위치에 저장."""
        existing = self._find_current_path(cand.id)
        if existing:
            old_status, old_path = existing
            old_path.unlink()
        new_path = self._path(target, cand.id)
        cand.status = target.value
        new_path.write_text(cand.to_json(), encoding="utf-8")
        return cand

    # --------------------------------------------------------
    # Stats / Logging
    # --------------------------------------------------------

    def stats(self) -> Dict:
        return {s.value: len(self.list(s)) for s in DiscoveryStatus}

    def _append_log(self, action: str, cand: DiscoveryCandidate) -> None:
        DISCOVERY_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "action": action,
            "id": cand.id,
            "title": cand.title,
            "status": cand.status,
            "source_type": cand.source_type,
            "trust_level": cand.trust_level,
            "reviewer": cand.reviewer,
        }
        with open(DISCOVERY_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def get_log(self, limit: int = 50) -> List[Dict]:
        if not DISCOVERY_LOG.exists():
            return []
        entries = []
        with open(DISCOVERY_LOG, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue
        return entries[-limit:]


__all__ = [
    "DiscoveryStatus",
    "DiscoveryCandidate",
    "DiscoveryQueue",
    "DISCOVERY_ROOT",
    "DISCOVERY_LOG",
]
