#!/usr/bin/env python3
"""
볼린저 스윙 포지션 체크 스크립트

워크플로우(bollinger-swing.yml)에서 호출되어:
1. 기존 볼린저 포지션 가격 업데이트
2. 청산 조건 체크 (손절 -5% / 익절 MA20 도달 또는 +7% / 기한 5영업일)
3. 신규 후보 종목 진입
4. bollinger_positions.json + bollinger_trades.json 저장

BNF의 position.py (BNFPositionManager) 를 재사용하되,
볼린저 스윙 전용 청산 조건을 적용한다.
"""

import json
import os
import sys
import warnings
from datetime import datetime, timedelta

import numpy as np
import pytz

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from paper_trading.bnf.position import BNFPositionManager, POSITION_RATIO

# ─── 볼린저 스윙 전용 상수 ───
BOLLINGER_STOP_LOSS_PCT = -5.0     # 손절 -5%
BOLLINGER_TAKE_PROFIT_PCT = 7.0    # 익절 +7%
MAX_HOLDING_DAYS = 5               # 최대 보유 영업일
BB_PERIOD = 20                     # 중심선 계산용


def count_business_days(start_date: str, end_date: str) -> int:
    """두 날짜 사이의 영업일 수 (토/일 제외, 공휴일 미반영)"""
    try:
        # 날짜 형식 자동 판별
        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                sd = datetime.strptime(start_date, fmt)
                break
            except ValueError:
                continue
        else:
            return 0

        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                ed = datetime.strptime(end_date, fmt)
                break
            except ValueError:
                continue
        else:
            return 0

        days = 0
        current = sd
        while current < ed:
            current += timedelta(days=1)
            if current.weekday() < 5:  # 월~금
                days += 1
        return days
    except Exception:
        return 0


def get_bb_middle(code: str, date_str: str) -> float:
    """종목의 현재 볼린저밴드 중심선(MA20) 계산"""
    try:
        from pykrx import stock
        end_dt = datetime.strptime(date_str, "%Y%m%d")
        start_dt = end_dt - timedelta(days=BB_PERIOD + 15)
        df = stock.get_market_ohlcv_by_date(
            start_dt.strftime("%Y%m%d"), date_str, code
        )
        if df.empty or len(df) < BB_PERIOD:
            return 0
        closes = df["종가"].astype(float).values
        return float(np.mean(closes[-BB_PERIOD:]))
    except Exception:
        return 0


