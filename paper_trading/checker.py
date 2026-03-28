"""
장중 상태 체크 모듈
- intraday_collector 활용 (기존 코드 재사용)
- 현재까지의 분봉 데이터로 익절/손절 도달 여부 확인
- 상태: waiting, profit_hit, loss_hit, none
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

# 기존 intraday_collector 재사용
from intraday_collector import IntradayCollector
from utils import format_kst_time

# 매매 파라미터 (simulator와 동일)
PROFIT_TARGET = 3.0
LOSS_TARGET = -1.5

DATA_DIR = Path(__file__).parent.parent / "data" / "paper_trading"


class StatusChecker:
    """장중 상태 체크기"""

    def __init__(self):
        self.collector = IntradayCollector()
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def check_status(self, date: str = None) -> Dict:
        """
        선정 종목들의 현재 상태 체크

        Args:
            date: 날짜 (YYYYMMDD), None이면 오늘

        Returns:
            상태 정보 dict
        """
        if date is None:
            date = format_kst_time(format_str='%Y%m%d')

        print(f"\n{'='*50}")
        print(f"[Checker] 장중 상태 체크 ({date})")
        print(f"  시간: {format_kst_time(format_str='%H:%M:%S')}")
        print(f"{'='*50}")

        # 오늘 선정 종목 로드
        candidates = self._load_candidates(date)

        if not candidates:
            print("[Checker] 선정 종목 없음")
            return {'date': date, 'status': 'no_candidates', 'stocks': []}

        print(f"  선정 종목: {len(candidates)}개")

        # 각 종목 상태 체크
        stock_statuses = []

        for candidate in candidates:
            status = self._check_stock_status(candidate, date)
            if status:
                stock_statuses.append(status)
                self._print_status(status)

        # 결과 저장
        result = {
            'date': date,
            'checked_at': format_kst_time(format_str='%Y-%m-%d %H:%M:%S'),
            'status': 'checked',
            'total_stocks': len(candidates),
            'profit_hit': len([s for s in stock_statuses if s['status'] == 'profit_hit']),
            'loss_hit': len([s for s in stock_statuses if s['status'] == 'loss_hit']),
            'waiting': len([s for s in stock_statuses if s['status'] == 'waiting']),
            'stocks': stock_statuses
        }

        self._save_status(date, result)
        self._print_summary(result)

        return result

    def _load_candidates(self, date: str) -> List[Dict]:
        """선정 종목 로드"""
        # candidates 파일 먼저 확인
        candidates_file = DATA_DIR / f"candidates_{date}.json"
        if candidates_file.exists():
            with open(candidates_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('candidates', [])

        # result 파일에서 selection 확인
        result_file = DATA_DIR / f"result_{date}.json"
        if result_file.exists():
            with open(result_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                selection = data.get('selection', {})
                return selection.get('candidates', [])

        return []

    def _check_stock_status(self, candidate: Dict, date: str) -> Optional[Dict]:
        """개별 종목 상태 체크"""
        code = candidate.get('code', '')
        name = candidate.get('name', '')

        try:
            # intraday_collector의 analyze_profit_loss 활용
            analysis = self.collector.analyze_profit_loss(
                code, date,
                profit_target=PROFIT_TARGET,
                loss_target=LOSS_TARGET,
                avg_volume_20d=0
            )

            if not analysis:
                return {
                    'code': code,
                    'name': name,
                    'status': 'no_data',
                    'message': '분봉 데이터 없음'
                }

            # 결과 추출
            virtual_result = analysis.get('actual_result') or analysis.get('virtual_result', {})
            first_hit = virtual_result.get('first_hit', 'none')
            first_hit_time = virtual_result.get('first_hit_time', '')
            entry_price = analysis.get('entry_check', {}).get('entry_price', 0) or analysis.get('opening_price', 0)
            current_price = virtual_result.get('closing_price', entry_price)

            # 상태 결정
            if first_hit == 'profit':
                status = 'profit_hit'
                message = f'익절 도달 ({first_hit_time})'
            elif first_hit == 'loss':
                status = 'loss_hit'
                message = f'손절 도달 ({first_hit_time})'
            else:
                status = 'waiting'
                current_pct = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
                message = f'대기 중 (현재 {current_pct:+.2f}%)'

            return {
                'code': code,
                'name': name,
                'status': status,
                'entry_price': entry_price,
                'current_price': current_price,
                'current_pct': round(((current_price - entry_price) / entry_price * 100), 2) if entry_price > 0 else 0,
                'hit_time': first_hit_time if first_hit in ['profit', 'loss'] else None,
                'max_profit_pct': round(virtual_result.get('max_profit_percent', 0), 2),
                'max_loss_pct': round(virtual_result.get('max_loss_percent', 0), 2),
                'message': message
            }

        except Exception as e:
            return {
                'code': code,
                'name': name,
                'status': 'error',
                'message': str(e)
            }

    def _print_status(self, status: Dict):
        """개별 상태 출력"""
        name = status.get('name', '')
        s = status.get('status', '')
        msg = status.get('message', '')

        icon = {
            'profit_hit': '✅',
            'loss_hit': '❌',
            'waiting': '⏳',
            'no_data': '⚠️',
            'error': '❗'
        }.get(s, '?')

        print(f"  {icon} [{name}] {msg}")

    def _print_summary(self, result: Dict):
        """요약 출력"""
        print(f"\n{'='*50}")
        print(f"[Checker] 상태 요약")
        print(f"{'='*50}")
        print(f"  총 종목: {result['total_stocks']}개")
        print(f"  익절 도달: {result['profit_hit']}개")
        print(f"  손절 도달: {result['loss_hit']}개")
        print(f"  대기 중: {result['waiting']}개")
        print(f"{'='*50}")

    def _save_status(self, date: str, result: Dict):
        """상태 저장"""
        status_file = DATA_DIR / f"status_{date}.json"

        with open(status_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"\n  저장됨: {status_file}")


def main():
    """CLI 메인 함수"""
    import argparse

    parser = argparse.ArgumentParser(description='페이퍼 트레이딩 장중 상태 체크')
    parser.add_argument('--date', '-d', type=str, default=None,
                       help='체크 날짜 (YYYYMMDD)')

    args = parser.parse_args()

    checker = StatusChecker()
    checker.check_status(date=args.date)


if __name__ == "__main__":
    main()
