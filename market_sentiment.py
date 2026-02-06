"""
시장 분위기 판단 모듈
VIX 지수, 원달러 환율, 코스피200 선물 데이터를 수집하여
공격/중립/방어 모드를 표시 (액션 없음, 정보 제공만)
"""

import requests
from bs4 import BeautifulSoup
import re
from utils import format_kst_time, get_headers


class MarketSentiment:
    def __init__(self):
        self.headers = get_headers()  # 랜덤 User-Agent 사용
        self.session = requests.Session()

    def get_vix(self):
        """VIX 지수 수집 (Yahoo Finance API - 네이버에서 VIX 종목 삭제됨)"""
        try:
            url = 'https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?range=2d&interval=1d'
            response = self.session.get(url, headers=self.headers, timeout=10)
            data = response.json()

            result = data.get('chart', {}).get('result', [{}])[0]
            meta = result.get('meta', {})

            vix = meta.get('regularMarketPrice')
            prev_close = meta.get('chartPreviousClose') or meta.get('previousClose')

            change = 0
            change_direction = 'unknown'
            if vix is not None and prev_close is not None:
                change = round(vix - prev_close, 2)
                change_direction = 'up' if change >= 0 else 'down'

            return {
                'value': round(vix, 2) if vix else None,
                'change': change,
                'direction': change_direction,
                'status': self._vix_status(vix) if vix else 'unknown'
            }

        except Exception as e:
            print(f"  ⚠️  VIX 수집 실패: {e}")
            return {'value': None, 'change': 0, 'direction': 'unknown', 'status': 'unknown'}

    def _vix_status(self, vix):
        """VIX 상태 판단"""
        if vix is None:
            return 'unknown'
        if vix < 15:
            return '매우 안정'
        elif vix < 20:
            return '안정'
        elif vix < 25:
            return '경계'
        elif vix < 30:
            return '불안'
        else:
            return '공포'

    def get_usd_krw(self):
        """원달러 환율 수집 (네이버 마켓인덱스)"""
        try:
            url = 'https://finance.naver.com/marketindex/'
            response = self.session.get(url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')

            # 환율 값
            exchange_area = soup.select_one('#exchangeList li.on')
            if not exchange_area:
                exchange_area = soup.select_one('#exchangeList li')

            if exchange_area:
                value_el = exchange_area.select_one('.value')
                change_el = exchange_area.select_one('.change')

                value = float(value_el.text.strip().replace(',', '')) if value_el else None
                change = float(change_el.text.strip().replace(',', '')) if change_el else 0

                # 상승/하락 판단
                head_el = exchange_area.select_one('.head_info')
                direction = 'up'
                if head_el:
                    class_list = head_el.get('class', [])
                    if 'minus' in ' '.join(class_list):
                        direction = 'down'
                        change = -abs(change)

                return {
                    'value': value,
                    'change': change,
                    'direction': direction,
                    'status': self._usd_krw_status(value, change) if value else 'unknown'
                }

            return {'value': None, 'change': 0, 'direction': 'unknown', 'status': 'unknown'}

        except Exception as e:
            print(f"  ⚠️  환율 수집 실패: {e}")
            return {'value': None, 'change': 0, 'direction': 'unknown', 'status': 'unknown'}

    def _usd_krw_status(self, value, change):
        """환율 상태 판단"""
        if value is None:
            return 'unknown'
        # 환율 상승 = 원화 약세 = 증시 부정적
        if change > 10:
            return '급등 (부정적)'
        elif change > 5:
            return '상승 (주의)'
        elif change > 0:
            return '소폭 상승'
        elif change > -5:
            return '소폭 하락 (긍정적)'
        else:
            return '하락 (긍정적)'

    def get_kospi200_futures(self):
        """코스피200 선물 수집 (네이버 국내지수)"""
        try:
            url = 'https://finance.naver.com/sise/sise_index.naver?code=KPI200'
            response = self.session.get(url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')

            # 현재값
            now_value = soup.select_one('#now_value')
            change_value = soup.select_one('#change_value_and_rate')

            value = None
            change_pct = 0

            if now_value:
                try:
                    value = float(now_value.text.strip().replace(',', ''))
                except (ValueError, AttributeError):
                    pass

            if change_value:
                # "1.23 +0.45%" 형태에서 퍼센트 추출
                text = change_value.text.strip()
                pct_match = re.search(r'([+-]?\d+\.?\d*)%', text)
                if pct_match:
                    change_pct = float(pct_match.group(1))
                else:
                    # 부호와 숫자 추출
                    nums = re.findall(r'[\d.]+', text)
                    if len(nums) >= 2:
                        change_pct = float(nums[1])
                    elif len(nums) == 1:
                        change_pct = float(nums[0])

            # 상승/하락 판단
            direction_el = soup.select_one('.no_exday img')
            if direction_el:
                alt_text = direction_el.get('alt', '')
                if '하락' in alt_text:
                    change_pct = -abs(change_pct)

            return {
                'value': value,
                'change_pct': change_pct,
                'direction': 'up' if change_pct >= 0 else 'down',
                'status': self._futures_status(change_pct)
            }

        except Exception as e:
            print(f"  ⚠️  코스피200 수집 실패: {e}")
            return {'value': None, 'change_pct': 0, 'direction': 'unknown', 'status': 'unknown'}

    def _futures_status(self, change_pct):
        """선물 상태 판단"""
        if change_pct >= 1.5:
            return '강세'
        elif change_pct >= 0.5:
            return '양호'
        elif change_pct >= -0.5:
            return '보합'
        elif change_pct >= -1.5:
            return '약세'
        else:
            return '급락'

    def _parse_naver_world_value(self, soup, selector):
        """네이버 해외지수 숫자 파싱 (span 분리 구조 대응)"""
        el = soup.select_one(selector)
        if not el:
            return None
        em = el.find('em')
        if em:
            raw = em.get_text().replace(' ', '').replace('\n', '').replace('\t', '')
            clean = re.sub(r'[^0-9.,]', '', raw)
            if clean:
                return float(clean.replace(',', ''))
        return None

    def get_us_market(self):
        """미국 증시 수집 (네이버 해외지수 - span 분리 구조 대응)"""
        result = {}
        indices = {
            'S&P500': 'SPI@SPX',
            'NASDAQ': 'NAS@IXIC',
            'DOW': 'DJI@DJI',
        }

        for name, symbol in indices.items():
            try:
                url = f'https://finance.naver.com/world/sise.naver?symbol={symbol}'
                response = self.session.get(url, headers=self.headers, timeout=10)
                soup = BeautifulSoup(response.text, 'html.parser')

                # 현재가 파싱 (.no_today > em > span들의 텍스트 합침)
                value = self._parse_naver_world_value(soup, '.no_today')

                # 변동값/퍼센트 파싱 (.no_exday > em들)
                change = 0
                change_pct = 0
                direction = 'unknown'

                no_exday = soup.select_one('.no_exday')
                if no_exday:
                    ems = no_exday.find_all('em')
                    if len(ems) >= 1:
                        raw = ems[0].get_text().replace(' ', '').replace('\n', '').replace('\t', '')
                        clean = re.sub(r'[^0-9.,]', '', raw)
                        if clean:
                            change = float(clean.replace(',', ''))
                        cls = ems[0].get('class', [])
                        if 'no_down' in cls:
                            direction = 'down'
                            change = -abs(change)
                        elif 'no_up' in cls:
                            direction = 'up'

                    if len(ems) >= 2:
                        raw = ems[1].get_text().replace(' ', '').replace('\n', '').replace('\t', '')
                        pct_match = re.search(r'([0-9.]+)%', raw)
                        if pct_match:
                            change_pct = float(pct_match.group(1))
                            if direction == 'down':
                                change_pct = -change_pct

                result[name] = {
                    'value': value,
                    'change': round(change, 2),
                    'change_pct': round(change_pct, 2),
                    'direction': direction,
                }

            except Exception as e:
                result[name] = {'value': None, 'change': 0, 'change_pct': 0, 'direction': 'unknown'}

        return result

    def determine_market_mode(self):
        """
        시장 모드 결정 (표시만, 액션 없음)

        Returns:
            dict: 시장 데이터 + 모드 판단 결과
        """
        print("\n" + "=" * 60)
        print("📊 글로벌 시장 & 장 분위기 체크")
        print("=" * 60)

        # 데이터 수집
        vix = self.get_vix()
        usd_krw = self.get_usd_krw()
        kospi200 = self.get_kospi200_futures()
        us_market = self.get_us_market()

        # 점수 계산 (표시용)
        score = 0

        # VIX 기반 점수
        if vix['value'] is not None:
            if vix['value'] < 15:
                score += 2
            elif vix['value'] < 20:
                score += 1
            elif vix['value'] < 25:
                score += 0
            elif vix['value'] < 30:
                score -= 1
            else:
                score -= 2

        # 환율 기반 점수
        if usd_krw['change'] is not None:
            if usd_krw['change'] < -5:
                score += 1
            elif usd_krw['change'] > 10:
                score -= 1

        # 선물 기반 점수
        if kospi200['change_pct'] is not None:
            if kospi200['change_pct'] >= 1.0:
                score += 2
            elif kospi200['change_pct'] >= 0.3:
                score += 1
            elif kospi200['change_pct'] <= -1.0:
                score -= 2
            elif kospi200['change_pct'] <= -0.3:
                score -= 1

        # 미국 증시 기반 점수
        for name, data in us_market.items():
            pct = data.get('change_pct') or 0
            if pct >= 1.0:
                score += 1
            elif pct <= -1.0:
                score -= 1

        # 모드 결정
        if score >= 3:
            mode = '공격'
            mode_desc = '시장 강세 - 적극적 매매 가능'
        elif score <= -3:
            mode = '방어'
            mode_desc = '시장 약세 - 신중한 접근 필요'
        else:
            mode = '중립'
            mode_desc = '시장 혼조 - 선별적 매매'

        # 출력
        print(f"\n■ 미국 증시")
        for name, data in us_market.items():
            arrow = '▲' if data['direction'] == 'up' else '▼' if data['direction'] == 'down' else '-'
            val_str = f"{data['value']:,.2f}" if data['value'] else 'N/A'
            pct_str = f"{data['change_pct']:+.2f}%" if data['change_pct'] else ''
            print(f"  - {name:8s}: {val_str} {arrow} {pct_str}")

        print(f"\n■ 공포 & 환율")
        vix_val = f"{vix['value']:.2f}" if vix['value'] else 'N/A'
        vix_change = f" ({vix['change']:+.2f})" if vix['change'] else ''
        print(f"  - VIX 지수  : {vix_val}{vix_change} [{vix['status']}]")

        usd_val = f"{usd_krw['value']:,.2f}원" if usd_krw['value'] else 'N/A'
        usd_change = f" ({usd_krw['change']:+.2f})" if usd_krw['change'] else ''
        print(f"  - 원/달러   : {usd_val}{usd_change} [{usd_krw['status']}]")

        print(f"\n■ 국내")
        k200_val = f"{kospi200['value']:,.2f}" if kospi200['value'] else 'N/A'
        k200_pct = f" ({kospi200['change_pct']:+.2f}%)" if kospi200['change_pct'] else ''
        print(f"  - 코스피200 : {k200_val}{k200_pct} [{kospi200['status']}]")

        print(f"\n{'=' * 60}")
        print(f"🎯 오늘 시장 모드: [{mode}] (점수: {score:+d})")
        print(f"   {mode_desc}")
        print(f"{'=' * 60}")

        return {
            'vix': vix,
            'usd_krw': usd_krw,
            'kospi200_futures': kospi200,
            'us_market': us_market,
            'score': score,
            'mode': mode,
            'mode_desc': mode_desc,
            'generated_at': format_kst_time(),
        }


if __name__ == '__main__':
    sentiment = MarketSentiment()
    result = sentiment.determine_market_mode()
