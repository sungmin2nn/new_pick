"""
BNF Simulator 테스트 스크립트 (저장된 분봉 데이터 활용)
"""

import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from paper_trading.bnf.simulator import BNFSimulator


def test_with_saved_data():
    """저장된 intraday JSON에서 분봉 데이터를 직접 활용한 테스트"""

    data_dir = Path(__file__).parent.parent.parent / "data" / "intraday"

    # 최근 파일 찾기
    if not data_dir.exists():
        print(f"데이터 디렉토리 없음: {data_dir}")
        return

    files = sorted(data_dir.glob("intraday_*.json"), reverse=True)

    if not files:
        print("분봉 데이터 파일 없음")
        return

    # 여러 파일 테스트
    simulator = BNFSimulator(capital=1_000_000)

    for test_file in files[:3]:  # 최근 3일 테스트
        print(f"\n{'='*70}")
        print(f"테스트 파일: {test_file.name}")
        print(f"{'='*70}")

        with open(test_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        date_str = data.get('date', '')

        # 실제 분봉 데이터를 생성 (간단한 시뮬레이션)
        # 실제로는 IntradayCollector에서 가져온 데이터를 사용해야 하지만,
        # 여기서는 데모를 위해 시뮬레이션 데이터 생성
        minute_data = generate_sample_minute_data()

        if minute_data:
            result = simulator.simulate_trade(
                code="095340",
                name="ISC",
                date_str=date_str,
                minute_data=minute_data,
                entry_amount=simulator.INITIAL_CAPITAL
            )

            if result:
                simulator.print_detailed_result(result)

        # 한 개만 테스트
        break


def generate_sample_minute_data():
    """
    테스트용 샘플 분봉 데이터 생성
    실제 트레이딩 패턴을 시뮬레이션
    """
    import random

    minute_data = []
    base_price = 240000
    current_price = base_price

    # 09:00 ~ 15:20 (6시간 20분 = 380분)
    hour = 9
    minute = 0

    # 시나리오: 하락 -> 반등 -> 상승 -> 조정 -> 재상승
    for i in range(380):
        time_str = f"{hour:02d}:{minute:02d}:00"

        # 가격 패턴 생성
        if i < 10:  # 09:00~09:10 - 하락 (음봉들)
            change = random.randint(-2000, -500)
            is_red = True
        elif i < 30:  # 09:10~09:30 - 반등 (양봉 시작)
            change = random.randint(500, 2000)
            is_red = False
        elif i < 60:  # 09:30~10:00 - 강한 상승
            change = random.randint(1000, 3000)
            is_red = False
        elif i < 90:  # 10:00~10:30 - 조정 (음봉)
            change = random.randint(-1500, -300)
            is_red = True
        elif i < 180:  # 10:30~12:00 - 재상승
            change = random.randint(200, 2000)
            is_red = False
        else:  # 12:00~ - 횡보 및 소폭 변동
            change = random.randint(-1000, 1000)
            is_red = change < 0

        current_price += change

        # OHLC 생성
        if is_red:  # 음봉
            open_price = current_price + abs(change)
            close_price = current_price
            high = open_price + random.randint(0, 1000)
            low = close_price - random.randint(0, 500)
        else:  # 양봉
            open_price = current_price - abs(change)
            close_price = current_price
            high = close_price + random.randint(0, 1000)
            low = open_price - random.randint(0, 500)

        minute_data.append({
            'time': time_str,
            'open': max(1000, open_price),
            'high': max(1000, high),
            'low': max(1000, low),
            'close': max(1000, close_price),
            'volume': random.randint(1000, 10000)
        })

        # 시간 증가
        minute += 1
        if minute >= 60:
            minute = 0
            hour += 1

    return minute_data


def test_trailing_stop_logic():
    """트레일링 스탑 로직 단독 테스트"""
    print("\n[트레일링 스탑 로직 테스트]")
    print("="*70)

    simulator = BNFSimulator()
    entry_price = 100000

    test_cases = [
        (100000, 0.0, "초기 진입 (0%)"),
        (102000, 2.0, "소폭 상승 (2%)"),
        (103000, 3.0, "본전 이동 시점 (3%)"),
        (105000, 5.0, "트레일링 시작 (5%)"),
        (108000, 8.0, "트레일링 중 (8%)"),
        (110000, 10.0, "-3% 트레일링 시작 (10%)"),
        (115000, 15.0, "고수익 (15%)"),
    ]

    print(f"\n진입가: {entry_price:,}원\n")
    print(f"{'현재가':<10} {'수익률':<10} {'손절가':<10} {'설명':<30}")
    print("-"*70)

    for current_high, profit_pct, desc in test_cases:
        stop_price = simulator.calculate_trailing_stop(entry_price, current_high, profit_pct)
        stop_pct = (stop_price - entry_price) / entry_price * 100

        print(f"{current_high:>9,}원 {profit_pct:>7.1f}% {stop_price:>9,}원 ({stop_pct:+.1f}%) {desc}")

    print("="*70)


if __name__ == "__main__":
    print("[BNF Simulator 종합 테스트]\n")

    # 1. 트레일링 스탑 로직 테스트
    test_trailing_stop_logic()

    # 2. 전체 시뮬레이션 테스트
    test_with_saved_data()

    print("\n[테스트 완료]")
