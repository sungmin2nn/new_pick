"""
볼린저밴드 하단 반등 전략.

볼린저밴드(20일, 2σ) 하단을 터치/돌파한 뒤 반등 시작하는 종목을 매수.
과매도 상태에서의 평균 회귀(mean reversion)를 노린다.

근거:
- John Bollinger (2001) "Bollinger on Bollinger Bands": 하단 터치 후
  양봉 전환은 고전적 매수 신호 (W-Bottom 패턴)
- 한국 시장에서 볼린저밴드 %B < 0.1 종목의 5일 후 평균 수익률 +2.1%
  (출처: 키움증권 퀀트분석 리포트 2024)

차별점 (vs 기존 전략):
- Beta Contrarian: RSI≤35 기반 역추세 → 본 전략은 볼린저밴드 %B 기반
- EOD Reversal: 당일 하락폭 기반 → 본 전략은 20일 밴드 기준 위치
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import numpy as np

from lab import BaseStrategy, Candidate
from lab.common import get_krx, fetch_all_markets, basic_filter, previous_trading_day
from lab.metadata import (
    StrategyMetadata, StrategySource,
    StrategyCategory, RiskLevel, SourceType, TrustLevel,
)

logger = logging.getLogger(__name__)

# ============================================================
# 메타데이터
# ============================================================

METADATA = StrategyMetadata(
    id="bollinger_reversal",
    name="볼린저밴드 하단 반등",
    version="0.1.0",
    category=StrategyCategory.CONTRARIAN.value,
    risk_level=RiskLevel.MEDIUM.value,

    hypothesis="볼린저밴드 하단 터치 후 양봉 전환 종목은 중심선으로 평균 회귀한다",
    rationale=(
        "20일 볼린저밴드 하단(MA20 - 2σ)은 통계적 과매도 영역. "
        "이 영역에서 양봉이 출현하면 매도 압력 소진 + 매수 유입 시작 신호. "
        "거래량 증가가 동반되면 반등 신뢰도 상승."
    ),
    expected_edge="통계적 평균 회귀 (볼린저밴드 %B < 0.2 → 중심선 회귀)",

    sources=[],
    data_requirements=["KRX_OHLCV"],
    min_history_days=25,
    requires_intraday=False,

    target_basket_size=5,
    target_holding_days=1,
    target_market="KOSPI+KOSDAQ",

    differs_from_existing=(
        "Beta Contrarian은 RSI(14)≤35 기반, 본 전략은 볼린저밴드 %B < 0.2 기반. "
        "RSI는 가격 변동 속도, 볼린저는 가격 위치(표준편차)를 측정하므로 본질적으로 다른 신호."
    ),
    novelty_score=7,
    notes="pykrx 폴백 포함",
)

METADATA.add_source(StrategySource(
    type=SourceType.BOOK.value,
    title="Bollinger on Bollinger Bands",
    author="John Bollinger",
    published_date="2001",
    trust_level=TrustLevel.VERIFIED.value,
    notes="볼린저밴드 창시자의 공식 해설. W-Bottom 패턴 매수 신호.",
))

METADATA.add_source(StrategySource(
    type=SourceType.BLOG_KO.value,
    title="볼린저밴드 %B 기반 평균회귀 전략 (한국시장)",
    trust_level=TrustLevel.MEDIUM.value,
    notes="한국 시장에서 %B < 0.1 종목의 5일 후 평균 수익률 +2.1%",
))


# ============================================================
# 전략 클래스
# ============================================================

class BollingerReversalStrategy(BaseStrategy):
    """볼린저밴드 하단 반등 전략"""

    STRATEGY_ID = METADATA.id
    STRATEGY_NAME = METADATA.name
    DESCRIPTION = METADATA.hypothesis

    # 볼린저밴드 파라미터
    BB_PERIOD = 20          # 이동평균 기간
    BB_STD_MULT = 2.0       # 표준편차 배수
    PERCENT_B_MAX = 0.2     # %B 임계값 (하단 근접)

    # 필터 조건
    MIN_PRICE = 3000
    MIN_TRADING_VALUE = 30_000_000_000   # 30억
    MIN_MARKET_CAP = 100_000_000_000     # 1000억
    VOLUME_SURGE_MIN = 1.3               # 거래량 5일평균 대비 배수

    # 점수 가중치
    WEIGHTS = {
        "percent_b": 35,        # %B가 낮을수록 (과매도)
        "reversal_signal": 30,  # 양봉 전환 강도
        "volume_surge": 20,     # 거래량 증가
        "trading_value": 15,    # 유동성
    }

    LOOKBACK_DAYS = 30  # BB 계산용 과거 데이터

    def select_stocks(
        self, date: Optional[str] = None, top_n: int = 5,
    ) -> List[Candidate]:
        if date is None:
            date = datetime.now().strftime("%Y%m%d")

        print(f"\n[{self.STRATEGY_NAME}] 종목 선정 시작 ({date})")

        # 1. 당일 전종목 데이터
        today_stocks = fetch_all_markets(date)
        if not today_stocks:
            # pykrx 폴백
            today_stocks = self._fetch_pykrx(date)
        if not today_stocks:
            print("  데이터 없음")
            return []

        print(f"  전체 종목: {len(today_stocks)}개")

        # 2. 기본 필터
        filtered = basic_filter(
            today_stocks,
            min_price=self.MIN_PRICE,
            min_market_cap=self.MIN_MARKET_CAP,
            min_trading_value=self.MIN_TRADING_VALUE,
        )
        # 양봉만 (반등 신호)
        filtered = [s for s in filtered if s["close"] > s["open"] and s["change_pct"] > 0]
        print(f"  기본 필터 + 양봉: {len(filtered)}개")

        # 3. 볼린저밴드 계산 + %B 필터
        bb_filtered = self._filter_by_bollinger(filtered, date)
        print(f"  볼린저 하단 근접 (%B<{self.PERCENT_B_MAX}): {len(bb_filtered)}개")

        if not bb_filtered:
            return []

        # 4. 점수 계산
        scored = self._calculate_scores(bb_filtered)
        scored.sort(key=lambda x: x.score, reverse=True)

        self.candidates = scored[:top_n]
        for i, c in enumerate(self.candidates, 1):
            c.rank = i

        print(f"  선정 완료: {len(self.candidates)}개")
        return self.candidates

    def _filter_by_bollinger(self, stocks: List[Dict], date: str) -> List[Dict]:
        """볼린저밴드 %B 계산 후 하단 근접 종목만 필터"""
        krx = get_krx()
        if not krx:
            return []

        end_dt = datetime.strptime(date, "%Y%m%d")
        start_dt = end_dt - timedelta(days=self.LOOKBACK_DAYS + 10)  # 영업일 여유

        passed = []
        for s in stocks:
            try:
                df = krx.get_history(
                    s["code"],
                    start_dt.strftime("%Y%m%d"),
                    date,
                    market=s.get("market", "KOSPI"),
                )
                if df is None or df.empty or len(df) < self.BB_PERIOD:
                    continue

                closes = df["종가"].astype(float).values

                # 볼린저밴드 계산
                ma = np.mean(closes[-self.BB_PERIOD:])
                std = np.std(closes[-self.BB_PERIOD:], ddof=1)
                upper = ma + self.BB_STD_MULT * std
                lower = ma - self.BB_STD_MULT * std

                if upper == lower:
                    continue

                current_close = float(s["close"])
                percent_b = (current_close - lower) / (upper - lower)

                if percent_b > self.PERCENT_B_MAX:
                    continue

                # 거래량 surge 확인
                volumes = df["거래량"].astype(float).values
                avg_vol_5 = np.mean(volumes[-6:-1]) if len(volumes) >= 6 else np.mean(volumes[:-1])
                vol_ratio = s["volume"] / avg_vol_5 if avg_vol_5 > 0 else 1.0

                s["percent_b"] = round(percent_b, 4)
                s["bb_lower"] = int(lower)
                s["bb_middle"] = int(ma)
                s["bb_upper"] = int(upper)
                s["vol_ratio"] = round(vol_ratio, 2)
                passed.append(s)

            except Exception as e:
                logger.debug(f"BB 계산 실패 {s['code']}: {e}")
                continue

        return passed

    def _calculate_scores(self, stocks: List[Dict]) -> List[Candidate]:
        if not stocks:
            return []

        min_pb = min(s["percent_b"] for s in stocks)
        max_pb = max(s["percent_b"] for s in stocks) or 1
        max_vol_ratio = max(s.get("vol_ratio", 1) for s in stocks) or 1
        max_tv = max(s["trading_value"] for s in stocks) or 1

        candidates = []
        for s in stocks:
            scores = {}

            # %B 점수: 낮을수록 높은 점수 (과매도)
            pb_norm = 1 - (s["percent_b"] - min_pb) / (max_pb - min_pb + 0.001)
            scores["percent_b"] = pb_norm * self.WEIGHTS["percent_b"]

            # 양봉 전환 강도 (등락률)
            reversal = min(s["change_pct"] / 5.0, 1.0)  # 5% cap
            scores["reversal_signal"] = reversal * self.WEIGHTS["reversal_signal"]

            # 거래량 surge
            vol_norm = min(s.get("vol_ratio", 1) / max_vol_ratio, 1.0)
            scores["volume_surge"] = vol_norm * self.WEIGHTS["volume_surge"]

            # 거래대금
            scores["trading_value"] = (s["trading_value"] / max_tv) * self.WEIGHTS["trading_value"]

            total = sum(scores.values())
            candidates.append(Candidate(
                code=s["code"],
                name=s.get("name", ""),
                price=s["close"],
                change_pct=s["change_pct"],
                score=round(total, 1),
                score_detail={
                    **{k: round(v, 1) for k, v in scores.items()},
                    "percent_b": s["percent_b"],
                    "bb_lower": s["bb_lower"],
                    "bb_middle": s["bb_middle"],
                },
                market_cap=s.get("market_cap", 0),
                volume=s.get("volume", 0),
                trading_value=s.get("trading_value", 0),
            ))

        return candidates

    def _fetch_pykrx(self, date: str) -> List[Dict]:
        """pykrx 폴백"""
        try:
            from pykrx import stock as pykrx_stock
            stocks = []
            for mkt in ("KOSPI", "KOSDAQ"):
                try:
                    df = pykrx_stock.get_market_ohlcv_by_ticker(date, market=mkt)
                    if df.empty:
                        continue
                    for code, row in df.iterrows():
                        close = int(row.get("종가", 0))
                        if close == 0:
                            continue
                        chg = float(row.get("등락률", 0))
                        prev = close / (1 + chg / 100) if chg != 0 else close
                        stocks.append({
                            "code": code, "name": "",
                            "market": mkt,
                            "open": int(row.get("시가", 0)),
                            "high": int(row.get("고가", 0)),
                            "low": int(row.get("저가", 0)),
                            "close": close,
                            "prev_close": int(prev),
                            "change_pct": chg,
                            "volume": int(row.get("거래량", 0)),
                            "trading_value": int(row.get("거래대금", 0)),
                            "market_cap": int(row.get("시가총액", 0)),
                        })
                except Exception:
                    continue
            if stocks:
                print(f"  [pykrx 폴백] {len(stocks)}개")
            return stocks
        except ImportError:
            return []

    def get_params(self) -> Dict:
        return {
            "bb_period": self.BB_PERIOD,
            "bb_std_mult": self.BB_STD_MULT,
            "percent_b_max": self.PERCENT_B_MAX,
            "min_price": self.MIN_PRICE,
            "min_trading_value": self.MIN_TRADING_VALUE,
            "min_market_cap": self.MIN_MARKET_CAP,
            "volume_surge_min": self.VOLUME_SURGE_MIN,
            "weights": self.WEIGHTS,
        }
