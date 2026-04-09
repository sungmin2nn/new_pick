"""
네이버 금융 시장 데이터 수집기
pykrx 대체용 - 종목 리스트, OHLCV, 시가총액 등

pykrx 함수 대체:
- get_market_ticker_list() -> get_ticker_list()
- get_market_ticker_name() -> get_ticker_name()
- get_market_ohlcv_by_ticker() -> get_ohlcv_by_ticker()
- get_market_cap_by_ticker() -> get_market_cap_by_ticker()
- get_market_ohlcv_by_date() -> get_ohlcv()
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
from datetime import datetime, timedelta


class NaverMarketData:
    """네이버 금융 시장 데이터 수집"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        # 종목명 캐시
        self._ticker_name_cache = {}

    def get_ticker_list(self, market='KOSPI'):
        """종목 코드 리스트 조회

        Args:
            market: 'KOSPI' 또는 'KOSDAQ'

        Returns:
            list: 종목 코드 리스트
        """
        sosok = '0' if market.upper() == 'KOSPI' else '1'
        tickers = []
        page = 1
        max_pages = 50  # 최대 50페이지

        while page <= max_pages:
            url = f'https://finance.naver.com/sise/sise_market_sum.naver?sosok={sosok}&page={page}'

            try:
                response = self.session.get(url, timeout=10)
                response.encoding = 'euc-kr'

                if response.status_code != 200:
                    break

                soup = BeautifulSoup(response.text, 'html.parser')
                table = soup.find('table', class_='type_2')

                if not table:
                    break

                rows = table.find_all('tr')
                found = 0

                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) < 2:
                        continue

                    link = cols[1].find('a')
                    if link and 'href' in link.attrs:
                        match = re.search(r'code=(\d{6})', link['href'])
                        if match:
                            code = match.group(1)
                            name = link.get_text(strip=True)
                            tickers.append(code)
                            self._ticker_name_cache[code] = name
                            found += 1

                if found == 0:
                    break

                page += 1
                time.sleep(0.2)

            except Exception as e:
                break

        return tickers

    def get_ticker_name(self, code):
        """종목명 조회

        Args:
            code: 종목코드 (6자리)

        Returns:
            str: 종목명
        """
        # 캐시 확인
        if code in self._ticker_name_cache:
            return self._ticker_name_cache[code]

        # 네이버에서 조회
        url = f'https://finance.naver.com/item/main.naver?code={code}'

        try:
            response = self.session.get(url, timeout=10)
            response.encoding = 'euc-kr'

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                title = soup.find('title')
                if title:
                    # "삼성전자 : 네이버 금융" 형식에서 종목명 추출
                    name = title.get_text().split(':')[0].strip()
                    self._ticker_name_cache[code] = name
                    return name

        except:
            pass

        return code

    def get_ohlcv(self, code, start_date=None, end_date=None):
        """종목 OHLCV 조회

        Args:
            code: 종목코드
            start_date: 시작일 (YYYYMMDD)
            end_date: 종료일 (YYYYMMDD)

        Returns:
            DataFrame: OHLCV 데이터 (index=날짜)
        """
        url = f'https://finance.naver.com/item/sise_day.naver?code={code}'
        all_data = []
        page = 1
        max_pages = 20

        # 날짜 파싱
        if end_date:
            end_dt = datetime.strptime(end_date, '%Y%m%d')
        else:
            end_dt = datetime.now()

        if start_date:
            start_dt = datetime.strptime(start_date, '%Y%m%d')
        else:
            start_dt = end_dt - timedelta(days=30)

        while page <= max_pages:
            try:
                response = self.session.get(f'{url}&page={page}', timeout=10)
                response.encoding = 'euc-kr'

                if response.status_code != 200:
                    break

                soup = BeautifulSoup(response.text, 'html.parser')
                table = soup.find('table', class_='type2')

                if not table:
                    break

                rows = table.find_all('tr')
                found = 0

                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) < 7:
                        continue

                    date_text = cols[0].get_text(strip=True)
                    if not date_text:
                        continue

                    try:
                        # 날짜 파싱 (2024.01.02 형식)
                        dt = datetime.strptime(date_text, '%Y.%m.%d')

                        # 범위 체크
                        if dt < start_dt:
                            return self._to_dataframe(all_data)
                        if dt > end_dt:
                            continue

                        close = int(cols[1].get_text(strip=True).replace(',', ''))
                        open_p = int(cols[3].get_text(strip=True).replace(',', ''))
                        high = int(cols[4].get_text(strip=True).replace(',', ''))
                        low = int(cols[5].get_text(strip=True).replace(',', ''))
                        volume = int(cols[6].get_text(strip=True).replace(',', ''))

                        all_data.append({
                            '날짜': dt,
                            '시가': open_p,
                            '고가': high,
                            '저가': low,
                            '종가': close,
                            '거래량': volume
                        })
                        found += 1

                    except (ValueError, IndexError):
                        continue

                if found == 0:
                    break

                page += 1
                time.sleep(0.2)

            except Exception as e:
                break

        return self._to_dataframe(all_data)

    def _to_dataframe(self, data):
        """데이터를 DataFrame으로 변환"""
        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)
        df = df.set_index('날짜')
        df = df.sort_index()
        return df

    def get_ohlcv_by_ticker(self, date, market='KOSPI'):
        """전체 종목 OHLCV 조회 (시가총액 페이지에서)

        Args:
            date: 날짜 (YYYYMMDD) - 현재는 당일만 지원
            market: 'KOSPI' 또는 'KOSDAQ'

        Returns:
            DataFrame: 종목별 OHLCV (index=종목코드)
        """
        sosok = '0' if market.upper() == 'KOSPI' else '1'
        all_data = []
        page = 1
        max_pages = 50

        while page <= max_pages:
            url = f'https://finance.naver.com/sise/sise_market_sum.naver?sosok={sosok}&page={page}'

            try:
                response = self.session.get(url, timeout=10)
                response.encoding = 'euc-kr'

                if response.status_code != 200:
                    break

                soup = BeautifulSoup(response.text, 'html.parser')
                table = soup.find('table', class_='type_2')

                if not table:
                    break

                rows = table.find_all('tr')
                found = 0

                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) < 10:
                        continue

                    link = cols[1].find('a')
                    if not link:
                        continue

                    match = re.search(r'code=(\d{6})', link.get('href', ''))
                    if not match:
                        continue

                    code = match.group(1)
                    name = link.get_text(strip=True)

                    try:
                        price = int(cols[2].get_text(strip=True).replace(',', ''))
                        change_text = cols[3].get_text(strip=True).replace(',', '')

                        # 등락률
                        change_pct_text = cols[4].get_text(strip=True).replace('%', '').replace('+', '')
                        change_pct = float(change_pct_text) if change_pct_text else 0

                        # 거래량
                        volume = int(cols[5].get_text(strip=True).replace(',', '') or 0)

                        # 거래대금 (백만원 -> 원)
                        trading_val_text = cols[6].get_text(strip=True).replace(',', '')
                        trading_value = int(trading_val_text) * 1_000_000 if trading_val_text else 0

                        all_data.append({
                            '종목코드': code,
                            '종목명': name,
                            '종가': price,
                            '등락률': change_pct,
                            '거래량': volume,
                            '거래대금': trading_value
                        })
                        self._ticker_name_cache[code] = name
                        found += 1

                    except (ValueError, IndexError):
                        continue

                if found == 0:
                    break

                page += 1
                time.sleep(0.2)

            except Exception as e:
                break

        if not all_data:
            return pd.DataFrame()

        df = pd.DataFrame(all_data)
        df = df.set_index('종목코드')
        return df

    def get_market_cap_by_ticker(self, date, market='KOSPI'):
        """전체 종목 시가총액 조회

        Args:
            date: 날짜 (YYYYMMDD) - 현재는 당일만 지원
            market: 'KOSPI' 또는 'KOSDAQ'

        Returns:
            DataFrame: 종목별 시가총액 (index=종목코드)
        """
        sosok = '0' if market.upper() == 'KOSPI' else '1'
        all_data = []
        page = 1
        max_pages = 50

        while page <= max_pages:
            # 시가총액 순위 페이지
            url = f'https://finance.naver.com/sise/sise_market_sum.naver?sosok={sosok}&page={page}'

            try:
                response = self.session.get(url, timeout=10)
                response.encoding = 'euc-kr'

                if response.status_code != 200:
                    break

                soup = BeautifulSoup(response.text, 'html.parser')
                table = soup.find('table', class_='type_2')

                if not table:
                    break

                rows = table.find_all('tr')
                found = 0

                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) < 10:
                        continue

                    link = cols[1].find('a')
                    if not link:
                        continue

                    match = re.search(r'code=(\d{6})', link.get('href', ''))
                    if not match:
                        continue

                    code = match.group(1)
                    name = link.get_text(strip=True)

                    try:
                        price = int(cols[2].get_text(strip=True).replace(',', ''))

                        # 시가총액 (억원)
                        cap_text = cols[6].get_text(strip=True).replace(',', '')
                        # 시가총액이 없으면 다음 컬럼 확인
                        if not cap_text.isdigit():
                            cap_text = cols[7].get_text(strip=True).replace(',', '')

                        market_cap = int(cap_text) * 100_000_000 if cap_text.isdigit() else 0

                        # 거래량
                        volume = int(cols[5].get_text(strip=True).replace(',', '') or 0)

                        # 거래대금
                        trading_text = cols[6].get_text(strip=True).replace(',', '')
                        trading_value = int(trading_text) * 1_000_000 if trading_text.isdigit() else 0

                        all_data.append({
                            '종목코드': code,
                            '종목명': name,
                            '종가': price,
                            '시가총액': market_cap,
                            '거래량': volume,
                            '거래대금': trading_value
                        })
                        self._ticker_name_cache[code] = name
                        found += 1

                    except (ValueError, IndexError):
                        continue

                if found == 0:
                    break

                page += 1
                time.sleep(0.2)

            except Exception as e:
                break

        if not all_data:
            return pd.DataFrame()

        df = pd.DataFrame(all_data)
        df = df.set_index('종목코드')
        return df

    def get_stock_info(self, code):
        """종목 상세 정보 (시가총액, 거래량 등)

        Args:
            code: 종목코드

        Returns:
            dict: 종목 정보
        """
        url = f'https://finance.naver.com/item/main.naver?code={code}'

        try:
            response = self.session.get(url, timeout=10)
            response.encoding = 'euc-kr'

            if response.status_code != 200:
                return None

            soup = BeautifulSoup(response.text, 'html.parser')

            info = {'code': code}

            # 종목명
            title = soup.find('title')
            if title:
                info['name'] = title.get_text().split(':')[0].strip()

            # 현재가
            price_tag = soup.find('p', class_='no_today')
            if price_tag:
                price_span = price_tag.find('span', class_='blind')
                if price_span:
                    info['price'] = int(price_span.get_text().replace(',', ''))

            # 시가총액, 거래량 등 테이블에서 추출
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    text = row.get_text()
                    if '시가총액' in text:
                        # 시가총액 추출
                        tds = row.find_all('td')
                        if tds:
                            cap_text = tds[0].get_text(strip=True)
                            # "1,234조" 또는 "1,234억" 파싱
                            cap_text = cap_text.replace(',', '').replace('조', '').replace('억', '')
                            if '조' in row.get_text():
                                info['market_cap'] = int(float(cap_text) * 1_000_000_000_000)
                            else:
                                info['market_cap'] = int(float(cap_text) * 100_000_000)

            return info

        except Exception as e:
            return None


