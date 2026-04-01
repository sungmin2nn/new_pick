"""
모멘텀 전략
- 전일 급등 종목 중 거래대금 상위
- 추세 추종 (상승 종목에 편승)
"""

import sys
from pathlib import Path
from typing import List, Dict
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from .base import BaseStrategy, Candidate
from .registry import StrategyRegistry
from utils import format_kst_time

# 네이버 금융 우선, pykrx 폴백
try:
    from naver_market import stock as naver_stock
    pykrx_stock = naver_stock
except ImportError:
    try:
        from pykrx import stock as pykrx_stock
    except ImportError:
        pykrx_stock = None


@StrategyRegistry.register
class MomentumStrategy(BaseStrategy):
    """모멘텀 전략"""

    STRATEGY_ID = "momentum"
    STRATEGY_NAME = "모멘텀 추세"
    DESCRIPTION = "전일 급등 종목 중 거래대금 상위 - 추세 추종"

    # 필터 조건
    MIN_PRICE = 3000           # 최소 가격
    MIN_CHANGE = 3.0           # 최소 상승률
    MAX_CHANGE = 15.0          # 최대 상승률 (상한가 제외)
    MIN_TRADING_VALUE = 30     # 최소 거래대금 (억)

    # 점수 가중치
    WEIGHTS = {
        'change_pct': 35,      # 상승률
        'trading_value': 30,   # 거래대금 (관심도)
        'volume_surge': 20,    # 거래량 급증
        'price_level': 15      # 가격대
    }

    def __init__(self):
        super().__init__()

    def select_stocks(self, date: str = None, top_n: int = 5) -> List[Candidate]:
        """종목 선정"""
        if date is None:
            date = format_kst_time(format_str='%Y%m%d')

        self.selection_date = date
        print(f"\n[{self.STRATEGY_NAME}] 종목 선정 시작 ({date})")

        # 1. 데이터 수집
        all_stocks = self._fetch_market_data(date)
        if not all_stocks:
            print(f"  데이터 없음")
            return []

        print(f"  전체 종목: {len(all_stocks)}개")

        # 2. 필터링
        filtered = self._filter_stocks(all_stocks)
        print(f"  필터 통과: {len(filtered)}개")

        # 3. 점수 계산
        scored = self._calculate_scores(filtered)

        # 4. 상위 N개 선정
        scored.sort(key=lambda x: x.score, reverse=True)
        self.candidates = scored[:top_n]

        for i, c in enumerate(self.candidates, 1):
            c.rank = i

        print(f"  선정 완료: {len(self.candidates)}개")
        return self.candidates

    def _fetch_market_data(self, date: str) -> List[Dict]:
        """시장 데이터 수집"""
        if pykrx_stock is None:
            return []

        stocks = []

        try:
            for market in ['KOSPI', 'KOSDAQ']:
                df = pykrx_stock.get_market_ohlcv_by_ticker(date, market=market)

                if df.empty:
                    continue

                for code in df.index:
                    try:
                        row = df.loc[code]
                        close = int(row['종가'])
                        if close == 0:
                            continue

                        change = float(row['등락률']) if '등락률' in row else 0
                        volume = int(row['거래량'])
                        trading_value = int(row['거래대금']) if '거래대금' in row else 0

                        name = pykrx_stock.get_market_ticker_name(code)

                        stocks.append({
                            'code': code,
                            'name': name,
                            'price': close,
                            'change_pct': change,
                            'volume': volume,
                            'trading_value': trading_value,
                            'market': market
                        })
                    except:
                        continue

        except Exception as e:
            print(f"  데이터 수집 오류: {e}")

        return stocks

    def _filter_stocks(self, stocks: List[Dict]) -> List[Dict]:
        """필터링"""
        filtered = []

        for s in stocks:
            # 가격 조건
            if s['price'] < self.MIN_PRICE:
                continue

            # 상승 조건
            if s['change_pct'] < self.MIN_CHANGE or s['change_pct'] > self.MAX_CHANGE:
                continue

            # 거래대금 조건
            if s['trading_value'] < self.MIN_TRADING_VALUE * 100000000:
                continue

            # 우선주/스팩 제외
            name = s.get('name', '')
            if any(x in name for x in ['우', '스팩', 'SPAC', '리츠']):
                continue

            filtered.append(s)

        return filtered

    def _calculate_scores(self, stocks: List[Dict]) -> List[Candidate]:
        """점수 계산"""
        if not stocks:
            return []

        max_change = max(s['change_pct'] for s in stocks) or 1
        max_value = max(s['trading_value'] for s in stocks) or 1

        candidates = []

        for s in stocks:
            scores = {}

            # 상승률 점수
            scores['change_pct'] = (s['change_pct'] / max_change) * self.WEIGHTS['change_pct']

            # 거래대금 점수
            scores['trading_value'] = (s['trading_value'] / max_value) * self.WEIGHTS['trading_value']

            # 거래량 급증 (평균 대비 - 간단히 거래대금으로 대체)
            scores['volume_surge'] = min(s['trading_value'] / (50 * 100000000), 1) * self.WEIGHTS['volume_surge']

            # 가격대 점수
            if 5000 <= s['price'] <= 50000:
                scores['price_level'] = self.WEIGHTS['price_level']
            else:
                scores['price_level'] = self.WEIGHTS['price_level'] * 0.5

            total_score = sum(scores.values())

            candidates.append(Candidate(
                code=s['code'],
                name=s['name'],
                price=s['price'],
                change_pct=s['change_pct'],
                score=round(total_score, 1),
                score_detail=scores,
                volume=s['volume'],
                trading_value=s['trading_value']
            ))

        return candidates

    def get_params(self) -> Dict:
        return {
            'min_price': self.MIN_PRICE,
            'min_change': self.MIN_CHANGE,
            'max_change': self.MAX_CHANGE,
            'min_trading_value': self.MIN_TRADING_VALUE,
            'weights': self.WEIGHTS
        }
