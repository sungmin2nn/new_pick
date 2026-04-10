"""
Naver 종목별 외국인/기관 매매 동향 수집

Phase 2.5b: KIS OpenAPI 대안 (KIS 가입 없이 수급 데이터 확보)

소스: https://finance.naver.com/item/frgn.naver?code=XXXXXX
- 종목당 최대 30일치 외국인 순매매량 + 기관 순매매량
- 종가 + 거래량 동반 제공
- 종목당 ~0.2초 (Top 200 = ~40초)

제공 메서드:
- get_investor_flow(code, limit=30): 단일 종목 일별 수급
- get_multi_investor_flow(codes, limit=10): 여러 종목 bulk fetch (순차)
- get_cumulative_net(code, days=5): N일 누적 외국인+기관 순매수 (수급 점수용)

캐시: data/naver_investor_cache/{code}_{date}.json (당일 1회 재사용)
"""

import json
import time
import logging
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "naver_investor_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class NaverInvestorClient:
    """Naver 금융 종목별 외국인/기관 매매 동향 클라이언트

    사용 예:
        client = NaverInvestorClient()
        data = client.get_investor_flow('005930', limit=10)
        # [{'date':'20260410','close':206000,'foreign_net':465171,'inst_net':-475614,...}, ...]

        score = client.get_cumulative_net('005930', days=5)
        # {'foreign': sum, 'institution': sum, 'combined': sum}
    """

    BASE_URL = 'https://finance.naver.com/item/frgn.naver'
    TIMEOUT = 10
    RATE_LIMIT_SLEEP = 0.15  # 150ms (naver 친화적)

    def __init__(self, use_cache: bool = True):
        self.use_cache = use_cache
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Referer': 'https://finance.naver.com/',
        })
        self._last_call_at = 0.0

    def get_investor_flow(self, code: str, limit: int = 30) -> List[Dict]:
        """단일 종목 일별 수급 조회

        Args:
            code: 종목코드 6자리
            limit: 최대 반환 일수

        Returns:
            [{'date','close','change_pct','volume','inst_net','foreign_net'}, ...]
            최근 날짜부터 과거 순 정렬
        """
        if not code or len(code) != 6:
            return []

        # 캐시 확인 (당일 기준)
        today = datetime.now(KST).strftime('%Y%m%d')
        cache_path = CACHE_DIR / f"{code}_{today}.json"
        if self.use_cache and cache_path.exists():
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                return cached[:limit]
            except Exception:
                pass

        # Rate limit
        now = time.time()
        elapsed = now - self._last_call_at
        if elapsed < self.RATE_LIMIT_SLEEP:
            time.sleep(self.RATE_LIMIT_SLEEP - elapsed)

        url = f'{self.BASE_URL}?code={code}'
        try:
            r = self.session.get(url, timeout=self.TIMEOUT)
            self._last_call_at = time.time()
            r.encoding = 'euc-kr'
            if r.status_code != 200:
                logger.warning(f"naver frgn {code}: HTTP {r.status_code}")
                return []
        except Exception as e:
            logger.warning(f"naver frgn {code} 요청 실패: {e}")
            return []

        soup = BeautifulSoup(r.text, 'html.parser')
        tables = soup.find_all('table', class_='type2')

        # type2 테이블 중 "날짜" 헤더가 있는 것 (2번째)
        target_table = None
        for t in tables:
            first_row = t.find('tr')
            if first_row and '날짜' in first_row.get_text():
                target_table = t
                break

        if not target_table:
            logger.debug(f"naver frgn {code}: 테이블 못 찾음")
            return []

        rows = target_table.find_all('tr')
        data = []
        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all('td')]
            if len(cells) < 7:
                continue
            # 첫 셀이 "YYYY.MM.DD" 형식
            if not re.match(r'\d{4}\.\d{2}\.\d{2}', cells[0]):
                continue
            try:
                data.append({
                    'date': cells[0].replace('.', ''),
                    'close': int(cells[1].replace(',', '')),
                    'change_pct': float(cells[3].replace('%', '').replace('+', '')),
                    'volume': int(cells[4].replace(',', '')),
                    'inst_net': int(cells[5].replace(',', '')),
                    'foreign_net': int(cells[6].replace(',', '')),
                })
            except (ValueError, IndexError) as e:
                logger.debug(f"naver frgn {code} 파싱 실패: {e}")
                continue

        # 캐시 저장
        if self.use_cache and data:
            try:
                with open(cache_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False)
            except Exception:
                pass

        return data[:limit]

    def get_multi_investor_flow(self, codes: List[str], limit: int = 10,
                                 progress_every: int = 50) -> Dict[str, List[Dict]]:
        """여러 종목 bulk fetch (순차 + 진행률 로그)

        Args:
            codes: 종목코드 리스트
            limit: 종목당 최대 일수
            progress_every: N개마다 로그

        Returns:
            {code: [data, ...], ...} — 실패한 종목은 빈 리스트
        """
        result = {}
        total = len(codes)
        t_start = time.time()
        for i, code in enumerate(codes, 1):
            try:
                data = self.get_investor_flow(code, limit=limit)
                result[code] = data
            except Exception as e:
                logger.debug(f"{code}: {e}")
                result[code] = []
            if i % progress_every == 0 or i == total:
                elapsed = time.time() - t_start
                logger.info(f"  naver_investor progress: {i}/{total} ({elapsed:.1f}s)")
        return result

    def get_cumulative_net(self, code: str, days: int = 5) -> Dict[str, int]:
        """N일 누적 외국인/기관 순매수 (수급 점수용)

        Args:
            code: 종목코드
            days: 누적 기간 (거래일 기준)

        Returns:
            {'foreign': 누적외국인, 'institution': 누적기관,
             'combined': 합계, 'days_used': 실제 사용 일수}
        """
        data = self.get_investor_flow(code, limit=days)
        if not data:
            return {'foreign': 0, 'institution': 0, 'combined': 0, 'days_used': 0}
        f = sum(d.get('foreign_net', 0) for d in data)
        i = sum(d.get('inst_net', 0) for d in data)
        return {
            'foreign': f,
            'institution': i,
            'combined': f + i,
            'days_used': len(data),
        }

    def rank_by_inflow(self, codes: List[str], days: int = 5,
                       require_both_positive: bool = True) -> List[Dict]:
        """N일 누적 수급 기준 종목 랭킹

        Args:
            codes: 종목코드 리스트
            days: 누적 기간
            require_both_positive: True면 외국인+기관 둘 다 양수인 종목만

        Returns:
            정렬된 리스트: [{'code','foreign','institution','combined'}, ...]
            combined 내림차순
        """
        results = []
        for code in codes:
            flow = self.get_cumulative_net(code, days=days)
            if flow['days_used'] == 0:
                continue
            if require_both_positive and (flow['foreign'] <= 0 or flow['institution'] <= 0):
                continue
            flow['code'] = code
            results.append(flow)
        results.sort(key=lambda x: x['combined'], reverse=True)
        return results