# pykrx 호환 래퍼 클래스
class NaverStock:
    """pykrx 호환 인터페이스"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._naver = NaverMarketData()
        return cls._instance

    def get_market_ticker_list(self, date, market='KOSPI'):
        """pykrx 호환: 종목 리스트"""
        return self._naver.get_ticker_list(market)

    def get_market_ticker_name(self, code):
        """pykrx 호환: 종목명"""
        return self._naver.get_ticker_name(code)

    def get_market_ohlcv_by_date(self, start=None, end=None, code=None, *,
                                   fromdate=None, todate=None, ticker=None):
        """pykrx 호환: 종목 OHLCV

        pykrx 스타일 키워드도 지원:
            fromdate -> start, todate -> end, ticker -> code
        """
        start = start or fromdate
        end = end or todate
        code = code or ticker
        return self._naver.get_ohlcv(code, start, end)

    def get_market_ohlcv_by_ticker(self, date, market='KOSPI'):
        """pykrx 호환: 전체 종목 OHLCV"""
        return self._naver.get_ohlcv_by_ticker(date, market)

    def get_market_cap_by_ticker(self, date, market='KOSPI'):
        """pykrx 호환: 전체 종목 시가총액"""
        return self._naver.get_market_cap_by_ticker(date, market)

    def get_market_ohlcv(self, start=None, end=None, code=None, *,
                          fromdate=None, todate=None, ticker=None):
        """pykrx 호환: 종목 OHLCV (다른 형식)"""
        start = start or fromdate
        end = end or todate
        code = code or ticker
        return self._naver.get_ohlcv(code, start, end)

    def get_market_cap_by_date(self, start=None, end=None, code=None, *,
                                fromdate=None, todate=None, ticker=None):
        """pykrx 호환: 종목 시가총액

        pykrx 스타일 키워드도 지원:
            fromdate -> start, todate -> end, ticker -> code
        """
        start = start or fromdate
        end = end or todate
        code = code or ticker
        info = self._naver.get_stock_info(code)
        if info and 'market_cap' in info:
            return pd.DataFrame([{'시가총액': info['market_cap']}])
        return pd.DataFrame()

    def get_market_cap(self, start=None, end=None, code=None, *,
                        fromdate=None, todate=None, ticker=None):
        """pykrx 호환: 개별 종목 시가총액 (get_market_cap_by_date 별칭)"""
        return self.get_market_cap_by_date(
            start=start, end=end, code=code,
            fromdate=fromdate, todate=todate, ticker=ticker
        )


# 전역 인스턴스
stock = NaverStock()


# 테스트
if __name__ == '__main__':
    print("=" * 50)
    print("네이버 금융 시장 데이터 수집 테스트")
    print("=" * 50)

    naver = NaverMarketData()

    # 1. 종목 리스트
    print("\n1. KOSPI 종목 리스트:")
    tickers = naver.get_ticker_list('KOSPI')
    print(f"   ✅ {len(tickers)}개 종목")
    print(f"   상위 5개: {tickers[:5]}")

    # 2. 종목명
    print("\n2. 종목명 조회:")
    for code in ['005930', '000660', '035720']:
        name = naver.get_ticker_name(code)
        print(f"   {code} = {name}")

    # 3. OHLCV (개별 종목)
    print("\n3. 삼성전자 OHLCV:")
    df = naver.get_ohlcv('005930', '20260325', '20260401')
    if not df.empty:
        print(f"   ✅ {len(df)}일 데이터")
        print(df.tail(3))

    # 4. OHLCV by ticker
    print("\n4. KOSPI 전체 종목 OHLCV:")
    df = naver.get_ohlcv_by_ticker('20260401', 'KOSPI')
    if not df.empty:
        print(f"   ✅ {len(df)}개 종목")
        print(df.head(3))

    # 5. 시가총액 by ticker
    print("\n5. KOSPI 전체 종목 시가총액:")
    df = naver.get_market_cap_by_ticker('20260401', 'KOSPI')
    if not df.empty:
        print(f"   ✅ {len(df)}개 종목")
        print(df.head(3))

    # pykrx 호환 테스트
    print("\n" + "=" * 50)
    print("pykrx 호환 인터페이스 테스트")
    print("=" * 50)

    print("\n6. stock.get_market_ticker_list:")
    tickers = stock.get_market_ticker_list('20260401', 'KOSPI')
    print(f"   ✅ {len(tickers)}개 종목")

    print("\n7. stock.get_market_ohlcv_by_ticker:")
    df = stock.get_market_ohlcv_by_ticker('20260401', 'KOSPI')
    print(f"   ✅ {len(df)}개 종목" if not df.empty else "   ❌ 데이터 없음")

    print("\n" + "=" * 50)
