"""
네이버 금융 테마 크롤러
- 테마 목록 및 테마별 종목 수집
- 캐싱으로 API 부하 최소화
"""

import requests
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import time

# 캐시 디렉토리
CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "theme_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 요청 헤더 (차단 우회)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://finance.naver.com/',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
}


class NaverThemeCrawler:
    """네이버 금융 테마 크롤러"""

    BASE_URL = "https://finance.naver.com"
    THEME_LIST_URL = f"{BASE_URL}/sise/theme.naver"
    THEME_DETAIL_URL = f"{BASE_URL}/sise/sise_group_detail.naver"

    def __init__(self, cache_hours: int = 6):
        """
        Args:
            cache_hours: 캐시 유효 시간 (기본 6시간)
        """
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.cache_hours = cache_hours

    def get_theme_list(self, force_refresh: bool = False) -> List[Dict]:
        """
        전체 테마 목록 조회

        Returns:
            [{'name': '테마명', 'code': '테마코드', 'change_pct': 등락률, 'stock_count': 종목수}, ...]
        """
        cache_file = CACHE_DIR / "theme_list.json"

        # 캐시 확인
        if not force_refresh and self._is_cache_valid(cache_file):
            return self._load_cache(cache_file)

        themes = []

        try:
            # 페이지 1~5 크롤링 (대부분의 테마 포함)
            for page in range(1, 6):
                url = f"{self.THEME_LIST_URL}?page={page}"
                response = self.session.get(url, timeout=10)
                response.encoding = 'euc-kr'

                soup = BeautifulSoup(response.text, 'html.parser')
                table = soup.find('table', {'class': 'type_1'})

                if not table:
                    continue

                rows = table.find_all('tr')

                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) < 4:
                        continue

                    # 테마명 링크에서 코드 추출
                    link = cols[0].find('a')
                    if not link:
                        continue

                    href = link.get('href', '')
                    if 'no=' not in href:
                        continue

                    theme_code = href.split('no=')[-1].split('&')[0]
                    theme_name = link.get_text(strip=True)

                    # 등락률
                    change_text = cols[2].get_text(strip=True).replace('%', '').replace(',', '')
                    try:
                        change_pct = float(change_text)
                    except:
                        change_pct = 0.0

                    # 상승 여부 확인 (class로 판별)
                    if 'nv01' in str(cols[2]):  # 하락
                        change_pct = -abs(change_pct)

                    themes.append({
                        'name': theme_name,
                        'code': theme_code,
                        'change_pct': change_pct,
                    })

                time.sleep(0.3)  # 요청 간격

            # 중복 제거
            seen = set()
            unique_themes = []
            for t in themes:
                if t['code'] not in seen:
                    seen.add(t['code'])
                    unique_themes.append(t)

            # 캐시 저장
            self._save_cache(cache_file, unique_themes)
            print(f"[NaverTheme] 테마 목록 수집 완료: {len(unique_themes)}개")

            return unique_themes

        except Exception as e:
            print(f"[NaverTheme] 테마 목록 수집 오류: {e}")
            # 캐시가 있으면 반환
            if cache_file.exists():
                return self._load_cache(cache_file)
            return []

    def get_theme_stocks(self, theme_code: str, theme_name: str = None) -> List[Dict]:
        """
        특정 테마의 종목 목록 조회

        Args:
            theme_code: 테마 코드
            theme_name: 테마명 (캐시 파일명용)

        Returns:
            [{'code': '종목코드', 'name': '종목명', 'price': 현재가, 'change_pct': 등락률}, ...]
        """
        cache_file = CACHE_DIR / f"theme_{theme_code}.json"

        # 캐시 확인
        if self._is_cache_valid(cache_file):
            return self._load_cache(cache_file)

        stocks = []

        try:
            url = f"{self.THEME_DETAIL_URL}?type=theme&no={theme_code}"
            response = self.session.get(url, timeout=10)
            response.encoding = 'euc-kr'

            soup = BeautifulSoup(response.text, 'html.parser')
            table = soup.find('table', {'class': 'type_5'})

            if not table:
                return stocks

            rows = table.find_all('tr')

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5:
                    continue

                # 종목 링크 (첫번째 컬럼)
                link = cols[0].find('a')
                if not link:
                    continue

                href = link.get('href', '')
                if 'code=' not in href:
                    continue

                stock_code = href.split('code=')[-1].split('&')[0]
                stock_name = link.get_text(strip=True)

                # 현재가 (3번째 컬럼, index 2)
                price_text = cols[2].get_text(strip=True).replace(',', '')
                try:
                    price = int(price_text)
                except:
                    price = 0

                # 등락률 (5번째 컬럼, index 4)
                change_text = cols[4].get_text(strip=True).replace('%', '').replace(',', '').replace('+', '')
                try:
                    change_pct = float(change_text)
                except:
                    change_pct = 0.0

                # 하락 여부 확인 (전일대비 컬럼의 class 또는 텍스트로 판별)
                change_col = cols[3]
                if '하락' in change_col.get_text() or 'nv01' in str(change_col):
                    change_pct = -abs(change_pct)

                stocks.append({
                    'code': stock_code,
                    'name': stock_name,
                    'price': price,
                    'change_pct': change_pct,
                    'theme': theme_name or theme_code
                })

            # 캐시 저장
            self._save_cache(cache_file, stocks)

            return stocks

        except Exception as e:
            print(f"[NaverTheme] 테마 종목 수집 오류 ({theme_code}): {e}")
            if cache_file.exists():
                return self._load_cache(cache_file)
            return []

    def get_hot_themes(self, top_n: int = 20, min_change: float = 1.0) -> List[Dict]:
        """
        상승률 상위 테마 조회

        Args:
            top_n: 상위 N개
            min_change: 최소 등락률 (%)

        Returns:
            테마 목록 (상승률 순)
        """
        themes = self.get_theme_list()

        # 상승 테마만 필터
        hot_themes = [t for t in themes if t['change_pct'] >= min_change]

        # 상승률 순 정렬
        hot_themes.sort(key=lambda x: x['change_pct'], reverse=True)

        return hot_themes[:top_n]

    def get_all_theme_stocks(self, theme_codes: List[str] = None) -> Dict[str, List[str]]:
        """
        여러 테마의 종목 코드 매핑

        Args:
            theme_codes: 테마 코드 리스트 (None이면 상위 30개 테마)

        Returns:
            {'테마명': ['종목코드1', '종목코드2', ...], ...}
        """
        if theme_codes is None:
            themes = self.get_theme_list()[:30]
            theme_codes = [(t['code'], t['name']) for t in themes]
        else:
            themes = self.get_theme_list()
            theme_map = {t['code']: t['name'] for t in themes}
            theme_codes = [(code, theme_map.get(code, code)) for code in theme_codes]

        result = {}

        for code, name in theme_codes:
            stocks = self.get_theme_stocks(code, name)
            if stocks:
                result[name] = [s['code'] for s in stocks]
            time.sleep(0.2)  # 요청 간격

        return result

    def build_stock_to_themes_index(
        self,
        refresh_missing: bool = False,
        save_path: Optional[Path] = None,
    ) -> Dict:
        """
        종목 → 테마 역인덱스 생성.

        theme_<code>.json (theme→stocks) 들을 읽어 stock→themes 역방향으로 뒤집는다.
        BNF/Bollinger 등 다른 전략의 "동일 테마 중복 회피" 필터에 쓰인다.

        Args:
            refresh_missing: True면 theme_list.json 에는 있지만 theme_<code>.json
                             캐시가 없는 테마를 fetch (200개 풀 커버시 ~60s).
                             False면 기존 캐시만 뒤집음 (cost 0).
            save_path: 출력 경로. None이면 CACHE_DIR / "_stock_to_themes.json"

        Returns:
            {
              "_meta": {"generated_at", "themes_with_stocks", "themes_missing",
                        "stocks_total", "coverage_pct", ...},
              "<stock_code>": {"name": "...", "themes": [{"code","name"}, ...]}
            }
        """
        themes = self.get_theme_list()
        theme_name_by_code = {t['code']: t['name'] for t in themes}

        if refresh_missing:
            for t in themes:
                cache_file = CACHE_DIR / f"theme_{t['code']}.json"
                if not cache_file.exists():
                    self.get_theme_stocks(t['code'], t['name'])
                    time.sleep(0.2)

        index: Dict[str, Dict] = {}
        themes_with_stocks: List[str] = []
        themes_missing: List[Dict] = []

        for t in themes:
            code = t['code']
            name = t['name']
            cache_file = CACHE_DIR / f"theme_{code}.json"
            if not cache_file.exists():
                themes_missing.append({'code': code, 'name': name})
                continue
            stocks = self._load_cache(cache_file)
            if not stocks:
                themes_missing.append({'code': code, 'name': name})
                continue
            themes_with_stocks.append(code)
            for s in stocks:
                stock_code = s.get('code')
                if not stock_code:
                    continue
                entry = index.setdefault(stock_code, {
                    'name': s.get('name', ''),
                    'themes': [],
                })
                if not any(th['code'] == code for th in entry['themes']):
                    entry['themes'].append({'code': code, 'name': name})

        result = {
            '_meta': {
                'generated_at': datetime.now().isoformat(timespec='seconds'),
                'themes_total_known': len(themes),
                'themes_with_stocks': len(themes_with_stocks),
                'themes_missing_count': len(themes_missing),
                'themes_missing': themes_missing,
                'stocks_total': len(index),
                'coverage_pct': round(100.0 * len(themes_with_stocks) / len(themes), 2) if themes else 0.0,
                'source_cache_dir': str(CACHE_DIR),
            },
            **index,
        }

        out_path = save_path or (CACHE_DIR / "_stock_to_themes.json")
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        return result

    def _is_cache_valid(self, cache_file: Path) -> bool:
        """캐시 유효성 확인"""
        if not cache_file.exists():
            return False

        mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
        return datetime.now() - mtime < timedelta(hours=self.cache_hours)

    def _load_cache(self, cache_file: Path) -> List:
        """캐시 로드"""
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []

    def _save_cache(self, cache_file: Path, data: List):
        """캐시 저장"""
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[NaverTheme] 캐시 저장 오류: {e}")


