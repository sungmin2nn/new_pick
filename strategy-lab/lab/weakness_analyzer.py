"""
Weakness Analyzer (Phase 7.A.2)
================================
부진 전략의 "왜 안됐나"를 구조화하여 자동 분석한다.

5개 분석 축:
    1) loss_pattern      — exit_type 분포, 손절 벽, 승/손 비대칭, 연속 손실
    2) timing_pattern    — 요일/날짜별 승률, 손실 집중일
    3) name_bias         — 반복 선정 종목, 종목별 승률, 다양성
    4) market_context    — peer 전략(같은 매트릭스) 대비 상대 성과
    5) score_correlation — selection.score ↔ 수익률 상관 (스코어링 유효성)

출력:
    WeaknessReport — 축별 수치 + 자연어 가설 리스트
"""

from __future__ import annotations

import json
import statistics as stats
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# ============================================================
# Result dataclasses
# ============================================================

@dataclass
class WeaknessReport:
    strategy_id: str
    strategy_name: str
    period_label: str
    start_date: str
    end_date: str

    loss_pattern: Dict[str, Any] = field(default_factory=dict)
    timing_pattern: Dict[str, Any] = field(default_factory=dict)
    name_bias: Dict[str, Any] = field(default_factory=dict)
    market_context: Dict[str, Any] = field(default_factory=dict)
    score_correlation: Dict[str, Any] = field(default_factory=dict)

    hypotheses: List[str] = field(default_factory=list)
    severity_notes: List[str] = field(default_factory=list)

    analyzed_at: str = ""

    def __post_init__(self):
        if not self.analyzed_at:
            self.analyzed_at = datetime.now().isoformat(timespec="seconds")

    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================
# Analyzer
# ============================================================

