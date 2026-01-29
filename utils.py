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
