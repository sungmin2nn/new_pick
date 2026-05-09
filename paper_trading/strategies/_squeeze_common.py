"""
임마누엘 스퀴즈 플레이 — 공통 로직 (DEC-004/005, P3-3b).

KOSPI v6 / KOSDAQ v5 두 변형이 공유하는:
- Universe 하드코딩 (4주 shadow 운영 동안 고정, DEC-005 결정 #3)
- BB(20, 2σ) %B 계산
- MA200 + 200MA 5일 전 비교(우상향)
- 20MA·200MA 간격(스퀴즈 spread%) 계산
- 변형별 필터 통과 판정

근거 백테스트 (2024-05-01 ~ 2026-04-30, 485영업일):
- KOSPI Top53 v6 (MA200 ON + sqz@10%, 5일 보유): 81거래, 승률 65.4%, 평균 +2.40%, MDD 8.17%, 위험조정 23.84
- KOSDAQ Top35 v5 (MA200 OFF + sqz@15%, 5일 보유): 418거래, 승률 47.8%, 평균 +0.57%, MDD 129.4%, 위험조정 1.83

참조:
- /tmp/backtest_p2_extended.py (백테스트 원본 — 동일 로직 검증)
- DEC-004, DEC-005, plan P3-3
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np


# ============================================================
# Universe — 4주 shadow 동안 고정 (DEC-005 결정 #3)
# 출처: backtest_p2_extended.py (동일 백테스트 결과 재현 보장)
# ============================================================

KOSPI_TOP_53: List[Tuple[str, str]] = [
    ("005930", "삼성전자"), ("000660", "SK하이닉스"), ("005935", "삼성전자우"),
    ("207940", "삼성바이오로직스"), ("373220", "LG에너지솔루션"), ("005380", "현대차"),
    ("000270", "기아"), ("035420", "NAVER"), ("105560", "KB금융"),
    ("028260", "삼성물산"), ("035720", "카카오"), ("055550", "신한지주"),
    ("012330", "현대모비스"), ("005490", "POSCO홀딩스"), ("138040", "메리츠금융지주"),
    ("086790", "하나금융지주"), ("015760", "한국전력"), ("003670", "포스코퓨처엠"),
    ("068270", "셀트리온"), ("042700", "한미반도체"), ("251270", "넷마블"),
    ("003550", "LG"), ("010130", "고려아연"), ("010950", "S-Oil"),
    ("030200", "KT"), ("017670", "SK텔레콤"), ("034730", "SK"),
    ("009150", "삼성전기"), ("011200", "HMM"), ("011170", "롯데케미칼"),
    ("097950", "CJ제일제당"), ("086280", "현대글로비스"), ("047810", "한국항공우주"),
    ("009540", "HD한국조선해양"), ("064350", "현대로템"), ("326030", "SK바이오팜"),
    ("011780", "금호석유"), ("011070", "LG이노텍"), ("018260", "삼성에스디에스"),
    ("032830", "삼성생명"), ("000810", "삼성화재"), ("088980", "맥쿼리인프라"),
    ("316140", "우리금융지주"), ("024110", "기업은행"), ("010140", "삼성중공업"),
    ("047040", "대우건설"), ("069960", "현대백화점"), ("271560", "오리온"),
    ("282330", "BGF리테일"), ("329180", "HD현대중공업"), ("402340", "SK스퀘어"),
    ("012450", "한화에어로스페이스"), ("034020", "두산에너빌리티"),
]

KOSDAQ_TOP_35: List[Tuple[str, str]] = [
    ("247540", "에코프로비엠"), ("086520", "에코프로"),
    ("196170", "알테오젠"), ("028300", "HLB"),
    ("263750", "펄어비스"), ("145020", "휴젤"),
    ("035760", "CJ ENM"), ("058470", "리노공업"),
    ("357780", "솔브레인"), ("240810", "원익IPS"),
    ("348370", "엔켐"), ("067310", "하나마이크론"),
    ("121600", "나노신소재"), ("178320", "서진시스템"),
    ("393890", "더블유씨피"), ("086900", "메디톡스"),
    ("095340", "ISC"), ("022100", "포스코DX"),
    ("293490", "카카오게임즈"), ("042000", "카페24"),
    ("067160", "SOOP"), ("048410", "아이센스"),
    ("388790", "그린리소스"), ("086450", "동국제약"),
    ("089030", "테크윙"), ("035600", "KG이니시스"),
    ("192820", "코스맥스"), ("950140", "잉글우드랩"),
    ("950210", "프레스티지바이오파마"), ("000250", "삼천당제약"),
    ("064290", "인텍플러스"), ("277810", "레인보우로보틱스"),
    ("213420", "덕산네오룩스"), ("060280", "큐렉소"),
    ("196300", "솔트웨어"),
]


# ============================================================
# 지표 계산 (백테스트 backtest_p2_extended.py 와 비트단위 동일 로직)
# ============================================================

BB_PERIOD = 20
BB_STD_MULT = 2.0
PERCENT_B_MAX = 0.2
MA200_PERIOD = 200


def compute_indicators(closes: np.ndarray, current_close: float) -> Dict:
    """BB(20,2σ), MA200, 5일전 MA200, 20MA·200MA spread% 계산.

    Args:
        closes: 종가 시계열 (오래된 → 최신 순), current_close 포함
        current_close: 시그널 일자 종가

    Returns:
        dict with valid:bool, percent_b, bb_middle, [ma200, ma200_rising, spread_pct]
    """
    if len(closes) < BB_PERIOD:
        return {"valid": False}
    ma = float(np.mean(closes[-BB_PERIOD:]))
    std = float(np.std(closes[-BB_PERIOD:], ddof=1))
    upper = ma + BB_STD_MULT * std
    lower = ma - BB_STD_MULT * std
    if upper == lower:
        return {"valid": False}
    cache: Dict = {
        "valid": True,
        "percent_b": (current_close - lower) / (upper - lower),
        "bb_middle": ma,
    }
    if len(closes) >= MA200_PERIOD + 5:
        ma200 = float(np.mean(closes[-MA200_PERIOD:]))
        ma200_5d = float(np.mean(closes[-(MA200_PERIOD + 5):-5]))
        cache["ma200"] = ma200
        cache["ma200_rising"] = ma200 > ma200_5d
        cache["spread_pct"] = abs(ma - ma200) / ma200 * 100 if ma200 > 0 else None
    return cache


def passes_variant(
    cache: Dict,
    current_close: float,
    is_positive_candle: bool,
    ma200_filter: bool,
    squeeze_filter: bool,
    squeeze_max_pct: Optional[float],
) -> bool:
    """변형별 필터 통과 판정 (backtest_p2_extended.passes_variant 와 동일).

    공통 조건: %B < 0.2 AND 양봉 (오늘 종가 > 시가)
    MA200 필터 (v6): 종가 > MA200 AND MA200 우상향 (5일 전 대비)
    Squeeze 필터: |20MA - 200MA| / 200MA × 100 ≤ squeeze_max_pct

    Returns:
        True 시 매수 후보
    """
    if not cache.get("valid"):
        return False
    if cache["percent_b"] > PERCENT_B_MAX or not is_positive_candle:
        return False
    if ma200_filter or squeeze_filter:
        if "ma200" not in cache:
            return False
        if ma200_filter and (current_close <= cache["ma200"] or not cache["ma200_rising"]):
            return False
        if squeeze_filter and squeeze_max_pct is not None:
            spread = cache.get("spread_pct")
            if spread is None or spread > squeeze_max_pct:
                return False
    return True


def score_candidate(
    cache: Dict,
    current_close: float,
    open_price: float,
    squeeze_max_pct: Optional[float],
    use_squeeze_score: bool,
) -> float:
    """후보 점수 (낮은 %B, 강한 양봉 전환, 좁은 spread 우대).

    백테스트는 점수 사용 안 함 (단순 카운팅) — 본 함수는 top_n 선정용.
    가중치는 strategy-lab bollinger_reversal.WEIGHTS 와 비례 유사:
      percent_b 35 / reversal 30 / squeeze 15 ~ (단순화)
    """
    score = 0.0
    # %B 낮을수록 점수 ↑ (0.0→35점, 0.2→0점)
    pb = cache.get("percent_b", 0.2)
    score += max(0.0, (PERCENT_B_MAX - pb) / PERCENT_B_MAX) * 35.0

    # 양봉 강도 (종가-시가)/시가
    if open_price > 0:
        candle_strength = (current_close - open_price) / open_price * 100
        score += min(candle_strength, 5.0) / 5.0 * 30.0

    # 스퀴즈 점수 (사용 시): spread 좁을수록 점수 ↑
    if use_squeeze_score and squeeze_max_pct and squeeze_max_pct > 0:
        spread = cache.get("spread_pct")
        if spread is not None:
            score += max(0.0, (squeeze_max_pct - spread) / squeeze_max_pct) * 15.0

    return round(score, 2)
