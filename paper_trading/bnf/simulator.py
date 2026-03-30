"""
BNF-style 트레이딩 시뮬레이터
- 분할 매수/매도 (Split Entry/Exit)
- 트레일링 스탑 (Trailing Stop Logic)
- 실시간 분봉 데이터 기반 정확한 체결
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field, asdict

# 상위 디렉토리 모듈 import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from intraday_collector import IntradayCollector
    INTRADAY_AVAILABLE = True
except ImportError:
    INTRADAY_AVAILABLE = False
    print("[BNFSimulator] Warning: intraday_collector not available")


@dataclass
class EntryPoint:
    """진입 포인트 정보"""
    entry_num: int          # 1차, 2차, 3차
    time: str               # 체결 시간
    price: int              # 체결 가격
    weight: float           # 비중 (0.3, 0.4, 0.3)
    amount: int             # 투자 금액
    quantity: int           # 매수 수량
    reason: str             # 진입 사유


@dataclass
class ExitPoint:
    """청산 포인트 정보"""
    exit_num: int           # 1차, 2차, 3차
    time: str               # 체결 시간
    price: int              # 체결 가격
    weight: float           # 청산 비중 (0.3, 0.4, 0.3)
    quantity: int           # 청산 수량
    profit_pct: float       # 개별 수익률
    profit_amount: int      # 개별 손익
    reason: str             # 청산 사유 (target/trailing_stop/deadline)


@dataclass
class BNFTradeResult:
    """BNF 트레이딩 결과"""
    code: str
    name: str
    date: str

    # 진입 정보
    entries: List[EntryPoint] = field(default_factory=list)
    total_entry_amount: int = 0
    total_quantity: int = 0
    avg_entry_price: float = 0

    # 청산 정보
    exits: List[ExitPoint] = field(default_factory=list)
    total_exit_amount: int = 0

    # 손익 정보
    total_profit_pct: float = 0
    total_profit_amount: int = 0

    # 장중 최고/최저
    max_profit_pct: float = 0
    max_loss_pct: float = 0
    current_high: int = 0

    # 트레일링 스탑 추적
    trailing_stop_price: int = 0
    trailing_stop_history: List[Dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        result = asdict(self)
        result['entries'] = [asdict(e) for e in self.entries]
        result['exits'] = [asdict(e) for e in self.exits]
        return result


class BNFSimulator:
    """
    BNF-style 트레이딩 시뮬레이터

    매매 규칙:
    1. 트레일링 스탑:
       - 초기 손절: -3%
       - 수익 3% 이상: 손절선 0% (본전)
       - 수익 5% 이상: 고점 대비 -2% 트레일링
       - 수익 10% 이상: 고점 대비 -3% 트레일링

    2. 분할 매수 (3회):
       - 1차: 30% (첫 반등 신호 - 하락 후 첫 양봉)
       - 2차: 40% (추가 상승 +1% 확인)
       - 3차: 30% (풀백 -1% 진입)

    3. 분할 매도 (3회):
       - 1차: 30% (+5% 목표)
       - 2차: 40% (+10% 목표 또는 트레일링 스탑)
       - 3차: 30% (트레일링 스탑 또는 15:20 종료)
    """

    # 매매 파라미터
    INITIAL_CAPITAL = 1_000_000  # 초기 자본 100만원

    # 진입 비중
    ENTRY_WEIGHTS = [0.3, 0.4, 0.3]  # 1차, 2차, 3차

    # 청산 비중
    EXIT_WEIGHTS = [0.3, 0.4, 0.3]   # 1차, 2차, 3차

    # 청산 목표
    EXIT_TARGETS = [5.0, 10.0, None]  # 1차 +5%, 2차 +10%, 3차 trailing

    # 트레일링 스탑 파라미터
    INITIAL_STOP = -3.0          # 초기 손절 -3%
    BREAKEVEN_THRESHOLD = 3.0    # 3% 이상 시 본전 이동
    TRAIL_START = 5.0            # 5% 이상 시 트레일링 시작
    TRAIL_PERCENT_1 = 2.0        # 5~10%: 고점 대비 -2%
    TRAIL_THRESHOLD_2 = 10.0     # 10% 이상 시 -3% 트레일링
    TRAIL_PERCENT_2 = 3.0        # 10% 이상: 고점 대비 -3%

    # 매수 진입 조건
    REVERSAL_CONFIRM = True      # 반등 확인 (첫 양봉)
    CONTINUATION_PCT = 1.0       # 2차 진입: +1% 상승
    PULLBACK_PCT = -1.0          # 3차 진입: -1% 풀백

    # 시간 제한
    EXIT_DEADLINE = "15:20"      # 장 마감 전 청산

    def __init__(self, capital: int = None):
        self.capital = capital or self.INITIAL_CAPITAL
        self.results: List[BNFTradeResult] = []

        # 분봉 수집기 초기화
        if INTRADAY_AVAILABLE:
            self.intraday = IntradayCollector()
        else:
            self.intraday = None

    def calculate_trailing_stop(self,
                                entry_price: int,
                                current_high: int,
                                profit_pct: float) -> int:
        """
        트레일링 스탑 가격 계산

        Args:
            entry_price: 평균 진입가
            current_high: 현재까지 최고가
            profit_pct: 현재 수익률

        Returns:
            트레일링 스탑 가격
        """
        # 초기 손절 (-3%)
        if profit_pct < self.BREAKEVEN_THRESHOLD:
            return int(entry_price * (1 + self.INITIAL_STOP / 100))

        # 본전 이동 (3% 이상 ~ 5% 미만)
        elif profit_pct < self.TRAIL_START:
            return entry_price

        # 5~10%: 고점 대비 -2% 트레일링
        elif profit_pct < self.TRAIL_THRESHOLD_2:
            return int(current_high * (1 - self.TRAIL_PERCENT_1 / 100))

        # 10% 이상: 고점 대비 -3% 트레일링
        else:
            return int(current_high * (1 - self.TRAIL_PERCENT_2 / 100))

    def find_entry_points(self,
                         minute_data: List[Dict],
                         entry_amount: int) -> List[EntryPoint]:
        """
        분할 매수 진입점 탐색

        분할 매수 로직:
        1차 (30%): 하락 후 첫 반등 신호 (첫 양봉)
        2차 (40%): 1차 진입 후 +1% 이상 상승 확인
        3차 (30%): 2차 진입 후 고점에서 -1% 풀백 진입

        Args:
            minute_data: 분봉 데이터 리스트
            entry_amount: 총 투자 금액

        Returns:
            진입 포인트 리스트
        """
        entries = []

        if not minute_data or len(minute_data) < 5:
            return entries

        # 1차 진입: 하락 후 첫 양봉 찾기 (09:00 이후)
        first_entry_found = False
        first_entry_price = 0

        for i in range(1, len(minute_data)):
            candle = minute_data[i]
            prev_candle = minute_data[i-1]

            # 09:00 이전은 스킵
            if candle['time'] < '09:00:00':
                continue

            # 양봉 확인 (종가 > 시가)
            is_green = candle['close'] > candle['open']

            # 이전 캔들이 음봉이고 현재가 양봉 -> 반등 신호
            prev_is_red = prev_candle['close'] < prev_candle['open']

            if is_green and prev_is_red and not first_entry_found:
                amount_1 = int(entry_amount * self.ENTRY_WEIGHTS[0])
                price_1 = candle['close']
                qty_1 = amount_1 // price_1

                if qty_1 > 0:
                    entries.append(EntryPoint(
                        entry_num=1,
                        time=candle['time'],
                        price=price_1,
                        weight=self.ENTRY_WEIGHTS[0],
                        amount=amount_1,
                        quantity=qty_1,
                        reason="첫 반등 신호 (양봉 전환)"
                    ))
                    first_entry_found = True
                    first_entry_price = price_1
                    break

        if not first_entry_found:
            return entries

        # 2차 진입: 1차 진입 후 +1% 이상 상승 확인
        second_entry_found = False
        second_entry_high = first_entry_price

        first_idx = next(i for i, c in enumerate(minute_data) if c['time'] == entries[0].time)

        for i in range(first_idx + 1, len(minute_data)):
            candle = minute_data[i]
            current_price = candle['close']

            # 고점 업데이트
            if candle['high'] > second_entry_high:
                second_entry_high = candle['high']

            # 1차 진입가 대비 +1% 이상 상승 확인
            gain_pct = (current_price - first_entry_price) / first_entry_price * 100

            if gain_pct >= self.CONTINUATION_PCT and not second_entry_found:
                amount_2 = int(entry_amount * self.ENTRY_WEIGHTS[1])
                price_2 = current_price
                qty_2 = amount_2 // price_2

                if qty_2 > 0:
                    entries.append(EntryPoint(
                        entry_num=2,
                        time=candle['time'],
                        price=price_2,
                        weight=self.ENTRY_WEIGHTS[1],
                        amount=amount_2,
                        quantity=qty_2,
                        reason=f"상승 확인 (+{gain_pct:.2f}%)"
                    ))
                    second_entry_found = True
                    break

        if not second_entry_found:
            return entries

        # 3차 진입: 2차 진입 후 고점에서 -1% 풀백
        third_entry_found = False
        recent_high = second_entry_high

        second_idx = next(i for i, c in enumerate(minute_data) if c['time'] == entries[1].time)

        for i in range(second_idx + 1, len(minute_data)):
            candle = minute_data[i]
            current_price = candle['close']

            # 고점 업데이트
            if candle['high'] > recent_high:
                recent_high = candle['high']

            # 고점 대비 -1% 풀백 확인
            pullback_pct = (current_price - recent_high) / recent_high * 100

            if pullback_pct <= self.PULLBACK_PCT and not third_entry_found:
                amount_3 = int(entry_amount * self.ENTRY_WEIGHTS[2])
                price_3 = current_price
                qty_3 = amount_3 // price_3

                if qty_3 > 0:
                    entries.append(EntryPoint(
                        entry_num=3,
                        time=candle['time'],
                        price=price_3,
                        weight=self.ENTRY_WEIGHTS[2],
                        amount=amount_3,
                        quantity=qty_3,
                        reason=f"풀백 진입 ({pullback_pct:.2f}% from high)"
                    ))
                    third_entry_found = True
                    break

        return entries

    def find_exit_points(self,
                        entries: List[EntryPoint],
                        minute_data: List[Dict]) -> List[ExitPoint]:
        """
        분할 매도 청산점 탐색

        분할 매도 로직:
        1차 (30%): +5% 목표
        2차 (40%): +10% 목표 또는 트레일링 스탑
        3차 (30%): 트레일링 스탑 또는 15:20 강제 청산

        Args:
            entries: 진입 포인트 리스트
            minute_data: 분봉 데이터 리스트

        Returns:
            청산 포인트 리스트
        """
        exits = []

        if not entries:
            return exits

        # 평균 진입가 계산
        total_quantity = sum(e.quantity for e in entries)
        if total_quantity == 0:
            return exits

        total_cost = sum(e.price * e.quantity for e in entries)
        avg_entry_price = total_cost / total_quantity

        # 마지막 진입 시점부터 분석
        last_entry_time = entries[-1].time
        last_entry_idx = next(i for i, c in enumerate(minute_data) if c['time'] == last_entry_time)

        # 청산 추적 변수
        exit_1_done = False
        exit_2_done = False
        exit_3_done = False

        current_high = avg_entry_price
        remaining_quantity = total_quantity

        for i in range(last_entry_idx, len(minute_data)):
            candle = minute_data[i]

            # 현재 고점 업데이트
            if candle['high'] > current_high:
                current_high = candle['high']

            current_price = candle['close']
            current_profit_pct = (current_price - avg_entry_price) / avg_entry_price * 100

            # 트레일링 스탑 가격 계산
            trailing_stop = self.calculate_trailing_stop(
                int(avg_entry_price),
                current_high,
                current_profit_pct
            )

            # 1차 청산: +5% 목표
            if not exit_1_done and current_profit_pct >= self.EXIT_TARGETS[0]:
                qty_1 = int(total_quantity * self.EXIT_WEIGHTS[0])
                price_1 = int(avg_entry_price * (1 + self.EXIT_TARGETS[0] / 100))

                exits.append(ExitPoint(
                    exit_num=1,
                    time=candle['time'],
                    price=price_1,
                    weight=self.EXIT_WEIGHTS[0],
                    quantity=qty_1,
                    profit_pct=self.EXIT_TARGETS[0],
                    profit_amount=int((price_1 - avg_entry_price) * qty_1),
                    reason=f"+{self.EXIT_TARGETS[0]}% 목표 도달"
                ))
                exit_1_done = True
                remaining_quantity -= qty_1
                continue

            # 2차 청산: +10% 목표 또는 트레일링 스탑
            if exit_1_done and not exit_2_done:
                # +10% 목표 도달
                if current_profit_pct >= self.EXIT_TARGETS[1]:
                    qty_2 = int(total_quantity * self.EXIT_WEIGHTS[1])
                    price_2 = int(avg_entry_price * (1 + self.EXIT_TARGETS[1] / 100))

                    exits.append(ExitPoint(
                        exit_num=2,
                        time=candle['time'],
                        price=price_2,
                        weight=self.EXIT_WEIGHTS[1],
                        quantity=qty_2,
                        profit_pct=self.EXIT_TARGETS[1],
                        profit_amount=int((price_2 - avg_entry_price) * qty_2),
                        reason=f"+{self.EXIT_TARGETS[1]}% 목표 도달"
                    ))
                    exit_2_done = True
                    remaining_quantity -= qty_2
                    continue

                # 트레일링 스탑 히트
                if candle['low'] <= trailing_stop:
                    qty_2 = int(total_quantity * self.EXIT_WEIGHTS[1])
                    price_2 = trailing_stop
                    exit_pct = (price_2 - avg_entry_price) / avg_entry_price * 100

                    exits.append(ExitPoint(
                        exit_num=2,
                        time=candle['time'],
                        price=price_2,
                        weight=self.EXIT_WEIGHTS[1],
                        quantity=qty_2,
                        profit_pct=exit_pct,
                        profit_amount=int((price_2 - avg_entry_price) * qty_2),
                        reason=f"트레일링 스탑 ({exit_pct:+.2f}%)"
                    ))
                    exit_2_done = True
                    remaining_quantity -= qty_2
                    continue

            # 3차 청산: 트레일링 스탑 또는 15:20 강제 청산
            if exit_1_done and exit_2_done and not exit_3_done:
                # 트레일링 스탑 히트
                if candle['low'] <= trailing_stop:
                    qty_3 = remaining_quantity
                    price_3 = trailing_stop
                    exit_pct = (price_3 - avg_entry_price) / avg_entry_price * 100

                    exits.append(ExitPoint(
                        exit_num=3,
                        time=candle['time'],
                        price=price_3,
                        weight=self.EXIT_WEIGHTS[2],
                        quantity=qty_3,
                        profit_pct=exit_pct,
                        profit_amount=int((price_3 - avg_entry_price) * qty_3),
                        reason=f"트레일링 스탑 ({exit_pct:+.2f}%)"
                    ))
                    exit_3_done = True
                    break

                # 15:20 강제 청산
                if candle['time'][:5] >= self.EXIT_DEADLINE:
                    qty_3 = remaining_quantity
                    price_3 = candle['close']
                    exit_pct = (price_3 - avg_entry_price) / avg_entry_price * 100

                    exits.append(ExitPoint(
                        exit_num=3,
                        time=candle['time'],
                        price=price_3,
                        weight=self.EXIT_WEIGHTS[2],
                        quantity=qty_3,
                        profit_pct=exit_pct,
                        profit_amount=int((price_3 - avg_entry_price) * qty_3),
                        reason=f"장 마감 청산 ({exit_pct:+.2f}%)"
                    ))
                    exit_3_done = True
                    break

        # 장 마감까지 청산 안된 경우 마지막 가격으로 강제 청산
        if not exit_3_done and minute_data and remaining_quantity > 0:
            last_candle = minute_data[-1]
            price_final = last_candle['close']
            exit_pct = (price_final - avg_entry_price) / avg_entry_price * 100

            exits.append(ExitPoint(
                exit_num=3,
                time=last_candle['time'],
                price=price_final,
                weight=self.EXIT_WEIGHTS[2],
                quantity=remaining_quantity,
                profit_pct=exit_pct,
                profit_amount=int((price_final - avg_entry_price) * remaining_quantity),
                reason=f"장 종료 강제 청산 ({exit_pct:+.2f}%)"
            ))

        return exits

    def simulate_trade(self,
                      code: str,
                      name: str,
                      date_str: str,
                      minute_data: List[Dict],
                      entry_amount: int) -> Optional[BNFTradeResult]:
        """
        BNF 방식 단일 종목 트레이딩 시뮬레이션

        Args:
            code: 종목 코드
            name: 종목 이름
            date_str: 거래일 (YYYYMMDD)
            minute_data: 분봉 데이터 리스트
            entry_amount: 투자 금액

        Returns:
            BNF 트레이딩 결과
        """
        if not minute_data or len(minute_data) < 10:
            print(f"  [{name}] 분봉 데이터 부족 - 스킵")
            return None

        # 1. 진입점 탐색
        entries = self.find_entry_points(minute_data, entry_amount)

        if not entries:
            print(f"  [{name}] 진입 신호 없음 - 스킵")
            return None

        # 2. 평균 진입가 계산
        total_quantity = sum(e.quantity for e in entries)
        total_cost = sum(e.price * e.quantity for e in entries)
        avg_entry_price = total_cost / total_quantity if total_quantity > 0 else 0

        # 3. 청산점 탐색
        exits = self.find_exit_points(entries, minute_data)

        # 4. 손익 계산
        total_exit_amount = sum(e.price * e.quantity for e in exits)
        total_profit_amount = sum(e.profit_amount for e in exits)
        total_profit_pct = (total_profit_amount / total_cost * 100) if total_cost > 0 else 0

        # 5. 장중 최대/최소 수익률 계산
        max_profit_pct = 0
        max_loss_pct = 0
        current_high = avg_entry_price

        if entries:
            last_entry_time = entries[-1].time
            last_entry_idx = next(i for i, c in enumerate(minute_data) if c['time'] == last_entry_time)

            for i in range(last_entry_idx, len(minute_data)):
                candle = minute_data[i]

                if candle['high'] > current_high:
                    current_high = candle['high']

                high_pct = (candle['high'] - avg_entry_price) / avg_entry_price * 100
                low_pct = (candle['low'] - avg_entry_price) / avg_entry_price * 100

                if high_pct > max_profit_pct:
                    max_profit_pct = high_pct
                if low_pct < max_loss_pct:
                    max_loss_pct = low_pct

        # 6. 트레일링 스탑 히스토리 생성
        trailing_stop_history = []
        if entries:
            last_entry_time = entries[-1].time
            last_entry_idx = next(i for i, c in enumerate(minute_data) if c['time'] == last_entry_time)

            temp_high = avg_entry_price
            for i in range(last_entry_idx, len(minute_data), 10):  # 10분마다 샘플링
                candle = minute_data[i]

                if candle['high'] > temp_high:
                    temp_high = candle['high']

                profit_pct = (candle['close'] - avg_entry_price) / avg_entry_price * 100
                stop_price = self.calculate_trailing_stop(int(avg_entry_price), temp_high, profit_pct)

                trailing_stop_history.append({
                    'time': candle['time'],
                    'price': candle['close'],
                    'high': temp_high,
                    'profit_pct': round(profit_pct, 2),
                    'stop_price': stop_price
                })

        # 7. 결과 생성
        result = BNFTradeResult(
            code=code,
            name=name,
            date=date_str,
            entries=entries,
            total_entry_amount=int(total_cost),
            total_quantity=total_quantity,
            avg_entry_price=round(avg_entry_price, 2),
            exits=exits,
            total_exit_amount=total_exit_amount,
            total_profit_pct=round(total_profit_pct, 2),
            total_profit_amount=total_profit_amount,
            max_profit_pct=round(max_profit_pct, 2),
            max_loss_pct=round(max_loss_pct, 2),
            current_high=current_high,
            trailing_stop_price=0,
            trailing_stop_history=trailing_stop_history
        )

        # 8. 결과 출력
        emoji = "+" if total_profit_pct > 0 else "-" if total_profit_pct < 0 else "="
        print(f"\n  [{name}] BNF 시뮬레이션")
        print(f"    진입: {len(entries)}회 / 평균가 {avg_entry_price:,.0f}원")
        print(f"    청산: {len(exits)}회")
        print(f"    손익: {total_profit_amount:+,}원 ({total_profit_pct:+.2f}%) {emoji}")
        print(f"    최대수익: +{max_profit_pct:.2f}% / 최대손실: {max_loss_pct:.2f}%")

        return result

    def print_detailed_result(self, result: BNFTradeResult):
        """상세 결과 출력"""
        print(f"\n{'='*70}")
        print(f"[BNF 상세 결과] {result.name} ({result.code}) - {result.date}")
        print(f"{'='*70}")

        # 진입 상세
        print(f"\n[진입 내역]")
        for entry in result.entries:
            print(f"  {entry.entry_num}차: {entry.time[:5]} | "
                  f"{entry.price:,}원 x {entry.quantity}주 = {entry.amount:,}원 "
                  f"({entry.weight*100:.0f}%) | {entry.reason}")
        print(f"  → 평균 진입가: {result.avg_entry_price:,.2f}원 (총 {result.total_quantity}주)")

        # 청산 상세
        print(f"\n[청산 내역]")
        for exit_point in result.exits:
            print(f"  {exit_point.exit_num}차: {exit_point.time[:5]} | "
                  f"{exit_point.price:,}원 x {exit_point.quantity}주 = {exit_point.profit_amount:+,}원 "
                  f"({exit_point.profit_pct:+.2f}%) | {exit_point.reason}")

        # 최종 손익
        print(f"\n[최종 손익]")
        print(f"  총 투자금: {result.total_entry_amount:,}원")
        print(f"  총 회수금: {result.total_exit_amount:,}원")
        print(f"  순손익: {result.total_profit_amount:+,}원")
        print(f"  수익률: {result.total_profit_pct:+.2f}%")
        print(f"  장중 최대수익: +{result.max_profit_pct:.2f}%")
        print(f"  장중 최대손실: {result.max_loss_pct:.2f}%")

        # 트레일링 스탑 샘플
        if result.trailing_stop_history:
            print(f"\n[트레일링 스탑 샘플] (10분 간격)")
            for i, stop in enumerate(result.trailing_stop_history[:5]):
                print(f"  {stop['time'][:5]} | 가격: {stop['price']:,}원 | "
                      f"수익: {stop['profit_pct']:+.2f}% | 스탑: {stop['stop_price']:,}원")
            if len(result.trailing_stop_history) > 5:
                print(f"  ... (총 {len(result.trailing_stop_history)}개 포인트)")

        print(f"{'='*70}")


# CLI 테스트
if __name__ == "__main__":
    print("[BNF Simulator] 테스트 모드")

    if not INTRADAY_AVAILABLE:
        print("Error: intraday_collector를 찾을 수 없습니다.")
        sys.exit(1)

    # 시뮬레이터 초기화
    simulator = BNFSimulator()

    # 테스트: 최근 분봉 데이터 로드
    import json
    import os

    data_dir = Path(__file__).parent.parent.parent / "data" / "intraday"

    # 최근 파일 찾기
    if data_dir.exists():
        files = sorted(data_dir.glob("intraday_*.json"), reverse=True)

        if files:
            latest_file = files[0]
            print(f"테스트 파일: {latest_file}")

            with open(latest_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            date_str = data.get('date', '')
            stocks = data.get('stocks', {})

            if stocks:
                # 첫 번째 종목으로 테스트
                first_code = list(stocks.keys())[0]
                stock_info = stocks[first_code]

                print(f"\n테스트 종목: {stock_info['name']} ({first_code})")

                # 분봉 데이터 수집
                collector = IntradayCollector()
                minute_data = collector.get_minute_data(first_code, date_str)

                if minute_data:
                    # 시뮬레이션 실행
                    result = simulator.simulate_trade(
                        code=first_code,
                        name=stock_info['name'],
                        date_str=date_str,
                        minute_data=minute_data,
                        entry_amount=simulator.INITIAL_CAPITAL
                    )

                    if result:
                        simulator.print_detailed_result(result)
                    else:
                        print("시뮬레이션 결과 없음")
                else:
                    print("분봉 데이터 없음")
            else:
                print("종목 데이터 없음")
        else:
            print("분봉 데이터 파일 없음")
    else:
        print(f"데이터 디렉토리 없음: {data_dir}")
