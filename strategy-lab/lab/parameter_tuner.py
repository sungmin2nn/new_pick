"""
Parameter Tuner (Phase 7.A.3)
==============================
약점 분석(WeaknessReport)을 입력으로 받아, 개선안이 적용된 v0.2
전략 스펙(VariantSpec)을 자동 생성한다.

접근:
    - 전체 grid search는 비용·노이즈 모두 과함.
    - 각 약점 가설을 "개선 rule"로 매핑 → 소수 variant만 생성.
    - 런타임 적용/비교는 7.A.4에서 담당.

두 개의 파라미터 namespace:
    1) strategy_params  — 전략 클래스 속성 (LOSS_THRESHOLD, WEIGHTS 등)
    2) exit_rules       — backtest simulator의 PROFIT_TARGET / LOSS_TARGET 오버라이드

출력:
    VariantSpec — 부모 전략 + 오버라이드 + 어떤 가설을 고치려는지 기록
    data/variants/{parent_id}_v0.2_{ts}.json 로 영속화
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# ============================================================
# Data classes
# ============================================================

@dataclass
class VariantSpec:
    """v0.2 이상의 개선 변형 명세."""
    variant_id: str                     # e.g. eod_reversal_korean_v0.2_a
    parent_strategy_id: str
    version: str                        # "0.2.0", "0.2.1", ...
    label: str                          # 사람 읽기용 짧은 설명
    strategy_param_overrides: Dict[str, Any] = field(default_factory=dict)
    exit_rule_overrides: Dict[str, float] = field(default_factory=dict)
    addresses_hypotheses: List[str] = field(default_factory=list)
    tuning_rationale: str = ""
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat(timespec="seconds")

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> str:
        overrides = []
        for k, v in self.exit_rule_overrides.items():
            overrides.append(f"{k}={v}")
        for k, v in self.strategy_param_overrides.items():
            overrides.append(f"{k}={v}")
        return f"[{self.variant_id}] {self.label} ({', '.join(overrides) or 'no-op'})"


# ============================================================
# Tuning rules
# ============================================================

@dataclass
class TuningRule:
    """약점 가설 → 파라미터 변경 매핑."""
    rule_id: str
    # 가설 탐지 함수 (loss_pattern/timing/... dict를 받아 bool 반환)
    detect: callable
    # 변경 후보 생성 함수 (weakness_report dict → List[VariantSpec 부분 dict])
    build_candidates: callable
    description: str = ""


# ============================================================
# Detectors (가설 매칭)
# ============================================================

def _has_stop_wall(wr: Dict) -> bool:
    return bool(wr.get("loss_pattern", {}).get("stop_wall_detected"))


def _has_asymmetry(wr: Dict) -> bool:
    return (wr.get("loss_pattern", {}).get("asymmetry", 0) or 0) >= 2.0


def _has_consecutive_losses(wr: Dict) -> bool:
    return (wr.get("loss_pattern", {}).get("max_consecutive_losses", 0) or 0) >= 5


def _has_low_diversity(wr: Dict) -> bool:
    return bool(wr.get("name_bias", {}).get("low_diversity"))


def _has_broken_scoring(wr: Dict) -> bool:
    sc = wr.get("score_correlation", {}) or {}
    return sc.get("available") and not sc.get("scoring_effective")


def _has_loss_day_concentration(wr: Dict) -> bool:
    return (wr.get("timing_pattern", {}).get("loss_concentration", 0) or 0) >= 0.7


# ============================================================
# Candidate builders
# ============================================================

def _build_stop_wall_variants(wr: Dict, parent_id: str) -> List[Dict]:
    """손절 벽 → LOSS_TARGET 완화 (backtest 레벨)."""
    lp = wr.get("loss_pattern", {})
    level = lp.get("stop_wall_level_pct", -3.0) or -3.0
    ratio = (lp.get("stop_wall_ratio", 0) or 0) * 100

    variants = []
    # 3단계: 소폭(-5), 중폭(-7), 대폭(-10)
    for loss_target in (-5.0, -7.0, -10.0):
        variants.append({
            "label": f"손절 {level}% → {loss_target}%",
            "exit_rule_overrides": {"loss_target": loss_target},
            "addresses_hypotheses": [
                f"손절 벽 {ratio:.0f}% at {level}% — 손절 폭 완화"
            ],
            "tuning_rationale": (
                f"손실 거래의 {ratio:.0f}%가 {level}%에 집중됨. "
                f"손절 폭을 {loss_target}%로 완화하여 "
                f"노이즈성 피격을 줄이고 reversal 시간을 허용."
            ),
        })
    return variants


def _build_asymmetry_variants(wr: Dict, parent_id: str) -> List[Dict]:
    """승/손 비대칭 → PROFIT_TARGET 상향."""
    lp = wr.get("loss_pattern", {})
    asym = lp.get("asymmetry", 0) or 0
    avg_win = lp.get("avg_win_pct", 0) or 0
    avg_loss = abs(lp.get("avg_loss_pct", 0) or 0)

    variants = []
    for profit_target in (7.0, 10.0):
        variants.append({
            "label": f"익절 상향 → +{profit_target}%",
            "exit_rule_overrides": {"profit_target": profit_target},
            "addresses_hypotheses": [
                f"승/손 비대칭 {asym:.1f}x (avg_win {avg_win}% vs avg_loss {avg_loss}%) — 익절 상향"
            ],
            "tuning_rationale": (
                f"현재 평균 손실이 평균 수익의 {asym:.1f}배. "
                f"익절을 +{profit_target}%로 상향하여 비대칭 해소 및 "
                f"승자가 더 뛸 시간 확보."
            ),
        })
    return variants


def _build_combined_stop_wall_and_asymmetry(wr: Dict, parent_id: str) -> List[Dict]:
    """손절 벽 + 비대칭 동시 해결 — 1개만 생성."""
    if not (_has_stop_wall(wr) and _has_asymmetry(wr)):
        return []

    return [{
        "label": "손절 -7% + 익절 +10% (복합 완화)",
        "exit_rule_overrides": {"loss_target": -7.0, "profit_target": 10.0},
        "addresses_hypotheses": [
            "손절 벽 + 승/손 비대칭 동시 해결 — 진폭 확장",
        ],
        "tuning_rationale": (
            "손절 벽과 비대칭이 함께 관찰되면 진폭 자체가 좁음. "
            "손절 -7% + 익절 +10%로 넓혀서 reversal 기회 허용 + "
            "승자 수익 극대화."
        ),
    }]


def _build_regime_filter_variant(wr: Dict, parent_id: str) -> List[Dict]:
    """연속 손실 → 간단 regime filter 플래그 추가."""
    streak = wr.get("loss_pattern", {}).get("max_consecutive_losses", 0) or 0
    return [{
        "label": f"regime filter ON (streak={streak})",
        "strategy_param_overrides": {
            "REGIME_FILTER_ENABLED": True,
            "REGIME_COOLDOWN_AFTER_LOSSES": 3,
        },
        "addresses_hypotheses": [
            f"{streak}연속 손실 — 시장 체제 변화 대응 부재",
        ],
        "tuning_rationale": (
            f"{streak}연속 손실은 전략이 불리한 market regime에서도 "
            f"계속 진입했음을 뜻함. 최근 3거래 손실 시 1일 cooldown 적용."
        ),
    }]


def _build_low_diversity_variant(wr: Dict, parent_id: str) -> List[Dict]:
    """저다양성 → max_per_name / 섹터 다양화 파라미터."""
    nb = wr.get("name_bias", {})
    unique = nb.get("unique_names", 0)
    total = nb.get("total_trades", 0)
    return [{
        "label": f"다양성 제약 (unique {unique}/{total})",
        "strategy_param_overrides": {
            "MAX_TRADES_PER_NAME_PER_PERIOD": 1,
        },
        "addresses_hypotheses": [
            f"다양성 {unique}/{total} — 종목 리스크 집중",
        ],
        "tuning_rationale": (
            "소수 종목 반복 진입 → 종목 고유 리스크에 노출. "
            "기간 내 동일 종목 1회 제약으로 분산."
        ),
    }]


def _build_entry_relaxation_variant(wr: Dict, parent_id: str) -> List[Dict]:
    """무거래(시그널 안 나옴) → 조건 완화 힌트."""
    lp = wr.get("loss_pattern", {})
    if lp.get("total_trades", 0) != 0:
        return []
    return [{
        "label": "진입 조건 완화 힌트",
        "strategy_param_overrides": {
            "ENTRY_RELAXATION_HINT": True,
        },
        "addresses_hypotheses": ["시그널 미발생 — 조건 완화 필요"],
        "tuning_rationale": (
            "거래 0건 → 진입 필터가 과도하게 엄격하거나 데이터 의존 실패. "
            "해당 전략의 threshold를 단계적으로 완화해 검증 필요. "
            "이 힌트는 사용자 검토용 플래그 (자동 완화는 보류)."
        ),
    }]


# ============================================================
# Registry
# ============================================================

TUNING_RULES: List[TuningRule] = [
    TuningRule(
        rule_id="stop_wall",
        detect=_has_stop_wall,
        build_candidates=_build_stop_wall_variants,
        description="손절 벽 → LOSS_TARGET 완화 3단계",
    ),
    TuningRule(
        rule_id="asymmetry",
        detect=_has_asymmetry,
        build_candidates=_build_asymmetry_variants,
        description="승/손 비대칭 → PROFIT_TARGET 상향 2단계",
    ),
    TuningRule(
        rule_id="stop_wall_plus_asymmetry",
        detect=lambda wr: _has_stop_wall(wr) and _has_asymmetry(wr),
        build_candidates=_build_combined_stop_wall_and_asymmetry,
        description="손절 벽 + 비대칭 복합 완화",
    ),
    TuningRule(
        rule_id="regime_filter",
        detect=_has_consecutive_losses,
        build_candidates=_build_regime_filter_variant,
        description="연속 손실 → regime filter 플래그",
    ),
    TuningRule(
        rule_id="low_diversity",
        detect=_has_low_diversity,
        build_candidates=_build_low_diversity_variant,
        description="저다양성 → 종목 중복 제약",
    ),
    TuningRule(
        rule_id="entry_relaxation",
        detect=lambda wr: (wr.get("loss_pattern", {}).get("total_trades", 0) or 0) == 0,
        build_candidates=_build_entry_relaxation_variant,
        description="무거래 → 진입 조건 완화 힌트",
    ),
]


# ============================================================
# Tuner
# ============================================================

class ParameterTuner:
    """WeaknessReport → List[VariantSpec] 변환."""

    def __init__(self, max_variants_per_strategy: int = 5):
        self.max_variants = max_variants_per_strategy

    def suggest_variants(
        self, weakness_report: Dict, version_prefix: str = "0.2"
    ) -> List[VariantSpec]:
        """
        Args:
            weakness_report: WeaknessReport.to_dict() 결과
            version_prefix: 생성 버전 prefix (예 "0.2" → 0.2.0, 0.2.1, ...)
        """
        parent_id = weakness_report.get("strategy_id", "unknown")
        all_candidates: List[Dict] = []

        for rule in TUNING_RULES:
            try:
                if rule.detect(weakness_report):
                    cands = rule.build_candidates(weakness_report, parent_id)
                    for c in cands:
                        c["_rule_id"] = rule.rule_id
                    all_candidates.extend(cands)
            except Exception:
                continue

        # 우선순위 정렬: stop_wall_plus_asymmetry > stop_wall > asymmetry > others
        priority = {
            "stop_wall_plus_asymmetry": 0,
            "stop_wall": 1,
            "asymmetry": 2,
            "regime_filter": 3,
            "low_diversity": 4,
            "entry_relaxation": 5,
        }
        all_candidates.sort(key=lambda c: priority.get(c.get("_rule_id", ""), 99))

        # 중복 제거: 동일 override 조합 병합
        seen_keys = set()
        deduped = []
        for c in all_candidates:
            key = (
                frozenset((c.get("strategy_param_overrides") or {}).items()),
                frozenset((c.get("exit_rule_overrides") or {}).items()),
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(c)

        # 상한 적용
        deduped = deduped[: self.max_variants]

        # VariantSpec 빌드
        variants: List[VariantSpec] = []
        for idx, c in enumerate(deduped):
            suffix = chr(ord("a") + idx)
            variants.append(
                VariantSpec(
                    variant_id=f"{parent_id}_v{version_prefix}_{suffix}",
                    parent_strategy_id=parent_id,
                    version=f"{version_prefix}.{idx}",
                    label=c.get("label", f"variant {suffix}"),
                    strategy_param_overrides=c.get("strategy_param_overrides") or {},
                    exit_rule_overrides=c.get("exit_rule_overrides") or {},
                    addresses_hypotheses=c.get("addresses_hypotheses") or [],
                    tuning_rationale=c.get("tuning_rationale", ""),
                )
            )
        return variants


# ============================================================
# Persistence
# ============================================================

def save_variants(variants: List[VariantSpec], out_dir: Path) -> List[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for v in variants:
        path = out_dir / f"{v.variant_id}.json"
        path.write_text(
            json.dumps(v.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        written.append(path)
    return written


def load_variant(path: Path) -> VariantSpec:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return VariantSpec(**data)


def suggest_from_weakness_file(
    weakness_path: Path,
    only_strategy_ids: Optional[List[str]] = None,
    max_variants_per_strategy: int = 5,
) -> Dict[str, List[VariantSpec]]:
    """weakness_report JSON 파일 → 전략별 variants."""
    data = json.loads(Path(weakness_path).read_text(encoding="utf-8"))
    tuner = ParameterTuner(max_variants_per_strategy=max_variants_per_strategy)
    out: Dict[str, List[VariantSpec]] = {}
    for report in data.get("reports", []):
        sid = report.get("strategy_id", "unknown")
        if only_strategy_ids and sid not in only_strategy_ids:
            continue
        variants = tuner.suggest_variants(report)
        if variants:
            out[sid] = variants
    return out


__all__ = [
    "VariantSpec",
    "TuningRule",
    "ParameterTuner",
    "TUNING_RULES",
    "save_variants",
    "load_variant",
    "suggest_from_weakness_file",
]
