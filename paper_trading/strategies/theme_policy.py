"""
테마/정책 전략
- 네이버 금융 실시간 테마 기반
- 상승 테마 자동 감지 및 종목 선정
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

# 네이버 테마 크롤러
try:
    from paper_trading.utils.naver_theme import NaverThemeCrawler
    NAVER_THEME_AVAILABLE = True
except ImportError:
    NAVER_THEME_AVAILABLE = False

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
class ThemePolicyStrategy(BaseStrategy):
    """테마/정책 전략 - 네이버 실시간 테마 기반"""

    STRATEGY_ID = "theme_policy"
    STRATEGY_NAME = "테마/정책"
    DESCRIPTION = "네이버 금융 상승 테마 기반 종목 선정"

    # 폴백용 기본 테마 (네이버 크롤링 실패 시)
    FALLBACK_THEMES = {
        '우주항공': ['047810', '190650', '012450', '042670'],
        '방산': ['012450', '047810', '079550', '272210'],
        '바이오': ['091990', '086890', '096530', '141080'],
        '2차전지': ['247540', '003670', '066970', '373220'],
        'AI반도체': ['005930', '000660', '042700', '069960'],
    }

    # 점수 가중치
    WEIGHTS = {
        'theme_relevance': 40,   # 테마 관련도
        'change_pct': 25,        # 등락률
        'trading_value': 20,     # 거래대금
        'theme_strength': 15     # 테마 강도 (테마 등락률)
    }

    def __init__(self):
        super().__init__()
        self.session = requests.Session()
        self.headers = get_headers()
        self.active_themes = []  # [{'name': 테마명, 'code': 코드, 'change_pct': 등락률}, ...]
        self.theme_stocks = {}   # {'테마명': [종목코드, ...], ...}
        self.theme_crawler = NaverThemeCrawler() if NAVER_THEME_AVAILABLE else None

    def select_stocks(self, date: str = None, top_n: int = 5) -> List[Candidate]:
        """종목 선정"""
        if date is None:
            date = format_kst_time(format_str='%Y%m%d')

        self.selection_date = date
        print(f"\n[{self.STRATEGY_NAME}] 종목 선정 시작 ({date})")

        # 1. 활성 테마 감지 (네이버 상승 테마)
        self.active_themes = self._detect_active_themes()

        if not self.active_themes:
            print(f"  테마 감지 실패 - 폴백 테마 사용")
            self.active_themes = [{'name': k, 'code': '', 'change_pct': 0}
                                  for k in list(self.FALLBACK_THEMES.keys())[:3]]
            self.theme_stocks = self.FALLBACK_THEMES

        theme_names = [t['name'] for t in self.active_themes]
        print(f"  활성 테마 {len(self.active_themes)}개: {', '.join(theme_names[:5])}")

        # 2. 테마 관련 종목 수집
        all_codes = set()
        code_to_themes = {}  # 종목코드 -> 소속 테마 리스트

        for theme in self.active_themes:
            theme_name = theme['name']
            codes = self.theme_stocks.get(theme_name, [])

            for code in codes:
                all_codes.add(code)
                if code not in code_to_themes:
                    code_to_themes[code] = []
                code_to_themes[code].append(theme)

        print(f"  관련 종목: {len(all_codes)}개")

        # 3. 시장 데이터 가져오기
        stocks = self._fetch_stock_data(list(all_codes), date, code_to_themes)

        # 4. 점수 계산
        scored = self._calculate_scores(stocks)

        # 5. 상위 N개 선정
        scored.sort(key=lambda x: x.score, reverse=True)
        self.candidates = scored[:top_n]

        for i, c in enumerate(self.candidates, 1):
            c.rank = i

        print(f"  선정 완료: {len(self.candidates)}개")
        return self.candidates

    def _detect_active_themes(self, top_n: int = 10, min_change: float = 0.5) -> List[Dict]:
        """
        활성 테마 감지 (네이버 금융 상승 테마)

        Args:
            top_n: 상위 N개 테마
            min_change: 최소 상승률 (%)

        Returns:
            [{'name': 테마명, 'code': 코드, 'change_pct': 등락률}, ...]
        """
        if not self.theme_crawler:
            print(f"  네이버 테마 크롤러 미사용")
            return []

        try:
            # 1. 상승 테마 목록 가져오기
            hot_themes = self.theme_crawler.get_hot_themes(top_n=top_n, min_change=min_change)

            if not hot_themes:
                print(f"  상승 테마 없음 (기준: +{min_change}%)")
                # 기준 낮춰서 재시도
                hot_themes = self.theme_crawler.get_hot_themes(top_n=top_n, min_change=0)

            # 2. 각 테마의 종목 수집
            self.theme_stocks = {}
            for theme in hot_themes[:top_n]:
                stocks = self.theme_crawler.get_theme_stocks(theme['code'], theme['name'])
                if stocks:
                    self.theme_stocks[theme['name']] = [s['code'] for s in stocks]
                    print(f"    {theme['name']}: {theme['change_pct']:+.2f}% ({len(stocks)}종목)")

            return hot_themes[:top_n]

        except Exception as e:
            print(f"  테마 감지 오류: {e}")
            return []

    def _fetch_stock_data(self, codes: List[str], date: str, code_to_themes: Dict = None) -> List[Dict]:
        """종목 데이터 수집

        Fix (Phase 7C): 종목별 1회 호출 대신 시장 전체 1회 fetch + 매핑.
        - 기존: get_market_ohlcv_by_date(date,date,ticker) × N → 미래 날짜에 빈 결과
        - 신규: get_market_ohlcv_by_ticker(date, market) × 2 → 현재 snapshot에서 추출
        """
        stocks = []

        if pykrx_stock is None:
            return stocks

        if code_to_themes is None:
            code_to_themes = {}

        if not codes:
            return stocks

        codes_set = set(codes)

        # KOSPI + KOSDAQ 시장 1회 fetch
        market_data = {}  # code -> row
        for market in ['KOSPI', 'KOSDAQ']:
            try:
                df = pykrx_stock.get_market_ohlcv_by_ticker(date, market=market)
                if df is None or df.empty:
                    continue
                # df.index가 종목코드, columns에 종목명/종가/등락률/거래량/거래대금
                for code in df.index:
                    if code in codes_set:
                        market_data[code] = df.loc[code]
            except Exception as e:
                print(f"[WARNING] {market} fetch 실패: {e}")
                continue

        for code in codes:
            row = market_data.get(code)
            if row is None:
                continue
            try:
                close = int(row['종가'])
                if close == 0:
                    continue
                change = float(row['등락률']) if '등락률' in row else 0
                volume = int(row['거래량']) if '거래량' in row else 0
                trading_value = int(row['거래대금']) if '거래대금' in row else 0
                name = row.get('종목명', '') if hasattr(row, 'get') else (row['종목명'] if '종목명' in row else '')
                if not name:
                    try:
                        name = pykrx_stock.get_market_ticker_name(code)
                    except Exception:
                        name = code

                themes_info = code_to_themes.get(code, [])
                theme_names = [t['name'] for t in themes_info] if themes_info else []
                max_theme_change = max([t['change_pct'] for t in themes_info], default=0) if themes_info else 0

                stocks.append({
                    'code': code,
                    'name': name,
                    'price': close,
                    'change_pct': change,
                    'volume': volume,
                    'trading_value': trading_value,
                    'themes': theme_names,
                    'theme_strength': max_theme_change
                })
            except Exception as e:
                print(f"[WARNING] {code} 스킵: {e}")
                continue

        return stocks

    def _calculate_scores(self, stocks: List[Dict]) -> List[Candidate]:
        """점수 계산"""
        if not stocks:
            return []

        # 정규화를 위한 최대값
        max_theme_count = max(len(s.get('themes', [])) for s in stocks) or 1
        max_theme_strength = max(s.get('theme_strength', 0) for s in stocks) or 1
        max_trading_value = max(s.get('trading_value', 0) for s in stocks) or 1

        candidates = []

        for s in stocks:
            scores = {}

            # 테마 관련도 (여러 테마에 속하면 높은 점수)
            theme_count = len(s.get('themes', []))
            scores['theme_relevance'] = (theme_count / max_theme_count) * self.WEIGHTS['theme_relevance']

            # 등락률 점수 (상승 우대)
            change = s['change_pct']
            if change > 0:
                scores['change_pct'] = min(change / 10, 1) * self.WEIGHTS['change_pct']
            else:
                scores['change_pct'] = max(0, (10 + change) / 20) * self.WEIGHTS['change_pct'] * 0.3

            # 거래대금 점수
            scores['trading_value'] = (s['trading_value'] / max_trading_value) * self.WEIGHTS['trading_value']

            # 테마 강도 점수 (소속 테마가 얼마나 강한지)
            theme_strength = s.get('theme_strength', 0)
            scores['theme_strength'] = (theme_strength / max_theme_strength) * self.WEIGHTS['theme_strength']

            total_score = sum(scores.values())

            candidates.append(Candidate(
                code=s['code'],
                name=s['name'],
                price=s['price'],
                change_pct=s['change_pct'],
                score=round(total_score, 1),
                score_detail={**{k: round(v, 1) for k, v in scores.items()}, 'themes': s.get('themes', [])},
                volume=s['volume'],
                trading_value=s['trading_value']
            ))

        return candidates

    def get_params(self) -> Dict:
        theme_info = [{'name': t['name'], 'change_pct': t['change_pct']}
                      for t in self.active_themes] if self.active_themes else []
        return {
            'active_themes': theme_info,
            'theme_count': len(self.active_themes),
            'total_stocks': sum(len(v) for v in self.theme_stocks.values()),
            'weights': self.WEIGHTS
        }
