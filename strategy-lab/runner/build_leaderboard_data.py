"""
Leaderboard Data Builder
=========================
matrix_*.json → leaderboard_data.js 변환

leaderboard.html이 읽을 수 있는 JS 형식으로 변환:
    window.LEADERBOARD_DATA = {
        generated_at: "...",
        strategies: [...],
        periods: { "1w": [start, end], ... },
        leaderboards: { "1w": [...], "1m": [...] },
        cells: [...]
    }

가장 최신 matrix_*.json을 자동으로 선택.
또는 --merge로 여러 결과 병합 가능.

CLI:
    python3 -m runner.build_leaderboard_data
    python3 -m runner.build_leaderboard_data --merge
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "data" / "results"
OUTPUT_PATH = PROJECT_ROOT / "data" / "leaderboard_data.js"


def find_latest_matrix() -> Path:
    files = sorted(RESULTS_DIR.glob("matrix_*.json"))
    if not files:
        raise FileNotFoundError(f"matrix 결과 파일 없음: {RESULTS_DIR}")
    return files[-1]


def load_latest_promotions() -> dict:
    """
    가장 최근 promotions_*.json을 로드.
    키: "{strategy_id}::{period_label}" (JSON 직렬화 가능한 str).
    """
    promo_dir = PROJECT_ROOT / "data" / "promotions"
    if not promo_dir.exists():
        return {}
    files = sorted(promo_dir.glob("promotions_*.json"), reverse=True)
    if not files:
        return {}
    try:
        data = json.loads(files[0].read_text(encoding="utf-8"))
    except Exception:
        return {}
    result = {}
    for e in data.get("evaluations", []):
        key = f"{e['strategy_id']}::{e.get('period_label', '')}"
        result[key] = {
            "status": e.get("status", ""),
            "score": e.get("score", 0),
            "passed_criteria": e.get("passed_criteria", []),
            "failed_criteria": e.get("failed_criteria", []),
            "rejection_reasons": e.get("rejection_reasons", []),
            "warnings": e.get("warnings", []),
        }
    return result


def load_strategy_metadata() -> dict:
    """전략별 메타데이터 JSON을 로드해서 dict로 반환."""
    meta_dir = PROJECT_ROOT / "data" / "sources" / "metadata"
    metas = {}
    if not meta_dir.exists():
        return metas
    for f in meta_dir.glob("*.metadata.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            metas[data["id"]] = {
                "category": data.get("category", ""),
                "risk_level": data.get("risk_level", ""),
                "hypothesis": data.get("hypothesis", ""),
                "rationale": data.get("rationale", ""),
                "expected_edge": data.get("expected_edge", ""),
                "differs_from_existing": data.get("differs_from_existing", ""),
                "novelty_score": data.get("novelty_score", 0),
                "data_requirements": data.get("data_requirements", []),
                "sources": data.get("sources", []),
            }
        except Exception:
            continue
    return metas


def merge_matrices(files: list) -> dict:
    """여러 matrix JSON을 하나로 병합 (같은 strategy_id+period는 최신 것 우선)."""
    merged = {
        "generated_at": datetime.now().isoformat(),
        "strategies": set(),
        "periods": {},
        "leaderboards": {},
        "cells": [],
        "strategy_meta": load_strategy_metadata(),
        "promotions": load_latest_promotions(),
    }

    cells_map = {}  # (strategy_id, period) → cell

    for f in sorted(files):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  스킵: {f.name} ({e})")
            continue

        merged["strategies"].update(data.get("strategies", []))
        merged["periods"].update(data.get("periods", {}))

        for cell in data.get("cells", []):
            key = (cell["strategy_id"], cell["period_label"])
            cells_map[key] = cell

    merged["strategies"] = sorted(merged["strategies"])

    # history: {strategy_id::period: [day_results...]} 맵으로 분리
    # cells에서 history 필드는 제거 (중복 방지, 용량 감소)
    merged["histories"] = {}
    cells_cleaned = []
    for cell in cells_map.values():
        history = cell.get("history")
        if cell.get("status") == "completed" and history:
            key = f"{cell['strategy_id']}::{cell['period_label']}"
            merged["histories"][key] = history
        cell_copy = {k: v for k, v in cell.items() if k != "history"}
        cells_cleaned.append(cell_copy)
    merged["cells"] = cells_cleaned

    # 리더보드 재생성 (메타데이터 + 승급 상태 결합)
    metas = merged["strategy_meta"]
    promos = merged["promotions"]
    period_labels = list(merged["periods"].keys())
    for period in period_labels:
        rows = []
        for cell in merged["cells"]:
            if cell["period_label"] != period or cell["status"] != "completed":
                continue
            m = cell.get("metrics") or {}
            meta = metas.get(cell["strategy_id"], {})
            promo = promos.get(f"{cell['strategy_id']}::{period}", {})
            rows.append({
                "strategy_id": cell["strategy_id"],
                "strategy_name": cell["strategy_name"],
                "period": period,
                "start_date": cell["start_date"],
                "end_date": cell["end_date"],
                "total_return_pct": m.get("total_return_pct", 0),
                "sharpe_ratio": m.get("sharpe_ratio", 0),
                "sortino_ratio": m.get("sortino_ratio", 0),
                "calmar_ratio": m.get("calmar_ratio", 0),
                "max_drawdown_pct": m.get("max_drawdown_pct", 0),
                "win_rate": m.get("win_rate", 0),
                "profit_factor": m.get("profit_factor", 0),
                "num_trades": m.get("num_trades", 0),
                "trading_days": m.get("trading_days", 0),
                "best_day_pct": m.get("best_day_pct", 0),
                "worst_day_pct": m.get("worst_day_pct", 0),
                "max_consecutive_losses": m.get("max_consecutive_losses", 0),
                # 메타데이터 통합
                "category": meta.get("category", ""),
                "risk_level": meta.get("risk_level", ""),
                "hypothesis": meta.get("hypothesis", ""),
                "novelty_score": meta.get("novelty_score", 0),
                "data_requirements": meta.get("data_requirements", []),
                "sources_count": len(meta.get("sources", [])),
                # 승급 상태 통합
                "promotion_status": promo.get("status", ""),
                "promotion_score": promo.get("score", 0),
                "promotion_passed": promo.get("passed_criteria", []),
                "promotion_failed": promo.get("failed_criteria", []),
                "promotion_rejection_reasons": promo.get("rejection_reasons", []),
                "promotion_warnings": promo.get("warnings", []),
            })
        rows.sort(key=lambda r: r["total_return_pct"], reverse=True)
        merged["leaderboards"][period] = rows

    return merged


def build_js(data: dict) -> str:
    """JSON → JS assignment 변환."""
    json_str = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    return f"// Auto-generated by build_leaderboard_data.py\n// {datetime.now().isoformat()}\n\nwindow.LEADERBOARD_DATA = {json_str};\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--merge", action="store_true",
        help="모든 matrix_*.json 병합 (기본: 최신 1개만)",
    )
    parser.add_argument("--input", type=Path, default=None, help="특정 파일 사용")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="출력 경로")
    args = parser.parse_args()

    if args.merge:
        files = sorted(RESULTS_DIR.glob("matrix_*.json"))
        if not files:
            print(f"matrix 결과 없음: {RESULTS_DIR}", file=sys.stderr)
            return 1
        print(f"병합: {len(files)}개 파일")
        data = merge_matrices(files)
    elif args.input:
        if not args.input.exists():
            print(f"파일 없음: {args.input}", file=sys.stderr)
            return 1
        data = json.loads(args.input.read_text(encoding="utf-8"))
    else:
        try:
            latest = find_latest_matrix()
        except FileNotFoundError as e:
            print(str(e), file=sys.stderr)
            return 1
        print(f"최신 파일 사용: {latest.name}")
        data = json.loads(latest.read_text(encoding="utf-8"))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_js(data), encoding="utf-8")

    n_periods = len(data.get("periods", {}))
    n_cells = sum(len(rows) for rows in data.get("leaderboards", {}).values())
    print(f"[OK] {args.output}")
    print(f"     기간: {n_periods}개, 리더보드 행: {n_cells}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
