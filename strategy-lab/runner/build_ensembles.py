"""
Ensemble Builder CLI (Phase 7.B)
=================================
matrix 결과에서 상위 전략을 선정하고 3가지 방식 앙상블을 빌드한 뒤
별도 JS 트랙으로 저장한다.

사용:
    python runner/build_ensembles.py
    python runner/build_ensembles.py --matrix data/results/matrix_xxx.json
    python runner/build_ensembles.py --top 3 --min-trades 5

출력:
    data/ensembles/ensembles_{ts}.json                — 구조화된 결과
    data/leaderboard_ensembles.js                      — 리더보드 트랙
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lab.ensemble import (  # noqa: E402
    CorrelationAnalyzer,
    EnsembleBuilder,
    EnsembleMethod,
    RankingCriteria,
    StrategyRanker,
    extract_daily_series_from_cell,
)


def _latest_matrix_with_history(results_dir: Path) -> Optional[Path]:
    for path in sorted(results_dir.glob("matrix_*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for c in data.get("cells", []):
                if c.get("history"):
                    return path
        except (json.JSONDecodeError, OSError):
            continue
    return None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="앙상블 전략 빌더")
    p.add_argument("--matrix", type=Path, default=None)
    p.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "data" / "ensembles",
    )
    p.add_argument("--top", type=int, default=5, help="상위 N개 전략 선정")
    p.add_argument("--min-trades", type=int, default=10)
    p.add_argument("--min-return", type=float, default=0.0)
    p.add_argument("--quiet", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    matrix_path = args.matrix or _latest_matrix_with_history(
        REPO_ROOT / "data" / "results"
    )
    if not matrix_path or not matrix_path.exists():
        print("[ERROR] matrix 파일 없음 (history 포함 필요)", file=sys.stderr)
        return 2

    data = json.loads(matrix_path.read_text(encoding="utf-8"))
    cells = data.get("cells", [])

    series_list = []
    for c in cells:
        s = extract_daily_series_from_cell(c)
        if s is not None:
            series_list.append(s)

    if not series_list:
        print("[ERROR] 추출 가능한 시계열 없음", file=sys.stderr)
        return 2

    print(f"Matrix: {matrix_path.name}")
    print(f"전략 시계열 {len(series_list)}개 추출")

    # 1) 상위 N 선정
    ranker = StrategyRanker(
        RankingCriteria(
            min_trades=args.min_trades,
            min_return_pct=args.min_return,
        )
    )
    top = ranker.select_top(series_list, top_n=args.top)
    if not top:
        print("[ERROR] 선정 통과 전략 없음 — 임계값 완화 필요", file=sys.stderr)
        return 2

    print(f"\n[상위 {len(top)} 선정]")
    for s, score in top:
        print(
            f"  ▸ {s.strategy_id:<35} score={score:5.1f}  "
            f"ret={s.total_return_pct:+6.2f}%  "
            f"sharpe={s.sharpe_ratio:+5.2f}  "
            f"wr={s.win_rate * 100:.0f}%  trades={s.num_trades}"
        )

    top_series = [s for s, _ in top]

    # 2) 상관관계
    corr = CorrelationAnalyzer()
    matrix = corr.compute_matrix(top_series)
    avg_corr = corr.average_correlation(matrix)
    print(f"\n[상관관계] 평균 페어 corr = {avg_corr:+.3f}")
    print("  대각 제외 페어별:")
    ids = [s.strategy_id for s in top_series]
    for i, a in enumerate(ids):
        for j, b in enumerate(ids):
            if j > i:
                print(f"    {a} vs {b}: {matrix[a][b]:+.3f}")

    # 3) 3가지 방식 앙상블
    builder = EnsembleBuilder()
    results = []
    for method in (
        EnsembleMethod.EQUAL,
        EnsembleMethod.PERFORMANCE_WEIGHTED,
        EnsembleMethod.VOLATILITY_SCALED,
    ):
        eid = f"ensemble_top{len(top_series)}_{method.value}"
        r = builder.build(top_series, method, ensemble_id=eid)
        results.append(r)

    print(f"\n[앙상블 결과 — 3 방식]")
    for r in results:
        weights_str = ", ".join(
            f"{k}={v:.2f}" for k, v in sorted(r.weights.items())
        )
        print(
            f"  {r.method:<22} ret={r.total_return_pct:+6.2f}%  "
            f"sharpe={r.sharpe_ratio:+5.2f}  "
            f"MDD={r.max_drawdown_pct:+5.2f}%  "
            f"vol={r.volatility_pct:5.1f}%"
        )
        if not args.quiet:
            print(f"    weights: {weights_str}")

    # 4) 저장
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"ensembles_{ts}.json"
    json_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "matrix_source": matrix_path.name,
                "top_strategies": [
                    {"strategy_id": s.strategy_id, "score": score}
                    for s, score in top
                ],
                "correlation_matrix": matrix,
                "average_correlation": avg_corr,
                "ensembles": [r.to_dict() for r in results],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n저장: {json_path}")

    # 5) 리더보드 트랙 JS 생성
    leaderboard_path = REPO_ROOT / "data" / "leaderboard_ensembles.js"
    rows = []
    for r in results:
        rows.append({
            "ensemble_id": r.ensemble_id,
            "method": r.method,
            "members": r.members,
            "weights": r.weights,
            "total_return_pct": r.total_return_pct,
            "sharpe_ratio": r.sharpe_ratio,
            "max_drawdown_pct": r.max_drawdown_pct,
            "volatility_pct": r.volatility_pct,
            "trading_days": r.trading_days,
        })
    leaderboard_data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "matrix_source": matrix_path.name,
        "top_strategies": [s.strategy_id for s in top_series],
        "average_correlation": avg_corr,
        "ensembles": rows,
    }
    leaderboard_path.write_text(
        "// Auto-generated by build_ensembles.py\n"
        f"// {datetime.now().isoformat(timespec='seconds')}\n\n"
        "window.LEADERBOARD_ENSEMBLES = "
        + json.dumps(leaderboard_data, ensure_ascii=False, indent=2)
        + ";\n",
        encoding="utf-8",
    )
    print(f"리더보드 트랙: {leaderboard_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
