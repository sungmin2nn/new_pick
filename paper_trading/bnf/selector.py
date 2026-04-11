"""
BNF (Buy iN Fall) 전략 - 낙폭과대 종목 선정 모듈

선정 기준:
1. 낙폭과대 조건 (OR 조건):
   - 5일 낙폭 >= 15%
   - 10일 낙폭 >= 20%
   - 최근 고점(20일) 대비 현재가 낙폭 >= 25%

2. 필터 조건 (AND 조건):
   - 시가총액 > 1조원 (대형주)
   - 일평균 거래대금 > 100억원 (유동성)
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
import logging
import json

# 상위 디렉토리 import 설정
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# 네이버 금융 우선, pykrx 폴백
try:
    from naver_market import stock
    import pandas as pd
    PYKRX_AVAILABLE = True
except ImportError:
    try:
        from pykrx import stock
        import pandas as pd
        PYKRX_AVAILABLE = True
    except ImportError:
        PYKRX_AVAILABLE = False
        print("[BNFSelector] Warning: naver_market/pykrx not available")

# 경고 무시
import warnings
warnings.filterwarnings('ignore')

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class BNFCandidate:
    """낙폭과대 종목 후보 데이터 클래스"""
    code: str
    name: str
    current_price: int
    market_cap: int
    trading_value: int

    # 낙폭 정보
    drop_5d: float = 0.0
    drop_10d: float = 0.0
    drop_from_high: float = 0.0
    max_drop: float = 0.0  # 최대 낙폭

    # 추가 정보
    high_20d: int = 0
    volume: int = 0
    avg_volume_20d: int = 0

    # 메타 정보
    selection_reason: str = ""
    rank: int = 0

    def to_dict(self) -> dict:
        """딕셔너리로 변환 (dashboard 호환 별칭 포함)"""
        return {
            'code': self.code,
            'name': self.name,
            # 두 키 모두 제공 (dashboard는 price/reasons 사용, 모듈은 current_price/selection_reason)
            'price': self.current_price,
            'current_price': self.current_price,
            'market_cap': self.market_cap,
            'trading_value': self.trading_value,
            'drop_5d': self.drop_5d,
            'drop_10d': self.drop_10d,
            'drop_from_high': self.drop_from_high,
            'max_drop': self.max_drop,
            'high_20d': self.high_20d,
            'volume': self.volume,
            'avg_volume_20d': self.avg_volume_20d,
            'selection_reason': self.selection_reason,
            'reasons': self.selection_reason,
            'rank': self.rank
        }


class BNFSelector:
    """
    BNF (Buy iN Fall) 전략 종목 선정기
    낙폭과대 종목을 선정하여 반등 기회 포착
    """

    # 낙폭 기준
    DROP_5D_THRESHOLD = 15.0   # 5일 낙폭 15% 이상
    DROP_10D_THRESHOLD = 20.0  # 10일 낙폭 20% 이상
    DROP_HIGH_THRESHOLD = 25.0 # 고점 대비 25% 이상

    # 필터 기준
    MIN_MARKET_CAP = 1_000_000_000_000      # 시가총액 1조원 이상
    MIN_TRADING_VALUE = 10_000_000_000      # 거래대금 100억원 이상

    # 데이터 조회 기간
    LOOKBACK_DAYS = 30  # 과거 30일 데이터 조회
    HIGH_LOOKBACK = 20  # 최근 고점 조회 기간

    def __init__(self, data_dir: str = "data/bnf"):
        """초기화"""
        self.candidates: List[BNFCandidate] = []
        self.selection_date: str = ""
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        logger.info("BNFSelector 초기화 완료")

    def get_trading_date(self, date_str: str, days_back: int = 0) -> str:
        """
        거래일 계산 (주말/공휴일 제외)

        Args:
            date_str: 기준 날짜 (YYYYMMDD)
            days_back: 과거 N일

        Returns:
            거래일 문자열 (YYYYMMDD)
        """
        if not PYKRX_AVAILABLE:
            base_date = datetime.strptime(date_str, "%Y%m%d")
            return (base_date - timedelta(days=days_back)).strftime("%Y%m%d")

        try:
            base_date = datetime.strptime(date_str, "%Y%m%d")
            # 충분한 여유를 두고 과거 날짜 계산 (주말/공휴일 고려)
            start_date = base_date - timedelta(days=days_back + 10)

            # KOSPI 거래일 목록 조회
            trading_dates = stock.get_index_ohlcv(
                start_date.strftime("%Y%m%d"),
                date_str,
                "1001"  # KOSPI
            )

            if trading_dates.empty:
                logger.warning(f"거래일 조회 실패: {date_str}")
                return (base_date - timedelta(days=days_back)).strftime("%Y%m%d")

            # 날짜 리스트 추출
            dates = [d.strftime("%Y%m%d") for d in trading_dates.index]

            if date_str in dates:
                idx = dates.index(date_str)
                if idx >= days_back:
                    return dates[idx - days_back]

            # 기준일이 거래일이 아닌 경우, 가장 최근 거래일 반환
            return dates[-1] if dates else date_str

        except Exception as e:
            logger.error(f"거래일 계산 오류: {e}")
            return (datetime.strptime(date_str, "%Y%m%d") - timedelta(days=days_back)).strftime("%Y%m%d")

    def get_all_stocks(self, date_str: str) -> List[str]:
        """
        전체 종목 코드 조회 (KOSPI + KOSDAQ)

        Args:
            date_str: 조회 날짜 (YYYYMMDD)

        Returns:
            종목 코드 리스트
        """
        if not PYKRX_AVAILABLE:
            logger.error("pykrx not available")
            return []

        try:
            logger.info(f"전체 종목 조회 중... ({date_str})")

            # KOSPI 종목
            kospi_tickers = stock.get_market_ticker_list(date_str, market="KOSPI")
            logger.info(f"KOSPI 종목: {len(kospi_tickers)}개")

            # KOSDAQ 종목
            kosdaq_tickers = stock.get_market_ticker_list(date_str, market="KOSDAQ")
            logger.info(f"KOSDAQ 종목: {len(kosdaq_tickers)}개")

            # 합치기
            all_tickers = list(set(kospi_tickers + kosdaq_tickers))
            logger.info(f"전체 종목: {len(all_tickers)}개")

            return all_tickers

        except Exception as e:
            logger.error(f"종목 조회 오류: {e}")
            return []

    def get_stock_ohlcv(self, code: str, start_date: str, end_date: str) -> 'pd.DataFrame':
        """
        종목 OHLCV 데이터 조회

        Args:
            code: 종목 코드
            start_date: 시작일 (YYYYMMDD)
            end_date: 종료일 (YYYYMMDD)

        Returns:
            OHLCV 데이터프레임
        """
        if not PYKRX_AVAILABLE:
            import pandas as pd
            return pd.DataFrame()

        try:
            df = stock.get_market_ohlcv(start_date, end_date, code)
            return df
        except Exception as e:
            logger.debug(f"OHLCV 조회 실패 ({code}): {e}")
            import pandas as pd
            return pd.DataFrame()

    def calculate_drop_percentage(self, code: str, date_str: str, days: int) -> float:
        """
        N일 낙폭 계산

        Args:
            code: 종목 코드
            date_str: 기준 날짜 (YYYYMMDD)
            days: 과거 N일

        Returns:
            낙폭 퍼센트 (양수: 하락, 음수: 상승)
        """
        try:
            # 시작일 계산
            start_date = self.get_trading_date(date_str, days)

            # OHLCV 조회
            df = self.get_stock_ohlcv(code, start_date, date_str)

            if df.empty or len(df) < 2:
                return 0.0

            # N일 전 종가와 현재 종가 비교
            past_price = df.iloc[0]['종가']
            current_price = df.iloc[-1]['종가']

            if past_price == 0:
                return 0.0

            # 낙폭 계산 (과거 대비 현재 가격 변동률)
            drop_pct = ((past_price - current_price) / past_price) * 100

            return round(drop_pct, 2)

        except Exception as e:
            logger.debug(f"낙폭 계산 실패 ({code}, {days}일): {e}")
            return 0.0

    def get_high_to_current_drop(self, code: str, date_str: str, lookback: int = 20) -> Tuple[float, int]:
        """
        최근 고점 대비 현재가 낙폭 계산

        Args:
            code: 종목 코드
            date_str: 기준 날짜 (YYYYMMDD)
            lookback: 고점 조회 기간 (기본 20일)

        Returns:
            (낙폭 퍼센트, 고점 가격)
        """
        try:
            # 시작일 계산
            start_date = self.get_trading_date(date_str, lookback)

            # OHLCV 조회
            df = self.get_stock_ohlcv(code, start_date, date_str)

            if df.empty:
                return 0.0, 0

            # 최근 고점
            high_price = df['고가'].max()
            current_price = df.iloc[-1]['종가']

            if high_price == 0:
                return 0.0, 0

            # 고점 대비 낙폭
            drop_pct = ((high_price - current_price) / high_price) * 100

            return round(drop_pct, 2), int(high_price)

        except Exception as e:
            logger.debug(f"고점 대비 낙폭 계산 실패 ({code}): {e}")
            return 0.0, 0

    def get_market_cap_and_trading_value(self, code: str, date_str: str) -> Tuple[int, int]:
        """
        시가총액 및 거래대금 조회

        Args:
            code: 종목 코드
            date_str: 조회 날짜 (YYYYMMDD)

        Returns:
            (시가총액, 거래대금)
        """
        if not PYKRX_AVAILABLE:
            return 0, 0

        try:
            # 시가총액 조회
            cap_df = stock.get_market_cap(date_str, date_str, code)

            if cap_df.empty:
                return 0, 0

            market_cap = int(cap_df.iloc[-1]['시가총액'])
            trading_value = int(cap_df.iloc[-1]['거래대금'])

            return market_cap, trading_value

        except Exception as e:
            logger.debug(f"시가총액/거래대금 조회 실패 ({code}): {e}")
            return 0, 0

    def get_volume_info(self, code: str, date_str: str) -> Tuple[int, int]:
        """
        거래량 정보 조회

        Args:
            code: 종목 코드
            date_str: 조회 날짜 (YYYYMMDD)

        Returns:
            (현재 거래량, 20일 평균 거래량)
        """
        try:
            # 20일 데이터 조회
            start_date = self.get_trading_date(date_str, 20)
            df = self.get_stock_ohlcv(code, start_date, date_str)

            if df.empty:
                return 0, 0

            current_volume = int(df.iloc[-1]['거래량'])
            avg_volume = int(df['거래량'].mean())

            return current_volume, avg_volume

        except Exception as e:
            logger.debug(f"거래량 조회 실패 ({code}): {e}")
            return 0, 0

    def check_oversold_condition(self, code: str, date_str: str) -> Optional[BNFCandidate]:
        """
        낙폭과대 조건 체크

        Args:
            code: 종목 코드
            date_str: 기준 날짜 (YYYYMMDD)

        Returns:
            조건 충족 시 BNFCandidate, 아니면 None
        """
        try:
            # 1. 시가총액 및 거래대금 체크 (먼저 필터링)
            market_cap, trading_value = self.get_market_cap_and_trading_value(code, date_str)

            if market_cap < self.MIN_MARKET_CAP:
                return None

            if trading_value < self.MIN_TRADING_VALUE:
                return None

            # 2. 낙폭 계산
            drop_5d = self.calculate_drop_percentage(code, date_str, 5)
            drop_10d = self.calculate_drop_percentage(code, date_str, 10)
            drop_from_high, high_20d = self.get_high_to_current_drop(code, date_str, self.HIGH_LOOKBACK)

            # 3. 낙폭과대 조건 체크 (OR 조건)
            reasons = []
            if drop_5d >= self.DROP_5D_THRESHOLD:
                reasons.append(f"5일 낙폭 {drop_5d:.1f}%")

            if drop_10d >= self.DROP_10D_THRESHOLD:
                reasons.append(f"10일 낙폭 {drop_10d:.1f}%")

            if drop_from_high >= self.DROP_HIGH_THRESHOLD:
                reasons.append(f"고점 대비 {drop_from_high:.1f}%")

            if not reasons:
                return None

            # 4. 현재가 및 거래량 정보
            start_date = self.get_trading_date(date_str, 1)
            df = self.get_stock_ohlcv(code, start_date, date_str)

            if df.empty:
                return None

            current_price = int(df.iloc[-1]['종가'])
            volume, avg_volume = self.get_volume_info(code, date_str)

            # 5. 종목명 조회
            try:
                name = stock.get_market_ticker_name(code) if PYKRX_AVAILABLE else code
            except:
                name = code

            # 6. 후보 생성
            max_drop = max(drop_5d, drop_10d, drop_from_high)

            candidate = BNFCandidate(
                code=code,
                name=name,
                current_price=current_price,
                market_cap=market_cap,
                trading_value=trading_value,
                drop_5d=drop_5d,
                drop_10d=drop_10d,
                drop_from_high=drop_from_high,
                max_drop=max_drop,
                high_20d=high_20d,
                volume=volume,
                avg_volume_20d=avg_volume,
                selection_reason=" | ".join(reasons)
            )

            return candidate

        except Exception as e:
            logger.debug(f"낙폭과대 체크 실패 ({code}): {e}")
            return None

    def select_oversold_stocks(self, date_str: str = None, top_n: int = 20) -> List[BNFCandidate]:
        """
        낙폭과대 종목 선정

        Args:
            date_str: 기준 날짜 (YYYYMMDD), None이면 최근 거래일
            top_n: 상위 N개 선정

        Returns:
            선정된 종목 리스트 (낙폭 큰 순)
        """
        # 날짜 설정
        if date_str is None:
            date_str = datetime.now().strftime("%Y%m%d")

        self.selection_date = date_str

        logger.info(f"\n{'='*60}")
        logger.info(f"BNF 낙폭과대 종목 선정 시작 ({date_str})")
        logger.info(f"{'='*60}")
        logger.info(f"선정 기준:")
        logger.info(f"  - 5일 낙폭 >= {self.DROP_5D_THRESHOLD}% OR")
        logger.info(f"  - 10일 낙폭 >= {self.DROP_10D_THRESHOLD}% OR")
        logger.info(f"  - 고점 대비 >= {self.DROP_HIGH_THRESHOLD}%")
        logger.info(f"  - 시가총액 >= {self.MIN_MARKET_CAP/1e12:.1f}조원")
        logger.info(f"  - 거래대금 >= {self.MIN_TRADING_VALUE/1e9:.0f}억원")
        logger.info(f"{'='*60}\n")

        # 전체 종목 조회
        all_stocks = self.get_all_stocks(date_str)

        if not all_stocks:
            logger.error("종목 목록 조회 실패")
            return []

        logger.info(f"총 {len(all_stocks)}개 종목 분석 시작...")

        # 종목별 체크
        candidates = []
        checked = 0

        for i, code in enumerate(all_stocks, 1):
            try:
                # 진행 상황 표시 (100개마다)
                if i % 100 == 0:
                    logger.info(f"진행: {i}/{len(all_stocks)} ({i/len(all_stocks)*100:.1f}%) - 후보: {len(candidates)}개")

                candidate = self.check_oversold_condition(code, date_str)

                if candidate:
                    candidates.append(candidate)
                    logger.info(f"  ✓ {candidate.name} ({candidate.code}): {candidate.selection_reason}")

                checked += 1

            except Exception as e:
                logger.debug(f"종목 체크 오류 ({code}): {e}")
                continue

        logger.info(f"\n분석 완료: {checked}개 종목 체크, {len(candidates)}개 후보 발견")

        # 낙폭 큰 순으로 정렬
        candidates.sort(key=lambda x: x.max_drop, reverse=True)

        # 순위 부여
        for i, candidate in enumerate(candidates[:top_n], 1):
            candidate.rank = i

        self.candidates = candidates[:top_n]

        # 결과 출력
        logger.info(f"\n{'='*60}")
        logger.info(f"상위 {min(top_n, len(candidates))}개 낙폭과대 종목:")
        logger.info(f"{'='*60}")

        for c in self.candidates:
            logger.info(f"\n{c.rank}. {c.name} ({c.code})")
            logger.info(f"   현재가: {c.current_price:,}원 | 시총: {c.market_cap/1e12:.2f}조")
            logger.info(f"   낙폭: 5일={c.drop_5d:.1f}% | 10일={c.drop_10d:.1f}% | 고점={c.drop_from_high:.1f}%")
            logger.info(f"   거래대금: {c.trading_value/1e8:.0f}억 | 거래량: {c.volume:,}주")
            logger.info(f"   선정 사유: {c.selection_reason}")

        logger.info(f"\n{'='*60}\n")

        return self.candidates

    def get_selection_summary(self) -> dict:
        """선정 결과 요약"""
        return {
            'date': self.selection_date,
            'strategy': 'BNF_낙폭과대',
            'total_candidates': len(self.candidates),
            'candidates': [c.to_dict() for c in self.candidates],
            'criteria': {
                'drop_5d_threshold': self.DROP_5D_THRESHOLD,
                'drop_10d_threshold': self.DROP_10D_THRESHOLD,
                'drop_high_threshold': self.DROP_HIGH_THRESHOLD,
                'min_market_cap': self.MIN_MARKET_CAP,
                'min_trading_value': self.MIN_TRADING_VALUE,
            }
        }

    def save_candidates(self, filename: str = None) -> str:
        """선정 결과를 JSON으로 저장"""
        if filename is None:
            filename = f"candidates_{self.selection_date}.json"

        filepath = self.data_dir / filename

        try:
            summary = self.get_selection_summary()
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
            logger.info(f"결과 저장 완료: {filepath}")
            return str(filepath)
        except Exception as e:
            logger.error(f"JSON 저장 실패: {e}")
            return ""

    def export_to_csv(self, filename: str = None):
        """결과를 CSV로 저장"""
        if not self.candidates:
            logger.warning("저장할 후보가 없습니다.")
            return

        if filename is None:
            filename = f"bnf_candidates_{self.selection_date}.csv"

        try:
            import pandas as pd
            df = pd.DataFrame([c.to_dict() for c in self.candidates])
            filepath = self.data_dir / filename
            df.to_csv(filepath, index=False, encoding='utf-8-sig')
            logger.info(f"CSV 저장 완료: {filepath}")
        except Exception as e:
            logger.error(f"CSV 저장 실패: {e}")


# CLI 테스트
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='BNF 낙폭과대 종목 선정')
    parser.add_argument('--date', type=str, help='기준 날짜 (YYYYMMDD)')
    parser.add_argument('--top', type=int, default=20, help='상위 N개 선정 (기본: 20)')
    parser.add_argument('--export', action='store_true', help='CSV로 저장')

    args = parser.parse_args()

    # 선정 실행
    selector = BNFSelector()
    candidates = selector.select_oversold_stocks(date_str=args.date, top_n=args.top)

    # JSON 저장
    if candidates:
        selector.save_candidates()

    # CSV 저장
    if args.export and candidates:
        selector.export_to_csv()

    # 요약 출력
    summary = selector.get_selection_summary()
    print(f"\n[선정 완료]")
    print(f"날짜: {summary['date']}")
    print(f"전략: {summary['strategy']}")
    print(f"선정 종목: {summary['total_candidates']}개")
