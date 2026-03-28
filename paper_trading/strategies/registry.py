"""
전략 레지스트리 - 모든 전략 관리
"""

import json
from pathlib import Path
from typing import Dict, List, Type, Optional
from datetime import datetime
from .base import BaseStrategy, StrategyResult

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "paper_trading"


class StrategyRegistry:
    """전략 레지스트리"""

    _strategies: Dict[str, Type[BaseStrategy]] = {}

    @classmethod
    def register(cls, strategy_class: Type[BaseStrategy]):
        """전략 등록"""
        cls._strategies[strategy_class.STRATEGY_ID] = strategy_class
        return strategy_class

    @classmethod
    def get(cls, strategy_id: str) -> Optional[Type[BaseStrategy]]:
        """전략 가져오기"""
        return cls._strategies.get(strategy_id)

    @classmethod
    def get_all(cls) -> Dict[str, Type[BaseStrategy]]:
        """모든 전략 가져오기"""
        return cls._strategies.copy()

    @classmethod
    def list_strategies(cls) -> List[Dict]:
        """전략 목록"""
        return [
            {
                'id': s.STRATEGY_ID,
                'name': s.STRATEGY_NAME,
                'description': s.DESCRIPTION
            }
            for s in cls._strategies.values()
        ]

    @classmethod
    def run_all(cls, date: str = None, top_n: int = 5) -> Dict[str, StrategyResult]:
        """모든 전략 실행"""
        results = {}

        for strategy_id, strategy_class in cls._strategies.items():
            print(f"\n[Registry] 전략 실행: {strategy_class.STRATEGY_NAME}")
            try:
                strategy = strategy_class()
                candidates = strategy.select_stocks(date=date, top_n=top_n)
                results[strategy_id] = strategy.get_result()
                print(f"  → {len(candidates)}개 종목 선정")
            except Exception as e:
                print(f"  → 오류: {e}")

        return results

    @classmethod
    def run_strategy(cls, strategy_id: str, date: str = None, top_n: int = 5) -> Optional[StrategyResult]:
        """특정 전략 실행"""
        strategy_class = cls.get(strategy_id)
        if not strategy_class:
            print(f"[Registry] 전략 없음: {strategy_id}")
            return None

        strategy = strategy_class()
        strategy.select_stocks(date=date, top_n=top_n)
        return strategy.get_result()

    @classmethod
    def save_results(cls, results: Dict[str, StrategyResult], date: str = None):
        """결과 저장"""
        if date is None:
            date = datetime.now().strftime('%Y%m%d')

        DATA_DIR.mkdir(parents=True, exist_ok=True)

        # 전략별 개별 저장
        for strategy_id, result in results.items():
            filename = DATA_DIR / f"candidates_{date}_{strategy_id}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
            print(f"  저장: {filename.name}")

        # 통합 저장 (비교용)
        combined = {
            'date': date,
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'strategies': {sid: r.to_dict() for sid, r in results.items()}
        }
        combined_file = DATA_DIR / f"candidates_{date}_all.json"
        with open(combined_file, 'w', encoding='utf-8') as f:
            json.dump(combined, f, ensure_ascii=False, indent=2)
        print(f"  통합 저장: {combined_file.name}")

    @classmethod
    def load_results(cls, date: str, strategy_id: str = None) -> Optional[Dict]:
        """결과 로드"""
        if strategy_id:
            filename = DATA_DIR / f"candidates_{date}_{strategy_id}.json"
        else:
            filename = DATA_DIR / f"candidates_{date}_all.json"

        if filename.exists():
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    @classmethod
    def get_comparison(cls, date: str) -> Dict:
        """전략별 결과 비교"""
        data = cls.load_results(date)
        if not data:
            return {}

        comparison = {
            'date': date,
            'strategies': []
        }

        for strategy_id, result in data.get('strategies', {}).items():
            sim = result.get('simulation', {})
            comparison['strategies'].append({
                'id': strategy_id,
                'name': result.get('strategy_name', strategy_id),
                'count': result.get('count', 0),
                'total_return': sim.get('total_return', 0) if sim else None,
                'win_rate': sim.get('win_rate', 0) if sim else None,
                'candidates': result.get('candidates', [])
            })

        return comparison
