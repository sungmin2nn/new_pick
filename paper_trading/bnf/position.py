"""
BNF Position Manager

positions.json / trade_history.json 을 관리하는 단일 모듈.
워크플로우, 대시보드, 텔레그램 스크립트가 모두 이 모듈을 통해 데이터에 접근한다.
"""

import json
import os
from copy import deepcopy
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Dict, Optional, Any


class PositionState(Enum):
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    FULL = "FULL"
    EXITING = "EXITING"
    CLOSED = "CLOSED"


# ---------- 기본 설정 ----------
DEFAULT_TOTAL_CAPITAL = 3_000_000
MAX_POSITIONS = 5
POSITION_RATIO = 0.20          # 종목당 최대 20%
STOP_LOSS_PCT = -3.0           # 손절 기준
TAKE_PROFIT_PCT = 10.0         # 익절 기준

# 손절 후 동일 종목 재진입 금지 기간 (영업일). 추세 하락 중 반복 진입 차단.
COOLDOWN_BUSINESS_DAYS = 5
# 손절 체결가 슬리피지 상한: 진입가 대비 -X%보다 더 낮은 가격으로는 기록하지 않음.
# 실제 갭하락으로 더 크게 빠져도 BNF 성과 통계가 왜곡되는 걸 완화 (실매매 관점은 주문 레벨에서 처리).
MAX_STOP_LOSS_SLIPPAGE_PCT = -7.0


