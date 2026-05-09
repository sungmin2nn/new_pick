"""
임마누엘 스퀴즈 플레이 — Paper Trading Shadow 4주 운영 패키지.

DEC-005, plan P3-3 (.claude/context/plans/squeeze-play-shadow-4w.md).

🚨 SHADOW_DRY_RUN — 본 패키지는 **실주문 절대 불가**.
    데이터 기록만 수행. 실주문 모듈 import 시 assert 실패.

스키마: schema.md
Writer: logger.ShadowLogger
"""

from __future__ import annotations

# 운영 가드 — P3-3 플랜 §5.1 안전장치
SHADOW_DRY_RUN: bool = True

if not SHADOW_DRY_RUN:
    raise RuntimeError(
        "SHADOW_DRY_RUN must be True. paper_trading.shadow는 실주문을 수행하지 않습니다. "
        "값을 변경한 운영 변경은 plan P3-3 / DEC-005 위반."
    )

from .logger import ShadowLogger, ShadowLogError, VARIANT_WHITELIST

__all__ = ["ShadowLogger", "ShadowLogError", "VARIANT_WHITELIST", "SHADOW_DRY_RUN"]
