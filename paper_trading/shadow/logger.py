"""
ShadowLogger — paper trading shadow 4주 운영의 일일 데이터 기록.

스키마: ./schema.md
- shadow_signals.jsonl  (append-only, 멱등 키 = signal_date+variant_id+code)
- shadow_positions.json (overwrite, 현재 보유 상태 스냅샷)
- shadow_intraday.jsonl (append-only, 선택적)
- shadow_trades.jsonl   (append-only, 멱등 키 = position_id)

격리: data/paper_trading_shadow/<variant_id>/ — 변형별 디렉토리 분리.
원자성: positions.json 은 tempfile + rename 으로 갱신 (크래시 방어).
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

# ============================================================
# 상수 / 화이트리스트
# ============================================================

SCHEMA_VERSION: int = 1
KST = timezone(timedelta(hours=9))

VARIANT_WHITELIST: Set[str] = {
    "squeeze_play_kospi_v6",
    "squeeze_play_kosdaq_v5",
}

# 데이터 위치 — plan §6 "프로젝트 내 격리"
DEFAULT_LOG_ROOT = Path(__file__).parent.parent.parent / "data" / "paper_trading_shadow"


# ============================================================
# 예외
# ============================================================

class ShadowLogError(ValueError):
    """스키마 위반 / 무결성 위반."""


# ============================================================
# 검증
# ============================================================

def _now_kst_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def _validate_variant_id(variant_id: str) -> None:
    if variant_id not in VARIANT_WHITELIST:
        raise ShadowLogError(
            f"variant_id={variant_id!r} 화이트리스트 외. "
            f"허용: {sorted(VARIANT_WHITELIST)}"
        )


def _validate_yyyymmdd(s: str, field: str) -> None:
    if not isinstance(s, str) or len(s) != 8 or not s.isdigit():
        raise ShadowLogError(f"{field}={s!r} 는 YYYYMMDD 형식이어야 함")


def _validate_signal(signal: Dict) -> None:
    required = {"variant_id", "code", "name", "signal_date",
                "expected_entry_date", "exit_planned_date",
                "signal_close_price", "score", "score_detail"}
    missing = required - signal.keys()
    if missing:
        raise ShadowLogError(f"signal 필수 필드 누락: {sorted(missing)}")

    _validate_variant_id(signal["variant_id"])
    _validate_yyyymmdd(signal["signal_date"], "signal_date")
    _validate_yyyymmdd(signal["expected_entry_date"], "expected_entry_date")
    _validate_yyyymmdd(signal["exit_planned_date"], "exit_planned_date")

    if not (signal["signal_date"] < signal["expected_entry_date"]
            <= signal["exit_planned_date"]):
        raise ShadowLogError(
            f"날짜 순서 오류: signal({signal['signal_date']}) < "
            f"entry({signal['expected_entry_date']}) <= "
            f"exit({signal['exit_planned_date']}) 위반"
        )

    if not isinstance(signal["signal_close_price"], int) or signal["signal_close_price"] <= 0:
        raise ShadowLogError(f"signal_close_price 양의 정수 아님: {signal['signal_close_price']!r}")

    sd = signal.get("score_detail") or {}
    pb = sd.get("percent_b")
    if pb is not None and not (-0.5 <= pb <= 1.5):
        raise ShadowLogError(f"percent_b={pb} 비현실 범위 (허용 -0.5~1.5)")


def _validate_position(pos: Dict) -> None:
    required = {"position_id", "variant_id", "code", "entry_date",
                "exit_planned_date", "fill_status"}
    missing = required - pos.keys()
    if missing:
        raise ShadowLogError(f"position 필수 필드 누락: {sorted(missing)}")
    _validate_variant_id(pos["variant_id"])
    _validate_yyyymmdd(pos["entry_date"], "entry_date")
    _validate_yyyymmdd(pos["exit_planned_date"], "exit_planned_date")
    if pos["fill_status"] not in {"filled", "partial", "rejected", "skipped"}:
        raise ShadowLogError(f"fill_status={pos['fill_status']!r} 화이트리스트 외")


def _validate_trade(trade: Dict) -> None:
    required = {"position_id", "variant_id", "code", "signal_date", "entry_date",
                "exit_date", "signal_close_price", "entry_open_price",
                "exit_close_price", "return_pct", "exit_type"}
    missing = required - trade.keys()
    if missing:
        raise ShadowLogError(f"trade 필수 필드 누락: {sorted(missing)}")
    _validate_variant_id(trade["variant_id"])
    for f in ("signal_date", "entry_date", "exit_date"):
        _validate_yyyymmdd(trade[f], f)
    if not (trade["signal_date"] < trade["entry_date"] <= trade["exit_date"]):
        raise ShadowLogError("trade 날짜 순서 오류 (signal<entry<=exit)")


# ============================================================
# 파일 I/O 유틸
# ============================================================

def _atomic_write_json(path: Path, data: Dict) -> None:
    """tempfile + rename 으로 원자적 덮어쓰기."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".tmp.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _append_jsonl(path: Path, record: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=False)
    if "\n" in line:
        raise ShadowLogError("JSONL 레코드에 개행 포함 — 멀티라인 금지")
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
        f.write("\n")


