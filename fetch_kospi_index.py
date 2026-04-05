"""
네이버 금융에서 KOSPI 지수 일별 데이터 수집
benchmark.js 업데이트용
"""

import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime

def fetch_kospi_index_data(pages=5):
    """네이버 금융에서 KOSPI 지수 일별 데이터 수집

    Args:
        pages: 수집할 페이지 수 (1페이지 = 약 10일)

    Returns:
        list: [{date: 'YYYY-MM-DD', close: 종가, change: 등락, change_pct: 등락률}, ...]
    """
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    })

    all_data = []

    for page in range(1, pages + 1):
        url = f'https://finance.naver.com/sise/sise_index_day.naver?code=KOSPI&page={page}'

        try:
            response = session.get(url, timeout=10)
            response.encoding = 'euc-kr'

            if response.status_code != 200:
                print(f"페이지 {page} 실패: HTTP {response.status_code}")
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            table = soup.find('table', class_='type_1')

            if not table:
                print(f"페이지 {page}: 테이블 없음")
                continue

            rows = table.find_all('tr')

            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 4:
                    continue

                date_text = cols[0].get_text(strip=True)
                if not date_text or '.' not in date_text:
                    continue

                try:
                    # 날짜 파싱 (2026.04.03 형식)
                    dt = datetime.strptime(date_text, '%Y.%m.%d')
                    date_str = dt.strftime('%Y-%m-%d')

                    # 종가
                    close_text = cols[1].get_text(strip=True).replace(',', '')
                    close = float(close_text)

                    # 등락
                    change_text = cols[2].get_text(strip=True).replace(',', '')
                    # 상승/하락 이미지로 부호 판단
                    img = cols[2].find('img')
                    if img:
                        src = img.get('src', '')
                        if 'down' in src or 'ico_down' in src:
                            change_text = '-' + change_text.lstrip('-')
                    change = float(change_text) if change_text else 0

                    # 등락률
                    pct_text = cols[3].get_text(strip=True).replace('%', '').replace(',', '')
                    if img:
                        src = img.get('src', '')
                        if 'down' in src or 'ico_down' in src:
                            pct_text = '-' + pct_text.lstrip('-')
                    change_pct = float(pct_text) if pct_text else 0

                    all_data.append({
                        'date': date_str,
                        'close': close,
                        'change': change,
                        'change_pct': change_pct
                    })

                except (ValueError, IndexError) as e:
                    continue

            print(f"페이지 {page} 완료: {len([d for d in all_data if d])}개 누적")

        except Exception as e:
            print(f"페이지 {page} 에러: {e}")
            continue

    # 날짜순 정렬 (오래된 날짜부터)
    all_data.sort(key=lambda x: x['date'])

    return all_data


def calculate_cumulative_returns(data, base_date='2026-01-28'):
    """누적 수익률 계산

    Args:
        data: KOSPI 일별 데이터 리스트
        base_date: 기준일 (이 날짜의 수익률을 0으로 설정)

    Returns:
        dict: {date: {close: 종가, return: 누적수익률}}
    """
    # 기준일 데이터 찾기
    base_close = None
    for d in data:
        if d['date'] == base_date:
            base_close = d['close']
            break

    # 기준일이 없으면 첫 번째 데이터 사용
    if base_close is None and data:
        base_close = data[0]['close']
        base_date = data[0]['date']
        print(f"기준일 {base_date} 없음, {data[0]['date']} 사용 (종가: {base_close})")

    result = {}
    for d in data:
        if d['date'] >= base_date:
            cumulative_return = ((d['close'] - base_close) / base_close) * 100
            result[d['date']] = {
                'close': d['close'],
                'return': round(cumulative_return, 2)
            }

    return result


def generate_js_code(kospi_data):
    """benchmark.js용 JavaScript 코드 생성

    Args:
        kospi_data: {date: {close, return}} 형태의 딕셔너리

    Returns:
        str: JavaScript 객체 문자열
    """
    lines = []
    lines.append("const KOSPI_DAILY_DATA = {")

    for date, values in sorted(kospi_data.items()):
        lines.append(f'    "{date}": {{ close: {values["close"]}, return: {values["return"]} }},')

    lines.append("};")

    return '\n'.join(lines)


if __name__ == '__main__':
    print("=" * 60)
    print("네이버 금융 KOSPI 지수 데이터 수집")
    print("=" * 60)

    # 1. 데이터 수집 (약 50일분)
    print("\n1. KOSPI 지수 데이터 수집 중...")
    raw_data = fetch_kospi_index_data(pages=6)
    print(f"   총 {len(raw_data)}일 데이터 수집")

    if raw_data:
        print(f"   기간: {raw_data[0]['date']} ~ {raw_data[-1]['date']}")
        print(f"   최근 종가: {raw_data[-1]['close']}")

    # 2. 누적 수익률 계산
    print("\n2. 누적 수익률 계산 중...")
    kospi_data = calculate_cumulative_returns(raw_data, base_date='2026-01-28')
    print(f"   {len(kospi_data)}일 데이터 변환 완료")

    # 3. JSON 출력
    print("\n3. 데이터 미리보기:")
    for date, values in list(kospi_data.items())[:5]:
        print(f'   "{date}": {{ close: {values["close"]}, return: {values["return"]} }}')
    print("   ...")
    for date, values in list(kospi_data.items())[-3:]:
        print(f'   "{date}": {{ close: {values["close"]}, return: {values["return"]} }}')

    # 4. JavaScript 코드 생성
    print("\n4. JavaScript 코드 생성...")
    js_code = generate_js_code(kospi_data)

    # 5. 파일로 저장
    output_file = 'data/kospi_index_data.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(kospi_data, f, ensure_ascii=False, indent=2)
    print(f"   JSON 저장: {output_file}")

    # JS 코드도 저장
    js_output = 'data/kospi_daily_data.js'
    with open(js_output, 'w', encoding='utf-8') as f:
        f.write("// KOSPI 일별 데이터 (네이버 금융에서 수집)\n")
        f.write(f"// 수집일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"// 기간: {list(kospi_data.keys())[0]} ~ {list(kospi_data.keys())[-1]}\n\n")
        f.write(js_code)
    print(f"   JS 저장: {js_output}")

    print("\n" + "=" * 60)
    print("완료! benchmark.js의 KOSPI_DAILY_DATA를 업데이트하세요.")
    print("=" * 60)
