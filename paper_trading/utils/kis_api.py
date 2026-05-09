"""
KIS (한국투자증권) OpenAPI 클라이언트

- 모의투자 (KIS_MOCK=true) / 실전 분기 자동
- access_token 24시간 캐시 (메모리, class attr)
- 분봉 historical (30일) + 일봉 historical (3개월~1년)
- Rate limit: 초당 20건 (50ms sleep), 일 50,000건 카운터
- 디스크 캐시: data/kis_cache/

도입 동기 (2026-05-09):
- ISSUE-014 검증 인프라: 네이버 분봉(당일만) → KIS 30일 historical
- ISSUE-015 차단 안전망: 분봉 시간 정렬로 데이터 leakage 자동 검출
- 실거래 전환 토대: paper-trading → KIS 모의주문 → 실주문 직접

플랜: ~/.claude/plans/velvet-humming-gray.md (Phase A)
"""

from __future__ import annotations

import os
import json
import time
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

import requests

try:
    import pandas as pd
except ImportError:
    pd = None  # 일봉 DataFrame 반환은 pandas 있을 때만

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "kis_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class KISClient:
    """KIS OpenAPI REST 클라이언트

    사용 예:
        kis = KISClient()  # .env 자동 로드, 모의투자 default
        bars = kis.get_minute_data('005930', '20260508', freq='1')
        df = kis.get_daily_data('005930', '20260401', '20260508')
    """

    BASE_URL_MOCK = "https://openapivts.koreainvestment.com:29443"
    BASE_URL_LIVE = "https://openapi.koreainvestment.com:9443"
    TIMEOUT = 15
    # 모의투자: 초당 한도 매우 낮음 (실측 EGW00201 빈발) → 1초/건
    # 실전: 초당 20건 가능 (별도 분기 가능)
    RATE_LIMIT_SLEEP_MOCK = 1.0
    RATE_LIMIT_SLEEP_LIVE = 0.05
    DAILY_LIMIT = 50_000
    EGW00201_BACKOFF = 2.0   # 초당 거래건수 초과 시 backoff
    EGW00201_MAX_RETRY = 3

    # TR ID (KIS OpenAPI 공식 문서 기준)
    TR_DAILY = "FHKST03010100"   # 일별 OHLCV (수정주가)
    TR_MINUTE = "FHKST03010200"  # 당일 분봉
    # 30일 분봉 historical: 일자별로 inquire-time-itemchartprice 반복 호출

    # 메모리 토큰 캐시 (class attr — 인스턴스 간 공유)
    _token_cache: Dict[str, Any] = {"access_token": None, "expires_at": 0.0}

    # 디스크 토큰 캐시 (프로세스 간 공유 — KIS 1분당 1회 발급 제한 회피)
    TOKEN_CACHE_PATH = CACHE_DIR / "token.json"

    def __init__(
        self,
        app_key: Optional[str] = None,
        app_secret: Optional[str] = None,
        account_no: Optional[str] = None,
        account_prod: Optional[str] = None,
        mock: Optional[bool] = None,
        use_cache: bool = True,
    ):
        # .env 자동 로드 (인자 미지정 시)
        self._load_env()

        self.app_key = app_key or os.getenv("KIS_APP_KEY")
        self.app_secret = app_secret or os.getenv("KIS_APP_SECRET")
        self.account_no = account_no or os.getenv("KIS_ACCOUNT_NO", "")
        self.account_prod = account_prod or os.getenv("KIS_ACCOUNT_PROD", "01")
        if mock is None:
            mock_str = os.getenv("KIS_MOCK", "true").lower()
            mock = mock_str in ("true", "1", "yes")
        self.mock = mock

        if not self.app_key or not self.app_secret:
            raise ValueError(
                "KIS_APP_KEY 또는 KIS_APP_SECRET 미설정. "
                ".env 파일 또는 환경변수를 확인하세요."
            )

        self.base_url = self.BASE_URL_MOCK if self.mock else self.BASE_URL_LIVE
        self.rate_limit_sleep = (
            self.RATE_LIMIT_SLEEP_MOCK if self.mock else self.RATE_LIMIT_SLEEP_LIVE
        )
        self.use_cache = use_cache
        self.session = requests.Session()
        self._last_call_at = 0.0
        self._daily_count = 0

        # 토큰 발급 (캐시된 게 만료됐으면 자동 갱신)
        self._refresh_token_if_needed()

    @staticmethod
    def _load_env():
        """프로젝트 루트의 .env 자동 로드 (있을 때만)"""
        try:
            from dotenv import load_dotenv
            env_path = Path(__file__).parent.parent.parent / ".env"
            if env_path.exists():
                load_dotenv(env_path)
        except ImportError:
            # dotenv 없으면 manual parse
            env_path = Path(__file__).parent.parent.parent / ".env"
            if env_path.exists():
                for ln in env_path.read_text().splitlines():
                    if "=" in ln and not ln.strip().startswith("#"):
                        k, v = ln.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    # ─────────────────────────────────────
    # 토큰 관리 (24h 유효, 만료 5분 전 자동 갱신)
    # ─────────────────────────────────────

    def _refresh_token_if_needed(self):
        now = time.time()
        # 1) 메모리 캐시 유효 시 그대로
        if (
            self._token_cache.get("access_token") is not None
            and now < self._token_cache.get("expires_at", 0) - 300  # 5분 전 갱신
        ):
            return
        # 2) 디스크 캐시 시도 (프로세스 간 공유)
        if self.TOKEN_CACHE_PATH.exists():
            try:
                with open(self.TOKEN_CACHE_PATH, "r", encoding="utf-8") as f:
                    disk = json.load(f)
                if disk.get("access_token") and now < disk.get("expires_at", 0) - 300:
                    type(self)._token_cache.update(disk)
                    logger.debug("KIS 토큰 디스크 캐시 사용")
                    return
            except Exception as e:
                logger.debug(f"토큰 디스크 캐시 로드 실패: {e}")
        # 3) 신규 발급 + 디스크 저장 (1분당 1회 제한 주의)
        new_token = self._fetch_token()
        type(self)._token_cache.update(new_token)
        try:
            with open(self.TOKEN_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(new_token, f, ensure_ascii=False)
            os.chmod(self.TOKEN_CACHE_PATH, 0o600)  # 본인만 읽기
        except Exception as e:
            logger.debug(f"토큰 디스크 캐시 저장 실패: {e}")

    def _fetch_token(self) -> Dict[str, Any]:
        """access_token 발급 (POST /oauth2/tokenP)"""
        url = f"{self.base_url}/oauth2/tokenP"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        try:
            r = self.session.post(url, json=payload, timeout=self.TIMEOUT)
            if r.status_code != 200:
                raise RuntimeError(
                    f"KIS 토큰 발급 실패 ({r.status_code}): {r.text[:200]}"
                )
            data = r.json()
            token = data.get("access_token")
            if not token:
                raise RuntimeError(f"토큰 응답에 access_token 없음: {data}")
            expires_in = int(data.get("expires_in", 86400))
            logger.info(f"KIS 토큰 발급 OK (expires in {expires_in}s)")
            return {
                "access_token": token,
                "expires_at": time.time() + expires_in,
                "token_type": data.get("token_type", "Bearer"),
            }
        except Exception as e:
            logger.error(f"KIS 토큰 발급 실패: {e}")
            raise

    # ─────────────────────────────────────
    # 공통 HTTP wrapper (rate limit + 401 retry)
    # ─────────────────────────────────────

    def _request(
        self,
        path: str,
        tr_id: str,
        params: Dict[str, Any],
        method: str = "GET",
    ) -> Dict[str, Any]:
        """KIS API 호출

        Returns:
            응답 JSON dict. 실패 시 빈 dict.
        """
        self._refresh_token_if_needed()

        # Rate limit (mock: 1.0s, live: 0.05s)
        now = time.time()
        elapsed = now - self._last_call_at
        if elapsed < self.rate_limit_sleep:
            time.sleep(self.rate_limit_sleep - elapsed)

        url = f"{self.base_url}{path}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._token_cache['access_token']}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",  # 개인
        }
        try:
            if method.upper() == "GET":
                r = self.session.get(url, params=params, headers=headers, timeout=self.TIMEOUT)
            else:
                r = self.session.post(url, json=params, headers=headers, timeout=self.TIMEOUT)
            self._last_call_at = time.time()
            self._daily_count += 1

            # 401 → 토큰 재발급 후 1회 retry
            if r.status_code == 401:
                logger.warning("KIS 401 — 토큰 재발급 후 재시도")
                new_token = self._fetch_token()
                type(self)._token_cache.update(new_token)
                headers["Authorization"] = f"Bearer {self._token_cache['access_token']}"
                if method.upper() == "GET":
                    r = self.session.get(url, params=params, headers=headers, timeout=self.TIMEOUT)
                else:
                    r = self.session.post(url, json=params, headers=headers, timeout=self.TIMEOUT)

            # 500 + EGW00201 (초당 거래건수 초과) → backoff retry
            if r.status_code != 200:
                txt = r.text or ""
                if "EGW00201" in txt:
                    for retry in range(self.EGW00201_MAX_RETRY):
                        time.sleep(self.EGW00201_BACKOFF * (retry + 1))
                        if method.upper() == "GET":
                            r = self.session.get(url, params=params, headers=headers, timeout=self.TIMEOUT)
                        else:
                            r = self.session.post(url, json=params, headers=headers, timeout=self.TIMEOUT)
                        self._last_call_at = time.time()
                        if r.status_code == 200:
                            break
                        if "EGW00201" not in (r.text or ""):
                            break
                if r.status_code != 200:
                    logger.warning(f"KIS API {r.status_code} ({tr_id}): {r.text[:300]}")
                    return {}

            if self._daily_count > self.DAILY_LIMIT:
                logger.warning(
                    f"KIS 일일 한도 초과 의심: {self._daily_count}/{self.DAILY_LIMIT}"
                )

            return r.json()
        except Exception as e:
            logger.error(f"KIS API 호출 실패 ({tr_id}): {e}")
            return {}

    # ─────────────────────────────────────
    # 분봉 (당일 + 30일 historical)
    # ─────────────────────────────────────

    # 30분씩 끊어 호출할 종료 시각 (09:30 ~ 15:30, 13회)
    _MINUTE_CHUNK_END_TIMES = [
        "093000", "100000", "103000", "110000", "113000", "120000",
        "123000", "130000", "133000", "140000", "143000", "150000", "153000",
    ]

    def get_minute_data(
        self, code: str, date: str, freq: str = "1"
    ) -> List[Dict[str, Any]]:
        """분봉 OHLCV (전 거래시간 09:00~15:30, 약 380봉)

        KIS API 한 번 호출당 30봉 한도라 30분씩 13회 호출 후 합치기.

        Args:
            code: 6자리 종목코드 (예: '005930')
            date: YYYYMMDD (당일 또는 30일 이내 historical)
            freq: 분봉 단위 (현재 1분봉만 지원)

        Returns:
            [{'time': 'HH:MM:SS', 'open': int, 'high': int, 'low': int,
              'close': int, 'volume': int}, ...]
            시간 오름차순 정렬.
        """
        cache_key = f"minute_{code}_{date}_{freq}.json"
        cache_path = CACHE_DIR / cache_key

        if self.use_cache and cache_path.exists():
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        path = "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"

        all_bars: Dict[str, Dict[str, Any]] = {}  # time → bar (dedupe)
        for end_time in self._MINUTE_CHUNK_END_TIMES:
            params = {
                "FID_ETC_CLS_CODE": "",
                "FID_COND_MRKT_DIV_CODE": "J",  # 주식
                "FID_INPUT_ISCD": code,
                "FID_INPUT_HOUR_1": end_time,    # 종료 시각 HHMMSS (그 시각 이전 30봉)
                "FID_PW_DATA_INCU_YN": "Y",      # 과거 데이터 포함
            }
            data = self._request(path, self.TR_MINUTE, params, method="GET")
            if not data:
                continue
            output = data.get("output2") or data.get("output") or []
            if not output:
                continue
            for row in output:
                try:
                    t = str(row.get("stck_cntg_hour", "") or "")
                    if len(t) >= 6:
                        time_str = f"{t[:2]}:{t[2:4]}:{t[4:6]}"
                    elif len(t) == 4:
                        time_str = f"{t[:2]}:{t[2:4]}:00"
                    else:
                        time_str = t
                    if not time_str or time_str in all_bars:
                        continue
                    all_bars[time_str] = {
                        "time": time_str,
                        "open": int(row.get("stck_oprc", 0) or 0),
                        "high": int(row.get("stck_hgpr", 0) or 0),
                        "low": int(row.get("stck_lwpr", 0) or 0),
                        "close": int(row.get("stck_prpr", 0) or 0),
                        "volume": int(row.get("cntg_vol", 0) or 0),
                    }
                except Exception as e:
                    logger.debug(f"분봉 파싱 실패: {e} row={row}")
                    continue

        bars = sorted(all_bars.values(), key=lambda x: x["time"])
        if not bars:
            logger.debug(f"KIS 분봉 빈 응답: code={code} date={date}")
            return []

        if self.use_cache and bars:
            try:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(bars, f, ensure_ascii=False)
            except Exception as e:
                logger.debug(f"캐시 저장 실패: {e}")

        return bars

    # ─────────────────────────────────────
    # 일봉 (기간)
    # ─────────────────────────────────────

    def get_daily_data(
        self, code: str, start: str, end: str
    ):
        """일봉 OHLCV 기간 조회 (수정주가)

        Args:
            code: 6자리 종목코드
            start: YYYYMMDD
            end: YYYYMMDD

        Returns:
            pandas DataFrame (open/high/low/close/volume/trading_value, index='날짜')
            pandas 미설치 시 list of dict.
        """
        cache_key = f"daily_{code}_{start}_{end}.json"
        cache_path = CACHE_DIR / cache_key

        if self.use_cache and cache_path.exists():
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    rows = json.load(f)
                if rows:
                    if pd is not None:
                        df = pd.DataFrame(rows).set_index("날짜").sort_index()
                        return df
                    return rows
            except Exception:
                pass

        path = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": code,
            "FID_INPUT_DATE_1": start,
            "FID_INPUT_DATE_2": end,
            "FID_PERIOD_DIV_CODE": "D",   # D=일, W=주, M=월, Y=년
            "FID_ORG_ADJ_PRC": "0",        # 0=수정주가, 1=원본
        }

        data = self._request(path, self.TR_DAILY, params, method="GET")
        if not data:
            return pd.DataFrame() if pd is not None else []

        output = data.get("output2") or data.get("output") or []
        if not output:
            return pd.DataFrame() if pd is not None else []

        rows = []
        for row in output:
            try:
                rows.append({
                    "날짜": row.get("stck_bsop_date", ""),
                    "open": int(row.get("stck_oprc", 0) or 0),
                    "high": int(row.get("stck_hgpr", 0) or 0),
                    "low": int(row.get("stck_lwpr", 0) or 0),
                    "close": int(row.get("stck_clpr", 0) or 0),
                    "volume": int(row.get("acml_vol", 0) or 0),
                    "trading_value": int(row.get("acml_tr_pbmn", 0) or 0),
                })
            except Exception as e:
                logger.debug(f"일봉 파싱 실패: {e} row={row}")
                continue

        if self.use_cache and rows:
            try:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(rows, f, ensure_ascii=False)
            except Exception as e:
                logger.debug(f"캐시 저장 실패: {e}")

        if pd is not None:
            df = pd.DataFrame(rows).set_index("날짜").sort_index()
            return df
        return rows


# 전역 싱글톤 (선택)
_default_client: Optional[KISClient] = None


def get_default_client() -> KISClient:
    """기본 KISClient 인스턴스 (싱글톤)"""
    global _default_client
    if _default_client is None:
        _default_client = KISClient()
    return _default_client