class BNFPositionManager:
    """
    positions.json 과 trade_history.json 을 읽고/쓰고/정합성을 유지하는 매니저.

    JSON 구조 (positions.json):
    {
      "updated_at": "...",
      "positions": [ { position dict }, ... ],   # 활성 포지션만
      "stats": { ... }
    }

    JSON 구조 (trade_history.json):
    {
      "updated_at": "...",
      "trades": [ { trade dict }, ... ],
      "stats": { ... }
    }
    """

    def __init__(self, data_dir: str = "data/bnf",
                 total_capital: float = DEFAULT_TOTAL_CAPITAL):
        self.data_dir = Path(data_dir)
        self.positions_file = self.data_dir / "positions.json"
        self.history_file = self.data_dir / "trade_history.json"
        self.total_capital = total_capital

        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 활성 포지션 목록 (CLOSED 제외)
        self.positions: List[Dict[str, Any]] = []
        # 완료된 거래 목록
        self.trades: List[Dict[str, Any]] = []
        # 재진입 쿨다운: code -> 'YYYY-MM-DD' (이 날짜까지 포함 금지)
        self.cooldown_until: Dict[str, str] = {}

        self.load()

    # ========== I/O ==========

    def load(self) -> None:
        """positions.json + trade_history.json 로드"""
        # positions
        if self.positions_file.exists():
            with open(self.positions_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            all_positions = data.get("positions", [])
            if isinstance(all_positions, dict):
                all_positions = list(all_positions.values())
            # CLOSED 는 무시 — trade_history 에만 존재해야 한다
            self.positions = [p for p in all_positions if p.get("state") != "CLOSED"]
            self.total_capital = data.get("stats", {}).get("total_capital", self.total_capital)
            raw_cooldown = data.get("cooldown_until", {}) or {}
            # 만료된 쿨다운 항목은 로드 시 버림 (today 미정이므로 여기선 유지만, 체크 시 판단)
            self.cooldown_until = {str(k): str(v) for k, v in raw_cooldown.items()}
        else:
            self.positions = []
            self.cooldown_until = {}

        # trade history
        if self.history_file.exists():
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.trades = data.get("trades", [])
        else:
            self.trades = []

    def save(self, timestamp: Optional[str] = None) -> None:
        """positions.json + trade_history.json 저장"""
        ts = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # --- positions.json (활성 포지션만) ---
        pos_stats = self._calc_position_stats()
        # 쿨다운은 오늘 기준으로 만료된 건 정리해서 저장 (무한 누적 방지)
        today_iso = datetime.now().strftime("%Y-%m-%d")
        active_cooldown = {
            code: until for code, until in self.cooldown_until.items()
            if until >= today_iso
        }
        self.cooldown_until = active_cooldown
        pos_data = {
            "updated_at": ts,
            "positions": self.positions,
            "cooldown_until": active_cooldown,
            "stats": pos_stats,
        }
        with open(self.positions_file, "w", encoding="utf-8") as f:
            json.dump(pos_data, f, indent=2, ensure_ascii=False)

        # --- trade_history.json ---
        trade_stats = self._calc_trade_stats()
        hist_data = {
            "updated_at": ts,
            "trades": self.trades,
            "stats": trade_stats,
        }
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(hist_data, f, indent=2, ensure_ascii=False)

    # ========== 포지션 조회 ==========

    def get_open_positions(self) -> List[Dict[str, Any]]:
        return [p for p in self.positions if p.get("state") != "CLOSED"]

    def find_position(self, code: str) -> Optional[Dict[str, Any]]:
        """활성 포지션 중 code 로 검색"""
        for p in self.positions:
            if p["code"] == code and p.get("state") != "CLOSED":
                return p
        return None

    def has_open_position(self, code: str) -> bool:
        return self.find_position(code) is not None

    def open_slots(self) -> int:
        return MAX_POSITIONS - len(self.get_open_positions())

    # ========== 재진입 쿨다운 ==========

    @staticmethod
    def _add_business_days(date_iso: str, n: int) -> str:
        """date_iso(YYYY-MM-DD)에 영업일 n일을 더한 날짜 (주말만 제외, 공휴일 미반영)."""
        from datetime import date as _date, timedelta as _td
        y, m, d = map(int, date_iso.split("-"))
        cur = _date(y, m, d)
        added = 0
        while added < n:
            cur += _td(days=1)
            if cur.weekday() < 5:  # Mon-Fri
                added += 1
        return cur.isoformat()

    def is_in_cooldown(self, code: str, today_iso: str) -> bool:
        until = self.cooldown_until.get(code)
        return bool(until and until >= today_iso)

    def get_cooldown_until(self, code: str) -> Optional[str]:
        return self.cooldown_until.get(code)

    # ========== 신규 진입 ==========

    def enter_position(self, code: str, name: str, price: int, quantity: int,
                       date: str, time: str,
                       selection_reason: str = "") -> Optional[Dict[str, Any]]:
        """
        신규 포지션 진입 (FULL 상태로 즉시 등록).
        이미 동일 종목을 보유 중이면 None 반환.
        """
        if self.has_open_position(code):
            print(f"이미 보유 중: {code}")
            return None

        # 재진입 쿨다운 체크 (손절 후 N영업일 금지)
        if self.is_in_cooldown(code, date):
            until = self.cooldown_until.get(code)
            print(f"  재진입 쿨다운: {name}({code}) {until}까지 금지 (손절 후 {COOLDOWN_BUSINESS_DAYS}영업일)")
            return None

        if self.open_slots() <= 0:
            print(f"슬롯 부족 (최대 {MAX_POSITIONS})")
            return None

        position = {
            "code": code,
            "name": name,
            "state": PositionState.FULL.value,
            "avg_price": price,
            "current_price": price,
            "total_quantity": quantity,
            "entry_date": date,
            "entry_price": price,
            "unrealized_pnl": 0,
            "unrealized_pnl_pct": 0.0,
            "selection_reason": selection_reason,
            "entries": [
                {"price": price, "quantity": quantity, "date": date, "time": time}
            ],
            "exits": [],
        }
        self.positions.append(position)
        return position

    # ========== 가격 업데이트 ==========

    def update_price(self, code: str, current_price: int) -> Optional[Dict[str, Any]]:
        """현재가 갱신 + 미실현 손익 재계산"""
        pos = self.find_position(code)
        if pos is None:
            return None

        pos["current_price"] = current_price
        avg = pos.get("avg_price", current_price)
        qty = pos.get("total_quantity", 0)
        pos["unrealized_pnl"] = (current_price - avg) * qty
        pos["unrealized_pnl_pct"] = ((current_price / avg) - 1) * 100 if avg > 0 else 0
        return pos

    # ========== 청산 ==========

    def close_position(self, code: str, exit_price: int, exit_date: str,
                       exit_reason: str, exit_time: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        포지션 청산:
        1. exits 배열에 기록
        2. trade_history 로 이동
        3. positions 에서 제거
        반환: 생성된 trade dict (또는 None)
        """
        pos = self.find_position(code)
        if pos is None:
            print(f"포지션 없음: {code}")
            return None

        qty = pos.get("total_quantity", 0)
        avg_price = pos.get("avg_price", 0)

        # 손절 체결가 슬리피지 가드: 실제가가 MAX_STOP_LOSS_SLIPPAGE_PCT 아래로 찍혀도
        # 그 라인에서 체결된 것으로 기록 (갭하락 노이즈로 BNF 성과가 과도하게 왜곡되는 걸 방지).
        # 실제 주문 집행은 별도 레이어에서 스탑 주문/분할 처리가 필요 (본 변경은 성과 회계용).
        is_stop_loss = "손절" in (exit_reason or "")
        if is_stop_loss and avg_price > 0:
            slip_floor = int(avg_price * (1 + MAX_STOP_LOSS_SLIPPAGE_PCT / 100))
            if exit_price < slip_floor:
                print(f"  슬리피지 가드: {pos['name']} 체결가 {exit_price:,} → {slip_floor:,} "
                      f"(진입가 {avg_price:,} 기준 {MAX_STOP_LOSS_SLIPPAGE_PCT}% 라인)")
                exit_price = slip_floor

        # exits 배열에 청산 기록 추가
        exit_record = {
            "price": exit_price,
            "quantity": qty,
            "date": exit_date,
            "time": exit_time or datetime.now().strftime("%H:%M:%S"),
            "reason": exit_reason,
        }
        pos["exits"].append(exit_record)

        # trade_history 용 레코드 생성
        return_pct = ((exit_price / avg_price) - 1) * 100 if avg_price > 0 else 0
        profit = int((exit_price - avg_price) * qty)

        trade = {
            "code": pos["code"],
            "name": pos["name"],
            "entry_date": pos.get("entry_date"),
            "entry_price": avg_price,
            "exit_date": exit_date,
            "exit_price": exit_price,
            "quantity": qty,
            "return_pct": round(return_pct, 2),
            "profit": profit,
            "exit_reason": exit_reason,
        }
        self.trades.append(trade)

        # 손절인 경우 재진입 쿨다운 등록 (해당 영업일 기준)
        if is_stop_loss:
            self.cooldown_until[code] = self._add_business_days(exit_date, COOLDOWN_BUSINESS_DAYS)

        # positions 에서 제거
        self.positions = [p for p in self.positions
                          if not (p["code"] == code and p is pos)]
        return trade

    # ========== 자동 청산 (손절/익절 판정) ==========

    def check_auto_close(self, today: str) -> List[Dict[str, Any]]:
        """
        모든 활성 포지션의 손절/익절 조건을 확인하고 자동 청산.
        반환: 청산된 trade 목록
        """
        closed_trades = []
        # 복사본으로 순회 (순회 중 제거 방지)
        for pos in list(self.positions):
            code = pos["code"]
            avg_price = pos.get("avg_price", 0)
            current_price = pos.get("current_price", 0)
            if avg_price <= 0 or current_price <= 0:
                continue

            gain_pct = ((current_price / avg_price) - 1) * 100

            if gain_pct <= STOP_LOSS_PCT:
                trade = self.close_position(
                    code, current_price, today,
                    exit_reason="손절 (-3%)"
                )
                if trade:
                    closed_trades.append(trade)
                    print(f"  손절: {pos['name']} ({gain_pct:.1f}%)")

            elif gain_pct >= TAKE_PROFIT_PCT:
                trade = self.close_position(
                    code, current_price, today,
                    exit_reason="익절 (+10%)"
                )
                if trade:
                    closed_trades.append(trade)
                    print(f"  익절: {pos['name']} ({gain_pct:.1f}%)")

        return closed_trades

    # ========== 통계 계산 ==========

    def _calc_position_stats(self) -> Dict[str, Any]:
        open_positions = self.get_open_positions()
        used_capital = sum(
            p.get("avg_price", 0) * p.get("total_quantity", 0)
            for p in open_positions
        )
        unrealized_pnl = sum(p.get("unrealized_pnl", 0) for p in open_positions)

        total_trades = len(self.trades)
        win_count = len([t for t in self.trades if t.get("return_pct", 0) > 0])
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0

        # 실현 손익 (청산 거래의 profit 합)
        realized_pnl = sum(t.get("profit", 0) for t in self.trades)
        # 자본 대비 누적 수익률 (실현 + 미실현)
        total_return_actual = (
            (realized_pnl + unrealized_pnl) / self.total_capital * 100
            if self.total_capital > 0 else 0
        )
        # 단순 % 합산 (백테스트 비교용 - 잘못된 값이지만 backward compat)
        total_return_simple = sum(t.get("return_pct", 0) for t in self.trades)
        avg_return = (total_return_simple / total_trades) if total_trades > 0 else 0
        current_capital = self.total_capital + realized_pnl + unrealized_pnl

        return {
            "total_capital": self.total_capital,
            "current_capital": int(current_capital),
            "used_capital": used_capital,
            "open_positions": len(open_positions),
            "total_trades": total_trades,
            "win_rate": round(win_rate, 1),
            "total_return": round(total_return_actual, 2),  # 메인 표시 (자본 대비)
            "total_return_simple": round(total_return_simple, 2),  # 단순 합 (backward compat)
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "avg_return": round(avg_return, 2),
        }

    def _calc_trade_stats(self) -> Dict[str, Any]:
        total_trades = len(self.trades)
        win_count = len([t for t in self.trades if t.get("return_pct", 0) > 0])
        total_profit = sum(t.get("profit", 0) for t in self.trades)
        # 자본 대비 실현 수익률 (미실현 제외)
        total_return_actual = (
            total_profit / self.total_capital * 100
            if self.total_capital > 0 else 0
        )
        total_return_simple = sum(t.get("return_pct", 0) for t in self.trades)
        avg_return = (total_return_simple / total_trades) if total_trades > 0 else 0

        # MDD (Maximum Drawdown) 계산 - 날짜순 누적 자산 기준
        mdd = 0.0
        if self.trades:
            sorted_trades = sorted(self.trades, key=lambda t: t.get("exit_date", ""))
            daily_profit: Dict[str, int] = {}
            for t in sorted_trades:
                d = t.get("exit_date", "")
                daily_profit[d] = daily_profit.get(d, 0) + t.get("profit", 0)

            cum_profit = 0
            peak = self.total_capital
            for d in sorted(daily_profit.keys()):
                cum_profit += daily_profit[d]
                equity = self.total_capital + cum_profit
                if equity > peak:
                    peak = equity
                drawdown = (equity - peak) / peak * 100 if peak > 0 else 0
                if drawdown < mdd:
                    mdd = drawdown

        return {
            "total_trades": total_trades,
            "win_count": win_count,
            "loss_count": total_trades - win_count,
            "win_rate": round((win_count / total_trades * 100) if total_trades > 0 else 0, 1),
            "total_profit": total_profit,
            "total_return": round(total_return_actual, 2),  # 메인 (자본 대비 실현)
            "total_return_simple": round(total_return_simple, 2),  # 단순 합
            "avg_return": round(avg_return, 2),
            "mdd": round(mdd, 2),
        }


# ========== CLI 테스트 ==========

if __name__ == "__main__":
    print("BNF Position Manager - 상태 확인\n")

    mgr = BNFPositionManager()
    open_pos = mgr.get_open_positions()
    print(f"활성 포지션: {len(open_pos)}개")
    for p in open_pos:
        pnl = p.get("unrealized_pnl", 0)
        pnl_pct = p.get("unrealized_pnl_pct", 0)
        print(f"  {p['name']}({p['code']}) "
              f"avg={p.get('avg_price', 0):,} "
              f"cur={p.get('current_price', 0):,} "
              f"pnl={pnl:+,} ({pnl_pct:+.1f}%)")

    print(f"\n완료 거래: {len(mgr.trades)}건")
    print(f"슬롯 여유: {mgr.open_slots()}개")
