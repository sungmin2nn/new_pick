"""
유틸리티 함수 모음
"""

from datetime import datetime, timedelta, timezone

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
    주식 시장 개장일인지 확인 (주말 제외, 공휴일은 미포함)

    Args:
        dt: datetime 객체 (None이면 현재 시간)

    Returns:
        bool: 개장일이면 True
    """
    weekday_info = get_kst_weekday(dt)
    return not weekday_info['is_weekend']


def print_current_time_info():
    """현재 시간 정보를 출력 (디버깅용)"""
    info = get_date_info()
    print(f"[시간 정보] {info['full_str']}")
    print(f"  - 주말 여부: {'예 (휴장)' if info['is_weekend'] else '아니오 (개장일)'}")
    return info