# 편의 함수들
_crawler = None

def get_crawler() -> NaverThemeCrawler:
    """싱글톤 크롤러 반환"""
    global _crawler
    if _crawler is None:
        _crawler = NaverThemeCrawler()
    return _crawler


def get_hot_themes(top_n: int = 20) -> List[Dict]:
    """상승 테마 조회"""
    return get_crawler().get_hot_themes(top_n)


def get_theme_stocks(theme_code: str) -> List[Dict]:
    """테마 종목 조회"""
    return get_crawler().get_theme_stocks(theme_code)


def get_theme_stock_map(top_n: int = 30) -> Dict[str, List[str]]:
    """테마-종목 매핑 (상위 N개 테마)"""
    return get_crawler().get_all_theme_stocks()


if __name__ == "__main__":
    # 테스트
    crawler = NaverThemeCrawler()

    print("\n=== 테마 목록 ===")
    themes = crawler.get_theme_list()
    print(f"총 {len(themes)}개 테마")

    for t in themes[:10]:
        print(f"  {t['name']}: {t['change_pct']:+.2f}%")

    print("\n=== 상승 테마 TOP 10 ===")
    hot = crawler.get_hot_themes(10)
    for t in hot:
        print(f"  {t['name']}: {t['change_pct']:+.2f}%")

    if hot:
        print(f"\n=== '{hot[0]['name']}' 종목 ===")
        stocks = crawler.get_theme_stocks(hot[0]['code'], hot[0]['name'])
        for s in stocks[:5]:
            print(f"  {s['name']}({s['code']}): {s['price']:,}원 ({s['change_pct']:+.2f}%)")
