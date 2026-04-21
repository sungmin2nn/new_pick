"""
Calibration — 분봉 실측 ← 확률적 일봉 보정
===============================================
동일 기간의 Tier 1 (분봉 실측) vs Tier 2 (확률적 일봉) 결과를 비교하여
"분봉 실측 대비 확률적 일봉의 편향"을 보정 계수로 산출.

산출된 보정 계수를 장기 확률적 일봉 결과에 적용 →
"분봉 수준의 현실성"을 장기에도 확장.

사용:
    from lab.realistic_sim.calibrator import Calibrator

    cal = Calibrator()
    cal.load_intraday_matrix("data/results/intraday_matrix_latest.json")
    cal.load_probabilistic_matrix("data/results/probabilistic_matrix_6d.json")
    factors = cal.compute_factors()
    # {strategy_id: {"return_factor": 0.5, "win_rate_factor": 0.8, ...}}

    # 장기 확률적 결과에 적용
    adjusted = cal.apply_to(long_term_result)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Optional


@dataclass
class CalibrationFactor:
    """전략별 보정 계수."""
    strategy_id: str
    return_factor: float = 1.0     # net_return_pct 비율
    win_rate_factor: float = 1.0   # win rate 비율
    sample_size: int = 0           # calibration 표본 크기 (days)
    confidence: float = 0.0        # 샘플 크기 기반 신뢰도
    intraday_return: float = 0.0
    probabilistic_return: float = 0.0


class Calibrator:
    """
    Intraday Matrix (Tier 1) ← Probabilistic Matrix (Tier 2) 보정.
    """

    def __init__(self):
        self.intraday_data: Optional[dict] = None
        self.probabilistic_data: Optional[dict] = None

    def load_intraday_matrix(self, path: Path) -> None:
        path = Path(path)
        self.intraday_data = json.loads(path.read_text(encoding="utf-8"))

    def load_probabilistic_matrix(self, path: Path) -> None:
        path = Path(path)
        self.probabilistic_data = json.loads(path.read_text(encoding="utf-8"))

    def compute_factors(self) -> Dict[str, CalibrationFactor]:
        """
        전략별 보정 계수 계산.

        factor = Tier1 (분봉 실측) / Tier2 (확률적 일봉)

        예:
          분봉: +16.46% / 확률: +35.25% → factor = 0.467
          즉 확률 결과에 0.467을 곱해야 분봉 수준이 됨.
        """
        if not self.intraday_data or not self.probabilistic_data:
            raise RuntimeError("Both intraday and probabilistic data must be loaded")

        factors: Dict[str, CalibrationFactor] = {}

        # 전략별 매핑
        intraday_by_id = {
            c["strategy_id"]: c
            for c in self.intraday_data.get("cells", [])
            if c.get("status") == "completed"
        }
        probabilistic_by_id = {
            c.get("strategy_id", ""): c
            for c in self.probabilistic_data.get("cells", [])
            if c.get("status") == "completed"
        }

        for sid, intraday_cell in intraday_by_id.items():
            prob_cell = probabilistic_by_id.get(sid)
            if not prob_cell:
                continue

            intraday_return = intraday_cell.get("net_return_pct", 0) or 0
            prob_return = prob_cell.get("metrics", {}).get("total_return_pct", 0) or 0

            # 분모가 0이거나 부호가 다르면 factor = 1 (보정 불가)
            if abs(prob_return) < 0.01:
                return_factor = 1.0
            elif (intraday_return > 0) != (prob_return > 0):
                return_factor = 0.0   # 방향이 반대면 신뢰 불가
            else:
                return_factor = round(intraday_return / prob_return, 4)

            # win rate factor
            intraday_wr = intraday_cell.get("win_rate", 0) or 0
            prob_wr = prob_cell.get("metrics", {}).get("win_rate", 0) or 0
            if prob_wr > 0:
                wr_factor = round(intraday_wr / prob_wr, 4)
            else:
                wr_factor = 1.0

            # confidence: sample size 기반 (6일 = 1.0 기준)
            sample_days = intraday_cell.get("trading_days", 1)
            confidence = min(sample_days / 6.0, 1.0)

            factors[sid] = CalibrationFactor(
                strategy_id=sid,
                return_factor=return_factor,
                win_rate_factor=wr_factor,
                sample_size=sample_days,
                confidence=round(confidence, 2),
                intraday_return=round(intraday_return, 4),
                probabilistic_return=round(prob_return, 4),
            )

        return factors

    def apply_to(
        self,
        probabilistic_result: dict,
        factors: Dict[str, CalibrationFactor],
    ) -> dict:
        """
        장기 확률적 결과에 보정 적용.

        Args:
            probabilistic_result: Probabilistic 매트릭스 단일 cell
            factors: compute_factors() 결과

        Returns:
            보정된 cell (원본에 calibrated_* 필드 추가)
        """
        sid = probabilistic_result.get("strategy_id", "")
        factor = factors.get(sid)
        if not factor:
            return {
                **probabilistic_result,
                "calibrated_return_pct": probabilistic_result.get("metrics", {}).get("total_return_pct", 0),
                "calibration_applied": False,
                "calibration_note": "no factor found",
            }

        metrics = probabilistic_result.get("metrics", {})
        original_return = metrics.get("total_return_pct", 0) or 0
        original_wr = metrics.get("win_rate", 0) or 0

        calibrated_return = round(original_return * factor.return_factor, 4)
        calibrated_wr = round(original_wr * factor.win_rate_factor, 4)

        return {
            **probabilistic_result,
            "calibrated_return_pct": calibrated_return,
            "calibrated_win_rate": calibrated_wr,
            "calibration_factor_return": factor.return_factor,
            "calibration_factor_win_rate": factor.win_rate_factor,
            "calibration_confidence": factor.confidence,
            "calibration_applied": True,
        }

    def save_factors(
        self,
        factors: Dict[str, CalibrationFactor],
        path: Path,
    ) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            sid: asdict(f)
            for sid, f in factors.items()
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


__all__ = [
    "CalibrationFactor",
    "Calibrator",
]
