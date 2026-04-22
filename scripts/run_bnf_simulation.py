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


# 신규 진입을 스킵할 candidates 기준일 영업일 임계값
# (후보 생성 배치가 T일 18:00, 시뮬레이션이 T+1 09:30 실행 → 정상이면 1영업일)
STALE_CANDIDATES_BIZDAYS = 2


def _business_days_between(date_str, target_date) -> int:
    """date_str(YYYY-MM-DD) 다음날부터 target_date까지의 주중 일수 (공휴일 미반영)."""
    from datetime import date as _date, timedelta as _td
    try:
        y, m, d = map(int, date_str.split('-'))
    except Exception:
        return 0
    src = _date(y, m, d)
    tgt = target_date if isinstance(target_date, _date) else target_date.date()
    if src >= tgt:
        return 0
    count = 0
    cur = src + _td(days=1)
    while cur <= tgt:
        if cur.weekday() < 5:
            count += 1
        cur += _td(days=1)
    return count


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
    cand_date = candidates_data.get("date", "")
    print(f"후보 종목: {len(candidates)}개 (기준일: {cand_date or '미상'})")

    if not candidates:
        print("후보 종목이 없습니다.")
        mgr.save(f"{today} {time_str}")
        return

    # 후보 기준일이 오래됐으면 신규 진입 스킵 (기존 포지션 관리는 계속 진행)
    skip_new_entry = False
    if cand_date:
        biz_age = _business_days_between(cand_date, now)
        if biz_age >= STALE_CANDIDATES_BIZDAYS:
            print(f"⚠️  candidates.json이 {biz_age}영업일 오래됨 → 신규 진입 스킵 "
                  f"(선정 배치 재실행 필요)")
            skip_new_entry = True

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
    if skip_new_entry:
        print(f"\n[신규 진입] 스킵 (stale candidates)")
    else:
        print(f"\n[신규 진입] 가능 슬롯: {slots}개")

    position_size = mgr.total_capital * POSITION_RATIO

    entry_iter = [] if skip_new_entry else candidates[:slots]
    for candidate in entry_iter:
        code = candidate["code"]
        name = candidate["name"]

        if mgr.has_open_position(code):
            print(f"  이미 보유 중: {name}")
            continue

        cand_price = candidate.get("price", 0)
        # 당일 시가를 우선 사용 (체결 가능 가격). 실패 시 선정일 종가로 폴백.
        entry_price = cand_price
        try:
            df = stock.get_market_ohlcv(today_str, today_str, code)
            if not df.empty:
                open_p = int(df.iloc[-1]["시가"])
                if open_p > 0:
                    entry_price = open_p
        except Exception as e:
            print(f"  {name}({code}) 당일 시가 조회 실패({e}) → 선정가 폴백")

        if entry_price <= 0:
            print(f"  가격 정보 없음: {name}")
            continue

        quantity = int(position_size / entry_price)
        if quantity <= 0:
            print(f"  수량 부족: {name} (가격 {entry_price:,}원)")
            continue

        reason = candidate.get("reasons", "")
        pos = mgr.enter_position(
            code=code, name=name, price=entry_price, quantity=quantity,
            date=today, time=time_str, selection_reason=reason,
        )
        if pos:
            note = ""
            if cand_price and entry_price != cand_price:
                gap = (entry_price - cand_price) / cand_price * 100
                note = f" (갭 {gap:+.1f}% vs 선정가 {cand_price:,})"
            print(f"  진입: {name}({code}) @ {entry_price:,}원 x {quantity}주{note}")

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
