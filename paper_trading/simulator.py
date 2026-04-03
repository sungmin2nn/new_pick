"""
가상 매매 시뮬레이터
- 당일: 분봉 기반 정확한 체결 시간 (intraday_collector 활용)
- 과거: 일봉 기반 시뮬레이션 (백테스트용)
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, field, asdict

sys.path.insert(0, str(Path(__file__).parent.parent))

# 네이버 금융 우선, pykrx 폴백
try:
    from naver_market import stock
except ImportError:
    from pykrx import stock

import pandas as pd

from .selector import StockCandidate

# 에러 로거
from error_logger import get_logger, log_warning, log_error
_logger = get_logger("simulator")

# 기존 intraday_collector 활용
try:
    from intraday_collector import IntradayCollector
    INTRADAY_AVAILABLE = True
except ImportError:
    INTRADAY_AVAILABLE = False
    log_warning(_logger, "intraday_collector 사용 불가 - 일봉 데이터만 사용")


@dataclass
class TradeResult:
    """매매 결과 데이터 클래스"""
    code: str
    name: str
    entry_price: int
    exit_price: int
    quantity: int
    return_pct: float
    return_amount: int
    exit_type: str  # 'profit', 'loss', 'close'
    entry_time: str = "09:00"
    exit_time: str = ""
    high_price: int = 0
    low_price: int = 0
    max_profit_pct: float = 0  # 장중 최대 수익률
    max_loss_pct: float = 0    # 장중 최대 손실률

    def to_dict(self) -> dict:
        return asdict(self)


class TradingSimulator:
    """
    페이퍼 트레이딩 시뮬레이터

    매매 규칙:
    - 진입: 당일 시가 매수 (09:00~09:05)
    - 익절: +3% 도달 시 즉시 청산
    - 손절: -1.5% 도달 시 즉시 청산
    - 시간 청산: 14:30 이후 종가 청산
    """

    # 매매 파라미터
    PROFIT_TARGET = 3.0     # 익절 +3%
    LOSS_TARGET = -1.5      # 손절 -1.5%
    EXIT_DEADLINE = "14:30"
    INITIAL_CAPITAL = 1_000_000  # 초기 자본 100만원
    MAX_STOCKS = 5          # 최대 종목 수

    def __init__(self, capital: int = None):
        self.capital = capital or self.INITIAL_CAPITAL
        self.results: List[TradeResult] = []
        self.trade_date: str = ""

        # 분봉 수집기 초기화
        if INTRADAY_AVAILABLE:
            self.intraday = IntradayCollector()
        else:
            self.intraday = None

    def simulate_day(self,
                     candidates: List[StockCandidate],
                     date: str = None,
                     use_intraday: bool = True) -> List[TradeResult]:
        """
        하루 매매 시뮬레이션

        Args:
            candidates: 선정된 종목 리스트
            date: 매매일 (YYYYMMDD)
            use_intraday: 분봉 데이터 사용 여부 (당일만 가능)

        Returns:
            매매 결과 리스트
        """
        self.trade_date = date or datetime.now().strftime("%Y%m%d")
        self.results = []

        if not candidates:
            print("[Simulator] 매매 대상 종목 없음")
            return []

        # 당일 여부 확인
        today = datetime.now().strftime("%Y%m%d")
        is_today = (self.trade_date == today)

        # 분봉 사용 가능 여부
        can_use_intraday = (
            use_intraday and
            INTRADAY_AVAILABLE and
            self.intraday and
            is_today
        )

        # 종목당 투자금액 계산
        num_stocks = min(len(candidates), self.MAX_STOCKS)
        amount_per_stock = self.capital // num_stocks

        print(f"\n{'='*50}")
        print(f"[Simulator] 매매 시뮬레이션 시작 ({self.trade_date})")
        print(f"  자본금: {self.capital:,}원")
        print(f"  종목수: {num_stocks}개")
        print(f"  종목당: {amount_per_stock:,}원")
        print(f"  데이터: {'분봉 (정확한 시간)' if can_use_intraday else '일봉 (추정 시간)'}")
        print(f"{'='*50}")

        for candidate in candidates[:self.MAX_STOCKS]:
            if can_use_intraday:
                result = self._simulate_trade_intraday(candidate, amount_per_stock)
            else:
                result = self._simulate_trade_daily(candidate, amount_per_stock)

            if result:
                self.results.append(result)

        # 결과 요약 출력
        self._print_summary()

        return self.results

    def _simulate_trade_intraday(self,
                                  candidate: StockCandidate,
                                  investment: int) -> Optional[TradeResult]:
        """
        분봉 기반 매매 시뮬레이션 (정확한 체결 시간)

        Args:
            candidate: 종목 후보
            investment: 투자 금액

        Returns:
            매매 결과
        """
        code = candidate.code
        name = candidate.name

        try:
            # intraday_collector의 analyze_profit_loss 활용
            analysis = self.intraday.analyze_profit_loss(
                code,
                self.trade_date,
                profit_target=self.PROFIT_TARGET,
                loss_target=self.LOSS_TARGET,
                avg_volume_20d=0
            )

            if not analysis:
                print(f"  [{name}] 분봉 데이터 없음 - 스킵")
                return None

            # 매수 조건 확인
            entry_check = analysis.get('entry_check', {})
            entry_price = entry_check.get('entry_price', 0) or analysis.get('opening_price', 0)
            entry_time = entry_check.get('entry_time', '09:00:00')

            if entry_price == 0:
                print(f"  [{name}] 진입가 0원 - 스킵")
                return None

            # 매수 수량 계산
            quantity = investment // entry_price
            if quantity == 0:
                print(f"  [{name}] 매수 불가 (금액 부족)")
                return None

            # 결과 추출
            virtual_result = analysis.get('actual_result') or analysis.get('virtual_result', {})
            first_hit = virtual_result.get('first_hit', 'none')
            first_hit_time = virtual_result.get('first_hit_time', '')
            first_hit_price = virtual_result.get('first_hit_price', 0)
            closing_price = virtual_result.get('closing_price', entry_price)

            # 청산 유형 및 가격 결정
            if first_hit == 'profit':
                exit_price = first_hit_price or int(entry_price * (1 + self.PROFIT_TARGET / 100))
                exit_type = 'profit'
                exit_time = first_hit_time or '10:00:00'
            elif first_hit == 'loss':
                exit_price = first_hit_price or int(entry_price * (1 + self.LOSS_TARGET / 100))
                exit_type = 'loss'
                exit_time = first_hit_time or '09:30:00'
            else:
                exit_price = closing_price
                exit_type = 'close'
                exit_time = '15:20:00'

            # 수익률 계산
            return_pct = (exit_price - entry_price) / entry_price * 100
            return_amount = int((exit_price - entry_price) * quantity)

            result = TradeResult(
                code=code,
                name=name,
                entry_price=entry_price,
                exit_price=exit_price,
                quantity=quantity,
                return_pct=round(return_pct, 2),
                return_amount=return_amount,
                exit_type=exit_type,
                entry_time=entry_time[:5] if entry_time else "09:00",
                exit_time=exit_time[:5] if exit_time else "",
                high_price=0,
                low_price=0,
                max_profit_pct=round(virtual_result.get('max_profit_percent', 0), 2),
                max_loss_pct=round(virtual_result.get('max_loss_percent', 0), 2)
            )

            # 개별 결과 출력
            emoji = "+" if return_pct > 0 else "-" if return_pct < 0 else "="
            print(f"  [{name}] {entry_price:,}원 → {exit_price:,}원 ({return_pct:+.2f}%) [{exit_type}@{exit_time[:5]}] {emoji}")

            return result

        except Exception as e:
            print(f"  [{name}] 분봉 시뮬레이션 오류: {e}")
            # 일봉 fallback
            return self._simulate_trade_daily(candidate, investment)

    def _simulate_trade_daily(self,
                               candidate: StockCandidate,
                               investment: int) -> Optional[TradeResult]:
        """
        일봉 기반 매매 시뮬레이션 (백테스트용, 추정 시간)

        Args:
            candidate: 종목 후보
            investment: 투자 금액

        Returns:
            매매 결과
        """
        code = candidate.code
        name = candidate.name

        try:
            # 당일 OHLCV 데이터 조회
            df = stock.get_market_ohlcv(self.trade_date, self.trade_date, code)

            if df.empty:
                print(f"  [{name}] 데이터 없음 - 스킵")
                return None

            row = df.iloc[0]
            open_price = int(row['시가'])
            high_price = int(row['고가'])
            low_price = int(row['저가'])
            close_price = int(row['종가'])

            if open_price == 0:
                print(f"  [{name}] 시가 0원 - 스킵")
                return None

            # 매수 수량 계산
            quantity = investment // open_price
            if quantity == 0:
                print(f"  [{name}] 매수 불가 (금액 부족)")
                return None

            # 목표가/손절가 계산
            profit_price = open_price * (1 + self.PROFIT_TARGET / 100)
            loss_price = open_price * (1 + self.LOSS_TARGET / 100)

            # 청산 시뮬레이션
            exit_price, exit_type, exit_time = self._determine_exit_daily(
                open_price, high_price, low_price, close_price,
                profit_price, loss_price
            )

            # 수익률 계산
            return_pct = (exit_price - open_price) / open_price * 100
            return_amount = int((exit_price - open_price) * quantity)

            # 장중 최대 수익/손실
            max_profit_pct = (high_price - open_price) / open_price * 100 if open_price > 0 else 0
            max_loss_pct = (low_price - open_price) / open_price * 100 if open_price > 0 else 0

            result = TradeResult(
                code=code,
                name=name,
                entry_price=open_price,
                exit_price=exit_price,
                quantity=quantity,
                return_pct=round(return_pct, 2),
                return_amount=return_amount,
                exit_type=exit_type,
                entry_time="09:00",
                exit_time=exit_time,
                high_price=high_price,
                low_price=low_price,
                max_profit_pct=round(max_profit_pct, 2),
                max_loss_pct=round(max_loss_pct, 2)
            )

            # 개별 결과 출력
            emoji = "+" if return_pct > 0 else "-" if return_pct < 0 else "="
            print(f"  [{name}] {open_price:,}원 → {exit_price:,}원 ({return_pct:+.2f}%) [{exit_type}@{exit_time}] {emoji}")

            return result

        except Exception as e:
            print(f"  [{name}] 오류: {e}")
            return None

    def _determine_exit_daily(self,
                               open_p: int,
                               high_p: int,
                               low_p: int,
                               close_p: int,
                               profit_p: float,
                               loss_p: float) -> tuple:
        """
        일봉 기반 청산 유형 결정 (추정 시간)

        로직:
        1. 고가가 익절가 이상 → 익절 (+3%)
        2. 저가가 손절가 이하 → 손절 (-1.5%)
        3. 둘 다 해당 → 손절 우선 (보수적)
        4. 둘 다 미해당 → 종가 청산

        Returns:
            (청산가, 청산유형, 청산시간)
        """
        hit_profit = high_p >= profit_p
        hit_loss = low_p <= loss_p

        if hit_profit and hit_loss:
            # 둘 다 도달한 경우 → 손절 우선 (보수적 접근)
            return int(loss_p), 'loss', '09:30'
        elif hit_profit:
            return int(profit_p), 'profit', '10:00'
        elif hit_loss:
            return int(loss_p), 'loss', '09:30'
        else:
            return close_p, 'close', '14:30'

    def _print_summary(self):
        """결과 요약 출력"""
        if not self.results:
            print("\n[Simulator] 매매 결과 없음")
            return

        total_trades = len(self.results)
        wins = len([r for r in self.results if r.return_pct > 0])
        losses = len([r for r in self.results if r.return_pct < 0])
        even = total_trades - wins - losses

        total_return_pct = sum(r.return_pct for r in self.results)
        total_return_amount = sum(r.return_amount for r in self.results)
        avg_return = total_return_pct / total_trades if total_trades > 0 else 0

        profit_exits = len([r for r in self.results if r.exit_type == 'profit'])
        loss_exits = len([r for r in self.results if r.exit_type == 'loss'])
        close_exits = len([r for r in self.results if r.exit_type == 'close'])

        print(f"\n{'='*50}")
        print(f"[Simulator] 일일 매매 결과 요약")
        print(f"{'='*50}")
        print(f"  총 거래: {total_trades}건")
        print(f"  승/패/무: {wins}/{losses}/{even}")
        print(f"  승률: {wins/total_trades*100:.1f}%")
        print(f"  총 수익률: {total_return_pct:+.2f}%")
        print(f"  총 손익: {total_return_amount:+,}원")
        print(f"  평균 수익률: {avg_return:+.2f}%")
        print(f"  청산 유형: 익절 {profit_exits} / 손절 {loss_exits} / 종가 {close_exits}")
        print(f"{'='*50}")

    def get_daily_summary(self) -> dict:
        """일일 결과 요약 반환"""
        if not self.results:
            return {
                'date': self.trade_date,
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0,
                'total_return': 0,
                'avg_return': 0,
                'results': []
            }

        total_trades = len(self.results)
        wins = len([r for r in self.results if r.return_pct > 0])
        total_return = sum(r.return_pct for r in self.results)

        return {
            'date': self.trade_date,
            'total_trades': total_trades,
            'wins': wins,
            'losses': total_trades - wins,
            'win_rate': round(wins / total_trades * 100, 1) if total_trades > 0 else 0,
            'total_return': round(total_return, 2),
            'avg_return': round(total_return / total_trades, 2) if total_trades > 0 else 0,
            'profit_exits': len([r for r in self.results if r.exit_type == 'profit']),
            'loss_exits': len([r for r in self.results if r.exit_type == 'loss']),
            'close_exits': len([r for r in self.results if r.exit_type == 'close']),
            'results': [r.to_dict() for r in self.results]
        }

    def backtest_period(self,
                        start_date: str,
                        end_date: str,
                        selector) -> List[dict]:
        """
        기간 백테스트 (일봉 기반)

        Args:
            start_date: 시작일 (YYYYMMDD)
            end_date: 종료일 (YYYYMMDD)
            selector: StockSelector 인스턴스

        Returns:
            일별 결과 리스트
        """
        print(f"\n{'='*60}")
        print(f"[Simulator] 기간 백테스트: {start_date} ~ {end_date}")
        print(f"  (과거 데이터는 일봉 기반 추정 시간 사용)")
        print(f"{'='*60}")

        # 거래일 목록 조회
        try:
            dates = stock.get_market_ohlcv(start_date, end_date, "005930").index
            trade_dates = [d.strftime("%Y%m%d") for d in dates]
        except Exception as e:
            log_error(_logger, "거래일 조회 실패", e)
            return []

        daily_results = []
        cumulative_return = 0

        for date in trade_dates:
            try:
                # 종목 선정
                candidates = selector.select_stocks(date)

                # 매매 시뮬레이션 (백테스트는 일봉 사용)
                self.simulate_day(candidates, date, use_intraday=False)

                # 결과 저장
                summary = self.get_daily_summary()
                cumulative_return += summary['total_return']
                summary['cumulative_return'] = round(cumulative_return, 2)

                daily_results.append(summary)

            except Exception as e:
                log_warning(_logger, f"일별 시뮬레이션 실패 ({date})", e)
                continue

        # 최종 요약
        total_days = len(daily_results)
        if total_days > 0:
            total_trades = sum(d['total_trades'] for d in daily_results)
            total_wins = sum(d['wins'] for d in daily_results)
            final_return = cumulative_return

            print(f"\n{'='*60}")
            print(f"[Simulator] 백테스트 최종 결과")
            print(f"{'='*60}")
            print(f"  기간: {start_date} ~ {end_date}")
            print(f"  거래일: {total_days}일")
            print(f"  총 거래: {total_trades}건")
            print(f"  전체 승률: {total_wins/total_trades*100:.1f}%" if total_trades > 0 else "  전체 승률: N/A")
            print(f"  누적 수익률: {final_return:+.2f}%")
            print(f"{'='*60}")

        return daily_results


# CLI 테스트
if __name__ == "__main__":
    from selector import StockSelector

    # 단일 날짜 테스트
    selector = StockSelector()
    simulator = TradingSimulator()

    # 최근 거래일로 테스트
    candidates = selector.select_stocks()
    if candidates:
        results = simulator.simulate_day(candidates)
        print("\n[일일 요약]")
        print(simulator.get_daily_summary())
