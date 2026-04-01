"""
기술적 지표 분석 모듈
5일선, 20일선, 전고점, 52주 고가 등 기술적 위치를 분석
점수에 반영하지 않고 표시만 (참고용)
"""

from datetime import datetime, timedelta
from utils import get_kst_now


class TechnicalAnalyzer:
    def __init__(self):
        self.use_pykrx = True
        # 네이버 금융 우선, pykrx 폴백
        try:
            from naver_market import stock
            self.pykrx_stock = stock
        except ImportError:
            try:
                from pykrx import stock
                self.pykrx_stock = stock
            except ImportError:
                print("  ⚠️  naver_market/pykrx 사용 불가. 기술적 분석을 스킵합니다.")
                self.use_pykrx = False

    def get_indicators(self, stock_code, date_str=None):
        """
        종목의 기술적 지표 계산

        Args:
            stock_code: 종목코드 (6자리)
            date_str: 기준 날짜 (YYYYMMDD), None이면 최근 영업일

        Returns:
            dict: 기술적 지표 결과 또는 None
        """
        if not self.use_pykrx:
            return None

        try:
            import pandas as pd

            if date_str is None:
                # 최근 영업일 계산
                today = get_kst_now()
                date_str = today.strftime('%Y%m%d')

            # 52주(365일) + 여유분 데이터 조회 (52주 고/저가 계산용)
            from_date = (datetime.strptime(date_str, '%Y%m%d') - timedelta(days=400)).strftime('%Y%m%d')

            df = self.pykrx_stock.get_market_ohlcv_by_date(from_date, date_str, stock_code)

            if df is None or len(df) < 5:
                return None

            # 이동평균 계산
            df['MA5'] = df['종가'].rolling(5).mean()
            df['MA20'] = df['종가'].rolling(20).mean()
            df['MA60'] = df['종가'].rolling(60).mean()

            # 거래량 이동평균
            df['VOL_MA20'] = df['거래량'].rolling(20).mean()

            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) >= 2 else latest

            # 52주(약 250 거래일) 고가/저가
            lookback = min(len(df), 250)
            high_52w = df['고가'].tail(lookback).max()
            low_52w = df['저가'].tail(lookback).min()

            # 20일 고가 (돌파 체크용)
            high_20d = df['고가'].tail(20).max() if len(df) >= 20 else df['고가'].max()

            # 이동평균 값 추출
            ma5 = latest['MA5'] if not pd.isna(latest['MA5']) else None
            ma20 = latest['MA20'] if not pd.isna(latest['MA20']) else None
            ma60 = latest['MA60'] if not pd.isna(latest['MA60']) else None
            vol_ma20 = latest['VOL_MA20'] if not pd.isna(latest['VOL_MA20']) else None

            current_price = int(latest['종가'])
            prev_high = int(prev['고가'])
            prev_close = int(prev['종가'])

            # 실제 20일 평균 거래량 (추정치가 아닌 실제값)
            avg_volume_20d = int(vol_ma20) if vol_ma20 else 0
            volume_ratio = (latest['거래량'] / vol_ma20) if vol_ma20 and vol_ma20 > 0 else 0

            result = {
                'code': stock_code,
                'current_price': current_price,
                'prev_close': prev_close,
                'prev_high': prev_high,

                # 이동평균
                'ma5': int(ma5) if ma5 else None,
                'ma20': int(ma20) if ma20 else None,
                'ma60': int(ma60) if ma60 else None,

                # 위치 판단 (bool()로 numpy.bool_ -> Python bool 변환)
                'above_ma5': bool(current_price > ma5) if ma5 else None,
                'above_ma20': bool(current_price > ma20) if ma20 else None,
                'above_ma60': bool(current_price > ma60) if ma60 else None,
                'ma5_above_ma20': bool(ma5 > ma20) if (ma5 and ma20) else None,

                # 전일 고가 대비
                'near_prev_high': bool(current_price >= prev_high * 0.98),
                'above_prev_high': bool(current_price > prev_high),

                # 20일 고가 대비
                'high_20d': int(high_20d),
                'near_high_20d': bool(current_price >= high_20d * 0.97),
                'above_high_20d': bool(current_price > high_20d),

                # 52주 고가/저가
                'high_52w': int(high_52w),
                'low_52w': int(low_52w),
                'pct_from_52w_high': round(float((current_price - high_52w) / high_52w * 100), 2),
                'near_52w_high': bool(current_price >= high_52w * 0.95),

                # 거래량
                'avg_volume_20d': avg_volume_20d,
                'volume_ratio': round(float(volume_ratio), 2),
            }

            return result

        except Exception as e:
            print(f"  ⚠️  기술적 분석 실패 ({stock_code}): {e}")
            return None

    def format_indicators(self, indicators):
        """기술적 지표를 포맷팅하여 문자열로 반환"""
        if not indicators:
            return "기술적 데이터 없음"

        lines = []
        price = indicators['current_price']

        # 이동평균 위치
        ma_status = []
        if indicators['above_ma5'] is True:
            ma_status.append("5일선↑")
        elif indicators['above_ma5'] is False:
            ma_status.append("5일선↓")

        if indicators['above_ma20'] is True:
            ma_status.append("20일선↑")
        elif indicators['above_ma20'] is False:
            ma_status.append("20일선↓")

        if indicators['above_ma60'] is True:
            ma_status.append("60일선↑")
        elif indicators['above_ma60'] is False:
            ma_status.append("60일선↓")

        lines.append(f"이동평균: {' / '.join(ma_status) if ma_status else 'N/A'}")

        # 골든크로스/데드크로스
        if indicators['ma5_above_ma20'] is True:
            lines.append("정배열 (5일선 > 20일선)")
        elif indicators['ma5_above_ma20'] is False:
            lines.append("역배열 (5일선 < 20일선)")

        # 돌파 여부
        if indicators['above_prev_high']:
            lines.append("전일 고가 돌파 ✅")
        elif indicators['near_prev_high']:
            lines.append("전일 고가 근접")

        if indicators['above_high_20d']:
            lines.append("20일 고가 돌파 ✅")
        elif indicators['near_high_20d']:
            lines.append("20일 고가 근접")

        if indicators['near_52w_high']:
            lines.append(f"52주 고가 근접 ({indicators['pct_from_52w_high']:+.1f}%)")

        # 이동평균 수치
        ma_values = []
        if indicators['ma5']:
            ma_values.append(f"MA5={indicators['ma5']:,}")
        if indicators['ma20']:
            ma_values.append(f"MA20={indicators['ma20']:,}")
        if indicators['ma60']:
            ma_values.append(f"MA60={indicators['ma60']:,}")

        if ma_values:
            lines.append(f"수치: {' / '.join(ma_values)}")

        # 거래량 비율 (실제 20일 평균 대비)
        if indicators['volume_ratio'] > 0:
            lines.append(f"거래량 비율: {indicators['volume_ratio']:.1f}x (20일 평균 대비)")

        return '\n'.join(lines)

    def get_technical_summary(self, indicators):
        """기술적 지표 요약 (한 줄)"""
        if not indicators:
            return '-'

        tags = []

        if indicators['above_ma5']:
            tags.append('5일↑')
        if indicators['above_ma20']:
            tags.append('20일↑')
        if indicators['ma5_above_ma20']:
            tags.append('정배열')
        if indicators['above_prev_high']:
            tags.append('전일고가돌파')
        elif indicators['near_prev_high']:
            tags.append('전일고가근접')
        if indicators['near_52w_high']:
            tags.append('52주고가근접')

        return ' / '.join(tags) if tags else '기술적 약세'

    def analyze_stocks(self, stocks, date_str=None):
        """
        여러 종목의 기술적 지표 일괄 분석

        Args:
            stocks: 종목 리스트 (code 필드 필요)
            date_str: 기준 날짜

        Returns:
            dict: {종목코드: 지표 결과}
        """
        if not self.use_pykrx:
            print("  ⚠️  pykrx를 사용할 수 없어 기술적 분석을 스킵합니다.")
            return {}

        print("\n📐 기술적 지표 분석 중...")
        results = {}
        import time

        for i, stock in enumerate(stocks, 1):
            code = stock.get('code', '')
            name = stock.get('name', '')

            indicators = self.get_indicators(code, date_str)

            if indicators:
                results[code] = indicators
                summary = self.get_technical_summary(indicators)
                print(f"  {i}. {name} ({code}): {summary}")
            else:
                print(f"  {i}. {name} ({code}): 데이터 없음")

            time.sleep(0.3)  # API 호출 간격

        print(f"  ✓ 기술적 분석 완료: {len(results)}개 종목")
        return results


if __name__ == '__main__':
    analyzer = TechnicalAnalyzer()

    if analyzer.use_pykrx:
        # 삼성전자 테스트
        indicators = analyzer.get_indicators('005930')
        if indicators:
            print("\n📐 삼성전자 기술적 지표:")
            print(analyzer.format_indicators(indicators))
        else:
            print("데이터를 가져올 수 없습니다.")
    else:
        print("pykrx가 설치되지 않았습니다.")
