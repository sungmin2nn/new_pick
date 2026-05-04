"""
유틸리티 함수 모음
"""

import json
import random
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 공휴일 원격 데이터 (hyunbinseo/holidays-kr — 우주항공청 월력요항 자동 반영, 임시공휴일 포함)
_HOLIDAYS_CACHE_DIR = Path(__file__).parent / 'data' / 'holidays_cache'
_HOLIDAYS_MEMORY_CACHE: dict = {}  # {year: set('MM-DD')}
_HOLIDAYS_REMOTE_URL = 'https://raw.githubusercontent.com/hyunbinseo/holidays-kr/main/public/{year}.json'
# 정부 공휴일이지만 KRX는 영업하는 날 (이름 부분일치). 추가 시 효과 즉시 반영
_KRX_OPEN_HOLIDAY_KEYWORDS = ('제헌절', '선거')

# 한국 시간대 (UTC+9)
KST = timezone(timedelta(hours=9))

def get_kst_now():
    """한국 표준시 현재 시간 반환"""
    return datetime.now(KST)

def format_kst_time(dt=None, format_str='%Y-%m-%d %H:%M:%S'):
    """
    한국 시간으로 포맷팅

    Args:
        dt: datetime 객체 (None이면 현재 시간)
        format_str: 출력 형식

    Returns:
        포맷팅된 시간 문자열
    """
    if dt is None:
        dt = get_kst_now()
    elif dt.tzinfo is None:
        # timezone 정보가 없으면 KST로 간주
        dt = dt.replace(tzinfo=KST)
    elif dt.tzinfo != KST:
        # 다른 timezone이면 KST로 변환
        dt = dt.astimezone(KST)

    return dt.strftime(format_str)

def get_kst_date_str(format_str='%Y%m%d'):
    """한국 시간 기준 날짜 문자열 반환"""
    return get_kst_now().strftime(format_str)


# 요일 한글 매핑
WEEKDAY_KR = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']
WEEKDAY_SHORT_KR = ['월', '화', '수', '목', '금', '토', '일']


def get_kst_weekday(dt=None):
    """
    한국 시간 기준 요일 반환

    Args:
        dt: datetime 객체 (None이면 현재 시간)

    Returns:
        dict: {'weekday': 0-6, 'weekday_kr': '월요일', 'weekday_short': '월', 'is_weekend': bool}
    """
    if dt is None:
        dt = get_kst_now()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    elif dt.tzinfo != KST:
        dt = dt.astimezone(KST)

    weekday = dt.weekday()  # 0=월요일, 6=일요일

    return {
        'weekday': weekday,
        'weekday_kr': WEEKDAY_KR[weekday],
        'weekday_short': WEEKDAY_SHORT_KR[weekday],
        'is_weekend': weekday >= 5  # 토(5), 일(6)
    }


def get_date_info(dt=None):
    """
    날짜의 상세 정보를 반환 (디버깅 및 로깅용)

    Args:
        dt: datetime 객체 (None이면 현재 시간)

    Returns:
        dict: 날짜, 요일, 주말 여부 등 상세 정보
    """
    if dt is None:
        dt = get_kst_now()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    elif dt.tzinfo != KST:
        dt = dt.astimezone(KST)

    weekday_info = get_kst_weekday(dt)

    return {
        'datetime': dt,
        'date_str': dt.strftime('%Y-%m-%d'),
        'date_str_kr': dt.strftime('%Y년 %m월 %d일'),
        'time_str': dt.strftime('%H:%M:%S'),
        'full_str': f"{dt.strftime('%Y-%m-%d')} ({weekday_info['weekday_short']}) {dt.strftime('%H:%M:%S')}",
        **weekday_info
    }


def is_market_day(dt=None):
    """
    주식 시장 개장일인지 확인 (주말 + 공휴일 제외)

    Args:
        dt: datetime 객체 (None이면 현재 시간)

    Returns:
        bool: 개장일이면 True
    """
    if dt is None:
        dt = get_kst_now()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    elif dt.tzinfo != KST:
        dt = dt.astimezone(KST)

    weekday_info = get_kst_weekday(dt)
    if weekday_info['is_weekend']:
        return False

    date_str = dt.strftime('%m-%d')
    year = dt.year
    holidays = _get_holidays(year)

    return date_str not in holidays


def _is_krx_open_holiday(names):
    """정부 공휴일이지만 KRX는 영업하는 날(제헌절·선거일 등)이면 True."""
    return any(
        any(kw in n for kw in _KRX_OPEN_HOLIDAY_KEYWORDS)
        for n in names
    )