# 전역 싱글톤
_default_client: Optional[NaverInvestorClient] = None


def get_default_client() -> NaverInvestorClient:
    global _default_client
    if _default_client is None:
        _default_client = NaverInvestorClient()
    return _default_client


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    client = NaverInvestorClient()

    print("\n[1] 삼성전자 최근 5일 수급")
    print("-" * 60)
    data = client.get_investor_flow('005930', limit=5)
    for d in data:
        print(f"  {d['date']}: 종가 {d['close']:,}원, "
              f"외국인 {d['foreign_net']:+,}주, 기관 {d['inst_net']:+,}주")

    print("\n[2] SK하이닉스 5일 누적 수급")
    print("-" * 60)
    cum = client.get_cumulative_net('000660', days=5)
    print(f"  외국인 누적: {cum['foreign']:+,}주")
    print(f"  기관 누적: {cum['institution']:+,}주")
    print(f"  합계: {cum['combined']:+,}주")

    print("\n[3] 10개 종목 랭킹 (외국인+기관 동반 매수)")
    print("-" * 60)
    codes = ['005930', '000660', '207940', '035420', '005380',
             '051910', '068270', '035720', '373220', '006400']
    import time as _t
    t0 = _t.time()
    ranking = client.rank_by_inflow(codes, days=5, require_both_positive=True)
    print(f"  ({_t.time()-t0:.1f}s, {len(ranking)}개 해당)")
    for i, r in enumerate(ranking[:5], 1):
        print(f"  {i}. {r['code']}: "
              f"외국인 {r['foreign']:+,} + 기관 {r['institution']:+,} = {r['combined']:+,}")
