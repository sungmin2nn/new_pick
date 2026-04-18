"""
DART 공시 기반 전략 (Phase 7G: backtest 지원)
- 전일 18:00 ~ 당일 08:30 긍정적 공시 종목 선정
- 실적, 계약, 투자, 기술, 배당 등 카테고리별 점수화
- 시초가 매매에 활용
"""

import sys
import os
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from .base import BaseStrategy, Candidate
from .registry import StrategyRegistry
from paper_trading.utils.dart_utils import DartFilter, get_dart_filter

logger = logging.getLogger(__name__)

# KRX OpenAPI (당일 + backtest historical)
try:
    from paper_trading.utils.krx_api import KRXClient
    _krx_client = None
    def _get_krx():
        global _krx_client
        if _krx_client is None:
            try:
                _krx_client = KRXClient()
            except Exception as e:
                logger.warning(f"KRX OpenAPI 초기화 실패: {e}")
                _krx_client = False
        return _krx_client if _krx_client else None
except ImportError:
    _get_krx = lambda: None

# 네이버 금융 폴백
try:
    from naver_market import stock as naver_stock
    pykrx_stock = naver_stock
except ImportError:
    try:
        from pykrx import stock as pykrx_stock
    except ImportError:
        pykrx_stock = None


@StrategyRegistry.register
class DartDisclosureStrategy(BaseStrategy):
    """DART 공시 기반 전략"""

    STRATEGY_ID = "dart_disclosure"
    STRATEGY_NAME = "DART 공시"
    DESCRIPTION = "전일 18:00~당일 08:30 긍정 공시 종목 - 시초가 매매"

    # 점수 가중치 (총 100점)
    WEIGHTS = {
        'disclosure': 40,     # 공시 점수 (DART)
        'change_pct': 25,     # 등락률
        'trading_value': 20,  # 거래대금
        'market_cap': 15      # 시가총액 (적정 규모)
    }

    # 필터 기준
    MIN_MARKET_CAP = 100_000_000_000   # 최소 시총 1000억
    MAX_MARKET_CAP = 10_000_000_000_000  # 최대 시총 10조 (너무 큰 종목 제외)
    MIN_TRADING_VALUE = 1_000_000_000   # 최소 거래대금 10억
    MAX_DROP_PCT = -10.0  # 최대 하락률 (급락 종목 제외)

    def __init__(self):
        super().__init__()
        self.dart_filter = get_dart_filter()

    def select_stocks(self, date: str = None, top_n: int = 5) -> List[Candidate]:
        """종목 선정"""
        if date is None:
            date = datetime.now().strftime('%Y%m%d')

        self.selection_date = date
        print(f"\n[{self.STRATEGY_NAME}] 종목 선정 시작 ({date})")

        # DART API 확인
        if not self.dart_filter.is_available():
            print("  [DART] API 키가 없습니다. DART_API_KEY 환경변수를 설정하세요.")
            self.candidates = []
            return self.candidates

        # 1. 긍정적 공시 종목 수집 (Phase 7G: target_date 전달)
        print("  1. 긍정적 공시 수집 중...")
        positive_stocks = self.dart_filter.get_positive_stocks(target_date=date)
        print(f"     → {len(positive_stocks)}개 종목 발견")

        if not positive_stocks:
            print("  긍정적 공시 종목이 없습니다.")
            self.candidates = []
            return self.candidates

        # 2. 시장 데이터 가져오기
        print("  2. 시장 데이터 수집 중...")
        stocks_with_data = self._fetch_market_data(positive_stocks, date)
        print(f"     → {len(stocks_with_data)}개 종목 데이터 확보")

        # 3. 필터링 (시총, 거래대금)
        print("  3. 필터링 중...")
        filtered = self._apply_filters(stocks_with_data)
        print(f"     → {len(filtered)}개 종목 통과")

        # 4. 점수 계산
        print("  4. 점수 계산 중...")
        scored = self._calculate_scores(filtered)

        # 5. 상위 N개 선정
        scored.sort(key=lambda x: x.score, reverse=True)
        self.candidates = scored[:top_n]

        for i, c in enumerate(self.candidates, 1):
            c.rank = i

        print(f"  선정 완료: {len(self.candidates)}개")
        for c in self.candidates:
            print(f"     {c.rank}. {c.name} ({c.code}): 점수 {c.score:.1f}")

        return self.candidates

    def _fetch_market_data(self, positive_stocks: List, date: str) -> List[Dict]:
        """시장 데이터 수집 (Phase 7G: KRX OpenAPI 우선 - backtest 지원)

        - KRX historical 지원으로 과거 날짜 backtest 가능
        - 시장 단위 1번 fetch 후 매핑 (효율 ↑)
        - pykrx/naver 폴백: 시장 단위 fetch (get_market_ohlcv_by_ticker +
          get_market_cap_by_ticker)로 시총/거래대금 누락 방지
        - 당일 데이터 없으면 전일로 자동 폴백
        """
        stocks = []

        # 종목코드 set
        valid_codes = {sc for sc, _ in positive_stocks if sc and len(sc) == 6}
        score_map = {sc: ds for sc, ds in positive_stocks if sc and len(sc) == 6}
        if not valid_codes:
            return stocks

        # 1차: KRX OpenAPI (당일 + 과거)
        krx = _get_krx() if callable(_get_krx) else None
        if krx:
            try:
                market_data = {}
                for market in ['KOSPI', 'KOSDAQ']:
                    df = krx.get_stock_ohlcv(date, market=market)
                    if df.empty:
                        continue
                    for code in df.index:
                        if code in valid_codes:
                            market_data[code] = (df.loc[code], market)

                for code in valid_codes:
                    item = market_data.get(code)
                    if item is None:
                        continue
                    row, mkt = item
                    try:
                        close = int(row.get('종가', 0))
                        if close == 0:
                            continue
                        dart_score = score_map[code]
                        disc_summary = [{
                            'category': d.category,
                            'report_nm': d.report_nm[:50],
                            'amount': d.amount,
                        } for d in dart_score.disclosures]
                        stocks.append({
                            'code': code,
                            'name': str(row.get('종목명', code)),
                            'price': close,
                            'change_pct': float(row.get('등락률', 0)),
                            'volume': int(row.get('거래량', 0)),
                            'trading_value': int(row.get('거래대금', 0)),
                            'market_cap': int(row.get('시가총액', 0)),
                            'dart_score': dart_score.disclosure_score,
                            'disclosures': disc_summary,
                        })
                    except Exception as e:
                        logger.debug(f"  KRX 매핑 실패 {code}: {e}")
                        continue

                if stocks:
                    return stocks
            except Exception as e:
                logger.warning(f"  KRX fetch 실패, pykrx/naver 폴백: {e}")

        # 2차: pykrx/naver 폴백 - 시장 단위 1회 fetch + 매핑
        #   기존: 종목별 get_market_ohlcv_by_date() → 당일 미장 시 빈 결과,
        #         get_market_cap_by_date(ticker=) 미지원으로 시총=0
        #   수정: get_market_ohlcv_by_ticker(date) + get_market_cap_by_ticker(date)
        #         시장 전체를 한 번에 가져와서 매핑 (효율 + 정확도 ↑)
        if pykrx_stock is None:
            return stocks

        ohlcv_data = {}   # code -> row (종가, 등락률, 거래량, 거래대금)
        cap_data = {}     # code -> 시가총액

        # 당일 → 전일 자동 폴백 (당일 장 시작 전이면 데이터 없음)
        fetch_dates = [date]
        try:
            dt = datetime.strptime(date, '%Y%m%d')
            prev = dt - timedelta(days=1)
            # 주말 건너뛰기
            while prev.weekday() >= 5:
                prev -= timedelta(days=1)
            fetch_dates.append(prev.strftime('%Y%m%d'))
        except ValueError:
            pass

        fetched = False
        used_date = date
        for try_date in fetch_dates:
            for market in ['KOSPI', 'KOSDAQ']:
                try:
                    df = pykrx_stock.get_market_ohlcv_by_ticker(try_date, market=market)
                    if df is None or df.empty:
                        continue
                    for code in df.index:
                        if code in valid_codes and code not in ohlcv_data:
                            ohlcv_data[code] = df.loc[code]
                except Exception as e:
                    logger.debug(f"  OHLCV fetch 실패 ({market}, {try_date}): {e}")
                    continue

                try:
                    cap_df = pykrx_stock.get_market_cap_by_ticker(try_date, market=market)
                    if cap_df is not None and not cap_df.empty:
                        for code in cap_df.index:
                            if code in valid_codes and code not in cap_data:
                                if '시가총액' in cap_df.columns:
                                    cap_data[code] = int(cap_df.loc[code]['시가총액'])
                except Exception as e:
                    logger.debug(f"  시총 fetch 실패 ({market}, {try_date}): {e}")
                    continue

            if ohlcv_data:
                used_date = try_date
                fetched = True
                break

        if used_date != date and fetched:
            logger.info(f"  당일({date}) 데이터 없음 → 전일({used_date}) 데이터 사용")

        # 매핑
        for stock_code, dart_score in positive_stocks:
            if not stock_code or len(stock_code) != 6:
                continue
            row = ohlcv_data.get(stock_code)
            if row is None:
                continue
            try:
                close = int(row['종가'])
                if close == 0:
                    continue
                change = float(row['등락률']) if '등락률' in row.index else 0
                volume = int(row['거래량']) if '거래량' in row.index else 0
                trading_value = int(row['거래대금']) if '거래대금' in row.index else 0
                name = str(row.get('종목명', '')) if hasattr(row, 'get') else ''
                if not name:
                    try:
                        name = pykrx_stock.get_market_ticker_name(stock_code)
                    except Exception:
                        name = stock_code
                market_cap = cap_data.get(stock_code, 0)

                disc_summary = [{
                    'category': d.category,
                    'report_nm': d.report_nm[:50],
                    'amount': d.amount,
                } for d in dart_score.disclosures]
                stocks.append({
                    'code': stock_code,
                    'name': name or '알수없음',
                    'price': close,
                    'change_pct': change,
                    'volume': volume,
                    'trading_value': trading_value,
                    'market_cap': market_cap,
                    'dart_score': dart_score.disclosure_score,
                    'disclosures': disc_summary,
                })
            except Exception as e:
                logger.debug(f"     [DART] pykrx/naver 매핑 실패 ({stock_code}): {e}")
                continue

        return stocks

    def _apply_filters(self, stocks: List[Dict]) -> List[Dict]:
        """필터링"""
        filtered = []

        for s in stocks:
            market_cap = s.get('market_cap', 0)
            trading_value = s.get('trading_value', 0)
            change_pct = s.get('change_pct', 0)

            # 급락 종목 제외 (전일 -10% 이상 하락)
            if change_pct < self.MAX_DROP_PCT:
                continue

            # 시총 필터 (데이터 없으면 통과)
            if market_cap > 0:
                if market_cap < self.MIN_MARKET_CAP:
                    continue
                if market_cap > self.MAX_MARKET_CAP:
                    continue

            # 거래대금 필터 (데이터 없으면 통과)
            if trading_value > 0 and trading_value < self.MIN_TRADING_VALUE:
                continue

            filtered.append(s)

        return filtered

    def _calculate_scores(self, stocks: List[Dict]) -> List[Candidate]:
        """점수 계산"""
        if not stocks:
            return []

        candidates = []

        # 정규화를 위한 최대값
        max_dart = max(s['dart_score'] for s in stocks) if stocks else 1
        max_change = max(abs(s['change_pct']) for s in stocks) if stocks else 1
        max_value = max(s['trading_value'] for s in stocks) if stocks else 1
        max_cap = max(s['market_cap'] for s in stocks) if stocks else 1

        for s in stocks:
            scores = {}

            # 1. 공시 점수 (최대 40점)
            scores['disclosure'] = (s['dart_score'] / max(max_dart, 1)) * self.WEIGHTS['disclosure']

            # 2. 등락률 점수 (상승 우대, 최대 25점)
            change = s['change_pct']
            if change > 0:
                scores['change_pct'] = min(change / 10, 1) * self.WEIGHTS['change_pct']
            else:
                scores['change_pct'] = 0

            # 3. 거래대금 점수 (최대 20점)
            value_ratio = s['trading_value'] / max(max_value, 1)
            scores['trading_value'] = value_ratio * self.WEIGHTS['trading_value']

            # 4. 시총 점수 (중형주 우대, 최대 15점)
            market_cap = s['market_cap']
            if market_cap > 0:
                # 시총 5000억~2조가 이상적
                ideal_low = 500_000_000_000
                ideal_high = 2_000_000_000_000

                if ideal_low <= market_cap <= ideal_high:
                    cap_score = 1.0  # 이상적 범위
                elif market_cap < ideal_low:
                    cap_score = market_cap / ideal_low * 0.8
                else:
                    cap_score = ideal_high / market_cap * 0.8

                scores['market_cap'] = cap_score * self.WEIGHTS['market_cap']
            else:
                scores['market_cap'] = self.WEIGHTS['market_cap'] * 0.5  # 데이터 없으면 중간값

            total_score = sum(scores.values())

            candidates.append(Candidate(
                code=s['code'],
                name=s['name'],
                price=s['price'],
                change_pct=s['change_pct'],
                score=round(total_score, 1),
                score_detail={
                    **scores,
                    'dart_raw': s['dart_score'],
                    'disclosures': s['disclosures']
                },
                market_cap=s['market_cap'],
                volume=s['volume'],
                trading_value=s['trading_value']
            ))

        return candidates

    def get_params(self) -> Dict:
        return {
            'weights': self.WEIGHTS,
            'min_market_cap': self.MIN_MARKET_CAP,
            'max_market_cap': self.MAX_MARKET_CAP,
            'min_trading_value': self.MIN_TRADING_VALUE
        }


if __name__ == '__main__':
    # 테스트
    from dotenv import load_dotenv
    load_dotenv()

    strategy = DartDisclosureStrategy()
    candidates = strategy.select_stocks(top_n=10)

    if candidates:
        print("\n=== 선정 결과 ===")
        for c in candidates:
            print(f"{c.rank}. {c.name} ({c.code})")
            print(f"   점수: {c.score:.1f}")
            print(f"   등락률: {c.change_pct:+.2f}%")
            if c.score_detail.get('disclosures'):
                for disc in c.score_detail['disclosures']:
                    print(f"   공시: [{disc['category']}] {disc['report_nm']}")
