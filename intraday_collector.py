"""
장중/장후 분봉 데이터 수집
선정된 종목들의 당일 거래 데이터 기록
"""

from datetime import datetime, timedelta
import json
import os
import requests
from bs4 import BeautifulSoup
import time
import re

class IntradayCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://finance.naver.com/'
        })

    def get_minute_data(self, stock_code, date_str, freq='1'):
        """
        네이버 증권에서 분봉 데이터 수집

        주의: 네이버 금융은 당일 장중 데이터만 제공합니다.
        과거 데이터는 조회할 수 없습니다.

        Args:
            stock_code: 종목코드 (6자리)
            date_str: 날짜 (YYYYMMDD) - 당일만 가능
            freq: 분봉 간격 ('1') - 네이버는 1분봉만 제공

        Returns:
            분봉 데이터 리스트
        """
        try:
            print(f"  📊 {stock_code} 분봉 데이터 수집 중... (Naver Finance)")

            minute_data = []
            page = 1
            max_pages = 50  # 최대 50페이지 (약 400개 데이터)

            # thistime 파라미터: 현재 시간 또는 당일 장 마감 시간 사용
            thistime = datetime.now().strftime('%Y%m%d%H%M%S')

            while page <= max_pages:
                url = f"https://finance.naver.com/item/sise_time.naver?code={stock_code}&thistime={thistime}&page={page}"

                try:
                    response = self.session.get(url, timeout=10)
                    response.raise_for_status()
                except Exception as e:
                    print(f"    ⚠️  페이지 {page} 요청 실패: {e}")
                    break

                soup = BeautifulSoup(response.text, 'html.parser')

                # 데이터 테이블 찾기
                table = soup.select_one('table.type2')
                if not table:
                    print(f"    ⚠️  페이지 {page} 테이블 없음")
                    break

                rows = table.select('tr')
                data_found = False

                for row in rows:
                    cols = row.select('td')
                    if len(cols) < 7:
                        continue

                    # 시간 (첫 번째 td의 span)
                    time_span = cols[0].select_one('span')
                    if not time_span:
                        continue

                    time_text = time_span.get_text(strip=True)
                    if not time_text or ':' not in time_text:
                        continue

                    # 체결가 (두 번째 td의 span)
                    price_span = cols[1].select_one('span')
                    if not price_span:
                        continue
                    price_text = price_span.get_text(strip=True).replace(',', '').replace('원', '')

                    # 거래량 (일곱 번째 td의 span)
                    volume_span = cols[6].select_one('span')
                    volume_text = '0'
                    if volume_span:
                        volume_text = volume_span.get_text(strip=True).replace(',', '')

                    try:
                        # 시간 파싱 (HH:MM)
                        time_parts = time_text.split(':')
                        if len(time_parts) != 2:
                            continue

                        close_price = int(price_text)
                        volume = int(volume_text) if volume_text else 0

                        # 네이버는 체결가만 제공하므로 OHLC를 체결가로 동일하게 설정
                        minute_data.append({
                            'time': f"{time_text}:00",
                            'open': close_price,
                            'high': close_price,
                            'low': close_price,
                            'close': close_price,
                            'volume': volume
                        })
                        data_found = True

                    except (ValueError, IndexError) as e:
                        continue

                if not data_found:
                    # 데이터 없으면 중단
                    break

                page += 1
                time.sleep(0.2)  # 요청 간격

            if minute_data:
                # 시간순으로 정렬 (오래된 것부터)
                minute_data.sort(key=lambda x: x['time'])
                print(f"    ✓ {len(minute_data)}개 데이터 수집 완료")
            else:
                print(f"    ⚠️  데이터 없음 (장중이 아니거나 당일이 아닙니다)")

            return minute_data

        except Exception as e:
            print(f"    ⚠️  분봉 데이터 수집 실패: {e}")
            import traceback
            traceback.print_exc()
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
            date_str: 날짜 (YYYYMMDD), None이면 오늘 (네이버는 당일만 조회 가능)
            profit_target: 익절 목표 (%, 기본 +3%)
            loss_target: 손절 목표 (%, 기본 -2%)
        """
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
