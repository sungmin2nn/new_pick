"""Arena / BNF / Bollinger 성과 데이터 결정적 검증.

LLM/에이전트가 raw 파일을 직접 해석하다 단위·매핑·정합성을 틀리는 환각을
원천 차단하기 위한 하네스. 모든 숫자는 이 스크립트에서 결정적으로 계산되어
`data/arena/_verified_facts.json` 한 파일로 출력된다.

원칙:
  1. 단일 진실원천(SoT): 각 팀 daily/<date>/trades.json 의 total_return_amount
     - 자본 = 초기자본 + sum(amount)
     - 모든 % 는 자본 기준 (capital-basis). simulation.total_return 같은
       "선정 종목 평균 수익률" 은 자본 영향이 아니므로 신뢰원천 아님.
  2. portfolio.json 은 교차검증용. 다르면 W_*_MISMATCH 로 보고만 한다.
  3. BNF (positions.json/trade_history.json) 와 Bollinger
     (bollinger_positions.json/bollinger_trades.json) 은 파일 경로로 분리.
  4. 단위는 항상 명시. capital-basis vs stock-basis 혼동 방지.

사용:
  python -m paper_trading.audit.verify_facts                # 검증 + 파일 쓰기 + 요약 출력
  python -m paper_trading.audit.verify_facts --no-write     # 콘솔 요약만
  python -m paper_trading.audit.verify_facts --quiet        # 파일만, 콘솔 출력 X
  python -m paper_trading.audit.verify_facts --update-issues # warning code 별로 issues.md 자동 등재 (dedupe)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

KST = timezone(timedelta(hours=9))
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARENA_DIR = PROJECT_ROOT / "data" / "arena"
BNF_DIR = PROJECT_ROOT / "data" / "bnf"
ISSUES_PATH = PROJECT_ROOT / ".claude" / "context" / "issues.md"
INITIAL_CAPITAL_DEFAULT = 10_000_000
SCHEMA_VERSION = "1.0"

# Warning code → issues.md 등재 템플릿. 같은 code 가 여러 번 발생해도 1개 ISSUE.
ISSUE_TEMPLATES: dict[str, dict[str, str]] = {
    "W_TRADE_COUNT_MISMATCH": {
        "title": "Arena portfolio.json vs daily/ trades.json 거래수 불일치",
        "증상": "portfolio.total_trades 가 daily/<date>/trades.json 합산보다 큼 (team_a/b/c/d 에서 5~10건씩 차이).",
        "원인": "arena_manager.run_daily() 동일 날짜 재실행 시 portfolio.update_after_day 는 total_trades 를 누적(+=)하지만 save_daily_record 는 trades.json 을 덮어씀. idempotency 부재. leaderboard.daily_history 에서 동일 일자 중복 등장으로 확인됨.",
        "해결": "(권고 1) run_daily 시작 시 daily/<date>/arena_report.json 존재 확인 후 skip + force 옵션. (권고 2) _load_portfolio 에서 daily 기반 자동 보정.",
        "예방": "verify_facts.py 가 매일 W_TRADE_COUNT_MISMATCH + W_DUPLICATE_RUNS 로 자동 감지. issues.md 자동 등재 (dedupe).",
    },
    "W_CAPITAL_MISMATCH": {
        "title": "Arena portfolio.json vs daily/ 합산 capital 불일치",
        "증상": "portfolio.current_capital 과 (초기자본 + sum(daily/*/trades.json/total_return_amount)) 차이 0.1% 초과.",
        "원인": "W_TRADE_COUNT_MISMATCH 와 동일 — 동일 날짜 재실행으로 portfolio 만 누적.",
        "해결": "W_TRADE_COUNT_MISMATCH 해결과 함께 처리.",
        "예방": "verify_facts.py 자동 감지.",
    },
    "W_DUPLICATE_RUNS": {
        "title": "leaderboard.daily_history 에 동일 일자 중복",
        "증상": "leaderboard.json 의 daily_history 배열에서 같은 date 가 2회 이상.",
        "원인": "arena_manager.run_daily 가 동일 일자에 여러 번 호출됨 (수동 재실행 또는 cron 중복).",
        "해결": "run_daily idempotency 추가 + 1회성 daily_history dedupe 스크립트.",
        "예방": "verify_facts.py 가 매일 자동 감지.",
    },
    "W_SUSPICIOUS_LOW_MDD": {
        "title": "자본 MDD 가 비현실적으로 낮음 — 시뮬 슬리피지 미반영 의심",
        "증상": "운영 5일 이상인 팀의 자본 MDD < 0.1% (예: team_a 0.04%, team_e 0%).",
        "원인": "trades.json 검사 결과 손절가/트레일링가가 정확한 % 단위로 체결됨. 시뮬에 슬리피지·호가·체결률 모형 없음.",
        "해결": "(권고 1) simulator.py 에 진입가/청산가에 ±0.2% 슬리피지 가정 추가. (권고 2) KIS 모의투자 연동(옵션 3, Phase A→G) 으로 실거래 검증.",
        "예방": "verify_facts.py 자동 감지. 모든 % 수치 보수적 해석 강제 (CLAUDE.md).",
    },
    "W_SIM_NO_SLIPPAGE": {
        "title": "시뮬레이터 슬리피지/체결률 모형 부재",
        "증상": "trades.json 의 손절가가 정확히 -3.0%, 트레일링/익절가도 정확한 % 로 체결됨.",
        "원인": "paper_trading/simulator.py 가 호가/체결률 모형 없이 이상적 가격 사용.",
        "해결": "단기: 슬리피지 ±0.2% 가정. 중기: KIS 모의투자(`broker/kis/`) 도입.",
        "예방": "verify_facts.py 가 매번 W_SIM_NO_SLIPPAGE 발행 (해결 전까지).",
    },
}


@dataclass
class FactsWarning:
    code: str
    severity: str  # info | warn | error
    scope: str
    message: str


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return {"_error": f"invalid_json: {e}"}


def _team_id_to_strategy_map(arena_dir: Path) -> dict[str, dict[str, Any]]:
    cfg = _read_json(arena_dir / "strategy_config.json") or {}
    out: dict[str, dict[str, Any]] = {}
    for sid, meta in (cfg.get("strategies") or {}).items():
        tid = meta.get("team_id")
        if not tid:
            continue
        out[tid] = {
            "strategy_id": sid,
            "team_name": meta.get("team_name"),
            "enabled": bool(meta.get("enabled", False)),
            "initial_capital": int(meta.get("initial_capital", INITIAL_CAPITAL_DEFAULT)),
        }
    return out


def _verify_team(
    team_id: str, team_meta: dict, warnings: list[FactsWarning]
) -> dict:
    team_dir = ARENA_DIR / team_id
    if not team_dir.exists():
        return {
            "team_id": team_id,
            "team_name": team_meta.get("team_name"),
            "strategy_id": team_meta.get("strategy_id"),
            "enabled": team_meta.get("enabled"),
            "exists": False,
        }

    initial = team_meta["initial_capital"]
    pf = _read_json(team_dir / "portfolio.json") or {}

    daily_dir = team_dir / "daily"
    daily_dates: list[str] = []
    capital = initial
    peak = capital
    max_dd_pct = 0.0
    worst_day_pct = 0.0
    best_day_pct = 0.0
    total_trades = 0
    total_wins = 0
    total_losses = 0

    if daily_dir.exists():
        for d in sorted(daily_dir.iterdir()):
            if not d.is_dir():
                continue
            tj = _read_json(d / "trades.json")
            if not tj or (isinstance(tj, dict) and "_error" in tj):
                continue
            amount = int(tj.get("total_return_amount", 0) or 0)
            wins = int(tj.get("wins", 0) or 0)
            losses = int(tj.get("losses", 0) or 0)
            n = int(tj.get("total_trades", 0) or 0)

            daily_dates.append(d.name)
            total_trades += n
            total_wins += wins
            total_losses += losses

            impact_pct = (amount / capital * 100) if capital > 0 else 0.0
            worst_day_pct = min(worst_day_pct, impact_pct)
            best_day_pct = max(best_day_pct, impact_pct)

            capital_new = capital + amount
            if capital_new > peak:
                peak = capital_new
            elif peak > 0:
                dd = (peak - capital_new) / peak * 100
                max_dd_pct = max(max_dd_pct, dd)
            capital = capital_new

    computed_current = capital
    computed_cum_pct = (capital - initial) / initial * 100 if initial > 0 else 0.0
    win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0.0

    pf_current = pf.get("current_capital")
    pf_cum_pct = pf.get("total_return_pct")
    pf_mdd = pf.get("max_drawdown_pct")
    pf_trades = pf.get("total_trades")
    pf_wins = pf.get("total_wins")

    # 교차검증 경고
    if pf_current is not None and pf_current != computed_current:
        diff_pct = abs(pf_current - computed_current) / max(computed_current, 1) * 100
        if diff_pct > 0.1:
            warnings.append(
                FactsWarning(
                    code="W_CAPITAL_MISMATCH",
                    severity="warn",
                    scope=team_id,
                    message=(
                        f"capital: portfolio.json={pf_current:,} vs daily 합산="
                        f"{computed_current:,} (차이 {diff_pct:.2f}%)"
                    ),
                )
            )

    if pf_trades is not None and pf_trades != total_trades:
        warnings.append(
            FactsWarning(
                code="W_TRADE_COUNT_MISMATCH",
                severity="warn",
                scope=team_id,
                message=(
                    f"거래수: portfolio.json={pf_trades} vs daily 합산="
                    f"{total_trades} (차이 {pf_trades - total_trades}건). "
                    f"daily/ 누락 일자 가능성"
                ),
            )
        )

    if (
        team_meta["enabled"]
        and len(daily_dates) >= 5
        and max_dd_pct < 0.1
    ):
        warnings.append(
            FactsWarning(
                code="W_SUSPICIOUS_LOW_MDD",
                severity="info",
                scope=team_id,
                message=(
                    f"자본 MDD {max_dd_pct:.4f}% — 시뮬 슬리피지 미반영 의심. "
                    f"실거래 시 더 큰 낙폭 예상"
                ),
            )
        )

    return {
        "team_id": team_id,
        "team_name": team_meta["team_name"],
        "strategy_id": team_meta["strategy_id"],
        "enabled": team_meta["enabled"],
        "exists": True,
        "operational_days": len(daily_dates),
        "capital": {
            "initial_krw": initial,
            "computed_current_krw": computed_current,
            "computed_current_source": (
                "sum(daily/<date>/trades.json/total_return_amount) + initial"
            ),
            "portfolio_json_current_krw": pf_current,
        },
        "returns_capital_basis": {
            "cumulative_pct": round(computed_cum_pct, 2),
            "best_day_impact_pct": round(best_day_pct, 2),
            "worst_day_impact_pct": round(worst_day_pct, 2),
            "portfolio_json_cumulative_pct": pf_cum_pct,
            "_note": (
                "stock-basis (daily/<date>/summary.json::simulation.total_return) "
                "는 5종목 평균 수익률이라 자본 영향 아님 — 인용 금지"
            ),
        },
        "drawdown": {
            "max_pct_capital_basis": round(max_dd_pct, 2),
            "portfolio_json_max_pct": pf_mdd,
        },
        "trades": {
            "total_daily_sum": total_trades,
            "wins_daily_sum": total_wins,
            "losses_daily_sum": total_losses,
            "win_rate_pct": round(win_rate, 2),
            "portfolio_json_total": pf_trades,
            "portfolio_json_wins": pf_wins,
        },
        "data_health": {
            "daily_files_count": len(daily_dates),
            "first_date": daily_dates[0] if daily_dates else None,
            "last_date": daily_dates[-1] if daily_dates else None,
            "trade_count_matches_portfolio": (
                pf_trades == total_trades if pf_trades is not None else None
            ),
            "capital_matches_portfolio": (
                pf_current == computed_current if pf_current is not None else None
            ),
        },
    }


def _verify_bnf_system(warnings: list[FactsWarning]) -> dict:
    pos_path = BNF_DIR / "positions.json"
    trades_path = BNF_DIR / "trade_history.json"

    pos = _read_json(pos_path)
    trades = _read_json(trades_path)

    if not pos or not trades:
        warnings.append(
            FactsWarning(
                code="W_BNF_FILES_MISSING",
                severity="warn",
                scope="bnf",
                message=f"BNF 파일 누락: positions={pos_path.exists()}, trades={trades_path.exists()}",
            )
        )
        return {"system_name": "BNF (낙폭과대 분할매수)", "exists": False}

    stats = pos.get("stats", {}) if isinstance(pos, dict) else {}
    active = pos.get("positions", []) if isinstance(pos, dict) else []
    cooldown = pos.get("cooldown_until", {}) if isinstance(pos, dict) else {}
    trades_list = trades if isinstance(trades, list) else (trades.get("trades", []) if isinstance(trades, dict) else [])

    wins_computed = sum(1 for t in trades_list if (t.get("return_pct") or 0) > 0)
    losses_computed = sum(1 for t in trades_list if (t.get("return_pct") or 0) < 0)

    return {
        "system_name": "BNF (낙폭과대 분할매수)",
        "exists": True,
        "files": {
            "positions": str(pos_path.relative_to(PROJECT_ROOT)),
            "trades": str(trades_path.relative_to(PROJECT_ROOT)),
            "candidates_pattern": "data/bnf/candidates_*.json",
        },
        "capital_krw": {
            "total": stats.get("total_capital"),
            "current": stats.get("current_capital"),
            "used": stats.get("used_capital"),
            "realized_pnl": stats.get("realized_pnl"),
            "unrealized_pnl": stats.get("unrealized_pnl"),
        },
        "returns": {
            "cumulative_pct": stats.get("total_return"),
            "simple_sum_pct": stats.get("total_return_simple"),
            "average_per_trade_pct": stats.get("avg_return"),
        },
        "trades": {
            "total": stats.get("total_trades", len(trades_list)),
            "wins_computed": wins_computed,
            "losses_computed": losses_computed,
            "win_rate_pct": stats.get("win_rate"),
        },
        "positions": {
            "active_count": len(active),
            "active": [
                {
                    "code": p.get("code"),
                    "name": p.get("name"),
                    "entry_date": p.get("entry_date"),
                    "unrealized_pnl_pct": round(p.get("unrealized_pnl_pct") or 0, 2),
                    "selection_reason": p.get("selection_reason"),
                }
                for p in active
            ],
            "cooldown_count": len(cooldown),
            "cooldown": cooldown,
        },
        "last_updated": pos.get("updated_at") if isinstance(pos, dict) else None,
    }


def _verify_bollinger_system(warnings: list[FactsWarning]) -> dict:
    pos_path = BNF_DIR / "bollinger_positions.json"
    trades_path = BNF_DIR / "bollinger_trades.json"

    pos = _read_json(pos_path)
    trades = _read_json(trades_path)

    if not pos or not trades:
        warnings.append(
            FactsWarning(
                code="W_BOLL_FILES_MISSING",
                severity="warn",
                scope="bollinger",
                message=f"Bollinger 파일 누락: positions={pos_path.exists()}, trades={trades_path.exists()}",
            )
        )
        return {"system_name": "Bollinger 스윙", "exists": False}

    active = pos.get("positions", []) if isinstance(pos, dict) else []
    trades_list = trades if isinstance(trades, list) else (trades.get("trades", []) if isinstance(trades, dict) else [])

    wins = sum(1 for t in trades_list if (t.get("return_pct") or 0) > 0)
    losses = sum(1 for t in trades_list if (t.get("return_pct") or 0) < 0)
    total_profit = sum(int(t.get("profit") or 0) for t in trades_list)
    win_rate = (wins / len(trades_list) * 100) if trades_list else 0.0

    return {
        "system_name": "Bollinger 스윙",
        "exists": True,
        "files": {
            "positions": str(pos_path.relative_to(PROJECT_ROOT)),
            "trades": str(trades_path.relative_to(PROJECT_ROOT)),
            "candidates_pattern": "data/bnf/bollinger_candidates_*.json",
        },
        "trades": {
            "total": len(trades_list),
            "wins": wins,
            "losses": losses,
            "win_rate_pct": round(win_rate, 2),
            "total_profit_krw": total_profit,
        },
        "positions": {
            "active_count": len(active),
            "active": [
                {
                    "code": p.get("code"),
                    "name": p.get("name"),
                    "entry_date": p.get("entry_date"),
                    "unrealized_pnl_pct": round(p.get("unrealized_pnl_pct") or 0, 2),
                    "selection_reason": p.get("selection_reason"),
                }
                for p in active
            ],
        },
        "last_updated": pos.get("updated_at") if isinstance(pos, dict) else None,
    }


def _check_duplicate_runs(warnings: list[FactsWarning]) -> dict:
    """leaderboard.daily_history 에서 동일 일자 중복 감지."""
    lb = _read_json(ARENA_DIR / "leaderboard.json") or {}
    history = lb.get("daily_history") or []
    if not isinstance(history, list):
        return {"checked": False}
    dates = [h.get("date") for h in history if isinstance(h, dict)]
    counts = Counter(d for d in dates if d)
    duplicates = {d: c for d, c in counts.items() if c > 1}
    if duplicates:
        warnings.append(
            FactsWarning(
                code="W_DUPLICATE_RUNS",
                severity="warn",
                scope="leaderboard",
                message=(
                    f"daily_history 중복 일자: {duplicates} — "
                    f"arena_manager.run_daily 동일 일자 재실행 의심"
                ),
            )
        )
    return {
        "checked": True,
        "total_entries": len(dates),
        "unique_dates": len(set(dates)),
        "duplicates": duplicates,
    }


def verify(write: bool = True, output_path: Path | None = None) -> dict:
    warnings: list[FactsWarning] = []
    team_strategy_map = _team_id_to_strategy_map(ARENA_DIR)

    arena = {tid: _verify_team(tid, meta, warnings) for tid, meta in sorted(team_strategy_map.items())}
    bnf = _verify_bnf_system(warnings)
    bollinger = _verify_bollinger_system(warnings)
    duplicate_runs = _check_duplicate_runs(warnings)

    # 전역 시뮬 결함 경고 — TradingSimulator.SLIPPAGE_PCT == 0 일 때만 발행
    try:
        from paper_trading.simulator import TradingSimulator
        slippage_pct = float(getattr(TradingSimulator, "SLIPPAGE_PCT", 0))
    except Exception:
        slippage_pct = 0.0
    if slippage_pct <= 0:
        warnings.append(
            FactsWarning(
                code="W_SIM_NO_SLIPPAGE",
                severity="info",
                scope="global",
                message=(
                    "TradingSimulator.SLIPPAGE_PCT=0 — 시뮬에 슬리피지/체결률 모형 없음. "
                    "KIS 모의투자 도입 전까지 모든 % 는 보수적으로 해석"
                ),
            )
        )

    facts = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(KST).isoformat(),
        "consumer_contract": {
            "rule_1": "이 파일의 숫자만 인용. raw daily/portfolio/trades 파일 직접 인용 금지",
            "rule_2": "단위 명시 필수. capital-basis vs stock-basis 혼동 시 환각",
            "rule_3": "warnings 무시 금지. severity=warn 이상은 결론에 반드시 반영",
            "rule_4": "이 파일에 없는 metric 은 '미검증' 표시",
        },
        "arena": arena,
        "bnf": bnf,
        "bollinger": bollinger,
        "duplicate_runs": duplicate_runs,
        "warnings": [asdict(w) for w in warnings],
    }

    if write:
        out = output_path or (ARENA_DIR / "_verified_facts.json")
        out.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")

    return facts


def _print_summary(facts: dict) -> None:
    print(f"\n=== Verified Facts (generated {facts['generated_at']}) ===\n")

    print("[Arena]")
    header = f"{'team':<8} {'strategy':<22} {'en':>3} {'days':>4} {'cum%':>7} {'mdd%':>6} {'trades':>6} {'wr%':>6} {'health':<28}"
    print(header)
    print("-" * len(header))
    for tid, t in facts["arena"].items():
        if not t.get("exists"):
            continue
        if not t.get("operational_days"):
            print(f"  {tid:<6} {t['strategy_id']:<22} {'Y' if t['enabled'] else 'N':>3} {0:>4} {'--':>7} {'--':>6} {'--':>6} {'--':>6} no daily data")
            continue
        cum = t["returns_capital_basis"]["cumulative_pct"]
        mdd = t["drawdown"]["max_pct_capital_basis"]
        n = t["trades"]["total_daily_sum"]
        wr = t["trades"]["win_rate_pct"]
        days = t["operational_days"]
        en = "Y" if t["enabled"] else "N"
        match_t = t["data_health"]["trade_count_matches_portfolio"]
        match_c = t["data_health"]["capital_matches_portfolio"]
        if match_t and match_c:
            health = "OK"
        else:
            issues = []
            if match_t is False:
                issues.append(f"trade pf={t['trades']['portfolio_json_total']}")
            if match_c is False:
                issues.append(f"cap pf={t['capital']['portfolio_json_current_krw']:,}")
            health = " ".join(issues)
        print(f"  {tid:<6} {t['strategy_id']:<22} {en:>3} {days:>4} {cum:>6.2f}% {mdd:>5.2f}% {n:>6} {wr:>5.2f}% {health:<28}")

    print("\n[Independent Systems]")
    if facts["bnf"].get("exists"):
        b = facts["bnf"]
        cap = b["capital_krw"]
        print(
            f"  BNF       cap_cur={cap['current']:,} cum={b['returns']['cumulative_pct']}%  "
            f"trades={b['trades']['total']} wr={b['trades']['win_rate_pct']}%  "
            f"active={b['positions']['active_count']} cooldown={b['positions']['cooldown_count']}"
        )
    else:
        print("  BNF       (missing)")
    if facts["bollinger"].get("exists"):
        b = facts["bollinger"]
        print(
            f"  Bollinger trades={b['trades']['total']} wr={b['trades']['win_rate_pct']}%  "
            f"profit={b['trades']['total_profit_krw']:,}  active={b['positions']['active_count']}"
        )
    else:
        print("  Bollinger (missing)")

    ws = facts["warnings"]
    print(f"\n[Warnings: {len(ws)}]")
    for w in ws:
        print(f"  [{w['severity']:>5}] {w['code']:<26} scope={w['scope']:<12} {w['message']}")


def update_issues_md(facts: dict, issues_path: Path = ISSUES_PATH) -> dict:
    """warnings 의 code 별로 issues.md 에 자동 등재 (이미 있으면 skip).

    동일 code 가 여러 scope 에서 발생해도 1개 ISSUE 로 통합.
    issues.md 본문에 'W_<CODE>' 또는 ISSUE 제목이 이미 있으면 추가 안 함.
    """
    if not issues_path.exists():
        return {"action": "skipped", "reason": "issues.md not found"}

    text = issues_path.read_text(encoding="utf-8")

    # 등재 후보: ISSUE_TEMPLATES 에 있고 + 현재 facts.warnings 에 등장하는 code
    seen_codes = set()
    code_scopes: dict[str, list[str]] = {}
    for w in facts["warnings"]:
        c = w["code"]
        seen_codes.add(c)
        code_scopes.setdefault(c, []).append(w["scope"])

    candidates = [c for c in seen_codes if c in ISSUE_TEMPLATES]

    # 마지막 ISSUE 번호
    nums = [int(m.group(1)) for m in re.finditer(r"## \[ISSUE-(\d+)\]", text)]
    next_num = (max(nums) if nums else 0) + 1

    added: list[str] = []
    skipped: list[str] = []

    # 정확한 매칭: "warning code: `<CODE>`" 라인이 이미 issues.md 에 있으면 skip.
    # 본문에 단순히 코드명이 들어간 경우(다른 ISSUE 의 원인 설명 등)는 skip 사유 아님.
    code_marker = lambda c: f"- **warning code**: `{c}`"

    for code in sorted(candidates):
        if code_marker(code) in text:
            skipped.append(code)
            continue
        tmpl = ISSUE_TEMPLATES[code]
        scopes = sorted(set(code_scopes.get(code, [])))
        today = datetime.now(KST).strftime("%Y-%m-%d")

        block = (
            f"\n## [ISSUE-{next_num:03d}] {tmpl['title']}\n"
            f"- **발생일**: {today}\n"
            f"- **에이전트**: verify_facts.py (자동 등재)\n"
            f"- **warning code**: `{code}`\n"
            f"- **scope**: {', '.join(scopes) if scopes else 'global'}\n"
            f"- **증상**: {tmpl['증상']}\n"
            f"- **원인**: {tmpl['원인']}\n"
            f"- **해결**: {tmpl['해결']}\n"
            f"- **예방**: {tmpl['예방']}\n"
            f"- **상태**: open\n\n---\n"
        )
        text = text.rstrip() + "\n" + block
        added.append(f"ISSUE-{next_num:03d} ({code})")
        next_num += 1

    if added:
        issues_path.write_text(text, encoding="utf-8")

    return {
        "action": "updated" if added else "no_change",
        "added": added,
        "skipped_already_present": skipped,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Arena/BNF/Bollinger 성과 데이터 결정적 검증")
    p.add_argument("--no-write", action="store_true", help="JSON 파일 출력 안 함")
    p.add_argument("--output", type=Path, default=None, help="출력 경로 (기본: data/arena/_verified_facts.json)")
    p.add_argument("--quiet", action="store_true", help="콘솔 요약 안 함")
    p.add_argument("--update-issues", action="store_true", help="warning code 별로 .claude/context/issues.md 자동 등재 (dedupe)")
    args = p.parse_args(argv)

    facts = verify(write=not args.no_write, output_path=args.output)

    if not args.quiet:
        _print_summary(facts)

    if args.update_issues:
        result = update_issues_md(facts)
        if not args.quiet:
            print(f"\n[issues.md] {result['action']}")
            for x in result.get("added", []):
                print(f"  + {x}")
            for x in result.get("skipped_already_present", []):
                print(f"  - skip (already present): {x}")

    has_error = any(w["severity"] == "error" for w in facts["warnings"])
    return 1 if has_error else 0


if __name__ == "__main__":
    sys.exit(main())
