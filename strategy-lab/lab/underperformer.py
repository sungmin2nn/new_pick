"""
Underperformer Identification (Phase 7.A.1)
============================================
백테스트 결과에서 "개선이 필요한" 전략을 자동 식별한다.

`promotion.py`의 REJECTED가 "탈락 (아이디어 폐기)" 판정이라면,
여기서의 UNDERPERFORMER는 "살릴 가치는 있지만 개선이 필요한" 중간 지대.
Phase 7의 약점 분석 → 파라미터 튜닝 → v0.2 생성 루프의 입력이 된다.

식별 기준 (3축):
    1) 수익률 (return) — total_return_pct < low_return_pct
    2) 낙폭 (drawdown) — max_drawdown_pct < deep_drawdown_pct (더 나쁨)
    3) 일관성 (consistency) — win_rate / profit_factor / sharpe 저조

특수 상태:
    - INACTIVE: num_trades == 0 (판정 불가 — 시그널이 안 나오는 전략)
    - MULTI_PERIOD_FAIL: 여러 기간에서 일관되게 부진

설계 원칙:
    - 임계값은 UnderperformerCriteria로 override 가능
    - REJECTED (탈락)와 별도 개념 — REJECTED도 살릴 가치 있으면 부진 후보로 묶음
    - 결과는 순수 dataclass (side effect 없음)
    - 저장/리포트 유틸은 별도 함수
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Optional


# ============================================================
# Enums
# ============================================================

class UnderperformerFlag(str, Enum):
    LOW_RETURN = "low_return"
    DEEP_DRAWDOWN = "deep_drawdown"
    LOW_WIN_RATE = "low_win_rate"
    LOW_PROFIT_FACTOR = "low_profit_factor"
    LOW_SHARPE = "low_sharpe"
    INACTIVE = "inactive"                      # num_trades == 0
    MULTI_PERIOD_FAIL = "multi_period_fail"    # 여러 기간 누적 판정


class Severity(str, Enum):
    NONE = "none"           # 부진 아님
    MILD = "mild"            # 1축 미달
    MODERATE = "moderate"    # 2축 미달
    SEVERE = "severe"        # 3축 모두 미달 / 음수 수익 + 깊은 낙폭
    INACTIVE = "inactive"    # 거래 없음 (개선보다는 진입 조건 재설계 필요)


# ============================================================
# Criteria
# ============================================================

@dataclass
class UnderperformerCriteria:
    """부진 판정 임계값. 모든 값은 override 가능."""

    # 1축: 수익률
    low_return_pct: float = 3.0           # 이 미만이면 LOW_RETURN

    # 2축: 낙폭
    deep_drawdown_pct: float = -10.0      # 이보다 더 나쁜 MDD면 DEEP_DRAWDOWN

    # 3축: 일관성 (3개 메트릭 중 하나라도 걸리면 "일관성 미달")
    low_win_rate: float = 0.45
    low_profit_factor: float = 1.2
    low_sharpe: float = 0.5
    max_sharpe_sanity: float = 15.0       # Sharpe > 15는 과대평가 (clipped)

    # 특수 조건
    inactive_if_no_trades: bool = True

    # 멀티-기간 집계
    multi_period_min_periods: int = 2     # 이 이상 기간 데이터가 있을 때만
    multi_period_fail_ratio: float = 0.5  # 50% 이상 기간에서 부진이면 MULTI_PERIOD_FAIL

    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================
# Result
# ============================================================

@dataclass
class UnderperformerReport:
    """단일 (전략, 기간) 부진 판정 결과."""
    strategy_id: str
    strategy_name: str
    period_label: str
    start_date: str
    end_date: str

    is_underperformer: bool = False
    severity: str = Severity.NONE.value
    flags: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

    # 주요 메트릭 요약 (약점 분석 단계로 전달)
    total_return_pct: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    max_drawdown_pct: float = 0.0
    num_trades: int = 0
    profit_factor: float = 0.0
    trading_days: int = 0

    # 약점 스코어 0~100 (높을수록 심각)
    weakness_score: float = 0.0
    evaluated_at: str = ""
    criteria_snapshot: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.evaluated_at:
            self.evaluated_at = datetime.now().isoformat(timespec="seconds")

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> str:
        icon = {
            Severity.NONE.value: "✅",
            Severity.MILD.value: "🟡",
            Severity.MODERATE.value: "🟠",
            Severity.SEVERE.value: "🔴",
            Severity.INACTIVE.value: "💤",
        }.get(self.severity, "❓")
        flag_str = ",".join(self.flags) if self.flags else "-"
        return (
            f"{icon} [{self.severity}] {self.strategy_id} ({self.period_label}) "
            f"return={self.total_return_pct:+.2f}% "
            f"MDD={self.max_drawdown_pct:.2f}% "
            f"WR={self.win_rate * 100:.0f}% "
            f"trades={self.num_trades} "
            f"flags=[{flag_str}] "
            f"weakness={self.weakness_score:.1f}"
        )


@dataclass
class MultiPeriodReport:
    """한 전략에 대한 기간 전반의 집계 판정."""
    strategy_id: str
    strategy_name: str
    total_periods: int
    underperform_periods: int
    inactive_periods: int
    multi_period_fail: bool
    avg_weakness_score: float
    worst_severity: str
    per_period: List[UnderperformerReport] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            **{k: v for k, v in asdict(self).items() if k != "per_period"},
            "per_period": [r.to_dict() for r in self.per_period],
        }


# ============================================================
# Detector
# ============================================================

class UnderperformerDetector:
    """리더보드 row(들)를 받아 부진 여부를 판정."""

    def __init__(self, criteria: Optional[UnderperformerCriteria] = None):
        self.criteria = criteria or UnderperformerCriteria()

    def detect(self, row: Dict) -> UnderperformerReport:
        """단일 row 판정 (leaderboard 항목 1개)."""
        c = self.criteria

        report = UnderperformerReport(
            strategy_id=row.get("strategy_id", "unknown"),
            strategy_name=row.get("strategy_name", ""),
            period_label=row.get("period") or row.get("period_label", ""),
            start_date=row.get("start_date", ""),
            end_date=row.get("end_date", ""),
            total_return_pct=float(row.get("total_return_pct") or 0),
            sharpe_ratio=float(row.get("sharpe_ratio") or 0),
            win_rate=float(row.get("win_rate") or 0),
            max_drawdown_pct=float(row.get("max_drawdown_pct") or 0),
            num_trades=int(row.get("num_trades") or 0),
            profit_factor=float(row.get("profit_factor") or 0),
            trading_days=int(row.get("trading_days") or 0),
            criteria_snapshot=c.to_dict(),
        )

        # INACTIVE: 거래 없음 — 개선 루프의 "진입 조건 재설계" 대상
        if c.inactive_if_no_trades and report.num_trades == 0:
            report.is_underperformer = True
            report.severity = Severity.INACTIVE.value
            report.flags = [UnderperformerFlag.INACTIVE.value]
            report.reasons = ["거래 없음 — 시그널 조건이 너무 엄격하거나 데이터 의존 실패"]
            report.weakness_score = 50.0  # 중간값 (개선 필요도 중간)
            return report

        flags: List[str] = []
        reasons: List[str] = []

        # 1축: 수익률
        if report.total_return_pct < c.low_return_pct:
            flags.append(UnderperformerFlag.LOW_RETURN.value)
            reasons.append(
                f"수익률 {report.total_return_pct:+.2f}% < 기준 {c.low_return_pct:.1f}%"
            )

        # 2축: 낙폭
        if report.max_drawdown_pct < c.deep_drawdown_pct:
            flags.append(UnderperformerFlag.DEEP_DRAWDOWN.value)
            reasons.append(
                f"MDD {report.max_drawdown_pct:.2f}% < 기준 {c.deep_drawdown_pct:.1f}%"
            )

        # 3축: 일관성 — 3개 서브 메트릭
        consistency_hits = 0
        if report.win_rate > 0 and report.win_rate < c.low_win_rate:
            flags.append(UnderperformerFlag.LOW_WIN_RATE.value)
            reasons.append(
                f"승률 {report.win_rate * 100:.1f}% < 기준 {c.low_win_rate * 100:.0f}%"
            )
            consistency_hits += 1

        if report.profit_factor > 0 and report.profit_factor < c.low_profit_factor:
            flags.append(UnderperformerFlag.LOW_PROFIT_FACTOR.value)
            reasons.append(
                f"PF {report.profit_factor:.2f} < 기준 {c.low_profit_factor:.2f}"
            )
            consistency_hits += 1

        sharpe_clipped = min(report.sharpe_ratio, c.max_sharpe_sanity)
        if sharpe_clipped < c.low_sharpe:
            flags.append(UnderperformerFlag.LOW_SHARPE.value)
            reasons.append(
                f"Sharpe {report.sharpe_ratio:.2f} < 기준 {c.low_sharpe:.2f}"
            )
            consistency_hits += 1

        # 축 카운트 (수익률/낙폭/일관성 3개 중 몇 개 미달?)
        axes_failed = 0
        if UnderperformerFlag.LOW_RETURN.value in flags:
            axes_failed += 1
        if UnderperformerFlag.DEEP_DRAWDOWN.value in flags:
            axes_failed += 1
        if consistency_hits > 0:
            axes_failed += 1

        if axes_failed == 0:
            report.severity = Severity.NONE.value
            report.is_underperformer = False
        else:
            report.is_underperformer = True
            if axes_failed == 1:
                report.severity = Severity.MILD.value
            elif axes_failed == 2:
                report.severity = Severity.MODERATE.value
            else:  # 3
                report.severity = Severity.SEVERE.value

        report.flags = flags
        report.reasons = reasons
        report.weakness_score = self._weakness_score(report)
        return report

    def detect_batch(self, rows: Iterable[Dict]) -> List[UnderperformerReport]:
        return [self.detect(r) for r in rows]

    def aggregate_multi_period(
        self, reports: List[UnderperformerReport]
    ) -> List[MultiPeriodReport]:
        """전략 단위로 기간 전반의 판정을 집계."""
        c = self.criteria
        by_strategy: Dict[str, List[UnderperformerReport]] = {}
        for r in reports:
            by_strategy.setdefault(r.strategy_id, []).append(r)

        severity_order = {
            Severity.NONE.value: 0,
            Severity.MILD.value: 1,
            Severity.MODERATE.value: 2,
            Severity.SEVERE.value: 3,
            Severity.INACTIVE.value: 2,  # INACTIVE는 MODERATE 수준 긴급도
        }

        out: List[MultiPeriodReport] = []
        for sid, rs in by_strategy.items():
            total = len(rs)
            under = sum(1 for r in rs if r.is_underperformer and r.severity != Severity.INACTIVE.value)
            inactive = sum(1 for r in rs if r.severity == Severity.INACTIVE.value)
            avg_score = sum(r.weakness_score for r in rs) / total if total else 0.0
            worst = max(rs, key=lambda r: severity_order.get(r.severity, 0))

            multi_fail = False
            if total >= c.multi_period_min_periods:
                fail_ratio = (under + inactive) / total
                if fail_ratio >= c.multi_period_fail_ratio:
                    multi_fail = True

            out.append(
                MultiPeriodReport(
                    strategy_id=sid,
                    strategy_name=rs[0].strategy_name,
                    total_periods=total,
                    underperform_periods=under,
                    inactive_periods=inactive,
                    multi_period_fail=multi_fail,
                    avg_weakness_score=round(avg_score, 2),
                    worst_severity=worst.severity,
                    per_period=rs,
                )
            )

        # 약점 점수 내림차순 (가장 개선이 시급한 순)
        out.sort(key=lambda m: m.avg_weakness_score, reverse=True)
        return out

    def _weakness_score(self, r: UnderperformerReport) -> float:
        """
        0~100. 높을수록 "개선 시급".
        - 수익률 부족도 (35점) : low_return_pct 대비 얼마나 낮은가
        - MDD 과대 (25점)     : deep_drawdown_pct 대비 얼마나 더 나쁜가
        - 승률 부족 (15점)
        - PF 부족 (15점)
        - Sharpe 부족 (10점)
        """
        c = self.criteria

        # 수익률: 기준 대비 gap (음수 수익도 벌점)
        return_gap = max(c.low_return_pct - r.total_return_pct, 0)
        return_score = min(return_gap / max(c.low_return_pct + 10, 1), 1) * 35

        # MDD: 기준 대비 추가 낙폭 (0% 넘을수록 심각)
        mdd_excess = max(c.deep_drawdown_pct - r.max_drawdown_pct, 0)
        mdd_score = min(mdd_excess / 15.0, 1) * 25

        # 승률
        wr_gap = max(c.low_win_rate - r.win_rate, 0) if r.win_rate > 0 else c.low_win_rate
        wr_score = min(wr_gap / c.low_win_rate, 1) * 15 if r.num_trades > 0 else 0

        # PF
        pf_gap = max(c.low_profit_factor - r.profit_factor, 0) if r.profit_factor > 0 else c.low_profit_factor
        pf_score = min(pf_gap / c.low_profit_factor, 1) * 15 if r.num_trades > 0 else 0

        # Sharpe
        sharpe_clipped = min(r.sharpe_ratio, c.max_sharpe_sanity)
        sharpe_gap = max(c.low_sharpe - sharpe_clipped, 0)
        sharpe_score = min(sharpe_gap / c.low_sharpe, 1) * 10 if r.num_trades > 0 else 0

        return round(return_score + mdd_score + wr_score + pf_score + sharpe_score, 1)


# ============================================================
# Loaders & persistence
# ============================================================

def _parse_leaderboard_js(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < 0:
        raise ValueError(f"leaderboard_data.js 형식 오류: {path}")
    return json.loads(raw[start:end + 1])


def detect_from_leaderboard_file(
    leaderboard_js_path: Path,
    criteria: Optional[UnderperformerCriteria] = None,
    period: Optional[str] = None,
) -> List[UnderperformerReport]:
    """`leaderboard_data.js`를 파싱하여 부진 판정."""
    leaderboard_js_path = Path(leaderboard_js_path)
    if not leaderboard_js_path.exists():
        raise FileNotFoundError(f"리더보드 파일 없음: {leaderboard_js_path}")

    data = _parse_leaderboard_js(leaderboard_js_path)
    rows: List[Dict] = []
    for period_key, period_rows in data.get("leaderboards", {}).items():
        if period and period_key != period:
            continue
        rows.extend(period_rows)

    detector = UnderperformerDetector(criteria)
    return detector.detect_batch(rows)


def save_report(
    reports: List[UnderperformerReport],
    multi: List[MultiPeriodReport],
    out_dir: Path,
    criteria: UnderperformerCriteria,
) -> Path:
    """부진 판정 결과를 JSON으로 저장."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"underperformers_{ts}.json"

    summary = {
        "total": len(reports),
        "underperformers": sum(1 for r in reports if r.is_underperformer),
        "by_severity": {},
    }
    for r in reports:
        summary["by_severity"][r.severity] = summary["by_severity"].get(r.severity, 0) + 1

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "criteria": criteria.to_dict(),
        "summary": summary,
        "multi_period_fails": [m.strategy_id for m in multi if m.multi_period_fail],
        "per_strategy": [m.to_dict() for m in multi],
        "reports": [r.to_dict() for r in reports],
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out_path


__all__ = [
    "UnderperformerFlag",
    "Severity",
    "UnderperformerCriteria",
    "UnderperformerReport",
    "MultiPeriodReport",
    "UnderperformerDetector",
    "detect_from_leaderboard_file",
    "save_report",
]
