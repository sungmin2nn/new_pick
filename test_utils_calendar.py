"""utils.is_market_day 휴장일 판정 테스트.

회귀 방지: '선거' KRX-OPEN 키워드 버그(전국단위 선거일을 영업일로 오판) 재발 차단.
"""

from datetime import datetime, timedelta, timezone

import pytest

from utils import _HOLIDAYS_MEMORY_CACHE, is_market_day

KST = timezone(timedelta(hours=9))


@pytest.fixture(autouse=True)
def _clear_cache():
    _HOLIDAYS_MEMORY_CACHE.clear()
    yield
    _HOLIDAYS_MEMORY_CACHE.clear()


def test_weekend():
    assert not is_market_day(datetime(2026, 5, 23, tzinfo=KST))  # 토
    assert not is_market_day(datetime(2026, 5, 24, tzinfo=KST))  # 일


def test_holiday():
    assert not is_market_day(datetime(2026, 6, 6, tzinfo=KST))   # 현충일
    assert not is_market_day(datetime(2026, 8, 17, tzinfo=KST))  # 광복절 대체


def test_business_day():
    assert is_market_day(datetime(2026, 5, 22, tzinfo=KST))  # 금
    assert is_market_day(datetime(2026, 6, 4, tzinfo=KST))   # 목


def test_election_day_is_holiday():
    """전국동시지방선거(2026-06-03)는 공휴일=KRX 휴장. '선거' 키워드 버그 회귀 방지."""
    assert not is_market_day(datetime(2026, 6, 3, tzinfo=KST))
