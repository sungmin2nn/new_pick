#!/usr/bin/env python3
"""
BNF 시뮬레이션 실행 스크립트

워크플로우(bnf-simulation.yml)에서 호출되어:
1. 기존 포지션 가격 업데이트
2. 손절/익절 자동 청산
3. 신규 후보 종목 진입
4. positions.json + trade_history.json 저장
"""

import json
import os
import sys
import warnings
from datetime import datetime, timedelta

import pytz

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paper_trading.bnf.position import BNFPositionManager, POSITION_RATIO


def main():
    warnings.filterwarnings("ignore")
    kst = pytz.timezone("Asia/Seoul")
    now = datetime.now(kst)
    today = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    today_str = now.strftime("%Y%m%d")
    start_str = (now - timedelta(days=10)).strftime("%Y%m%d")

    print(f"BNF 시뮬레이션 - {today} {time_str}")
    print("=" * 60)

    # 매니저 로드
    mgr = BNFPositionManager(data_dir="data/bnf")

    # 후보 종목 로드
    candidates_file = "data/bnf/candidates.json"
    if not os.path.exists(candidates_file):
        print("후보 종목 파일이 없습니다.")
        mgr.save(f"{today} {time_str}")
        return

    with open(candidates_file, "r", encoding="utf-8") as f:
        candidates_data = json.load(f)

    candidates = candidates_data.get("candidates", [])
    print(f"후보 종목: {len(candidates)}개")

    if not candidates:
        print("후보 종목이 없습니다.")
        mgr.save(f"{today} {time_str}")
        return

    try:
        from pykrx import stock
    except ImportError:
        print("pykrx 설치 필요: pip install pykrx")
        mgr.save(f"{today} {time_str}")
        return

    # --- 1) 기존 포지션 가격 업데이트 ---
    print(f"\n[가격 업데이트] 활성 포지션 {len(mgr.get_open_positions())}개")
    for pos in mgr.get_open_positions():
        code = pos["code"]
        try:
            df = stock.get_market_ohlcv(start_str, today_str, code)
            if not df.empty:
                current_price = int(df.iloc[-1]["종가"])
                mgr.update_price(code, current_price)
                pnl_pct = pos.get("unrealized_pnl_pct", 0)
                print(f"  {pos['name']}({code}): {current_price:,}원 ({pnl_pct:+.1f}%)")
        except Exception as e:
            print(f"  가격 조회 실패: {code} - {e}")

    # --- 2) 손절/익절 자동 청산 ---
    closed = mgr.check_auto_close(today)
    if closed:
        print(f"\n[자동 청산] {len(closed)}건")
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

        reason = candidate.get("reasons", "")
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
    print(f"총 거래: {len(mgr.trades)}건, "
          f"승률: {mgr._calc_trade_stats()['win_rate']:.1f}%")


if __name__ == "__main__":
    main()
