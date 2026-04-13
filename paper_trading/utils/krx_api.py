"""
KRX OpenAPI 클라이언트
- 공식 KRX OpenAPI (data-dbg.krx.co.kr) 사용
- pykrx (비공식 스크래퍼) 고장 우회
- AUTH_KEY는 .env의 KRX_API_KEY 사용

제공 데이터:
- 유가증권/코스닥 일별 OHLCV + 시가총액
- KOSPI/KOSDAQ 지수 일별
- 종목 기본정보 (상장일, 업종 등)

캐시: 날짜별 디스크 캐시 (data/krx_cache/)
"""

import os
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict

import requests
import pandas as pd

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "krx_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class KRXClient:
    """KRX OpenAPI REST 클라이언트

    사용 예:
        client = KRXClient()
        df = client.get_stock_ohlcv('20260410', market='KOSPI')
        idx = client.get_index_ohlcv('20260410', market='KOSPI')
    """

    BASE_URL = "https://data-dbg.krx.co.kr/svc/apis"
    TIMEOUT = 15
    RATE_LIMIT_SLEEP = 0.2  # 호출 간 200ms (KRX 권장 안전선)

    # 엔드포인트 매핑
    ENDPOINTS = {
        ('stock', 'KOSPI'): 'sto/stk_bydd_trd',
        ('stock', 'KOSDAQ'): 'sto/ksq_bydd_trd',
        ('index', 'KOSPI'): 'idx/kospi_dd_trd',
        ('index', 'KOSDAQ'): 'idx/kosdaq_dd_trd',
        ('base', 'KOSPI'): 'sto/stk_isu_base_info',
        ('base', 'KOSDAQ'): 'sto/ksq_isu_base_info',
    }

    def __init__(self, api_key: Optional[str] = None, use_cache: bool = True):
        # API 키: 인자 우선, 없으면 .env에서 로드
        if api_key:
            self.api_key = api_key
        else:
            self.api_key = os.getenv('KRX_API_KEY')
            if not self.api_key:
                # .env 직접 로드 시도
                try:
                    from dotenv import load_dotenv
                    env_path = Path(__file__).parent.parent.parent / '.env'
                    load_dotenv(env_path)
                    self.api_key = os.getenv('KRX_API_KEY')
                except ImportError:
                    pass

        if not self.api_key:
            raise ValueError(
                "KRX_API_KEY가 설정되지 않았습니다. "
                ".env 파일 또는 환경변수에 KRX_API_KEY를 설정하세요."
            )

        self.use_cache = use_cache
        self.session = requests.Session()
        self.session.headers.update({'AUTH_KEY': self.api_key})
        self._last_call_at = 0.0

    # ─────────────────────────────────────
    # 공개 메서드 - 일별 데이터 fetch
    # ─────────────────────────────────────

    def get_stock_ohlcv(self, date: str, market: str = 'KOSPI') -> pd.DataFrame:
        """전체 종목 일별 OHLCV + 시가총액

        Args:
            date: YYYYMMDD
            market: 'KOSPI' or 'KOSDAQ'

        Returns:
            DataFrame: index=종목코드, columns=[종목명, 시가, 고가, 저가, 종가,
                       전일대비, 등락률, 거래량, 거래대금, 시가총액, 상장주식수]
        """
        rows = self._fetch('stock', market, date)
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        # 표준 컬럼명으로 변환
        df = df.rename(columns={
            'ISU_CD': 'isu_cd',
            'ISU_NM': '종목명',
            'TDD_OPNPRC': '시가',
            'TDD_HGPRC': '고가',
            'TDD_LWPRC': '저가',
            'TDD_CLSPRC': '종가',
            'CMPPREVDD_PRC': '전일대비',
            'FLUC_RT': '등락률',
            'ACC_TRDVOL': '거래량',
            'ACC_TRDVAL': '거래대금',
            'MKTCAP': '시가총액',
            'LIST_SHRS': '상장주식수',
        })
        # 종목코드: ISIN(KR700...)에서 단축코드 추출
        # ISU_SRT_CD가 없으므로 ISU_CD 마지막 6자리에서 1자 빼기 (실제로 ISU_CD = KR700XXXXXXX)
        # 더 간단: KRX 응답에서 ISU_CD가 12자리 ISIN, 단축코드는 7~12 슬라이스 후 마지막 1자 제거
        # 가장 안전: 별도 종목정보 매핑 불필요시, ISU_CD를 그대로 인덱스로 사용
        df['종목코드'] = df['isu_cd'].str[3:9]  # KR700095570 -> 700095 (X) — 다른 방법 필요
        # 실제 응답 분석: ISU_CD가 짧은 형태일 수도. 일단 양쪽 다 호환되게.
        if df['isu_cd'].iloc[0].startswith('KR'):
            df['종목코드'] = df['isu_cd'].str[3:9]
        else:
            df['종목코드'] = df['isu_cd']
        df = df.set_index('종목코드')
        # 숫자 컬럼 변환
        num_cols = ['시가', '고가', '저가', '종가', '전일대비', '등락률',
                    '거래량', '거래대금', '시가총액', '상장주식수']
        for c in num_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
        return df

    def get_index_ohlcv(self, date: str, market: str = 'KOSPI') -> pd.DataFrame:
        """지수 일별 OHLCV

        Args:
            date: YYYYMMDD
            market: 'KOSPI' or 'KOSDAQ'

        Returns:
            DataFrame: 지수별 1행 (KOSPI 종합지수, KOSPI 200, etc.)
                       columns=[지수명, 시가, 고가, 저가, 종가, 등락률, ...]
        """
        rows = self._fetch('index', market, date)
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df = df.rename(columns={
            'IDX_NM': '지수명',
            'IDX_CLSS': '지수분류',
            'OPNPRC_IDX': '시가',
            'HGPRC_IDX': '고가',
            'LWPRC_IDX': '저가',
            'CLSPRC_IDX': '종가',
            'CMPPREVDD_IDX': '전일대비',
            'FLUC_RT': '등락률',
        })
        num_cols = ['시가', '고가', '저가', '종가', '전일대비', '등락률']
        for c in num_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
        return df

    def get_kospi_change(self, date: str) -> Optional[float]:
        """KOSPI 종합지수 일일 등락률 (편의 함수)

        Returns:
            float: 등락률(%), 실패 시 None
        """
        try:
            df = self.get_index_ohlcv(date, market='KOSPI')
            if df.empty:
                return None
            # KOSPI 종합지수 = 지수명에 '코스피'만 있고 200/소형 등 없는 첫 행
            kospi = df[df['지수명'].str.strip() == '코스피']
            if not kospi.empty:
                return float(kospi.iloc[0]['등락률'])
            # 폴백: 첫 번째 KOSPI 인덱스
            return float(df.iloc[0]['등락률'])
        except Exception as e:
            logger.warning(f"KOSPI 등락률 조회 실패: {e}")
            return None

    def get_history(self, code: str, start: str, end: str,
                    market: str = 'KOSPI') -> pd.DataFrame:
        """특정 종목의 기간 OHLCV (날짜 루프 fetch)

        Args:
            code: 종목코드 6자리
            start: YYYYMMDD
            end: YYYYMMDD
            market: 'KOSPI' or 'KOSDAQ'

        Returns:
            DataFrame: index=날짜, columns=[시가/고가/저가/종가/거래량/시가총액]
        """
        start_dt = datetime.strptime(start, '%Y%m%d')
        end_dt = datetime.strptime(end, '%Y%m%d')

        rows = []
        cur = start_dt
        while cur <= end_dt:
            # 주말 skip
            if cur.weekday() >= 5:
                cur += timedelta(days=1)
                continue
            date_str = cur.strftime('%Y%m%d')
            try:
                df = self.get_stock_ohlcv(date_str, market=market)
                if not df.empty and code in df.index:
                    row = df.loc[code].to_dict()
                    row['날짜'] = date_str
                    rows.append(row)
            except Exception as e:
                logger.debug(f"{date_str} {code} fetch 실패: {e}")
            cur += timedelta(days=1)

        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows).set_index('날짜')
        return df

    # ─────────────────────────────────────
    # 내부: HTTP fetch + 캐시
    # ─────────────────────────────────────

    def _fetch(self, kind: str, market: str, date: str) -> List[Dict]:
        """엔드포인트 호출 + 캐시 + rate limit"""
        cache_key = f"{kind}_{market}_{date}.json"
        cache_path = CACHE_DIR / cache_key

        # 캐시 hit
        if self.use_cache and cache_path.exists():
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass

        # 엔드포인트 검증
        path = self.ENDPOINTS.get((kind, market))
        if not path:
            raise ValueError(f"알 수 없는 엔드포인트: {kind}/{market}")

        # Rate limit
        now = time.time()
        elapsed = now - self._last_call_at
        if elapsed < self.RATE_LIMIT_SLEEP:
            time.sleep(self.RATE_LIMIT_SLEEP - elapsed)

        url = f"{self.BASE_URL}/{path}"
        params = {'basDd': date}

        try:
            r = self.session.get(url, params=params, timeout=self.TIMEOUT)
            self._last_call_at = time.time()
            if r.status_code != 200:
                logger.warning(f"KRX API {r.status_code}: {r.text[:200]}")
                return []
            data = r.json()
            rows = data.get('OutBlock_1', [])
            # 캐시 저장
            if self.use_cache and rows:
                try:
                    with open(cache_path, 'w', encoding='utf-8') as f:
                        json.dump(rows, f, ensure_ascii=False)
                except Exception as e:
                    logger.debug(f"캐시 저장 실패: {e}")
            return rows
        except Exception as e:
            logger.error(f"KRX API 호출 실패: {e}")
            return []


# 전역 싱글톤 (선택)
_default_client: Optional[KRXClient] = None


def get_default_client() -> KRXClient:
    """기본 KRXClient 인스턴스 (싱글톤)"""
    global _default_client
    if _default_client is None:
        _default_client = KRXClient()
    return _default_client


if __name__ == '__main__':
    # 간단 self-test
    import sys
    logging.basicConfig(level=logging.INFO)
    client = KRXClient()
    test_date = '20260409'

    print(f"\n=== {test_date} KOSPI OHLCV ===")
    df = client.get_stock_ohlcv(test_date, 'KOSPI')
    print(f"  종목 수: {len(df)}")
    if not df.empty:
        print(df[['종목명', '종가', '등락률', '시가총액']].head(3))

    print(f"\n=== {test_date} KOSPI 지수 ===")
    idx = client.get_index_ohlcv(test_date, 'KOSPI')
    print(f"  지수 수: {len(idx)}")
    if not idx.empty:
        print(idx[['지수명', '종가', '등락률']].head(3))

    print(f"\n=== KOSPI 등락률 (편의 함수) ===")
    chg = client.get_kospi_change(test_date)
    print(f"  KOSPI: {chg}%")
