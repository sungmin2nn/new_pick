"""
장중/장후 분봉 데이터 수집
선정된 종목들의 당일 거래 데이터 기록
"""

from datetime import datetime, timedelta
import json
import os

class IntradayCollector:
    def __init__(self):
        self.use_pykrx = True
        try:
            from pykrx import stock
            self.pykrx_stock = stock
        except ImportError:
            print("⚠️  pykrx 라이브러리가 설치되지 않았습니다.")
            self.use_pykrx = False

    def get_minute_data(self, stock_code, date_str, freq='1'):
        """
        특정 종목의 분봉 데이터 수집

        Args:
            stock_code: 종목코드 (6자리)
            date_str: 날짜 (YYYYMMDD)
            freq: 분봉 간격 ('1', '5', '10', '30', '60')

        Returns:
            분봉 데이터 리스트
        """
        if not self.use_pykrx:
            return []

        try:
            print(f"  📊 {stock_code} 분봉 데이터 수집 중... (freq={freq}분)")

            df = self.pykrx_stock.get_market_ohlcv_by_minute(
                date_str,
                stock_code,
                freq=freq
            )

            if df is None or df.empty:
                print(f"    ⚠️  데이터 없음")
                return []

            # DataFrame을 리스트로 변환
            minute_data = []
            for timestamp, row in df.iterrows():
                minute_data.append({
                    'time': timestamp.strftime('%H:%M:%S'),
                    'open': int(row['시가']),
                    'high': int(row['고가']),
                    'low': int(row['저가']),
                    'close': int(row['종가']),
                    'volume': int(row['거래량'])
                })

            print(f"    ✓ {len(minute_data)}개 데이터 수집 완료")
            return minute_data

        except Exception as e:
            print(f"    ⚠️  분봉 데이터 수집 실패: {e}")
            return []

    def analyze_profit_loss(self, stock_code, date_str, profit_target=3.0, loss_target=-2.0):
        """
        시초가 매매 익절/손절 분석

        Args:
            stock_code: 종목코드
            date_str: 날짜
            profit_target: 익절 목표 (%, 예: 3.0 = +3%)
            loss_target: 손절 목표 (%, 예: -2.0 = -2%)

        Returns:
            익절/손절 분석 결과
        """
        minute_data = self.get_minute_data(stock_code, date_str, freq='1')

        if not minute_data or len(minute_data) == 0:
            return None

        # 시초가 = 09:00 시가
        opening_price = minute_data[0]['open']

        if opening_price == 0:
            return None

        # 익절/손절 목표가 계산
        profit_price = opening_price * (1 + profit_target / 100)
        loss_price = opening_price * (1 + loss_target / 100)

        result = {
            'opening_price': opening_price,
            'profit_target_percent': profit_target,
            'loss_target_percent': loss_target,
            'profit_target_price': int(profit_price),
            'loss_target_price': int(loss_price),
            'first_hit': None,  # 'profit' or 'loss' or 'none'
            'first_hit_time': None,
            'first_hit_price': None,
            'profit_hit_time': None,
            'loss_hit_time': None,
            'max_profit_percent': 0,
            'max_loss_percent': 0,
            'closing_price': minute_data[-1]['close'],
            'closing_percent': ((minute_data[-1]['close'] - opening_price) / opening_price * 100) if opening_price > 0 else 0
        }

        profit_hit = False
        loss_hit = False

        # 1분봉 순회하며 익절/손절 도달 시점 확인
        for candle in minute_data:
            high = candle['high']
            low = candle['low']
            time = candle['time']

            # 수익률 계산
            high_percent = ((high - opening_price) / opening_price * 100) if opening_price > 0 else 0
            low_percent = ((low - opening_price) / opening_price * 100) if opening_price > 0 else 0

            # 최대 수익/손실 업데이트
            if high_percent > result['max_profit_percent']:
                result['max_profit_percent'] = high_percent
            if low_percent < result['max_loss_percent']:
                result['max_loss_percent'] = low_percent

            # 익절 도달 확인 (고가가 익절가 도달)
            if not profit_hit and high >= profit_price:
                profit_hit = True
                result['profit_hit_time'] = time

                if result['first_hit'] is None:
                    result['first_hit'] = 'profit'
                    result['first_hit_time'] = time
                    result['first_hit_price'] = int(profit_price)

            # 손절 도달 확인 (저가가 손절가 도달)
            if not loss_hit and low <= loss_price:
                loss_hit = True
                result['loss_hit_time'] = time

                if result['first_hit'] is None:
                    result['first_hit'] = 'loss'
                    result['first_hit_time'] = time
                    result['first_hit_price'] = int(loss_price)

            # 둘 다 도달했으면 더 이상 확인 불필요
            if profit_hit and loss_hit:
                break

        # 익절/손절 둘 다 도달 안 함
        if result['first_hit'] is None:
            result['first_hit'] = 'none'

        return result

    def collect_intraday_data(self, candidates, date_str=None, profit_target=3.0, loss_target=-2.0):
        """
        선정 종목들의 당일 거래 데이터 수집 + 익절/손절 분석

        Args:
            candidates: 선정 종목 리스트 (morning_candidates.json의 candidates)
            date_str: 날짜 (YYYYMMDD), None이면 오늘
            profit_target: 익절 목표 (%, 기본 +3%)
            loss_target: 손절 목표 (%, 기본 -2%)
        """
        if not self.use_pykrx:
            print("⚠️  pykrx를 사용할 수 없습니다.")
            return {}

        if date_str is None:
            date_str = datetime.now().strftime('%Y%m%d')

        print(f"\n📈 시초가 매매 분석 시작 - {date_str}")
        print(f"   익절 목표: +{profit_target}% / 손절 목표: {loss_target}%")

        intraday_data = {}

        for candidate in candidates:
            stock_code = candidate.get('code', '')
            stock_name = candidate.get('name', '')

            print(f"\n🔍 {stock_name} ({stock_code})")

            # 익절/손절 분석
            pl_analysis = self.analyze_profit_loss(stock_code, date_str, profit_target, loss_target)

            intraday_data[stock_code] = {
                'code': stock_code,
                'name': stock_name,
                'date': date_str,
                'profit_loss_analysis': pl_analysis,
                'selection_score': candidate.get('total_score', 0),
                'selection_reason': candidate.get('selection_reason', '-')
            }

        return intraday_data

    def save_intraday_data(self, intraday_data, date_str=None):
        """장중 데이터를 JSON 파일로 저장"""
        if date_str is None:
            date_str = datetime.now().strftime('%Y%m%d')

        os.makedirs('data/intraday', exist_ok=True)
        output_path = f'data/intraday/intraday_{date_str}.json'

        result = {
            'generated_at': datetime.now().isoformat(),
            'date': date_str,
            'count': len(intraday_data),
            'stocks': intraday_data
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"\n✅ 장중 데이터 저장 완료: {output_path}")
        return output_path