def _parse_holidays_json(data, year):
    """원격 JSON({YYYY-MM-DD: [name,...]})에서 KRX 휴장일 set('MM-DD') 추출."""
    return {
        k[5:] for k, names in data.items()
        if k.startswith(f'{year}-') and not _is_krx_open_holiday(names)
    }


def _load_remote_holidays(year):
    """hyunbinseo/holidays-kr 에서 해당 연도의 KRX 휴장일 set('MM-DD') 반환.
    1일 디스크 캐시 + 메모리 캐시. 네트워크/파싱 실패 시 None."""
    try:
        _HOLIDAYS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file = _HOLIDAYS_CACHE_DIR / f'{year}.json'

        if cache_file.exists():
            mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
            if datetime.now() - mtime < timedelta(days=1):
                data = json.loads(cache_file.read_text(encoding='utf-8'))
                return _parse_holidays_json(data, year)

        url = _HOLIDAYS_REMOTE_URL.format(year=year)
        with urllib.request.urlopen(url, timeout=5) as r:
            raw = r.read().decode('utf-8')
        data = json.loads(raw)
        cache_file.write_text(raw, encoding='utf-8')
        return _parse_holidays_json(data, year)

    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
            OSError, TimeoutError, ValueError):
        # 네트워크 차단 / 파싱 실패 → stale 디스크 캐시라도 시도
        try:
            cache_file = _HOLIDAYS_CACHE_DIR / f'{year}.json'
            if cache_file.exists():
                data = json.loads(cache_file.read_text(encoding='utf-8'))
                return _parse_holidays_json(data, year)
        except Exception:
            pass
        return None


def _get_holidays(year):
    """
    해당 연도의 한국 공휴일 set('MM-DD') 반환.
    1차: hyunbinseo/holidays-kr 원격 (정부 출처 자동 반영, 임시공휴일 포함, 1일 캐시)
    2차: 하드코딩 폴백 (네트워크 장애 시)
    """
    if year in _HOLIDAYS_MEMORY_CACHE:
        return _HOLIDAYS_MEMORY_CACHE[year]

    remote = _load_remote_holidays(year)
    if remote is not None:
        _HOLIDAYS_MEMORY_CACHE[year] = remote
        return remote

    # === Fallback (오프라인/장애 시) — 매년 수동 갱신 필요 ===
    fixed = {
        '01-01',  # 신정
        '03-01',  # 삼일절
        '05-01',  # 노동절 (2026~ 정식 법정공휴일로 격상)
        '05-05',  # 어린이날
        '06-06',  # 현충일
        '08-15',  # 광복절
        '10-03',  # 개천절
        '10-09',  # 한글날
        '12-25',  # 크리스마스
    }
    variable = {
        2025: {
            '01-28', '01-29', '01-30',  # 설날 연휴
            '05-05',  # 부처님오신날 (어린이날과 겹침)
            '05-06',  # 대체공휴일
            '09-05', '09-06', '09-07', '09-08',  # 추석 연휴 + 대체공휴일
        },
        2026: {
            '02-16', '02-17', '02-18',  # 설날 연휴
            '03-02',  # 삼일절 대체공휴일
            '05-24',  # 부처님오신날
            '05-25',  # 부처님오신날 대체공휴일
            '08-17',  # 광복절 대체공휴일
            '09-24', '09-25', '09-26',  # 추석 연휴
            '10-05',  # 개천절 대체공휴일
        },
        2027: {
            '02-05', '02-06', '02-07',  # 설날 연휴 (추정)
            '05-13',  # 부처님오신날 (추정)
            '09-14', '09-15', '09-16',  # 추석 연휴 (추정)
        },
    }
    holidays = set(fixed)
    if year in variable:
        holidays.update(variable[year])
    _HOLIDAYS_MEMORY_CACHE[year] = holidays
    return holidays


def print_current_time_info():
    """현재 시간 정보를 출력 (디버깅용)"""
    info = get_date_info()
    print(f"[시간 정보] {info['full_str']}")
    print(f"  - 주말 여부: {'예 (휴장)' if info['is_weekend'] else '아니오 (개장일)'}")
    return info


# ============================================================
# User-Agent 로테이션 (웹 스크래핑 차단 방지)
# ============================================================
USER_AGENTS = [
    # Chrome (Windows)
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    # Chrome (Mac)
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    # Firefox (Windows)
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    # Firefox (Mac)
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',
    # Safari (Mac)
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    # Edge (Windows)
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
]


def get_random_user_agent():
    """랜덤 User-Agent 반환"""
    return random.choice(USER_AGENTS)


def get_headers():
    """랜덤 User-Agent가 포함된 HTTP 헤더 반환"""
    return {
        'User-Agent': get_random_user_agent(),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
