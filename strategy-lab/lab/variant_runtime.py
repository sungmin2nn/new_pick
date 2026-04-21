"""
Variant Runtime (Phase 7.A.4)
==============================
VariantSpec을 실제 실행 가능한 전략/backtest 설정으로 변환.

두 종류의 override:
    1) strategy_param_overrides — 전략 클래스 속성을 동적 서브클래스로 오버라이드
    2) exit_rule_overrides      — backtest simulator의 profit/loss target 오버라이드

설계:
    - 원본 클래스 변경 없음 (서브클래스 생성)
    - 주입 가능한 속성만 override (class-level constants / dict)
    - "힌트" 플래그 (ENTRY_RELAXATION_HINT 등)는 실행에 영향 없음 (사용자 검토용)
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple, Type

from lab.parameter_tuner import VariantSpec


# 힌트 플래그 — 실제 실행에 영향 없고 기록만 됨
_HINT_FLAGS = {"ENTRY_RELAXATION_HINT"}


def apply_strategy_overrides(
    base_cls: Type, overrides: Dict[str, Any]
) -> Type:
    """
    base_cls를 상속한 새 클래스를 만들어 class attribute를 override.

    힌트 플래그는 넘겨받지만 실행에 직접 영향 없음 (로깅용).
    딕셔너리 속성 (예: WEIGHTS)은 얕은 병합.
    """
    if not overrides:
        return base_cls

    attrs: Dict[str, Any] = {}
    for key, value in overrides.items():
        if key in _HINT_FLAGS:
            attrs[key] = value
            continue
        existing = getattr(base_cls, key, None)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged = dict(existing)
            merged.update(value)
            attrs[key] = merged
        else:
            attrs[key] = value

    new_cls_name = f"{base_cls.__name__}_Variant"
    return type(new_cls_name, (base_cls,), attrs)


def resolve_exit_rules(
    spec: VariantSpec,
) -> Tuple[Optional[float], Optional[float]]:
    """VariantSpec의 exit_rule_overrides에서 (profit_target, loss_target)."""
    overrides = spec.exit_rule_overrides or {}
    return (
        overrides.get("profit_target"),
        overrides.get("loss_target"),
    )


def describe_variant_effects(spec: VariantSpec) -> Dict[str, Any]:
    """variant가 실제로 어떤 실행 효과를 갖는지 요약."""
    strat = dict(spec.strategy_param_overrides or {})
    runtime_hints = {k: strat.pop(k) for k in list(strat) if k in _HINT_FLAGS}
    return {
        "variant_id": spec.variant_id,
        "real_strategy_overrides": strat,
        "runtime_hints": runtime_hints,
        "exit_rule_overrides": spec.exit_rule_overrides or {},
        "is_noop": not (strat or spec.exit_rule_overrides),
    }


__all__ = [
    "apply_strategy_overrides",
    "resolve_exit_rules",
    "describe_variant_effects",
]
