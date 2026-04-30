"""
테마/정책 전략 (Phase 7D dual-mode)
- 당일 운영: 네이버 실시간 테마 (세분화)
- 과거 backtest: KRX 업종 지수 기반 sector momentum (51개 섹터)
"""

import sys
import logging
from pathlib import Path
from typing import List, Dict
from datetime import datetime
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from .base import BaseStrategy, Candidate
from .registry import StrategyRegistry
from utils import format_kst_time, get_headers

logger = logging.getLogger(__name__)

# 네이버 테마 크롤러 (당일 모드)
try:
    from paper_trading.utils.naver_theme import NaverThemeCrawler
    NAVER_THEME_AVAILABLE = True
except ImportError:
    NAVER_THEME_AVAILABLE = False

# KRX OpenAPI (backtest 모드 - 과거 업종 지수)
try:
    from paper_trading.utils.krx_api import KRXClient
    _krx_client = None
    def _get_krx():
        global _krx_client
        if _krx_client is None:
            try:
                _krx_client = KRXClient()
            except Exception as e:
                logger.warning(f"KRX OpenAPI 초기화 실패: {e}")
                _krx_client = False
        return _krx_client if _krx_client else None
except ImportError:
    _get_krx = lambda: None

# 네이버 금융 우선, pykrx 폴백 (snapshot용)
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

    # ───── 4월 부진 진단 적용 룰 (2026-04-29) ─────
    # 1순위 — 동일 그룹 진입 캡 (top_n 선정 후처리)
    #   동일 광역 시총/업종에 후보 수렴하는 4/23·4/30 동반 손실 패턴 차단
    LARGE_CAP_THRESHOLD = 10_000_000_000_000  # 시총 10조 이상 = "대형주"
    MAX_LARGE_CAP = 2                          # top_n 중 대형주 최대 2건
    MAX_PER_SECTOR = 2                         # 동일 sector(KRX 업종) 최대 2건

    # 2순위 — KRX 광역 모드 시총 상한 + tolerance 축소
    #   005930(약 600조), 000660(약 200조), 402340(약 70조)이 모두 걸리도록 30조 컷
    KRX_BACKTEST_MCAP_CAP = 30_000_000_000_000  # 시총 30조 초과 = candidates 제외
    KRX_BACKTEST_TOLERANCE = 1.5                # 광역 업종 tolerance ±1.5% (기존 2.5)
    KRX_BACKTEST_MEMBERS_PER_SECTOR = 12        # 섹터당 후보 풀 (기존 8 → 12)

    def __init__(self):
        super().__init__()
        self.session = requests.Session()
        self.headers = get_headers()
        self.active_themes = []  # [{'name': 테마명, 'code': 코드, 'change_pct': 등락률}, ...]
        self.theme_stocks = {}   # {'테마명': [종목코드, ...], ...}
        self.theme_crawler = NaverThemeCrawler() if NAVER_THEME_AVAILABLE else None
        # KRX 백테스트 모드에서 채워지는 메타정보 (1순위 캡 적용용)
        self.stock_mcap = {}     # {code: 시가총액(원)}
        self.code_to_sector = {} # {code: 첫 번째로 매칭된 sector명 (대표 업종)}

    def select_stocks(self, date: str = None, top_n: int = 5) -> List[Candidate]:
        """종목 선정"""
        if date is None:
            date = format_kst_time(format_str='%Y%m%d')

        self.selection_date = date
        print(f"\n[{self.STRATEGY_NAME}] 종목 선정 시작 ({date})")

        # 1. 활성 테마 감지 (date-aware: 당일=naver, 과거=KRX 업종)
        self.active_themes = self._detect_active_themes(date=date)

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

        # 5. 상위 N개 선정 — 1순위 진단 룰: 정렬 → 다양성 캡 적용 → top_n
        scored.sort(key=lambda x: x.score, reverse=True)
        self.candidates = self._apply_diversification_caps(scored, top_n)

        for i, c in enumerate(self.candidates, 1):
            c.rank = i

        print(f"  선정 완료: {len(self.candidates)}개")
        return self.candidates

    def _apply_diversification_caps(self, scored: List[Candidate], top_n: int) -> List[Candidate]:
        """1순위 진단 룰 — 동일 그룹 진입 캡.

        - 시총 ≥ LARGE_CAP_THRESHOLD(10조) 종목은 top_n 중 ≤ MAX_LARGE_CAP(2)건
        - 동일 sector(self.code_to_sector 첫 번째 매칭 업종) ≤ MAX_PER_SECTOR(2)건
        - score 정렬 순서대로 위에서부터 검사, 캡 도달 시 다음 후보로 대체
        - 대체 풀 부족하면 후보 부족 그대로 진행 (top_n 미달 허용)

        4/23·4/30 동반 손실 5종 (005930·005935·000660·402340·034020) 처럼
        시총 톱·동일 광역 업종 수렴 패턴을 차단.
        """
        if not scored:
            return []

        selected: List[Candidate] = []
        large_cap_count = 0
        sector_count: Dict[str, int] = {}
        skipped_for_cap = []  # 디버그 로그용

        for c in scored:
            if len(selected) >= top_n:
                break

            mcap = self.stock_mcap.get(c.code, 0) or getattr(c, 'market_cap', 0) or 0
            sector = self.code_to_sector.get(c.code, '')

            # 대형주 캡
            if mcap >= self.LARGE_CAP_THRESHOLD and large_cap_count >= self.MAX_LARGE_CAP:
                skipped_for_cap.append((c.code, c.name, 'large_cap', mcap))
                continue

            # 동일 sector 캡 (sector 정보 있는 경우만 적용)
            if sector and sector_count.get(sector, 0) >= self.MAX_PER_SECTOR:
                skipped_for_cap.append((c.code, c.name, f'sector:{sector}', sector_count[sector]))
                continue

            selected.append(c)
            # market_cap을 candidate에도 채워서 downstream(저장/시각화) 노출
            if mcap and not getattr(c, 'market_cap', 0):
                c.market_cap = mcap
            if mcap >= self.LARGE_CAP_THRESHOLD:
                large_cap_count += 1
            if sector:
                sector_count[sector] = sector_count.get(sector, 0) + 1

        if skipped_for_cap:
            print(f"  [진단룰] 캡으로 제외: {len(skipped_for_cap)}건 → "
                  + ", ".join(f"{n}({r})" for _, n, r, _ in skipped_for_cap[:5]))
        if len(selected) < top_n:
            print(f"  [진단룰] 캡 적용 후 {len(selected)}/{top_n}건 (대체 풀 부족)")

        return selected

    def _detect_active_themes(self, top_n: int = 10, min_change: float = 0.5,
                                date: str = None) -> List[Dict]:
        """활성 테마 감지 (date-aware dual mode)

        - date == today (또는 None): Naver 테마 크롤링 (세분화 테마)
        - date == 과거: KRX 업종 지수 기반 (51개 섹터 + 시총 상위 종목)
        """
        today = format_kst_time(format_str='%Y%m%d')
        is_backtest = date is not None and date != today

        if is_backtest:
            return self._detect_themes_krx(date, top_n=top_n)

        # 당일: Naver 테마
        if not self.theme_crawler:
            print(f"  네이버 테마 크롤러 미사용")
            return []

        try:
            hot_themes = self.theme_crawler.get_hot_themes(top_n=top_n, min_change=min_change)

            if not hot_themes:
                print(f"  상승 테마 없음 (기준: +{min_change}%)")
                hot_themes = self.theme_crawler.get_hot_themes(top_n=top_n, min_change=0)

            # 각 테마의 종목 수집
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

    def _detect_themes_krx(self, date: str, top_n: int = 10) -> List[Dict]:
        """KRX 업종 지수 기반 테마 감지 (backtest 모드)

        - 51개 KOSPI 지수 + 40개 KOSDAQ 지수 중 업종 지수 추출
        - 상위 N개 섹터 선정
        - 각 섹터에서 시총 상위 종목 8개를 매핑
        """
        krx = _get_krx() if callable(_get_krx) else None
        if not krx:
            print("  KRX OpenAPI 사용 불가")
            return []

        print(f"  [Backtest mode] KRX 업종 지수 fetch ({date})")

        try:
            # KOSPI + KOSDAQ 지수
            idx_kospi = krx.get_index_ohlcv(date, 'KOSPI')
            idx_kosdaq = krx.get_index_ohlcv(date, 'KOSDAQ')

            # 업종 지수만 필터: '코스피 200', '코스피 (외국주포함)' 등 종합 지수 제외
            sector_indices = []
            for df, mkt in [(idx_kospi, 'KOSPI'), (idx_kosdaq, 'KOSDAQ')]:
                if df.empty:
                    continue
                for _, row in df.iterrows():
                    name = str(row.get('지수명', ''))
                    # 종합/대형/중형/소형 지수는 제외, 업종 분류만
                    if any(skip in name for skip in ['200', '외국주', '대형주', '중형주', '소형주', '제외']):
                        continue
                    if not name or name == '코스피' or name == '코스닥':
                        continue
                    try:
                        change = float(row.get('등락률', 0))
                        sector_indices.append({
                            'name': name,
                            'change_pct': change,
                            'market': mkt,
                        })
                    except Exception:
                        continue

            # 등락률 상위 N개 섹터
            sector_indices.sort(key=lambda x: x['change_pct'], reverse=True)
            top_sectors = sector_indices[:top_n]

            # 종목 데이터 fetch (시총 상위 매핑용)
            kospi_df = krx.get_stock_ohlcv(date, 'KOSPI')
            kosdaq_df = krx.get_stock_ohlcv(date, 'KOSDAQ')

            # 섹터 이름 → 종목 매핑 (간단한 키워드 매칭, naver theme 부재 시 fallback)
            # KRX 종목정보에는 SECT_TP_NM이 빈값이라 정확한 매핑 불가
            # 대안: 각 섹터의 등락률에 비슷한 종목들을 시총 + 등락률로 candidate에 흡수
            #
            # 2순위 진단 룰 (2026-04-29):
            #   - 시총 상한 KRX_BACKTEST_MCAP_CAP(30조) 추가: 005930/000660/402340 같은
            #     초대형주 자동 배제 → 일중 변동성 확보
            #   - tolerance 1.5로 축소: 광역 섹터에 무차별 흡수 완화
            #   - 섹터당 후보 풀 12개로 확대: 캡 적용 후 대체 풀 확보
            self.theme_stocks = {}
            self.stock_mcap = {}
            self.code_to_sector = {}

            mcap_cap = self.KRX_BACKTEST_MCAP_CAP
            tolerance = self.KRX_BACKTEST_TOLERANCE
            members_per_sector = self.KRX_BACKTEST_MEMBERS_PER_SECTOR

            for sector in top_sectors:
                # 섹터 등락률과 비슷한 (±tolerance) 종목 중 시총 1000억~30조 종목을 "섹터 멤버"로 근사
                target_chg = sector['change_pct']
                candidates = []
                for df in [kospi_df, kosdaq_df]:
                    if df.empty:
                        continue
                    for code in df.index:
                        try:
                            row = df.loc[code]
                            chg = float(row.get('등락률', 0))
                            if abs(chg - target_chg) > tolerance:
                                continue
                            mcap = int(row.get('시가총액', 0))
                            if mcap < 100_000_000_000:  # 하한 1000억
                                continue
                            if mcap > mcap_cap:  # 2순위 상한 30조 (시총 톱 수렴 차단)
                                continue
                            candidates.append((code, mcap))
                        except Exception:
                            continue
                # 시총 상위 N개
                candidates.sort(key=lambda x: x[1], reverse=True)
                if candidates:
                    members = candidates[:members_per_sector]
                    self.theme_stocks[sector['name']] = [c[0] for c in members]
                    # 메타: code → mcap, 첫 매칭 sector 보관 (1순위 캡 적용용)
                    for code, mcap in members:
                        self.stock_mcap[code] = mcap
                        self.code_to_sector.setdefault(code, sector['name'])
                    print(f"    {sector['name']}: {sector['change_pct']:+.2f}% ({len(members)}종목, mcap≤30조)")

            return top_sectors

        except Exception as e:
            logger.warning(f"KRX 업종 지수 fetch 실패: {e}")
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

            # 1순위 캡 적용을 위해 KRX 모드 메타에서 시총 주입 (가능시)
            mcap_for_cand = self.stock_mcap.get(s['code'], 0) if self.stock_mcap else 0
            candidates.append(Candidate(
                code=s['code'],
                name=s['name'],
                price=s['price'],
                change_pct=s['change_pct'],
                score=round(total_score, 1),
                score_detail={**{k: round(v, 1) for k, v in scores.items()}, 'themes': s.get('themes', [])},
                volume=s['volume'],
                trading_value=s['trading_value'],
                market_cap=mcap_for_cand,
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
