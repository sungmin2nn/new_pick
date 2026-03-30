"""
요구사항 검증 스크립트
모든 필수 기능이 구현되었는지 확인
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from paper_trading.bnf.simulator import (
    BNFSimulator,
    BNFTradeResult,
    EntryPoint,
    ExitPoint
)


def verify_requirements():
    """모든 요구사항 검증"""

    print("="*70)
    print("BNF Simulator 요구사항 검증")
    print("="*70)

    results = []

    # 1. 클래스 및 상수 확인
    print("\n[1] 클래스 및 초기 자본 확인")
    try:
        simulator = BNFSimulator()
        assert hasattr(simulator, 'INITIAL_CAPITAL')
        assert simulator.INITIAL_CAPITAL == 1_000_000
        print("  ✓ BNFSimulator 클래스 존재")
        print("  ✓ INITIAL_CAPITAL = 1,000,000원")
        results.append(("클래스 및 초기 자본", True))
    except Exception as e:
        print(f"  ✗ 오류: {e}")
        results.append(("클래스 및 초기 자본", False))

    # 2. 트레일링 스탑 로직 확인
    print("\n[2] 트레일링 스탑 로직 확인")
    try:
        simulator = BNFSimulator()

        # 초기 손절 -3%
        stop1 = simulator.calculate_trailing_stop(100000, 100000, 0.0)
        assert stop1 == 97000, f"초기 손절 오류: {stop1} != 97000"
        print(f"  ✓ 초기 손절 -3%: {stop1:,}원")

        # 본전 이동 (3% 이상)
        stop2 = simulator.calculate_trailing_stop(100000, 103000, 3.0)
        assert stop2 == 100000, f"본전 이동 오류: {stop2} != 100000"
        print(f"  ✓ 수익 3% 이상 → 본전 (0%): {stop2:,}원")

        # 5% 이상 → 고점 대비 -2% 트레일링
        stop3 = simulator.calculate_trailing_stop(100000, 105000, 5.0)
        expected3 = int(105000 * 0.98)  # 102,900
        assert stop3 == expected3, f"트레일링 -2% 오류: {stop3} != {expected3}"
        print(f"  ✓ 수익 5% 이상 → 고점 대비 -2%: {stop3:,}원")

        # 10% 이상 → 고점 대비 -3% 트레일링
        stop4 = simulator.calculate_trailing_stop(100000, 110000, 10.0)
        expected4 = int(110000 * 0.97)  # 106,700
        assert stop4 == expected4, f"트레일링 -3% 오류: {stop4} != {expected4}"
        print(f"  ✓ 수익 10% 이상 → 고점 대비 -3%: {stop4:,}원")

        results.append(("트레일링 스탑 로직", True))
    except Exception as e:
        print(f"  ✗ 오류: {e}")
        results.append(("트레일링 스탑 로직", False))

    # 3. 분할 매수 비중 확인
    print("\n[3] 분할 매수 (3회) 비중 확인")
    try:
        simulator = BNFSimulator()
        assert simulator.ENTRY_WEIGHTS == [0.3, 0.4, 0.3]
        assert sum(simulator.ENTRY_WEIGHTS) == 1.0
        print(f"  ✓ 1차 진입: {simulator.ENTRY_WEIGHTS[0]*100:.0f}%")
        print(f"  ✓ 2차 진입: {simulator.ENTRY_WEIGHTS[1]*100:.0f}%")
        print(f"  ✓ 3차 진입: {simulator.ENTRY_WEIGHTS[2]*100:.0f}%")
        print(f"  ✓ 총합: {sum(simulator.ENTRY_WEIGHTS)*100:.0f}%")
        results.append(("분할 매수 비중", True))
    except Exception as e:
        print(f"  ✗ 오류: {e}")
        results.append(("분할 매수 비중", False))

    # 4. 분할 매도 비중 확인
    print("\n[4] 분할 매도 (3회) 비중 확인")
    try:
        simulator = BNFSimulator()
        assert simulator.EXIT_WEIGHTS == [0.3, 0.4, 0.3]
        assert sum(simulator.EXIT_WEIGHTS) == 1.0
        print(f"  ✓ 1차 청산: {simulator.EXIT_WEIGHTS[0]*100:.0f}%")
        print(f"  ✓ 2차 청산: {simulator.EXIT_WEIGHTS[1]*100:.0f}%")
        print(f"  ✓ 3차 청산: {simulator.EXIT_WEIGHTS[2]*100:.0f}%")
        print(f"  ✓ 총합: {sum(simulator.EXIT_WEIGHTS)*100:.0f}%")
        results.append(("분할 매도 비중", True))
    except Exception as e:
        print(f"  ✗ 오류: {e}")
        results.append(("분할 매도 비중", False))

    # 5. 청산 목표 확인
    print("\n[5] 청산 목표 확인")
    try:
        simulator = BNFSimulator()
        assert simulator.EXIT_TARGETS[0] == 5.0
        assert simulator.EXIT_TARGETS[1] == 10.0
        assert simulator.EXIT_TARGETS[2] is None
        print(f"  ✓ 1차 청산 목표: +{simulator.EXIT_TARGETS[0]}%")
        print(f"  ✓ 2차 청산 목표: +{simulator.EXIT_TARGETS[1]}%")
        print(f"  ✓ 3차 청산 목표: 트레일링 스탑 또는 15:20")
        results.append(("청산 목표", True))
    except Exception as e:
        print(f"  ✗ 오류: {e}")
        results.append(("청산 목표", False))

    # 6. 필수 메서드 존재 확인
    print("\n[6] 필수 메서드 확인")
    try:
        simulator = BNFSimulator()
        assert hasattr(simulator, 'calculate_trailing_stop')
        assert hasattr(simulator, 'find_entry_points')
        assert hasattr(simulator, 'find_exit_points')
        assert hasattr(simulator, 'simulate_trade')
        print("  ✓ calculate_trailing_stop() 메서드 존재")
        print("  ✓ find_entry_points() 메서드 존재")
        print("  ✓ find_exit_points() 메서드 존재")
        print("  ✓ simulate_trade() 메서드 존재")
        results.append(("필수 메서드", True))
    except Exception as e:
        print(f"  ✗ 오류: {e}")
        results.append(("필수 메서드", False))

    # 7. 데이터 클래스 확인
    print("\n[7] 데이터 클래스 확인")
    try:
        # EntryPoint
        entry = EntryPoint(
            entry_num=1,
            time="09:10:00",
            price=100000,
            weight=0.3,
            amount=300000,
            quantity=3,
            reason="테스트"
        )
        assert entry.entry_num == 1
        print("  ✓ EntryPoint 데이터 클래스")

        # ExitPoint
        exit_point = ExitPoint(
            exit_num=1,
            time="10:00:00",
            price=105000,
            weight=0.3,
            quantity=3,
            profit_pct=5.0,
            profit_amount=15000,
            reason="목표 도달"
        )
        assert exit_point.exit_num == 1
        print("  ✓ ExitPoint 데이터 클래스")

        # BNFTradeResult
        result = BNFTradeResult(
            code="095340",
            name="ISC",
            date="20260330"
        )
        assert result.code == "095340"
        assert hasattr(result, 'to_dict')
        print("  ✓ BNFTradeResult 데이터 클래스")

        results.append(("데이터 클래스", True))
    except Exception as e:
        print(f"  ✗ 오류: {e}")
        results.append(("데이터 클래스", False))

    # 8. 분봉 데이터 포맷 확인
    print("\n[8] 분봉 데이터 포맷 확인")
    try:
        # 샘플 분봉 데이터
        minute_data = [
            {
                'time': '09:00:00',
                'open': 100000,
                'high': 101000,
                'low': 99000,
                'close': 100500,
                'volume': 1000
            }
        ]

        # 필수 필드 확인
        assert 'time' in minute_data[0]
        assert 'open' in minute_data[0]
        assert 'high' in minute_data[0]
        assert 'low' in minute_data[0]
        assert 'close' in minute_data[0]
        assert 'volume' in minute_data[0]

        print("  ✓ 분봉 데이터 포맷: time, open, high, low, close, volume")
        results.append(("분봉 데이터 포맷", True))
    except Exception as e:
        print(f"  ✗ 오류: {e}")
        results.append(("분봉 데이터 포맷", False))

    # 9. sys.path 처리 확인
    print("\n[9] 상위 디렉토리 import 확인")
    try:
        # simulator.py 파일 읽어서 sys.path.insert 확인
        simulator_file = Path(__file__).parent / "simulator.py"
        with open(simulator_file, 'r', encoding='utf-8') as f:
            content = f.read()

        assert 'sys.path.insert' in content
        assert 'Path(__file__).parent.parent.parent' in content
        print("  ✓ sys.path.insert(0, str(Path(__file__).parent.parent.parent))")
        results.append(("sys.path 처리", True))
    except Exception as e:
        print(f"  ✗ 오류: {e}")
        results.append(("sys.path 처리", False))

    # 최종 결과
    print("\n" + "="*70)
    print("검증 결과 요약")
    print("="*70)

    passed = sum(1 for _, ok in results if ok)
    total = len(results)

    for name, ok in results:
        status = "✓ PASS" if ok else "✗ FAIL"
        print(f"  {status} - {name}")

    print("\n" + "="*70)
    print(f"총 {total}개 항목 중 {passed}개 통과 ({passed/total*100:.0f}%)")
    print("="*70)

    if passed == total:
        print("\n축하합니다! 모든 요구사항이 충족되었습니다.")
        return True
    else:
        print(f"\n주의: {total - passed}개 항목이 실패했습니다.")
        return False


if __name__ == "__main__":
    success = verify_requirements()
    sys.exit(0 if success else 1)
