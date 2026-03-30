"""
BNF Simulator 사용 예제
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from paper_trading.bnf.simulator import BNFSimulator
from intraday_collector import IntradayCollector


def example_1_basic_simulation():
    """예제 1: 기본 시뮬레이션"""
    print("\n" + "="*70)
    print("예제 1: 기본 시뮬레이션")
    print("="*70)

    # 1. 시뮬레이터 초기화
    simulator = BNFSimulator(capital=1_000_000)

    # 2. 분봉 데이터 수집
    collector = IntradayCollector()
    minute_data = collector.get_minute_data(
        stock_code="095340",
        date_str="20260330"
    )

    if not minute_data:
        print("분봉 데이터 없음 (당일 장중 데이터만 조회 가능)")
        return

    # 3. 시뮬레이션 실행
    result = simulator.simulate_trade(
        code="095340",
        name="ISC",
        date_str="20260330",
        minute_data=minute_data,
        entry_amount=1_000_000
    )

    # 4. 결과 출력
    if result:
        simulator.print_detailed_result(result)
    else:
        print("진입 신호 없음")


def example_2_trailing_stop_calculation():
    """예제 2: 트레일링 스탑 계산"""
    print("\n" + "="*70)
    print("예제 2: 트레일링 스탑 계산")
    print("="*70)

    simulator = BNFSimulator()

    # 시나리오: 100,000원에 진입
    entry_price = 100000

    scenarios = [
        (100000, 0.0, "초기 진입"),
        (102000, 2.0, "2% 상승"),
        (103000, 3.0, "3% 상승 (본전 이동)"),
        (105000, 5.0, "5% 상승 (트레일링 시작)"),
        (110000, 10.0, "10% 상승 (강화 트레일링)"),
        (115000, 15.0, "15% 상승"),
    ]

    print(f"\n진입가: {entry_price:,}원\n")
    print(f"{'현재 고점':<12} {'수익률':<8} {'손절가':<12} {'손절률':<8} {'상태':<20}")
    print("-"*70)

    for high_price, profit_pct, status in scenarios:
        stop_price = simulator.calculate_trailing_stop(
            entry_price=entry_price,
            current_high=high_price,
            profit_pct=profit_pct
        )
        stop_pct = (stop_price - entry_price) / entry_price * 100

        print(f"{high_price:>11,}원 {profit_pct:>6.1f}% {stop_price:>11,}원 {stop_pct:>6.1f}% {status:<20}")


def example_3_custom_parameters():
    """예제 3: 파라미터 커스터마이징"""
    print("\n" + "="*70)
    print("예제 3: 파라미터 커스터마이징")
    print("="*70)

    # 커스텀 파라미터로 시뮬레이터 생성
    simulator = BNFSimulator(capital=2_000_000)

    # 파라미터 조정
    simulator.INITIAL_STOP = -2.0           # 초기 손절 -2%
    simulator.BREAKEVEN_THRESHOLD = 2.5     # 2.5% 이상 시 본전 이동
    simulator.TRAIL_START = 4.0             # 4% 이상 시 트레일링 시작
    simulator.TRAIL_PERCENT_1 = 1.5         # 고점 대비 -1.5%
    simulator.TRAIL_PERCENT_2 = 2.5         # 고점 대비 -2.5%

    simulator.ENTRY_WEIGHTS = [0.4, 0.4, 0.2]   # 진입 비중 40%, 40%, 20%
    simulator.EXIT_WEIGHTS = [0.25, 0.5, 0.25]  # 청산 비중 25%, 50%, 25%
    simulator.EXIT_TARGETS = [3.0, 7.0, None]   # 청산 목표 +3%, +7%

    print("\n커스터마이징된 파라미터:")
    print(f"  자본금: {simulator.capital:,}원")
    print(f"  초기 손절: {simulator.INITIAL_STOP}%")
    print(f"  본전 이동: {simulator.BREAKEVEN_THRESHOLD}% 이상")
    print(f"  트레일링 시작: {simulator.TRAIL_START}% 이상")
    print(f"  트레일링 비율: {simulator.TRAIL_PERCENT_1}% / {simulator.TRAIL_PERCENT_2}%")
    print(f"  진입 비중: {simulator.ENTRY_WEIGHTS}")
    print(f"  청산 비중: {simulator.EXIT_WEIGHTS}")
    print(f"  청산 목표: {simulator.EXIT_TARGETS}")


def example_4_entry_exit_analysis():
    """예제 4: 진입/청산 포인트 분석"""
    print("\n" + "="*70)
    print("예제 4: 진입/청산 포인트 분석")
    print("="*70)

    simulator = BNFSimulator()

    # 샘플 분봉 데이터 (간단한 예제)
    minute_data = []
    base_price = 100000

    # 09:00 ~ 09:30 샘플 데이터
    prices = [
        # 하락 (음봉들)
        100000, 99500, 99000, 98500, 98000,
        # 반등 (양봉)
        98500, 99000, 99500, 100000, 100500,
        # 상승
        101000, 102000, 103000, 102500, 103500,
        # 추가 상승
        104000, 105000, 106000, 107000, 108000,
    ]

    for i, price in enumerate(prices):
        hour = 9
        minute = i
        is_green = i >= 5  # 5번째부터 양봉

        if is_green:
            open_p = price - 200
            close_p = price
        else:
            open_p = price + 200
            close_p = price

        minute_data.append({
            'time': f"{hour:02d}:{minute:02d}:00",
            'open': open_p,
            'high': max(open_p, close_p) + 100,
            'low': min(open_p, close_p) - 100,
            'close': close_p,
            'volume': 1000
        })

    # 진입점 탐색
    print("\n[진입점 탐색]")
    entries = simulator.find_entry_points(minute_data, entry_amount=1_000_000)

    if entries:
        for entry in entries:
            print(f"  {entry.entry_num}차 진입:")
            print(f"    시간: {entry.time}")
            print(f"    가격: {entry.price:,}원")
            print(f"    수량: {entry.quantity}주")
            print(f"    비중: {entry.weight*100:.0f}% ({entry.amount:,}원)")
            print(f"    사유: {entry.reason}")

        # 청산점 탐색
        print("\n[청산점 탐색]")
        exits = simulator.find_exit_points(entries, minute_data)

        if exits:
            for exit_point in exits:
                print(f"  {exit_point.exit_num}차 청산:")
                print(f"    시간: {exit_point.time}")
                print(f"    가격: {exit_point.price:,}원")
                print(f"    수량: {exit_point.quantity}주")
                print(f"    수익: {exit_point.profit_pct:+.2f}% ({exit_point.profit_amount:+,}원)")
                print(f"    사유: {exit_point.reason}")
    else:
        print("  진입 신호 없음")


def example_5_result_data_access():
    """예제 5: 결과 데이터 접근"""
    print("\n" + "="*70)
    print("예제 5: 결과 데이터 접근")
    print("="*70)

    # 시뮬레이션 결과를 딕셔너리로 변환하여 JSON 저장 가능
    from paper_trading.bnf.simulator import BNFTradeResult, EntryPoint, ExitPoint

    # 샘플 결과 생성
    result = BNFTradeResult(
        code="095340",
        name="ISC",
        date="20260330",
        entries=[
            EntryPoint(1, "09:10:00", 100000, 0.3, 300000, 3, "첫 반등"),
            EntryPoint(2, "09:15:00", 102000, 0.4, 400000, 3, "상승 확인"),
            EntryPoint(3, "09:20:00", 101000, 0.3, 300000, 2, "풀백 진입"),
        ],
        exits=[
            ExitPoint(1, "10:00:00", 105000, 0.3, 3, 5.0, 15000, "+5% 목표"),
            ExitPoint(2, "10:30:00", 110000, 0.4, 3, 10.0, 30000, "+10% 목표"),
            ExitPoint(3, "15:20:00", 108000, 0.3, 2, 8.0, 16000, "장 마감"),
        ],
        total_entry_amount=1000000,
        total_quantity=8,
        avg_entry_price=100875.0,
        total_exit_amount=1061000,
        total_profit_pct=6.1,
        total_profit_amount=61000,
        max_profit_pct=12.5,
        max_loss_pct=-2.3
    )

    # 딕셔너리로 변환
    result_dict = result.to_dict()

    print("\n결과 데이터 구조:")
    print(f"  종목: {result_dict['name']} ({result_dict['code']})")
    print(f"  평균 진입가: {result_dict['avg_entry_price']:,.2f}원")
    print(f"  총 수익률: {result_dict['total_profit_pct']:+.2f}%")
    print(f"  진입 횟수: {len(result_dict['entries'])}회")
    print(f"  청산 횟수: {len(result_dict['exits'])}회")

    # JSON으로 저장 가능
    import json
    json_str = json.dumps(result_dict, ensure_ascii=False, indent=2)
    print(f"\nJSON 저장 가능: {len(json_str)} bytes")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("BNF Simulator 사용 예제")
    print("="*70)

    # 예제 2: 트레일링 스탑 계산 (항상 실행 가능)
    example_2_trailing_stop_calculation()

    # 예제 3: 파라미터 커스터마이징
    example_3_custom_parameters()

    # 예제 4: 진입/청산 포인트 분석
    example_4_entry_exit_analysis()

    # 예제 5: 결과 데이터 접근
    example_5_result_data_access()

    # 예제 1: 기본 시뮬레이션 (실제 데이터 필요)
    # example_1_basic_simulation()  # 주석 처리 (당일 장중 데이터 필요)

    print("\n" + "="*70)
    print("모든 예제 완료!")
    print("="*70)
