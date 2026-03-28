"""
일일 실행 스케줄러
- 장 종료 후 자동 실행
- 종목 선정 → 시뮬레이션 → 결과 기록 → 리포트 생성
- project_logger 연동
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import json
import time
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from .selector import StockSelector
from .simulator import TradingSimulator

# project_logger import
try:
    from project_logger import ProjectLogger
    from auto_reporter import AutoReporter
    LOGGER_AVAILABLE = True
except ImportError:
    LOGGER_AVAILABLE = False
    print("[Scheduler] Warning: project_logger not available")


class DailyScheduler:
    """
    일일 페이퍼 트레이딩 스케줄러

    실행 흐름:
    1. 장 종료 확인 (16:00 이후)
    2. 전일 데이터로 종목 선정
    3. 당일 데이터로 매매 시뮬레이션
    4. 결과 기록 (project_logger)
    5. 리포트 생성 (auto_reporter)
    """

    MARKET_CLOSE_HOUR = 16  # 장 종료 시간 (16:00)
    DATA_DIR = Path(__file__).parent.parent / "data" / "paper_trading"

    def __init__(self, capital: int = 1_000_000):
        self.selector = StockSelector()
        self.simulator = TradingSimulator(capital)

        if LOGGER_AVAILABLE:
            self.logger = ProjectLogger()
            self.reporter = AutoReporter()
        else:
            self.logger = None
            self.reporter = None

        # 데이터 디렉토리 생성
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)

    def run_daily(self, date: str = None, force: bool = False) -> dict:
        """
        일일 페이퍼 트레이딩 실행

        Args:
            date: 실행 날짜 (YYYYMMDD), None이면 오늘
            force: 장 종료 전이라도 강제 실행

        Returns:
            실행 결과 dict
        """
        if date is None:
            date = datetime.now().strftime("%Y%m%d")

        print(f"\n{'#'*60}")
        print(f"# 페이퍼 트레이딩 일일 실행")
        print(f"# 날짜: {date}")
        print(f"# 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'#'*60}")

        # 장 종료 확인
        if not force and not self._is_market_closed():
            print("[Scheduler] 장이 아직 종료되지 않았습니다. (force=True로 강제 실행 가능)")
            return {'status': 'skipped', 'reason': 'market_open'}

        result = {
            'date': date,
            'status': 'success',
            'selection': None,
            'simulation': None,
            'logged': False
        }

        try:
            # 1. 종목 선정
            print("\n[Step 1] 종목 선정")
            candidates = self.selector.select_stocks(date)
            result['selection'] = self.selector.get_selection_summary()

            if not candidates:
                print("[Scheduler] 선정된 종목 없음 - 종료")
                result['status'] = 'no_candidates'
                self._save_result(date, result)
                return result

            # 2. 매매 시뮬레이션
            print("\n[Step 2] 매매 시뮬레이션")
            trade_results = self.simulator.simulate_day(candidates, date)
            result['simulation'] = self.simulator.get_daily_summary()

            # 3. 결과 저장 (JSON)
            print("\n[Step 3] 결과 저장")
            self._save_result(date, result)

            # 4. project_logger 기록
            if self.logger:
                print("\n[Step 4] 로거 기록")
                self._log_to_project_logger(date, candidates, result['simulation'])
                result['logged'] = True

            # 5. 리포트 생성
            if self.reporter:
                print("\n[Step 5] 리포트 생성")
                self.reporter.generate_daily_report(date.replace('', '-'))
                self.reporter.update_knowledge_base()

            print(f"\n[Scheduler] 일일 실행 완료!")

        except Exception as e:
            print(f"[Scheduler] 오류 발생: {e}")
            result['status'] = 'error'
            result['error'] = str(e)
            import traceback
            traceback.print_exc()

        return result

    def _is_market_closed(self) -> bool:
        """장 종료 여부 확인"""
        now = datetime.now()
        # 주말 체크
        if now.weekday() >= 5:
            return True
        # 시간 체크
        return now.hour >= self.MARKET_CLOSE_HOUR

    def _save_result(self, date: str, result: dict):
        """결과를 JSON 파일로 저장"""
        file_path = self.DATA_DIR / f"result_{date}.json"

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)

        print(f"  저장됨: {file_path}")

    def _log_to_project_logger(self, date: str, candidates, simulation: dict):
        """project_logger에 결과 기록"""
        if not self.logger:
            return

        # 선정 종목 데이터 구성
        selections = [{
            'code': c.code,
            'name': c.name,
            'price': c.price,
            'change_pct': c.change_pct,
            'score': c.score
        } for c in candidates]

        # 결과 데이터 구성
        results = simulation.get('results', [])

        # 시장 상황 (TODO: 실제 데이터 연동)
        market_condition = {
            'kospi_change': 0,
            'kosdaq_change': 0
        }

        # 로거 호출
        formatted_date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
        self.logger.log_daily_trade(
            date=formatted_date,
            selections=selections,
            results=results,
            strategy_used="대형주_역추세",
            market_condition=market_condition
        )

        print(f"  project_logger 기록 완료")

    def run_backtest(self,
                     start_date: str,
                     end_date: str,
                     save_results: bool = True) -> dict:
        """
        기간 백테스트 실행

        Args:
            start_date: 시작일 (YYYYMMDD)
            end_date: 종료일 (YYYYMMDD)
            save_results: 결과 저장 여부

        Returns:
            백테스트 결과
        """
        print(f"\n{'#'*60}")
        print(f"# 페이퍼 트레이딩 백테스트")
        print(f"# 기간: {start_date} ~ {end_date}")
        print(f"{'#'*60}")

        daily_results = self.simulator.backtest_period(
            start_date, end_date, self.selector
        )

        if save_results:
            # 백테스트 결과 저장
            file_path = self.DATA_DIR / f"backtest_{start_date}_{end_date}.json"
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(daily_results, f, ensure_ascii=False, indent=2, default=str)
            print(f"\n[Scheduler] 백테스트 결과 저장됨: {file_path}")

        return {
            'start_date': start_date,
            'end_date': end_date,
            'total_days': len(daily_results),
            'daily_results': daily_results
        }

    def schedule_loop(self, interval_minutes: int = 60):
        """
        스케줄 루프 (지정 간격으로 실행 체크)

        Args:
            interval_minutes: 체크 간격 (분)
        """
        print(f"\n[Scheduler] 스케줄 루프 시작 (간격: {interval_minutes}분)")
        print(f"[Scheduler] 장 종료(16:00) 후 자동 실행됩니다.")

        last_run_date = None

        while True:
            now = datetime.now()
            today = now.strftime("%Y%m%d")

            # 이미 오늘 실행했으면 스킵
            if last_run_date == today:
                time.sleep(interval_minutes * 60)
                continue

            # 장 종료 후 실행
            if self._is_market_closed():
                print(f"\n[{now.strftime('%H:%M:%S')}] 장 종료 감지 - 일일 실행 시작")
                result = self.run_daily(today)

                if result['status'] == 'success':
                    last_run_date = today
                    print(f"[Scheduler] 오늘 실행 완료. 내일까지 대기.")

            # 대기
            print(f"[{now.strftime('%H:%M:%S')}] 다음 체크: {interval_minutes}분 후")
            time.sleep(interval_minutes * 60)


def main():
    """CLI 메인 함수"""
    import argparse

    parser = argparse.ArgumentParser(description='페이퍼 트레이딩 스케줄러')
    parser.add_argument('command', choices=['run', 'backtest', 'loop'],
                       help='실행 명령')
    parser.add_argument('--date', '-d', type=str, default=None,
                       help='실행 날짜 (YYYYMMDD)')
    parser.add_argument('--start', '-s', type=str, default=None,
                       help='백테스트 시작일')
    parser.add_argument('--end', '-e', type=str, default=None,
                       help='백테스트 종료일')
    parser.add_argument('--capital', '-c', type=int, default=1000000,
                       help='초기 자본금')
    parser.add_argument('--force', '-f', action='store_true',
                       help='장중에도 강제 실행')

    args = parser.parse_args()

    scheduler = DailyScheduler(capital=args.capital)

    if args.command == 'run':
        scheduler.run_daily(date=args.date, force=args.force)

    elif args.command == 'backtest':
        if not args.start or not args.end:
            print("백테스트에는 --start와 --end가 필요합니다.")
            return
        scheduler.run_backtest(args.start, args.end)

    elif args.command == 'loop':
        scheduler.schedule_loop()


if __name__ == "__main__":
    main()