class WeaknessAnalyzer:
    """matrix cell(전략 × 기간)을 받아 약점 구조 리포트를 생성."""

    # 손절 벽 감지: 같은 손실 pct에 몰린 거래 비율
    STOP_WALL_THRESHOLD = 0.5          # 50% 이상이 동일 pct면 손절 벽
    STOP_WALL_BUCKET_PCT = 0.3         # 0.3%p 간격 버킷

    # 다양성: 고유 종목 / 총 거래
    LOW_DIVERSITY_THRESHOLD = 0.5

    def analyze(
        self,
        cell: Dict,
        peer_cells: Optional[List[Dict]] = None,
    ) -> WeaknessReport:
        """
        Args:
            cell: matrix 결과 1개 (strategy_id, metrics, history 포함)
            peer_cells: 같은 기간 다른 전략들 (market_context 비교용)
        """
        report = WeaknessReport(
            strategy_id=cell.get("strategy_id", "unknown"),
            strategy_name=cell.get("strategy_name", ""),
            period_label=cell.get("period_label", ""),
            start_date=cell.get("start_date", ""),
            end_date=cell.get("end_date", ""),
        )

        history = cell.get("history") or []
        trades = self._flatten_trades(history)

        if not trades:
            report.severity_notes.append(
                "거래 이력이 없어 상세 분석 불가 — 시그널 조건 재설계 필요"
            )
            report.hypotheses.append(
                "진입 조건이 너무 엄격하거나 데이터 의존성이 실패했을 가능성"
            )
            return report

        report.loss_pattern = self._analyze_loss_pattern(trades)
        report.timing_pattern = self._analyze_timing(history)
        report.name_bias = self._analyze_name_bias(trades)
        report.score_correlation = self._analyze_score_correlation(trades)

        if peer_cells:
            report.market_context = self._analyze_market_context(
                cell, peer_cells
            )

        report.hypotheses = self._generate_hypotheses(report, cell, trades)
        return report

    # --------------------------------------------------------
    # Helpers
    # --------------------------------------------------------

    def _flatten_trades(self, history: List[Dict]) -> List[Dict]:
        out = []
        for day in history:
            for t in day.get("trade_details", []) or []:
                t = dict(t)
                t["_date"] = day.get("date", "")
                out.append(t)
        return out

    def _analyze_loss_pattern(self, trades: List[Dict]) -> Dict[str, Any]:
        losses = [t for t in trades if (t.get("return_pct") or 0) < 0]
        wins = [t for t in trades if (t.get("return_pct") or 0) > 0]

        # exit_type 분포
        exit_types = Counter(t.get("exit_type", "unknown") for t in trades)

        # 손절 벽: 손실 trade들을 0.3%p 버킷으로 묶어서 가장 큰 버킷 비율
        stop_wall_detected = False
        stop_wall_level: Optional[float] = None
        stop_wall_ratio = 0.0
        if losses:
            buckets: Counter = Counter()
            for t in losses:
                bucket = round(t["return_pct"] / self.STOP_WALL_BUCKET_PCT) * self.STOP_WALL_BUCKET_PCT
                buckets[round(bucket, 2)] += 1
            top_bucket, top_count = buckets.most_common(1)[0]
            stop_wall_ratio = top_count / len(losses)
            if stop_wall_ratio >= self.STOP_WALL_THRESHOLD:
                stop_wall_detected = True
                stop_wall_level = top_bucket

        # 연속 손실 스트릭
        streak = 0
        max_streak = 0
        for t in trades:
            if (t.get("return_pct") or 0) < 0:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0

        avg_win = stats.mean(t["return_pct"] for t in wins) if wins else 0.0
        avg_loss = stats.mean(t["return_pct"] for t in losses) if losses else 0.0

        return {
            "total_trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "loss_ratio": round(len(losses) / len(trades), 3) if trades else 0,
            "exit_type_distribution": dict(exit_types),
            "avg_win_pct": round(avg_win, 2),
            "avg_loss_pct": round(avg_loss, 2),
            "asymmetry": round(
                abs(avg_loss) / avg_win if avg_win > 0 else 0, 2
            ),
            "max_consecutive_losses": max_streak,
            "stop_wall_detected": stop_wall_detected,
            "stop_wall_level_pct": stop_wall_level,
            "stop_wall_ratio": round(stop_wall_ratio, 3),
        }

    def _analyze_timing(self, history: List[Dict]) -> Dict[str, Any]:
        if not history:
            return {}

        daily_returns = [
            {"date": h.get("date", ""), "return_pct": h.get("daily_return_pct") or 0}
            for h in history
        ]

        losing_days = [d for d in daily_returns if d["return_pct"] < 0]
        winning_days = [d for d in daily_returns if d["return_pct"] > 0]

        # 요일 분석 (날짜가 YYYYMMDD 형식)
        weekday_stats: Dict[int, Dict[str, float]] = defaultdict(
            lambda: {"count": 0, "sum_return": 0.0}
        )
        for d in daily_returns:
            try:
                dt = datetime.strptime(d["date"], "%Y%m%d")
                wd = dt.weekday()
                weekday_stats[wd]["count"] += 1
                weekday_stats[wd]["sum_return"] += d["return_pct"]
            except (ValueError, TypeError):
                continue

        weekday_avg = {
            wd: round(s["sum_return"] / s["count"], 2) if s["count"] else 0.0
            for wd, s in weekday_stats.items()
        }

        return {
            "total_days": len(daily_returns),
            "winning_days": len(winning_days),
            "losing_days": len(losing_days),
            "worst_day": min(daily_returns, key=lambda x: x["return_pct"])
            if daily_returns else None,
            "best_day": max(daily_returns, key=lambda x: x["return_pct"])
            if daily_returns else None,
            "weekday_avg_return_pct": weekday_avg,
            "loss_concentration": round(
                len(losing_days) / len(daily_returns), 3
            )
            if daily_returns else 0,
        }

    def _analyze_name_bias(self, trades: List[Dict]) -> Dict[str, Any]:
        name_counter = Counter(t.get("name", "") for t in trades)
        name_returns: Dict[str, List[float]] = defaultdict(list)
        for t in trades:
            name_returns[t.get("name", "")].append(t.get("return_pct") or 0)

        unique = len(name_counter)
        diversity = unique / len(trades) if trades else 0

        # 상위 5개 빈도 종목 + 해당 종목 평균 수익률
        top_names = []
        for name, cnt in name_counter.most_common(5):
            avg_ret = stats.mean(name_returns[name])
            wins = sum(1 for r in name_returns[name] if r > 0)
            top_names.append({
                "name": name,
                "count": cnt,
                "avg_return_pct": round(avg_ret, 2),
                "win_rate": round(wins / cnt, 2) if cnt else 0,
            })

        return {
            "unique_names": unique,
            "total_trades": len(trades),
            "diversity_ratio": round(diversity, 3),
            "top_repeated": top_names,
            "low_diversity": diversity < self.LOW_DIVERSITY_THRESHOLD,
        }

    def _analyze_score_correlation(self, trades: List[Dict]) -> Dict[str, Any]:
        """selection.score와 return_pct의 상관관계."""
        pairs = []
        for t in trades:
            sel = t.get("selection") or {}
            score = sel.get("score")
            ret = t.get("return_pct")
            if score is not None and ret is not None:
                pairs.append((float(score), float(ret)))

        if len(pairs) < 3:
            return {"available": False, "reason": "score 데이터 부족"}

        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        n = len(pairs)

        # Pearson correlation
        mx, my = stats.mean(xs), stats.mean(ys)
        num = sum((x - mx) * (y - my) for x, y in pairs)
        dx = sum((x - mx) ** 2 for x in xs) ** 0.5
        dy = sum((y - my) ** 2 for y in ys) ** 0.5
        corr = num / (dx * dy) if dx > 0 and dy > 0 else 0.0

        # 상위/하위 스코어 그룹 평균 수익 비교
        sorted_pairs = sorted(pairs, key=lambda p: p[0], reverse=True)
        top_half = sorted_pairs[: n // 2]
        bot_half = sorted_pairs[n // 2:]
        top_avg = stats.mean(p[1] for p in top_half) if top_half else 0
        bot_avg = stats.mean(p[1] for p in bot_half) if bot_half else 0

        return {
            "available": True,
            "n": n,
            "pearson_corr": round(corr, 3),
            "top_half_avg_return": round(top_avg, 2),
            "bottom_half_avg_return": round(bot_avg, 2),
            "scoring_effective": corr > 0.2 and top_avg > bot_avg,
        }

    def _analyze_market_context(
        self, cell: Dict, peer_cells: List[Dict]
    ) -> Dict[str, Any]:
        """같은 기간 peer 전략들 대비 상대 성과."""
        own_return = (cell.get("metrics") or {}).get("total_return_pct", 0)
        peer_returns = [
            (c.get("metrics") or {}).get("total_return_pct", 0)
            for c in peer_cells
            if c.get("strategy_id") != cell.get("strategy_id")
            and c.get("status") == "completed"
            and ((c.get("metrics") or {}).get("num_trades") or 0) > 0
        ]

        if not peer_returns:
            return {"available": False}

        peer_avg = stats.mean(peer_returns)
        peer_median = stats.median(peer_returns)
        rank = sum(1 for r in peer_returns if r > own_return) + 1

        return {
            "available": True,
            "own_return_pct": round(own_return, 2),
            "peer_count": len(peer_returns),
            "peer_avg_return_pct": round(peer_avg, 2),
            "peer_median_return_pct": round(peer_median, 2),
            "rank_among_peers": f"{rank}/{len(peer_returns) + 1}",
            "relative_gap_pct": round(own_return - peer_avg, 2),
            "underperformed_peers": own_return < peer_avg,
        }

    # --------------------------------------------------------
    # Hypothesis generation (rule-based NL)
    # --------------------------------------------------------

    def _generate_hypotheses(
        self, report: WeaknessReport, cell: Dict, trades: List[Dict]
    ) -> List[str]:
        hs: List[str] = []
        lp = report.loss_pattern
        tm = report.timing_pattern
        nb = report.name_bias
        mc = report.market_context
        sc = report.score_correlation

        # 1) 손절 벽
        if lp.get("stop_wall_detected"):
            lvl = lp.get("stop_wall_level_pct")
            ratio = lp.get("stop_wall_ratio", 0) * 100
            hs.append(
                f"손절 벽 감지: 전체 손실의 {ratio:.0f}%가 {lvl}% 수준에 집중 — "
                f"손절 폭이 너무 타이트해 노이즈에 반복 피격"
            )

        # 2) 승/손 비대칭
        asym = lp.get("asymmetry", 0)
        if asym > 2.0 and lp.get("wins", 0) > 0:
            hs.append(
                f"평균 손실이 평균 수익의 {asym:.1f}배 — 승률로 만회해야 하지만 "
                f"승률 {lp['wins']}/{lp['total_trades']} 부족"
            )

        # 3) 연속 손실
        if lp.get("max_consecutive_losses", 0) >= 5:
            hs.append(
                f"{lp['max_consecutive_losses']}연속 손실 발생 — 시장 체제 변화 대응 "
                f"로직 부재 (regime filter 필요 가능)"
            )

        # 4) 낮은 다양성
        if nb.get("low_diversity"):
            hs.append(
                f"종목 다양성 낮음 ({nb['unique_names']}/{nb['total_trades']} 고유) — "
                f"소수 종목에 쏠려 종목 리스크 집중"
            )

        # 5) 스코어링 무효
        if sc.get("available") and not sc.get("scoring_effective"):
            corr = sc.get("pearson_corr", 0)
            hs.append(
                f"selection score와 수익률 상관 {corr:+.2f} — 선정 로직이 "
                f"실제 성과를 예측하지 못함 (스코어 공식 재설계 필요)"
            )
        elif sc.get("available") and sc.get("scoring_effective"):
            hs.append(
                f"스코어링은 유효 (corr={sc['pearson_corr']:+.2f}, "
                f"상위50% 평균 {sc['top_half_avg_return']:+.2f}% vs "
                f"하위50% {sc['bottom_half_avg_return']:+.2f}%) — "
                f"상위 N개만 선별 강화 여지"
            )

        # 6) 시장 대비 열위
        if mc.get("available"):
            if mc.get("underperformed_peers"):
                gap = mc.get("relative_gap_pct", 0)
                hs.append(
                    f"peer 평균 대비 {gap:+.2f}%p 열위 ({mc['rank_among_peers']}) — "
                    f"같은 기간 다른 전략은 작동 → 본 전략 고유 문제"
                )
            else:
                hs.append(
                    f"peer 평균보다 우위 ({mc['relative_gap_pct']:+.2f}%p) — "
                    f"시장 환경이 전략에 불리했을 가능성"
                )

        # 7) 손실일 집중
        if tm.get("loss_concentration", 0) >= 0.7:
            hs.append(
                f"거래일의 {tm['loss_concentration'] * 100:.0f}%가 손실일 — "
                f"엔트리 타이밍 자체가 시장 방향과 반대"
            )

        # 8) 최악의 날
        worst = tm.get("worst_day")
        if worst and worst.get("return_pct", 0) <= -3.0:
            hs.append(
                f"최악일 {worst['date']} {worst['return_pct']:+.2f}% — "
                f"단일 이벤트 영향 크므로 포지션 사이즈/분산 조정 고려"
            )

        if not hs:
            hs.append("구조적 약점 미발견 — 샘플 기간 확장 필요")

        return hs


# ============================================================
# Loaders & persistence
# ============================================================

def analyze_matrix_file(
    matrix_path: Path,
    underperformer_ids: Optional[List[str]] = None,
) -> List[WeaknessReport]:
    """matrix 결과 파일을 읽어 부진 전략(또는 전체)을 분석."""
    matrix_path = Path(matrix_path)
    data = json.loads(matrix_path.read_text(encoding="utf-8"))
    cells = data.get("cells", [])

    if underperformer_ids:
        target_cells = [c for c in cells if c.get("strategy_id") in underperformer_ids]
    else:
        target_cells = cells

    analyzer = WeaknessAnalyzer()
    reports = []
    for cell in target_cells:
        peer = [c for c in cells if c.get("period_label") == cell.get("period_label")]
        reports.append(analyzer.analyze(cell, peer_cells=peer))
    return reports


def save_weakness_reports(
    reports: List[WeaknessReport], out_dir: Path
) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"weakness_{ts}.json"
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total": len(reports),
        "reports": [r.to_dict() for r in reports],
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out_path


__all__ = [
    "WeaknessReport",
    "WeaknessAnalyzer",
    "analyze_matrix_file",
    "save_weakness_reports",
]
