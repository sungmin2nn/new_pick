"""
테마/정책 전략
- 정부 정책 발표 관련 테마주
- 미국 섹터 ETF 연동
"""

import sys
from pathlib import Path
from typing import List, Dict
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from .base import BaseStrategy, Candidate
from .registry import StrategyRegistry
from utils import format_kst_time, get_headers

try:
    from pykrx import stock as pykrx_stock
except ImportError:
    pykrx_stock = None


@StrategyRegistry.register
class ThemePolicyStrategy(BaseStrategy):
    """테마/정책 전략"""

    STRATEGY_ID = "theme_policy"
    STRATEGY_NAME = "테마/정책"
    DESCRIPTION = "정부 정책 및 테마 관련주 - 뉴스 기반 선정"

    # 테마별 관련 종목
    THEME_STOCKS = {
        '우주항공': ['047810', '190650', '012450', '042670'],  # 한국항공우주, 코미팜, 한화에어로, 인트로메딕
        '방산': ['012450', '047810', '079550', '272210'],  # 한화에어로, 한국항공우주, LIG넥스원, 한화시스템
        '바이오': ['091990', '086890', '096530', '141080'],  # 셀트리온헬스, 이수앱지스, 씨젠, 레고켐바이오
        '2차전지': ['247540', '003670', '066970', '373220'],  # 에코프로비엠, 포스코퓨처엠, 엘앤에프, LG에너지솔루션
        'AI반도체': ['005930', '000660', '042700', '069960'],  # 삼성전자, SK하이닉스, 한미반도체, 현대로템
    }

    # 점수 가중치
    WEIGHTS = {
        'theme_relevance': 40,   # 테마 관련도
        'change_pct': 25,        # 등락률
        'trading_value': 20,     # 거래대금
        'news_count': 15         # 뉴스 언급량
    }

    def __init__(self):
        super().__init__()
        self.session = requests.Session()
        self.headers = get_headers()
        self.active_themes = []

    def select_stocks(self, date: str = None, top_n: int = 5) -> List[Candidate]:
        """종목 선정"""
        if date is None:
            date = format_kst_time(format_str='%Y%m%d')

        self.selection_date = date
        print(f"\n[{self.STRATEGY_NAME}] 종목 선정 시작 ({date})")

        # 1. 활성 테마 감지
        self.active_themes = self._detect_active_themes()
        print(f"  활성 테마: {self.active_themes}")

        if not self.active_themes:
            # 기본 테마 사용
            self.active_themes = ['AI반도체', '2차전지']
            print(f"  기본 테마 사용: {self.active_themes}")

        # 2. 테마 관련 종목 수집
        theme_codes = set()
        for theme in self.active_themes:
            codes = self.THEME_STOCKS.get(theme, [])
            theme_codes.update(codes)

        print(f"  관련 종목: {len(theme_codes)}개")

        # 3. 시장 데이터 가져오기
        stocks = self._fetch_stock_data(list(theme_codes), date)

        # 4. 점수 계산
        scored = self._calculate_scores(stocks)

        # 5. 상위 N개 선정
        scored.sort(key=lambda x: x.score, reverse=True)
        self.candidates = scored[:top_n]

        for i, c in enumerate(self.candidates, 1):
            c.rank = i

        print(f"  선정 완료: {len(self.candidates)}개")
        return self.candidates

    def _detect_active_themes(self) -> List[str]:
        """활성 테마 감지 (뉴스 기반)"""
        active = []

        keywords = {
            '우주': '우주항공',
            '누리호': '우주항공',
            '방산': '방산',
            '무기': '방산',
            '바이오': '바이오',
            '신약': '바이오',
            '배터리': '2차전지',
            '전기차': '2차전지',
            'AI': 'AI반도체',
            '반도체': 'AI반도체',
            '엔비디아': 'AI반도체',
        }

        try:
            # 네이버 뉴스 헤드라인 체크
            url = 'https://finance.naver.com/news/mainnews.naver'
            response = self.session.get(url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')

            headlines = soup.find_all('a', {'class': 'articleSubject'})
            text = ' '.join([h.get_text() for h in headlines[:20]])

            for keyword, theme in keywords.items():
                if keyword in text and theme not in active:
                    active.append(theme)

        except Exception as e:
            print(f"  뉴스 체크 실패: {e}")

        return active[:3]  # 최대 3개 테마

    def _fetch_stock_data(self, codes: List[str], date: str) -> List[Dict]:
        """종목 데이터 수집"""
        stocks = []

        if pykrx_stock is None:
            return stocks

        for code in codes:
            try:
                df = pykrx_stock.get_market_ohlcv_by_date(
                    fromdate=date, todate=date, ticker=code
                )

                if df.empty:
                    continue

                row = df.iloc[0]
                close = int(row['종가'])
                change = float(row['등락률']) if '등락률' in row else 0
                volume = int(row['거래량'])
                trading_value = int(row['거래대금']) if '거래대금' in row else 0

                name = pykrx_stock.get_market_ticker_name(code)

                # 어떤 테마에 속하는지
                themes = [t for t, codes in self.THEME_STOCKS.items()
                         if code in codes and t in self.active_themes]

                stocks.append({
                    'code': code,
                    'name': name,
                    'price': close,
                    'change_pct': change,
                    'volume': volume,
                    'trading_value': trading_value,
                    'themes': themes
                })

            except Exception as e:
                continue

        return stocks

    def _calculate_scores(self, stocks: List[Dict]) -> List[Candidate]:
        """점수 계산"""
        if not stocks:
            return []

        candidates = []

        for s in stocks:
            scores = {}

            # 테마 관련도 (여러 테마에 속하면 높은 점수)
            theme_count = len(s.get('themes', []))
            scores['theme_relevance'] = (theme_count / len(self.active_themes)) * self.WEIGHTS['theme_relevance']

            # 등락률 점수 (상승 우대)
            change = s['change_pct']
            if change > 0:
                scores['change_pct'] = min(change / 10, 1) * self.WEIGHTS['change_pct']
            else:
                scores['change_pct'] = 0

            # 거래대금 점수
            value_score = min(s['trading_value'] / (100 * 100000000), 1)
            scores['trading_value'] = value_score * self.WEIGHTS['trading_value']

            # 뉴스 점수 (간단히 거래대금으로 대체)
            scores['news_count'] = value_score * self.WEIGHTS['news_count']

            total_score = sum(scores.values())

            candidates.append(Candidate(
                code=s['code'],
                name=s['name'],
                price=s['price'],
                change_pct=s['change_pct'],
                score=round(total_score, 1),
                score_detail={**scores, 'themes': s.get('themes', [])},
                volume=s['volume'],
                trading_value=s['trading_value']
            ))

        return candidates

    def get_params(self) -> Dict:
        return {
            'active_themes': self.active_themes,
            'weights': self.WEIGHTS
        }