def main():
    warnings.filterwarnings("ignore")
    kst = pytz.timezone("Asia/Seoul")
    now = datetime.now(kst)
    today = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    today_str = now.strftime("%Y%m%d")
    start_str = (now - timedelta(days=10)).strftime("%Y%m%d")

    print(f"볼린저 스윙 포지션 체크 - {today} {time_str}")
    print("=" * 60)

    # 볼린저 전용 파일 경로로 매니저 생성
    mgr = BNFPositionManager(data_dir="data/bnf")
    # 파일 경로를 볼린저 전용으로 오버라이드
    mgr.positions_file = mgr.data_dir / "bollinger_positions.json"
    mgr.history_file = mgr.data_dir / "bollinger_trades.json"
    mgr.load()  # 새 파일 경로로 재로드

    # 후보 종목 로드
    candidates_file = os.path.join(PROJECT_ROOT, "data/bnf/bollinger_candidates.json")
    if not os.path.exists(candidates_file):
        print("후보 종목 파일이 없습니다. (bollinger_candidates.json)")
        mgr.save(f"{today} {time_str}")
        return

    with open(candidates_file, "r", encoding="utf-8") as f:
        candidates_data = json.load(f)

    candidates = candidates_data.get("candidates", [])
    print(f"후보 종목: {len(candidates)}개")

    try:
        from pykrx import stock
    except ImportError:
        print("pykrx 설치 필요: pip install pykrx")
        mgr.save(f"{today} {time_str}")
        return

    # --- 1) 기존 포지션 가격 업데이트 ---
    open_positions = mgr.get_open_positions()
    print(f"\n[가격 업데이트] 활성 포지션 {len(open_positions)}개")

    for pos in open_positions:
        code = pos["code"]
        try:
            df = stock.get_market_ohlcv_by_date(start_str, today_str, code)
            if not df.empty:
                current_price = int(df.iloc[-1]["종가"])
                mgr.update_price(code, current_price)
                pnl_pct = pos.get("unrealized_pnl_pct", 0)
                print(f"  {pos['name']}({code}): {current_price:,}원 ({pnl_pct:+.1f}%)")
        except Exception as e:
            print(f"  가격 조회 실패: {code} - {e}")

    # --- 2) 볼린저 스윙 청산 조건 체크 ---
    closed_trades = []
    for pos in list(mgr.get_open_positions()):
        code = pos["code"]
        avg_price = pos.get("avg_price", 0)
        current_price = pos.get("current_price", 0)
        entry_date = pos.get("entry_date", "")

        if avg_price <= 0 or current_price <= 0:
            continue

        gain_pct = ((current_price / avg_price) - 1) * 100

        # 2a) 손절 체크 (-5%)
        if gain_pct <= BOLLINGER_STOP_LOSS_PCT:
            trade = mgr.close_position(
                code, current_price, today,
                exit_reason=f"손절 ({gain_pct:+.1f}%, 기준 {BOLLINGER_STOP_LOSS_PCT}%)"
            )
            if trade:
                closed_trades.append(trade)
                print(f"  손절: {pos['name']} ({gain_pct:+.1f}%)")
            continue

        # 2b) 익절 체크 (+7%)
        if gain_pct >= BOLLINGER_TAKE_PROFIT_PCT:
            trade = mgr.close_position(
                code, current_price, today,
                exit_reason=f"익절 ({gain_pct:+.1f}%, 기준 +{BOLLINGER_TAKE_PROFIT_PCT}%)"
            )
            if trade:
                closed_trades.append(trade)
                print(f"  익절(+{BOLLINGER_TAKE_PROFIT_PCT}%): {pos['name']} ({gain_pct:+.1f}%)")
            continue

        # 2c) 중심선(MA20) 도달 체크
        bb_middle = get_bb_middle(code, today_str)
        if bb_middle > 0 and current_price >= bb_middle:
            trade = mgr.close_position(
                code, current_price, today,
                exit_reason=f"BB중심선 도달 (MA20={bb_middle:,.0f}, 현재={current_price:,})"
            )
            if trade:
                closed_trades.append(trade)
                print(f"  BB중심선 도달: {pos['name']} (MA20={bb_middle:,.0f})")
            continue

        # 2d) 기한 청산 (5영업일)
        if entry_date:
            biz_days = count_business_days(entry_date, today)
            if biz_days >= MAX_HOLDING_DAYS:
                trade = mgr.close_position(
                    code, current_price, today,
                    exit_reason=f"기한 청산 ({biz_days}영업일, 최대 {MAX_HOLDING_DAYS}일)"
                )
                if trade:
                    closed_trades.append(trade)
                    print(f"  기한 청산: {pos['name']} ({biz_days}영업일, {gain_pct:+.1f}%)")
                continue

    if closed_trades:
        print(f"\n[자동 청산] {len(closed_trades)}건")
    else:
        print("\n[자동 청산] 해당 없음")

    # --- 3) 신규 진입 ---
    slots = mgr.open_slots()
    print(f"\n[신규 진입] 가능 슬롯: {slots}개")

    position_size = mgr.total_capital * POSITION_RATIO

    for candidate in candidates[:slots]:
        code = candidate["code"]
        name = candidate["name"]

        if mgr.has_open_position(code):
            print(f"  이미 보유 중: {name}")
            continue

        price = candidate.get("price", 0)
        if price <= 0:
            print(f"  가격 정보 없음: {name}")
            continue

        quantity = int(position_size / price)
        if quantity <= 0:
            print(f"  수량 부족: {name} (가격 {price:,}원)")
            continue

        reason = candidate.get("reasons", candidate.get("selection_reason", ""))
        pos = mgr.enter_position(
            code=code, name=name, price=price, quantity=quantity,
            date=today, time=time_str, selection_reason=reason,
        )
        if pos:
            print(f"  진입: {name}({code}) @ {price:,}원 x {quantity}주")

    # --- 4) 저장 ---
    mgr.save(f"{today} {time_str}")

    # --- 요약 ---
    open_pos = mgr.get_open_positions()
    print("\n" + "=" * 60)
    print(f"오픈 포지션: {len(open_pos)}개")
    trade_stats = mgr._calc_trade_stats()
    print(
        f"총 거래: {trade_stats['total_trades']}건, "
        f"승률: {trade_stats['win_rate']:.1f}%"
    )


if __name__ == "__main__":
    main()
