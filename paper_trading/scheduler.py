"""
일일 실행 스케줄러 (전략별 분리)
- 장 종료 후 자동 실행
- 전략별 독립 시뮬레이션 → 전략별 결과 저장 → 전략별 리포트 + 비교 리포트
- project_logger 연동
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import json
import time
from typing import Optional, Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from .strategies import StrategyRegistry, StrategyResult, Candidate
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
    일일 페이퍼 트레이딩 스케줄러 (전략별 분리)

    실행 흐름:
    1. 장 종료 확인 (16:00 이후)
    2. 전략별 종목 선정
    3. 전략별 독립 매매 시뮬레이션
    4. 전략별 결과 저장 (result_{date}_{strategy_id}.json)
    5. 비교 리포트 저장 (result_{date}_comparison.json)
    6. project_logger 기록 (전략별)
    7. 리포트 생성
    """

    MARKET_CLOSE_HOUR = 16  # 장 종료 시간 (16:00)
    DATA_DIR = Path(__file__).parent.parent / "data" / "paper_trading"

    def __init__(self, capital: int = 1_000_000):
        self.capital = capital

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
        일일 페이퍼 트레이딩 실행 (전략별 분리)

        Args:
            date: 실행 날짜 (YYYYMMDD), None이면 오늘
            force: 장 종료 전이라도 강제 실행

        Returns:
            실행 결과 dict (전략별 결과 포함)
        """
        if date is None:
            date = datetime.now().strftime("%Y%m%d")

        print(f"\n{'#'*60}")
        print(f"# 페이퍼 트레이딩 일일 실행 (전략별 분리)")
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
            'strategies': {},
            'comparison': None,
            'logged': False,
        }

        try:
            # 1. 전략별 종목 선정
            print("\n[Step 1] 전략별 종목 선정")
            strategy_results = StrategyRegistry.run_all(date=date, top_n=5)

            if not strategy_results:
                print("[Scheduler] 실행 가능한 전략 없음 - 종료")
                result['status'] = 'no_strategies'
                return result

            # 2. 전략별 독립 시뮬레이션
            print("\n[Step 2] 전략별 독립 시뮬레이션")
            for strategy_id, strat_result in strategy_results.items():
                print(f"\n  --- {strat_result.strategy_name} ({strategy_id}) ---")

                if not strat_result.candidates:
                    print(f"  [{strategy_id}] 선정 종목 없음 - 스킵")
                    result['strategies'][strategy_id] = {
                        'strategy_id': strategy_id,
                        'strategy_name': strat_result.strategy_name,
                        'selection': strat_result.to_dict(),
                        'simulation': None,
                        'status': 'no_candidates'
                    }
                    continue

                # 전략별 독립 시뮬레이터 생성
                simulator = TradingSimulator(
                    capital=self.capital,
                    strategy_id=strategy_id,
                    strategy_name=strat_result.strategy_name
                )

                # Candidate → StockCandidate 변환
                from .selector import StockCandidate
                stock_candidates = []
                for c in strat_result.candidates:
                    sc = StockCandidate(
                        code=c.code,
                        name=c.name,
                        price=c.price,
                        change_pct=c.change_pct,
                        trading_value=c.trading_value,
                        market_cap=c.market_cap,
                        volume=c.volume,
                        score=c.score,
                        score_detail=c.score_detail,
                        rank=c.rank,
                    )
                    stock_candidates.append(sc)

                # 시뮬레이션 실행
                trade_results = simulator.simulate_day(stock_candidates, date)
                sim_summary = simulator.get_daily_summary()

                # StrategyResult에 시뮬레이션 결과 저장
                strat_result.simulation = sim_summary

                result['strategies'][strategy_id] = {
                    'strategy_id': strategy_id,
                    'strategy_name': strat_result.strategy_name,
                    'selection': strat_result.to_dict(),
                    'simulation': sim_summary,
                    'status': 'success'
                }

            # 3. 전략별 개별 결과 저장
            print("\n[Step 3] 전략별 결과 저장")
            for strategy_id, strat_data in result['strategies'].items():
                self._save_strategy_result(date, strategy_id, strat_data)

            # 4. 비교 리포트 생성 및 저장
            print("\n[Step 4] 비교 리포트 생성")
            comparison = self._generate_comparison(date, result['strategies'])
            result['comparison'] = comparison
            self._save_comparison(date, comparison)

            # 5. project_logger 기록 (전략별)
            if self.logger:
                print("\n[Step 5] 로거 기록 (전략별)")
                for strategy_id, strat_data in result['strategies'].items():
                    if strat_data.get('simulation'):
                        self._log_to_project_logger(
                            date, strategy_id, strat_data
                        )
                result['logged'] = True

            # 6. 리포트 생성
            if self.reporter:
                print("\n[Step 6] 리포트 생성")
                self.reporter.generate_daily_report(date.replace('', '-'))
                self.reporter.update_knowledge_base()

            # 7. 통합 결과도 저장 (하위 호환)
            self._save_combined_result(date, result)

            print(f"\n[Scheduler] 일일 실행 완료!")
            self._print_comparison(comparison)

        except Exception as e:
            print(f"[Scheduler] 오류 발생: {e}")
            result['status'] = 'error'
            result['error'] = str(e)
            import traceback
            traceback.print_exc()

        return result

    def _save_strategy_result(self, date: str, strategy_id: str, data: dict):
        """전략별 결과를 개별 JSON 파일로 저장"""
        file_path = self.DATA_DIR / f"result_{date}_{strategy_id}.json"

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

        print(f"  저장됨: {file_path.name}")

    def _save_comparison(self, date: str, comparison: dict):
        """비교 리포트 저장"""
        file_path = self.DATA_DIR / f"result_{date}_comparison.json"

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(comparison, f, ensure_ascii=False, indent=2, default=str)

        print(f"  비교 리포트 저장됨: {file_path.name}")

    def _save_combined_result(self, date: str, result: dict):
        """통합 결과 저장 (하위 호환용)"""
        file_path = self.DATA_DIR / f"result_{date}.json"

        # 기존 형식과 호환되는 통합 요약
        best_strategy = None
        best_return = -999

        for sid, sdata in result['strategies'].items():
            sim = sdata.get('simulation')
            if sim and sim.get('total_return', -999) > best_return:
                best_return = sim['total_return']
                best_strategy = sid

        combined = {
            'date': date,
            'status': result['status'],
            'best_strategy': best_strategy,
            'strategies': result['strategies'],
            'comparison': result['comparison'],
            # 하위 호환: 베스트 전략의 결과를 selection/simulation에 넣음
            'selection': result['strategies'].get(best_strategy, {}).get('selection') if best_strategy else None,
            'simulation': result['strategies'].get(best_strategy, {}).get('simulation') if best_strategy else None,
            'logged': result.get('logged', False),
        }

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(combined, f, ensure_ascii=False, indent=2, default=str)

        print(f"  통합 결과 저장됨: {file_path.name}")

    def _generate_comparison(self, date: str, strategies: dict) -> dict:
        """전략별 비교 리포트 생성"""
        comparison = {
            'date': date,
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'strategy_count': len(strategies),
            'strategies': [],
            'ranking': [],
        }

        strategy_summaries = []

        for strategy_id, sdata in strategies.items():
            sim = sdata.get('simulation', {})
            selection = sdata.get('selection', {})

            summary = {
                'strategy_id': strategy_id,
                'strategy_name': sdata.get('strategy_name', strategy_id),
                'status': sdata.get('status', 'unknown'),
                'candidate_count': selection.get('count', 0) if selection else 0,
                'total_trades': sim.get('total_trades', 0) if sim else 0,
                'wins': sim.get('wins', 0) if sim else 0,
                'losses': sim.get('losses', 0) if sim else 0,
                'win_rate': sim.get('win_rate', 0) if sim else 0,
                'total_return': sim.get('total_return', 0) if sim else 0,
                'avg_return': sim.get('avg_return', 0) if sim else 0,
                'total_return_amount': sim.get('total_return_amount', 0) if sim else 0,
                'profit_exits': sim.get('profit_exits', 0) if sim else 0,
                'loss_exits': sim.get('loss_exits', 0) if sim else 0,
                'close_exits': sim.get('close_exits', 0) if sim else 0,
            }
            strategy_summaries.append(summary)

        comparison['strategies'] = strategy_summaries

        # 수익률 기준 랭킹
        ranked = sorted(
            strategy_summaries,
            key=lambda x: x['total_return'],
            reverse=True
        )
        comparison['ranking'] = [
            {
                'rank': i + 1,
                'strategy_id': s['strategy_id'],
                'strategy_name': s['strategy_name'],
                'total_return': s['total_return'],
                'win_rate': s['win_rate'],
            }
            for i, s in enumerate(ranked)
        ]

        # 전체 통합 통계
        total_trades = sum(s['total_trades'] for s in strategy_summaries)
        total_wins = sum(s['wins'] for s in strategy_summaries)
        total_return_sum = sum(s['total_return'] for s in strategy_summaries)
        active_strategies = len([s for s in strategy_summaries if s['total_trades'] > 0])

        comparison['aggregate'] = {
            'active_strategies': active_strategies,
            'total_trades': total_trades,
            'total_wins': total_wins,
            'overall_win_rate': round(total_wins / total_trades * 100, 1) if total_trades > 0 else 0,
            'avg_strategy_return': round(total_return_sum / active_strategies, 2) if active_strategies > 0 else 0,
            'best_strategy': ranked[0]['strategy_id'] if ranked else None,
            'worst_strategy': ranked[-1]['strategy_id'] if ranked else None,
        }

        return comparison

    def _print_comparison(self, comparison: dict):
        """비교 리포트 출력"""
        print(f"\n{'='*60}")
        print(f"[비교 리포트] 전략별 성과 ({comparison['date']})")
        print(f"{'='*60}")

        print(f"\n{'전략':<25} {'거래':>5} {'승률':>8} {'수익률':>10} {'손익':>12}")
        print("-" * 65)

        for s in comparison.get('strategies', []):
            name = s['strategy_name'][:23]
            trades = s['total_trades']
            wr = f"{s['win_rate']:.1f}%"
            ret = f"{s['total_return']:+.2f}%"
            amt = f"{s['total_return_amount']:+,}원"
            print(f"{name:<25} {trades:>5} {wr:>8} {ret:>10} {amt:>12}")

        print("-" * 65)

        # 랭킹
        ranking = comparison.get('ranking', [])
        if ranking:
            print(f"\n[랭킹] ", end="")
            for r in ranking:
                print(f"{r['rank']}위 {r['strategy_name']}({r['total_return']:+.2f}%) ", end="")
            print()

        # 통합 통계
        agg = comparison.get('aggregate', {})
        if agg:
            print(f"\n[통합] 활성 전략: {agg['active_strategies']}개 | "
                  f"전체 승률: {agg['overall_win_rate']:.1f}% | "
                  f"평균 전략 수익률: {agg['avg_strategy_return']:+.2f}%")

        print(f"{'='*60}")

    def _is_market_closed(self) -> bool:
        """장 종료 여부 확인"""
        now = datetime.now()
        if now.weekday() >= 5:
            return True
        return now.hour >= self.MARKET_CLOSE_HOUR

    def _log_to_project_logger(self, date: str, strategy_id: str, strat_data: dict):
        """project_logger에 전략별 결과 기록"""
        if not self.logger:
            return

        selection = strat_data.get('selection', {})
        simulation = strat_data.get('simulation', {})

        # 선정 종목 데이터
        selections = selection.get('candidates', [])

        # 결과 데이터
        results = simulation.get('results', [])

        # 시장 상황
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
            strategy_used=strat_data.get('strategy_name', strategy_id),
            market_condition=market_condition
        )

        print(f"  [{strategy_id}] project_logger 기록 완료")

    def run_backtest(self,
                     start_date: str,
                     end_date: str,
                     strategy_id: str = None,
                     save_results: bool = True) -> dict:
        """
        기간 백테스트 실행 (전략별)

        Args:
            start_date: 시작일 (YYYYMMDD)
            end_date: 종료일 (YYYYMMDD)
            strategy_id: 특정 전략만 실행 (None이면 전체)
            save_results: 결과 저장 여부

        Returns:
            백테스트 결과
        """
        print(f"\n{'#'*60}")
        print(f"# 페이퍼 트레이딩 백테스트 (전략별)")
        print(f"# 기간: {start_date} ~ {end_date}")
        if strategy_id:
            print(f"# 전략: {strategy_id}")
        print(f"{'#'*60}")

        # 대상 전략 결정
        if strategy_id:
            strategy_class = StrategyRegistry.get(strategy_id)
            if not strategy_class:
                print(f"[Scheduler] 전략 없음: {strategy_id}")
                return {}
            target_strategies = {strategy_id: strategy_class}
        else:
            target_strategies = StrategyRegistry.get_all()

        # 거래일 목록 조회
        try:
            from pykrx import stock
            dates = stock.get_market_ohlcv(start_date, end_date, "005930").index
            trade_dates = [d.strftime("%Y%m%d") for d in dates]
        except Exception as e:
            print(f"[Scheduler] 거래일 조회 실패: {e}")
            return {}

        # 전략별 백테스트 결과
        backtest_results = {}

        for sid, strategy_class in target_strategies.items():
            print(f"\n{'='*50}")
            print(f"[Backtest] {strategy_class.STRATEGY_NAME} ({sid})")
            print(f"{'='*50}")

            daily_results = []
            cumulative_return = 0

            for dt in trade_dates:
                try:
                    strategy = strategy_class()
                    candidates = strategy.select_stocks(date=dt, top_n=5)

                    if not candidates:
                        continue

                    # 전략별 시뮬레이터
                    simulator = TradingSimulator(
                        capital=self.capital,
                        strategy_id=sid,
                        strategy_name=strategy_class.STRATEGY_NAME
                    )

                    from .selector import StockCandidate
                    stock_candidates = [
                        StockCandidate(
                            code=c.code, name=c.name, price=c.price,
                            change_pct=c.change_pct, trading_value=c.trading_value,
                            market_cap=c.market_cap, volume=c.volume,
                            score=c.score, score_detail=c.score_detail, rank=c.rank,
                        )
                        for c in candidates
                    ]

                    simulator.simulate_day(stock_candidates, dt, use_intraday=False)
                    summary = simulator.get_daily_summary()
                    cumulative_return += summary['total_return']
                    summary['cumulative_return'] = round(cumulative_return, 2)
                    daily_results.append(summary)

                except Exception as e:
                    print(f"  [{dt}] 오류: {e}")
                    continue

            backtest_results[sid] = {
                'strategy_id': sid,
                'strategy_name': strategy_class.STRATEGY_NAME,
                'start_date': start_date,
                'end_date': end_date,
                'total_days': len(daily_results),
                'cumulative_return': round(cumulative_return, 2),
                'daily_results': daily_results,
            }

        if save_results:
            suffix = f"_{strategy_id}" if strategy_id else "_all"
            file_path = self.DATA_DIR / f"backtest_{start_date}_{end_date}{suffix}.json"
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(backtest_results, f, ensure_ascii=False, indent=2, default=str)
            print(f"\n[Scheduler] 백테스트 결과 저장됨: {file_path}")

        return backtest_results

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

    parser = argparse.ArgumentParser(description='페이퍼 트레이딩 스케줄러 (전략별 분리)')
    parser.add_argument('command', choices=['run', 'backtest', 'loop'],
                       help='실행 명령')
    parser.add_argument('--date', '-d', type=str, default=None,
                       help='실행 날짜 (YYYYMMDD)')
    parser.add_argument('--start', '-s', type=str, default=None,
                       help='백테스트 시작일')
    parser.add_argument('--end', '-e', type=str, default=None,
                       help='백테스트 종료일')
    parser.add_argument('--strategy', type=str, default=None,
                       help='특정 전략만 실행 (strategy_id)')
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
        scheduler.run_backtest(args.start, args.end, strategy_id=args.strategy)

    elif args.command == 'loop':
        scheduler.schedule_loop()


if __name__ == "__main__":
    main()