if __name__ == '__main__':
    # 테스트: morning_candidates.json 읽어서 수집
    collector = IntradayCollector()

    if not collector.use_pykrx:
        print("pykrx가 설치되지 않았습니다.")
        exit(1)

    # morning_candidates.json 로드
    try:
        with open('data/morning_candidates.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            candidates = data.get('candidates', [])

        if not candidates:
            print("선정된 종목이 없습니다.")
            exit(1)

        print(f"✓ {len(candidates)}개 선정 종목 로드 완료")

        # 당일 데이터 수집 (익절 +3%, 손절 -2%)
        intraday_data = collector.collect_intraday_data(candidates, profit_target=3.0, loss_target=-2.0)

        # 저장
        collector.save_intraday_data(intraday_data)

        # 익절/손절 분석 결과 출력
        print("\n" + "="*70)
        print("📊 시초가 매매 백테스팅 결과 (익절 +3% / 손절 -2%)")
        print("="*70)

        profit_count = 0
        loss_count = 0
        none_count = 0

        for code, data in intraday_data.items():
            pl = data.get('profit_loss_analysis')
            if pl:
                print(f"\n{data['name']} ({code})")
                print(f"  시초가: {pl['opening_price']:,}원")
                print(f"  익절가: {pl['profit_target_price']:,}원 (+{pl['profit_target_percent']}%)")
                print(f"  손절가: {pl['loss_target_price']:,}원 ({pl['loss_target_percent']}%)")

                first_hit = pl['first_hit']
                if first_hit == 'profit':
                    print(f"  ✅ 결과: 익절 도달 (시간: {pl['first_hit_time']})")
                    profit_count += 1
                elif first_hit == 'loss':
                    print(f"  ❌ 결과: 손절 도달 (시간: {pl['first_hit_time']})")
                    loss_count += 1
                else:
                    print(f"  ⚪ 결과: 익절/손절 미도달")
                    none_count += 1

                print(f"  최대 수익: +{pl['max_profit_percent']:.2f}%")
                print(f"  최대 손실: {pl['max_loss_percent']:.2f}%")
                print(f"  종가: {pl['closing_price']:,}원 ({pl['closing_percent']:+.2f}%)")
                print(f"  선정 점수: {data['selection_score']}점")

        # 통계
        total = len(intraday_data)
        print("\n" + "="*70)
        print(f"📈 전체 통계")
        print(f"  총 {total}개 종목")
        print(f"  익절 성공: {profit_count}개 ({profit_count/total*100:.1f}%)")
        print(f"  손절 발생: {loss_count}개 ({loss_count/total*100:.1f}%)")
        print(f"  미도달: {none_count}개 ({none_count/total*100:.1f}%)")
        if total > 0:
            win_rate = profit_count / total * 100
            print(f"  승률: {win_rate:.1f}%")
        print("="*70)

    except FileNotFoundError:
        print("morning_candidates.json 파일을 찾을 수 없습니다.")
    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()
