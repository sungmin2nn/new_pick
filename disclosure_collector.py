"""
DART 공시 정보 수집
전일 18:00 ~ 당일 08:30 공시를 수집하여 시초가 매매에 활용
"""

import requests
from datetime import datetime, timedelta
import time

class DisclosureCollector:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = 'https://opendart.fss.or.kr/api'

        # 긍정적 공시 키워드 (시초가 상승 요인)
        self.positive_keywords = {
            '실적': ['매출', '영업이익', '순이익', '실적', '어닝', '턴어라운드'],
            '계약': ['계약체결', '수주', '공급계약', 'MOU', '협약'],
            '투자': ['투자', '출자', '지분취득', '인수'],
            '기술': ['특허', '기술이전', '개발완료', '상용화'],
            '배당': ['배당', '주주환원', '자사주'],
            '기타': ['IR자료', '사업보고서', '분기보고서']
        }

        # 부정적 공시 키워드 (필터링)
        self.negative_keywords = [
            '횡령', '배임', '소송', '과징금', '영업정지',
            '관리종목', '상장폐지', '감사의견', '적자', '손실'
        ]

    def get_recent_disclosures(self):
        """최근 공시 수집 (전일 18:00 ~ 당일 08:30)"""
        print("\n📋 DART 공시 수집 중...")

        try:
            # 어제 날짜 (공시는 전일 18시부터)
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
            today = datetime.now().strftime('%Y%m%d')

            all_disclosures = []

            # 어제 공시 가져오기
            disclosures_yesterday = self._fetch_disclosures(yesterday)
            all_disclosures.extend(disclosures_yesterday)

            # 오늘 공시 가져오기
            disclosures_today = self._fetch_disclosures(today)
            all_disclosures.extend(disclosures_today)

            # 시간 필터링 (전일 18:00 ~ 당일 08:30)
            filtered = self._filter_by_time(all_disclosures)

            # 긍정적 공시만 선별
            positive = self._filter_positive_disclosures(filtered)

            print(f"  ✓ 전체 공시: {len(all_disclosures)}건")
            print(f"  ✓ 시간 필터링: {len(filtered)}건")
            print(f"  ✓ 긍정적 공시: {len(positive)}건")

            return positive

        except Exception as e:
            print(f"  ⚠️  공시 수집 실패: {e}")
            return []

    def _fetch_disclosures(self, date):
        """특정 날짜의 공시 가져오기"""
        url = f"{self.base_url}/list.json"

        params = {
            'crtfc_key': self.api_key,
            'bgn_de': date,
            'end_de': date,
            'page_count': 100  # 최대 100건
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            if data.get('status') == '000':
                return data.get('list', [])
            else:
                print(f"  ⚠️  DART API 오류: {data.get('message')}")
                return []

        except Exception as e:
            print(f"  ⚠️  공시 조회 실패 ({date}): {e}")
            return []

    def _filter_by_time(self, disclosures):
        """시간 필터링 (전일 18:00 ~ 당일 08:30)"""
        now = datetime.now()
        yesterday_18 = (now - timedelta(days=1)).replace(hour=18, minute=0, second=0)
        today_0830 = now.replace(hour=8, minute=30, second=0)

        filtered = []

        for disc in disclosures:
            try:
                # rcept_dt: 접수일자 (YYYYMMDD)
                # rcept_no: 접수번호에 시간 포함
                rcept_dt = disc.get('rcept_dt', '')

                if not rcept_dt:
                    continue

                # DART는 접수번호에서 시간 추출 가능 (rcept_no 끝 6자리가 시간)
                rcept_no = disc.get('rcept_no', '')
                if len(rcept_no) >= 14:
                    time_str = rcept_no[-6:]  # HHMMSS
                    hour = int(time_str[:2])
                    minute = int(time_str[2:4])

                    # 날짜 파싱
                    disc_date = datetime.strptime(rcept_dt, '%Y%m%d')
                    disc_datetime = disc_date.replace(hour=hour, minute=minute)

                    # 시간 범위 체크
                    if yesterday_18 <= disc_datetime <= today_0830:
                        filtered.append(disc)
                else:
                    # 시간 정보 없으면 날짜만으로 판단
                    disc_date = datetime.strptime(rcept_dt, '%Y%m%d')
                    if disc_date.date() == (now - timedelta(days=1)).date() or disc_date.date() == now.date():
                        filtered.append(disc)

            except Exception as e:
                continue

        return filtered

    def _filter_positive_disclosures(self, disclosures):
        """긍정적 공시만 필터링"""
        positive = []

        for disc in disclosures:
            report_nm = disc.get('report_nm', '')  # 보고서명

            # 부정적 키워드 체크 (제외)
            is_negative = False
            for neg_keyword in self.negative_keywords:
                if neg_keyword in report_nm:
                    is_negative = True
                    break

            if is_negative:
                continue

            # 긍정적 키워드 체크
            matched_category = None
            for category, keywords in self.positive_keywords.items():
                for keyword in keywords:
                    if keyword in report_nm:
                        matched_category = category
                        break
                if matched_category:
                    break

            if matched_category:
                disc['disclosure_category'] = matched_category
                positive.append(disc)

        return positive

    def calculate_disclosure_score(self, stock_code, disclosures):
        """종목별 공시 점수 계산 (40점)"""
        stock_disclosures = []

        # 해당 종목 공시 찾기
        for disc in disclosures:
            corp_code = disc.get('corp_code', '')
            stock_cd = disc.get('stock_code', '')

            # 종목코드 매칭 (A 접두사 제거)
            if stock_code == stock_cd or stock_code == stock_cd.replace('A', ''):
                stock_disclosures.append(disc)

        if not stock_disclosures:
            return 0, []

        # 공시 개수와 중요도에 따른 점수
        score = 0

        for disc in stock_disclosures:
            category = disc.get('disclosure_category', '기타')

            # 카테고리별 점수
            if category == '실적':
                score += 20  # 실적 관련이 가장 중요
            elif category == '계약':
                score += 15
            elif category == '투자':
                score += 12
            elif category == '기술':
                score += 10
            elif category == '배당':
                score += 8
            else:
                score += 5

        # 최대 40점으로 제한
        score = min(score, 40)

        return score, stock_disclosures

    def get_stock_name_by_code(self, stock_code):
        """종목코드로 회사명 조회 (DART API)"""
        url = f"{self.base_url}/company.json"

        params = {
            'crtfc_key': self.api_key,
            'corp_code': stock_code
        }

        try:
            response = requests.get(url, params=params, timeout=5)
            data = response.json()

            if data.get('status') == '000':
                return data.get('corp_name', '')

        except Exception:
            pass

        return ''


if __name__ == '__main__':
    # 테스트 (실제 API 키 필요)
    import os

    api_key = os.environ.get('DART_API_KEY', '')

    if not api_key:
        print("⚠️  DART_API_KEY 환경변수를 설정해주세요")
        print("export DART_API_KEY='your_api_key'")
    else:
        collector = DisclosureCollector(api_key)
        disclosures = collector.get_recent_disclosures()

        print(f"\n✅ 수집 완료: {len(disclosures)}건")

        if disclosures:
            print("\n📋 최근 긍정적 공시:")
            for disc in disclosures[:10]:
                print(f"  - {disc.get('corp_name', 'N/A')}: {disc.get('report_nm', 'N/A')}")
                print(f"    카테고리: {disc.get('disclosure_category', 'N/A')}")
