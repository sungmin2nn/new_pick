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
from utils import get_kst_now, format_kst_time, get_random_user_agent

class IntradayCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': get_random_user_agent(),  # 랜덤 User-Agent 사용
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

            # thistime 파라미터: 한국 시간 기준
            thistime = format_kst_time(format_str='%Y%m%d%H%M%S')

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

    def check_entry_conditions(self, minute_data, avg_volume_20d=0):
        """
        매수 진입 조건 체크 (09:05 기준)

        Args:
            minute_data: 분봉 데이터
            avg_volume_20d: 20일 평균 거래량

        Returns:
            매수 조건 체크 결과
        """
        import config

        check_minutes = getattr(config, 'VOLUME_CHECK_MINUTES', 5)
        volume_threshold = getattr(config, 'VOLUME_CHECK_THRESHOLD', 0.5)
        max_gap = getattr(config, 'MAX_GAP_UP', 5.0)
        min_gap = getattr(config, 'MIN_GAP_DOWN', -5.0)

        result = {
            'volume_5min': 0,
            'volume_5min_ratio': 0,
            'volume_sufficient': False,
            'gap_percent': 0,
            'gap_ok': True,
            'should_buy': False,
            'skip_reason': None,
            'entry_price': 0,
            'entry_time': None
        }

        if not minute_data or len(minute_data) == 0:
            result['skip_reason'] = '분봉 데이터 없음'
            return result

        # 09:00~09:05 거래량 합산
        volume_5min = 0
        entry_price = 0
        entry_time = None

        for candle in minute_data:
            time_str = candle['time']  # "09:01:00" 형식
            try:
                hour_min = time_str[:5]  # "09:01"
                hour = int(hour_min[:2])
                minute = int(hour_min[3:5])

                if hour == 9 and minute < check_minutes:
                    volume_5min += candle['volume']

                # 매수 시점 가격 (09:05 또는 그 직후)
                if hour == 9 and minute == check_minutes:
                    entry_price = candle['open']
                    entry_time = time_str
            except:
                continue

        # 매수 시점이 없으면 09:00 시가 사용
        if entry_price == 0 and minute_data:
            entry_price = minute_data[0]['open']
            entry_time = minute_data[0]['time']

        result['volume_5min'] = volume_5min
        result['entry_price'] = entry_price
        result['entry_time'] = entry_time

        # 거래량 충분 여부 체크
        if avg_volume_20d > 0:
            # 5분간 예상 거래량 = 일 평균 / 390분 * 5분
            expected_5min_volume = (avg_volume_20d / 390) * check_minutes
            result['volume_5min_ratio'] = volume_5min / expected_5min_volume if expected_5min_volume > 0 else 0
            result['volume_sufficient'] = result['volume_5min_ratio'] >= volume_threshold
        else:
            # 평균 거래량 정보 없으면 통과
            result['volume_sufficient'] = True
            result['volume_5min_ratio'] = 1.0

        # 갭 체크 (시초가 기준)
        if minute_data:
            opening_price = minute_data[0]['open']
            # 전일 종가는 분봉에서 알 수 없으므로, 외부에서 전달받거나 스킵
            # 여기서는 갭 체크를 스킵하고 stock_screener에서 이미 체크했다고 가정
            result['gap_ok'] = True

        # 최종 매수 여부 결정
        if not result['volume_sufficient']:
            result['skip_reason'] = f"거래량 부족 (비율: {result['volume_5min_ratio']:.2f})"
        elif not result['gap_ok']:
            result['skip_reason'] = f"갭 필터 미통과"
        else:
            result['should_buy'] = True

        return result

    def analyze_profit_loss(self, stock_code, date_str, profit_target=3.0, loss_target=-2.0, avg_volume_20d=0):
        """
        시초가 매매 익절/손절 분석 (매수 조건 체크 포함)

        Args:
            stock_code: 종목코드
            date_str: 날짜
            profit_target: 익절 목표 (%, 예: 5.0 = +5%)
            loss_target: 손절 목표 (%, 예: -3.0 = -3%)
            avg_volume_20d: 20일 평균 거래량

        Returns:
            매수 조건 + 익절/손절 분석 결과
        """
        minute_data = self.get_minute_data(stock_code, date_str, freq='1')

        if not minute_data or len(minute_data) == 0:
            return None

        # 1. 매수 조건 체크
        entry_check = self.check_entry_conditions(minute_data, avg_volume_20d)

        # 시초가 = 09:00 시가
        opening_price = minute_data[0]['open']

        if opening_price == 0:
            return None

        # 매수 기준가 = 09:05 가격 (또는 시초가)
        entry_price = entry_check['entry_price'] if entry_check['entry_price'] > 0 else opening_price

        # 익절/손절 목표가 계산 (매수 기준가 기준)
        profit_price = entry_price * (1 + profit_target / 100)
        loss_price = entry_price * (1 + loss_target / 100)

        # 2. 가상 결과 (매수했다면의 결과) - 항상 계산
        virtual_result = {
            'entry_price': entry_price,
            'entry_time': entry_check['entry_time'],
            'profit_target_percent': profit_target,
            'loss_target_percent': loss_target,
            'profit_target_price': int(profit_price),
            'loss_target_price': int(loss_price),
            'first_hit': None,
            'first_hit_time': None,
            'first_hit_price': None,
            'profit_hit_time': None,
            'loss_hit_time': None,
            'max_profit_percent': 0,
            'max_loss_percent': 0,
            'closing_price': minute_data[-1]['close'],
            'closing_percent': ((minute_data[-1]['close'] - entry_price) / entry_price * 100) if entry_price > 0 else 0
        }

        profit_hit = False
        loss_hit = False

        # 매수 시점 이후 분봉만 분석
        entry_time_str = entry_check['entry_time'] or '09:00:00'

        for candle in minute_data:
            # 매수 시점 이전은 스킵
            if candle['time'] < entry_time_str:
                continue

            high = candle['high']
            low = candle['low']
            time = candle['time']

            # 수익률 계산
            high_percent = ((high - entry_price) / entry_price * 100) if entry_price > 0 else 0
            low_percent = ((low - entry_price) / entry_price * 100) if entry_price > 0 else 0

            # 최대 수익/손실 업데이트
            if high_percent > virtual_result['max_profit_percent']:
                virtual_result['max_profit_percent'] = high_percent
            if low_percent < virtual_result['max_loss_percent']:
                virtual_result['max_loss_percent'] = low_percent

            # 익절 도달 확인
            if not profit_hit and high >= profit_price:
                profit_hit = True
                virtual_result['profit_hit_time'] = time

                if virtual_result['first_hit'] is None:
                    virtual_result['first_hit'] = 'profit'
                    virtual_result['first_hit_time'] = time
                    virtual_result['first_hit_price'] = int(profit_price)

            # 손절 도달 확인
            if not loss_hit and low <= loss_price:
                loss_hit = True
                virtual_result['loss_hit_time'] = time

                if virtual_result['first_hit'] is None:
                    virtual_result['first_hit'] = 'loss'
                    virtual_result['first_hit_time'] = time
                    virtual_result['first_hit_price'] = int(loss_price)

            if profit_hit and loss_hit:
                break

        if virtual_result['first_hit'] is None:
            virtual_result['first_hit'] = 'none'

        # 3. 최종 결과 구조
        result = {
            'opening_price': opening_price,
            'entry_check': entry_check,
            'should_buy': entry_check['should_buy'],
            'skip_reason': entry_check['skip_reason'],

            # 실제 결과 (매수 조건 통과 시)
            'actual_result': virtual_result if entry_check['should_buy'] else None,

            # 가상 결과 (매수 조건 미통과 시, 만약 샀다면)
            'virtual_result': virtual_result if not entry_check['should_buy'] else None,

            # 하위 호환성 (기존 필드 유지)
            'profit_target_percent': profit_target,
            'loss_target_percent': loss_target,
            'first_hit': virtual_result['first_hit'],
            'first_hit_time': virtual_result['first_hit_time'],
            'closing_price': virtual_result['closing_price'],
            'closing_percent': virtual_result['closing_percent'],
            'max_profit_percent': virtual_result['max_profit_percent'],
            'max_loss_percent': virtual_result['max_loss_percent']
        }

        return result

    def analyze_multi_scenario(self, stock_code, date_str, avg_volume_20d=0):
        """
        4가지 익절/손절 시나리오 동시 분석

        Returns:
            dict: 각 시나리오별 결과
        """
        import config

        scenarios = getattr(config, 'MULTI_SCENARIOS', [
            {'name': 'A', 'label': '+3%/-2%', 'profit': 3.0, 'loss': -2.0},
            {'name': 'B', 'label': '+3%/-3%', 'profit': 3.0, 'loss': -3.0},
            {'name': 'C', 'label': '+5%/-2%', 'profit': 5.0, 'loss': -2.0},
            {'name': 'D', 'label': '+5%/-3%', 'profit': 5.0, 'loss': -3.0},
        ])

        minute_data = self.get_minute_data(stock_code, date_str, freq='1')

        if not minute_data or len(minute_data) == 0:
            return None

        # 매수 조건 체크 (공통)
        entry_check = self.check_entry_conditions(minute_data, avg_volume_20d)
        opening_price = minute_data[0]['open']

        if opening_price == 0:
            return None

        entry_price = entry_check['entry_price'] if entry_check['entry_price'] > 0 else opening_price
        entry_time_str = entry_check['entry_time'] or '09:00:00'
        closing_price = minute_data[-1]['close']
        closing_percent = ((closing_price - entry_price) / entry_price * 100) if entry_price > 0 else 0

        results = {
            'entry_price': entry_price,
            'entry_time': entry_time_str,
            'opening_price': opening_price,
            'closing_price': closing_price,
            'closing_percent': round(closing_percent, 4),
            'scenarios': {}
        }

        for scenario in scenarios:
            profit_target = scenario['profit']
            loss_target = scenario['loss']
            profit_price = entry_price * (1 + profit_target / 100)
            loss_price = entry_price * (1 + loss_target / 100)

            first_hit = None
            first_hit_time = None
            max_profit = 0
            max_loss = 0

            for candle in minute_data:
                if candle['time'] < entry_time_str:
                    continue

                high = candle['high']
                low = candle['low']

                high_pct = ((high - entry_price) / entry_price * 100) if entry_price > 0 else 0
                low_pct = ((low - entry_price) / entry_price * 100) if entry_price > 0 else 0

                if high_pct > max_profit:
                    max_profit = high_pct
                if low_pct < max_loss:
                    max_loss = low_pct

                if first_hit is None and high >= profit_price:
                    first_hit = 'profit'
                    first_hit_time = candle['time']
                if first_hit is None and low <= loss_price:
                    first_hit = 'loss'
                    first_hit_time = candle['time']

            if first_hit is None:
                first_hit = 'none'

            results['scenarios'][scenario['name']] = {
                'label': scenario['label'],
                'profit_target': profit_target,
                'loss_target': loss_target,
                'profit_target_price': int(profit_price),
                'loss_target_price': int(loss_price),
                'rr': scenario.get('rr', 0),
                'result': first_hit,
                'hit_time': first_hit_time,
                'max_profit_percent': round(max_profit, 4),
                'max_loss_percent': round(max_loss, 4),
            }

        return results

    def analyze_scalp_strategy(self, stock_code, minute_data):
        """
        단타 전략 분석 (09:00~09:10 집중)

        1단계: 09:00~09:03 관망 (방향 확인)
        2단계: 09:03~09:10 진입 판단
        3단계: 09:30까지 청산

        Returns:
            dict: 단타 전략 분석 결과
        """
        import config

        scalp = getattr(config, 'SCALP_STRATEGY', {
            'observation_end': '09:03',
            'entry_window_start': '09:03',
            'entry_window_end': '09:10',
            'exit_deadline': '09:30',
            'profit_target': 2.0,
            'loss_target': -1.0,
            'min_momentum': 0.5,
        })

        if not minute_data or len(minute_data) == 0:
            return {'should_enter': False, 'reason': '분봉 데이터 없음'}

        obs_end = scalp.get('observation_end', '09:03')
        entry_start = scalp.get('entry_window_start', '09:03')
        entry_end = scalp.get('entry_window_end', '09:10')
        exit_deadline = scalp.get('exit_deadline', '09:30')
        profit_target = scalp.get('profit_target', 2.0)
        loss_target = scalp.get('loss_target', -1.0)
        min_momentum = scalp.get('min_momentum', 0.5)

        # 1단계: 09:00~09:03 관망 (방향 확인)
        early_candles = [c for c in minute_data if '09:00' <= c['time'][:5] < obs_end]

        if not early_candles:
            return {'should_enter': False, 'reason': '초반 데이터 없음'}

        first_price = early_candles[0]['open']
        last_price = early_candles[-1]['close']
        momentum = ((last_price - first_price) / first_price) * 100 if first_price > 0 else 0

        if momentum < min_momentum:
            direction = 'down' if momentum < 0 else 'flat'
        else:
            direction = 'up'

        # 2단계: 진입 판단
        entry_candles = [c for c in minute_data if entry_start <= c['time'][:5] <= entry_end]

        should_enter = direction == 'up' and momentum >= min_momentum
        entry_reason = ''

        if should_enter:
            entry_reason = f"상승 모멘텀 확인 (+{momentum:.2f}%)"
        elif direction == 'down':
            entry_reason = f"하락 모멘텀 ({momentum:.2f}%) - 진입 보류"
        else:
            entry_reason = f"모멘텀 부족 (+{momentum:.2f}%) - 관망"

        result = {
            'direction': direction,
            'momentum_3min': round(momentum, 4),
            'observation_price_start': first_price,
            'observation_price_end': last_price,
            'should_enter': should_enter,
            'entry_reason': entry_reason,
            'exit_result': None,
            'exit_time': None,
            'exit_percent': None,
            'entry_price': None,
        }

        # 3단계: 매수했다면 결과 (09:03~09:30)
        if entry_candles:
            entry_price = entry_candles[0]['open']
            result['entry_price'] = entry_price

            exit_candles = [c for c in minute_data if entry_start <= c['time'][:5] <= exit_deadline]

            for candle in exit_candles:
                if entry_price == 0:
                    break

                high_pct = ((candle['high'] - entry_price) / entry_price) * 100
                low_pct = ((candle['low'] - entry_price) / entry_price) * 100

                if high_pct >= profit_target:
                    result['exit_result'] = 'profit'
                    result['exit_time'] = candle['time']
                    result['exit_percent'] = round(profit_target, 2)
                    break

                if low_pct <= loss_target:
                    result['exit_result'] = 'loss'
                    result['exit_time'] = candle['time']
                    result['exit_percent'] = round(loss_target, 2)
                    break

            # 09:30까지 미도달 시 종료 가격
            if result['exit_result'] is None and exit_candles:
                deadline_candles = [c for c in exit_candles if c['time'][:5] >= exit_deadline[:5]]
                if deadline_candles:
                    final_price = deadline_candles[0]['close']
                else:
                    final_price = exit_candles[-1]['close']

                final_pct = ((final_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0
                result['exit_result'] = 'timeout'
                result['exit_time'] = exit_deadline + ':00'
                result['exit_percent'] = round(final_pct, 2)

        return result

    def analyze_swing_strategy(self, stock_code, minute_data):
        """
        스윙 전략 분석 (종가 기준 판단)

        Returns:
            dict: 스윙 전략 분석 결과
        """
        import config

        swing = getattr(config, 'SWING_STRATEGY', {
            'strong_profit': 3.0,
            'mild_profit': 0.0,
            'mild_loss': -2.0,
            'stop_loss': -3.0,
        })

        if not minute_data or len(minute_data) == 0:
            return None

        opening_price = minute_data[0]['open']
        closing_price = minute_data[-1]['close']

        if opening_price == 0:
            return None

        closing_percent = ((closing_price - opening_price) / opening_price) * 100

        # 종가 기준 판단
        if closing_percent >= swing['strong_profit']:
            result_label = '강한 수익'
            action = '홀딩 또는 추가 매수 검토'
            signal = 'strong_buy'
        elif closing_percent >= swing['mild_profit']:
            result_label = '소폭 수익'
            action = '다음날 추이 관망'
            signal = 'hold'
        elif closing_percent >= swing['mild_loss']:
            result_label = '소폭 손실'
            action = '다음날 반등 확인 후 판단'
            signal = 'watch'
        elif closing_percent >= swing['stop_loss']:
            result_label = '손실 경고'
            action = '반등 없으면 매도 검토'
            signal = 'warning'
        else:
            result_label = '손절 라인'
            action = '다음날 장 시작 시 매도 검토'
            signal = 'sell'

        # 장중 고가/저가 계산
        day_high = max(c['high'] for c in minute_data)
        day_low = min(c['low'] for c in minute_data)
        day_high_pct = ((day_high - opening_price) / opening_price) * 100 if opening_price > 0 else 0
        day_low_pct = ((day_low - opening_price) / opening_price) * 100 if opening_price > 0 else 0

        return {
            'opening_price': opening_price,
            'closing_price': closing_price,
            'closing_percent': round(closing_percent, 4),
            'day_high': day_high,
            'day_low': day_low,
            'day_high_percent': round(day_high_pct, 4),
            'day_low_percent': round(day_low_pct, 4),
            'result_label': result_label,
            'action': action,
            'signal': signal,
        }

    def collect_intraday_data(self, candidates, date_str=None, profit_target=3.0, loss_target=-2.0):
        """
        선정 종목들의 당일 거래 데이터 수집 + 익절/손절 분석
        멀티 시나리오 + 단타 + 스윙 전략 포함

        Args:
            candidates: 선정 종목 리스트 (morning_candidates.json의 candidates)
            date_str: 날짜 (YYYYMMDD), None이면 오늘 (네이버는 당일만 조회 가능)
            profit_target: 익절 목표 (%, 기본 +3%)
            loss_target: 손절 목표 (%, 기본 -2%)
        """
        if date_str is None:
            date_str = format_kst_time(format_str='%Y%m%d')

        print(f"\n📈 시초가 매매 분석 시작 (KST) - {date_str}")
        print(f"   기본 익절 목표: +{profit_target}% / 손절 목표: {loss_target}%")
        print(f"   + 4가지 시나리오 비교 / 단타 전략 / 스윙 전략")

        intraday_data = {}

        for candidate in candidates:
            stock_code = candidate.get('code', '')
            stock_name = candidate.get('name', '')
            avg_volume_20d = candidate.get('avg_volume_20d', 0)

            print(f"\n🔍 {stock_name} ({stock_code})")

            # 기본 익절/손절 분석 (기존 호환)
            pl_analysis = self.analyze_profit_loss(stock_code, date_str, profit_target, loss_target, avg_volume_20d)

            # 분봉 데이터 (이미 수집됨, 재사용을 위해 다시 수집)
            minute_data = self.get_minute_data(stock_code, date_str, freq='1')

            # 4가지 시나리오 분석
            multi_scenario = self.analyze_multi_scenario(stock_code, date_str, avg_volume_20d)

            # 단타 전략 분석
            scalp_result = self.analyze_scalp_strategy(stock_code, minute_data)

            # 스윙 전략 분석
            swing_result = self.analyze_swing_strategy(stock_code, minute_data)

            intraday_data[stock_code] = {
                'code': stock_code,
                'name': stock_name,
                'date': date_str,
                'profit_loss_analysis': pl_analysis,
                'multi_scenario': multi_scenario,
                'scalp_strategy': scalp_result,
                'swing_strategy': swing_result,
                'selection_score': candidate.get('total_score', 0),
                'selection_reason': candidate.get('selection_reason', '-')
            }

        return intraday_data

    def save_intraday_data(self, intraday_data, date_str=None):
        """장중 데이터를 JSON 파일로 저장"""
        if date_str is None:
            date_str = format_kst_time(format_str='%Y%m%d')

        os.makedirs('data/intraday', exist_ok=True)
        output_path = f'data/intraday/intraday_{date_str}.json'

        result = {
            'generated_at': format_kst_time(format_str='%Y-%m-%dT%H:%M:%S'),
            'date': date_str,
            'count': len(intraday_data),
            'stocks': intraday_data
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"\n✅ 장중 데이터 저장 완료: {output_path}")
        return output_path


    def print_multi_scenario_report(self, intraday_data):
        """4가지 시나리오 비교 리포트 출력"""
        print("\n" + "=" * 70)
        print("📊 4가지 시나리오 비교 분석")
        print("=" * 70)

        # 시나리오별 통계
        scenario_stats = {}

        for code, data in intraday_data.items():
            ms = data.get('multi_scenario')
            if not ms or not ms.get('scenarios'):
                continue

            print(f"\n{data['name']} ({code}) - 진입가: {ms['entry_price']:,}원")
            print(f"  {'시나리오':8s} | {'익절가':>8s} | {'손절가':>8s} | {'R:R':>5s} | {'결과':6s} | 시간")
            print(f"  {'-'*60}")

            for name, sc in ms['scenarios'].items():
                result_icon = '✅익절' if sc['result'] == 'profit' else '❌손절' if sc['result'] == 'loss' else '⚪미도달'
                hit_time = sc['hit_time'] if sc['hit_time'] else '-'
                print(f"  {sc['label']:8s} | {sc['profit_target_price']:>7,}원 | {sc['loss_target_price']:>7,}원 | {sc['rr']:>5.2f} | {result_icon} | {hit_time}")

                # 통계 집계
                if name not in scenario_stats:
                    scenario_stats[name] = {'label': sc['label'], 'profit': 0, 'loss': 0, 'none': 0, 'total': 0}
                scenario_stats[name]['total'] += 1
                if sc['result'] == 'profit':
                    scenario_stats[name]['profit'] += 1
                elif sc['result'] == 'loss':
                    scenario_stats[name]['loss'] += 1
                else:
                    scenario_stats[name]['none'] += 1

        # 전체 시나리오 비교
        if scenario_stats:
            print(f"\n{'=' * 70}")
            print(f"📈 시나리오별 통계 요약")
            print(f"{'=' * 70}")
            print(f"  {'시나리오':8s} | {'종목수':>5s} | {'승률':>6s} | {'익절':>4s} | {'손절':>4s} | {'미도달':>5s}")
            print(f"  {'-'*50}")

            for name in sorted(scenario_stats.keys()):
                st = scenario_stats[name]
                win_rate = (st['profit'] / st['total'] * 100) if st['total'] > 0 else 0
                print(f"  {st['label']:8s} | {st['total']:>4d}개 | {win_rate:>5.1f}% | {st['profit']:>3d}개 | {st['loss']:>3d}개 | {st['none']:>4d}개")

    def print_scalp_report(self, intraday_data):
        """단타 전략 리포트 출력"""
        print(f"\n{'=' * 70}")
        print(f"⚡ 단타 전략 분석 (09:00~09:10 집중)")
        print(f"{'=' * 70}")

        for code, data in intraday_data.items():
            scalp = data.get('scalp_strategy')
            if not scalp:
                continue

            name = data['name']
            arrow = '↑' if scalp['direction'] == 'up' else '↓' if scalp['direction'] == 'down' else '→'

            print(f"\n{name} ({code})")
            print(f"  [관망] 09:00~09:03: {scalp['observation_price_start']:,} -> {scalp['observation_price_end']:,} ({scalp['momentum_3min']:+.2f}%) {arrow}")
            print(f"  [판단] {scalp['entry_reason']}")

            if scalp['entry_price']:
                print(f"  [진입] {scalp['entry_price']:,}원")

            if scalp['exit_result']:
                result_icon = '✅' if scalp['exit_result'] == 'profit' else '❌' if scalp['exit_result'] == 'loss' else '⏰'
                print(f"  [청산] {result_icon} {scalp['exit_result']} ({scalp['exit_percent']:+.2f}%) - {scalp['exit_time']}")

    def print_swing_report(self, intraday_data):
        """스윙 전략 리포트 출력"""
        print(f"\n{'=' * 70}")
        print(f"📈 스윙 전략 분석 (종가 기준 판단)")
        print(f"{'=' * 70}")

        for code, data in intraday_data.items():
            swing = data.get('swing_strategy')
            if not swing:
                continue

            name = data['name']
            signal_icon = {'strong_buy': '🟢', 'hold': '🟡', 'watch': '🟠', 'warning': '🔴', 'sell': '⛔'}.get(swing['signal'], '⚪')

            print(f"\n{name} ({code})")
            print(f"  시초가: {swing['opening_price']:,}원 -> 종가: {swing['closing_price']:,}원 ({swing['closing_percent']:+.2f}%)")
            print(f"  장중 고가: {swing['day_high']:,}원 ({swing['day_high_percent']:+.2f}%)")
            print(f"  장중 저가: {swing['day_low']:,}원 ({swing['day_low_percent']:+.2f}%)")
            print(f"  {signal_icon} [{swing['result_label']}] {swing['action']}")


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

        # 당일 데이터 수집 (기본 익절/손절 + 멀티 시나리오 + 단타 + 스윙)
        import config
        profit = getattr(config, 'PROFIT_TARGET', 5.0)
        loss = getattr(config, 'LOSS_TARGET', -3.0)
        intraday_data = collector.collect_intraday_data(candidates, profit_target=profit, loss_target=loss)

        # 저장
        collector.save_intraday_data(intraday_data)

        # 기본 익절/손절 결과 출력
        print("\n" + "=" * 70)
        print(f"📊 기본 시초가 매매 결과 (익절 +{profit}% / 손절 {loss}%)")
        print("=" * 70)

        profit_count = 0
        loss_count = 0
        none_count = 0

        for code, stock_data in intraday_data.items():
            pl = stock_data.get('profit_loss_analysis')
            if pl:
                print(f"\n{stock_data['name']} ({code})")
                print(f"  시초가: {pl['opening_price']:,}원")
                print(f"  종가: {pl['closing_price']:,}원 ({pl['closing_percent']:+.2f}%)")

                first_hit = pl['first_hit']
                if first_hit == 'profit':
                    print(f"  ✅ 익절 도달 ({pl['first_hit_time']})")
                    profit_count += 1
                elif first_hit == 'loss':
                    print(f"  ❌ 손절 도달 ({pl['first_hit_time']})")
                    loss_count += 1
                else:
                    print(f"  ⚪ 미도달")
                    none_count += 1

        total = len(intraday_data)
        if total > 0:
            print(f"\n기본 통계: 총 {total}개 / 익절 {profit_count} / 손절 {loss_count} / 미도달 {none_count} / 승률 {profit_count/total*100:.1f}%")

        # 멀티 시나리오 비교 리포트
        collector.print_multi_scenario_report(intraday_data)

        # 단타 전략 리포트
        collector.print_scalp_report(intraday_data)

        # 스윙 전략 리포트
        collector.print_swing_report(intraday_data)

    except FileNotFoundError:
        print("morning_candidates.json 파일을 찾을 수 없습니다.")
    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()