def _read_jsonl(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    out: List[Dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                # 손상된 라인은 skip — 이후 lint 단계에서 감지
                continue
    return out


# ============================================================
# ShadowLogger
# ============================================================

@dataclass
class ShadowLogger:
    """
    변형(variant) 별 shadow 로그 writer.

    Usage:
        logger = ShadowLogger("squeeze_play_kospi_v6")
        logger.append_signal({...})
        logger.update_positions([{...}, {...}])
        logger.append_trade({...})

    멱등:
    - signal: (signal_date, variant_id, code) 중복 ignore
    - trade: position_id 중복 ignore
    - positions: 항상 덮어쓰기
    """
    variant_id: str
    log_root: Path = None  # type: ignore[assignment]

    def __post_init__(self):
        _validate_variant_id(self.variant_id)
        if self.log_root is None:
            self.log_root = DEFAULT_LOG_ROOT
        elif isinstance(self.log_root, str):
            self.log_root = Path(self.log_root)
        self.variant_dir = self.log_root / self.variant_id
        self.variant_dir.mkdir(parents=True, exist_ok=True)

    # ── 파일 경로 ──
    @property
    def signals_path(self) -> Path:
        return self.variant_dir / "shadow_signals.jsonl"

    @property
    def positions_path(self) -> Path:
        return self.variant_dir / "shadow_positions.json"

    @property
    def intraday_path(self) -> Path:
        return self.variant_dir / "shadow_intraday.jsonl"

    @property
    def trades_path(self) -> Path:
        return self.variant_dir / "shadow_trades.jsonl"

    # ── Write API ──
    def append_signal(self, signal: Dict) -> bool:
        """시그널 1건 append. 멱등. 신규 추가 시 True."""
        signal = {**signal}
        signal.setdefault("schema_version", SCHEMA_VERSION)
        signal.setdefault("timestamp", _now_kst_iso())
        if signal.get("variant_id") != self.variant_id:
            raise ShadowLogError(
                f"signal.variant_id={signal.get('variant_id')!r} != logger.variant_id={self.variant_id!r}"
            )
        _validate_signal(signal)

        # 멱등 검사 (signal_date + code)
        existing = self._existing_signal_keys()
        key = (signal["signal_date"], signal["code"])
        if key in existing:
            return False
        _append_jsonl(self.signals_path, signal)
        return True

    def update_positions(self, positions: Iterable[Dict]) -> int:
        """현재 보유 상태 전체 덮어쓰기. 반환: 기록된 포지션 수."""
        positions = list(positions)
        for p in positions:
            if p.get("variant_id") != self.variant_id:
                raise ShadowLogError(
                    f"position.variant_id={p.get('variant_id')!r} != "
                    f"logger.variant_id={self.variant_id!r}"
                )
            _validate_position(p)
        snapshot = {
            "schema_version": SCHEMA_VERSION,
            "as_of": _now_kst_iso(),
            "variant_id": self.variant_id,
            "open_positions": positions,
        }
        _atomic_write_json(self.positions_path, snapshot)
        return len(positions)

    def append_intraday_snapshot(self, snapshot: Dict) -> None:
        """장중 스냅샷 — 검증 가벼움 (선택적 기록)."""
        snapshot = {
            "schema_version": SCHEMA_VERSION,
            "timestamp": snapshot.get("timestamp") or _now_kst_iso(),
            **{k: v for k, v in snapshot.items() if k not in ("schema_version", "timestamp")},
        }
        if "position_id" not in snapshot:
            raise ShadowLogError("intraday snapshot 에 position_id 필수")
        _append_jsonl(self.intraday_path, snapshot)

    def append_trade(self, trade: Dict) -> bool:
        """청산 결과 1건 append. 멱등. 신규 추가 시 True."""
        trade = {**trade}
        trade.setdefault("schema_version", SCHEMA_VERSION)
        trade.setdefault("timestamp", _now_kst_iso())
        if trade.get("variant_id") != self.variant_id:
            raise ShadowLogError(
                f"trade.variant_id={trade.get('variant_id')!r} != "
                f"logger.variant_id={self.variant_id!r}"
            )
        _validate_trade(trade)

        existing = self._existing_trade_ids()
        if trade["position_id"] in existing:
            return False
        _append_jsonl(self.trades_path, trade)
        return True

    # ── Read API ──
    def list_signals(self, since_date: Optional[str] = None) -> List[Dict]:
        """signal_date >= since_date 인 시그널들 (since 없으면 전체)."""
        records = _read_jsonl(self.signals_path)
        if since_date:
            records = [r for r in records if r.get("signal_date", "") >= since_date]
        return records

    def get_open_positions(self) -> List[Dict]:
        if not self.positions_path.exists():
            return []
        with open(self.positions_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("open_positions", [])

    def list_trades(self, since_date: Optional[str] = None) -> List[Dict]:
        records = _read_jsonl(self.trades_path)
        if since_date:
            records = [r for r in records if r.get("entry_date", "") >= since_date]
        return records

    # ── 내부 ──
    def _existing_signal_keys(self) -> Set[tuple]:
        return {
            (r.get("signal_date", ""), r.get("code", ""))
            for r in _read_jsonl(self.signals_path)
        }

    def _existing_trade_ids(self) -> Set[str]:
        return {
            r.get("position_id", "")
            for r in _read_jsonl(self.trades_path)
        }
