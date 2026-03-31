"""
대형주 역추세 전략
- 시총 상위 대형주 중 전일 하락 종목
- 기술적 과매도 + 반등 가능성
"""

import sys
from pathlib import Path
from typing import List, Dict
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from .base import BaseStrategy, Candidate
from .registry import StrategyRegistry
from utils import format_kst_time

# pykrx import
try:
    from pykrx import stock as pykrx_stock
except ImportError:
    pykrx_stock = None


@StrategyRegistry.register
class LargecapContrarianStrategy(BaseStrategy):
    """대형주 역추세 전략"""

    STRATEGY_ID = "largecap_contrarian"
    STRATEGY_NAME = "대형주 역추세"
    DESCRIPTION = "시총 상위 대형주 중 전일 하락 종목에서 반등 기회 포착"

    # 시총 상위 대형주 목록 (KOSPI 50 + 주요 대형주)
    LARGE_CAP_STOCKS = [
        '005930',  # 삼성전자
        '000660',  # SK하이닉스
        '373220',  # LG에너지솔루션
        '005380',  # 현대차
        '000270',  # 기아
        '005490',  # POSCO홀딩스
        '035420',  # NAVER
        '035720',  # 카카오
        '051910',  # LG화학
        '006400',  # 삼성SDI
        '003670',  # 포스코퓨처엠
        '105560',  # KB금융
        '055550',  # 신한지주
        '086790',  # 하나금융지주
        '012330',  # 현대모비스
        '028260',  # 삼성물산
        '066570',  # LG전자
        '003550',  # LG
        '096770',  # SK이노베이션
        '034730',  # SK
        '018260',  # 삼성에스디에스
        '032830',  # 삼성생명
        '015760',  # 한국전력
        '033780',  # KT&G
        '009150',  # 삼성전기
        '000810',  # 삼성화재
        '017670',  # SK텔레콤
        '030200',  # KT
        '036570',  # 엔씨소프트
        '011170',  # 롯데케미칼
        '010950',  # S-Oil
        '004020',  # 현대제철
        '090430',  # 아모레퍼시픽
        '097950',  # CJ제일제당
        '051900',  # LG생활건강
        '010130',  # 고려아연
        '009540',  # 한국조선해양
        '267250',  # 현대중공업
        '042660',  # 한화오션
        '352820',  # 하이브
    ]

    # 필터 조건
    MIN_PRICE = 5000          # 최소 가격
    MAX_CHANGE = -1.5         # 최대 등락률 (하락만)
    MIN_TRADING_VALUE = 50    # 최소 거래대금 (억)

    # 점수 가중치
    WEIGHTS = {
        'market_cap': 30,      # 시가총액 (대형주)
        'change_pct': 25,      # 하락폭 (클수록)
        'trading_value': 20,   # 거래대금
        'price_level': 15,     # 가격대
        'volatility': 10       # 변동성
    }

    def __init__(self):
        super().__init__()

    def select_stocks(self, date: str = None, top_n: int = 5) -> List[Candidate]:
        """종목 선정"""
        if date is None:
            date = format_kst_time(format_str='%Y%m%d')

        self.selection_date = date
        print(f"\n[{self.STRATEGY_NAME}] 종목 선정 시작 ({date})")

        # 1. 전체 종목 데이터 수집
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
        """시장 데이터 수집 (미리 정의된 대형주 목록 사용)"""
        if pykrx_stock is None:
            print("  pykrx 없음")
            return []

        stocks = []
        print(f"  대형주 {len(self.LARGE_CAP_STOCKS)}개 조회 중...")

        for code in self.LARGE_CAP_STOCKS:
            try:
                # 개별 종목 OHLCV 조회
                df = pykrx_stock.get_market_ohlcv(date, date, code)
                if df.empty:
                    continue

                row = df.iloc[-1]
                close = int(row['종가'])
                if close == 0:
                    continue

                change = float(row['등락률']) if '등락률' in row.index else 0
                volume = int(row['거래량']) if '거래량' in row.index else 0

                # 거래대금 계산 (거래량 * 종가)
                trading_value = volume * close

                # 종목명 조회
                name = pykrx_stock.get_market_ticker_name(code)

                stocks.append({
                    'code': code,
                    'name': name,
                    'price': close,
                    'change_pct': change,
                    'volume': volume,
                    'trading_value': trading_value,
                    'market_cap': 0,  # 시총은 별도 조회 필요시 추가
                    'market': 'KOSPI'
                })
            except Exception as e:
                continue

        print(f"  조회 완료: {len(stocks)}개")
        return stocks

    def _filter_stocks(self, stocks: List[Dict]) -> List[Dict]:
        """필터링"""
        filtered = []

        for s in stocks:
            # 가격 조건
            if s['price'] < self.MIN_PRICE:
                continue

            # 하락 조건
            if s['change_pct'] > self.MAX_CHANGE:
                continue

            # 거래대금 조건 (억 단위)
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

        # 정규화를 위한 최대/최소값
        max_cap = max(s['market_cap'] for s in stocks) or 1
        max_change = max(abs(s['change_pct']) for s in stocks) or 1
        max_value = max(s['trading_value'] for s in stocks) or 1

        candidates = []

        for s in stocks:
            scores = {}

            # 시가총액 점수 (대형주 우대)
            scores['market_cap'] = (s['market_cap'] / max_cap) * self.WEIGHTS['market_cap']

            # 하락폭 점수 (많이 하락할수록)
            scores['change_pct'] = (abs(s['change_pct']) / max_change) * self.WEIGHTS['change_pct']

            # 거래대금 점수
            scores['trading_value'] = (s['trading_value'] / max_value) * self.WEIGHTS['trading_value']

            # 가격대 점수 (중간 가격대 우대)
            if 10000 <= s['price'] <= 100000:
                scores['price_level'] = self.WEIGHTS['price_level']
            elif 5000 <= s['price'] < 10000:
                scores['price_level'] = self.WEIGHTS['price_level'] * 0.7
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
                market_cap=s['market_cap'],
                volume=s['volume'],
                trading_value=s['trading_value']
            ))

        return candidates

    def get_params(self) -> Dict:
        return {
            'min_price': self.MIN_PRICE,
            'max_change': self.MAX_CHANGE,
            'min_trading_value': self.MIN_TRADING_VALUE,
            'weights': self.WEIGHTS
        }
