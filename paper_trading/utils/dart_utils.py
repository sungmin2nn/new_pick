"""
DART API 유틸리티 모듈
- 공시 정보 수집 및 필터링
- 재무 건전성 체크
- 전략 통합용 인터페이스
"""

import os
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
import re


@dataclass
class DisclosureInfo:
    """공시 정보"""
    corp_code: str
    corp_name: str
    stock_code: str
    report_nm: str
    rcept_dt: str
    rcept_no: str
    category: str = "기타"
    amount: int = 0  # 억원 단위
    is_positive: bool = False


@dataclass
class DartScore:
    """DART 점수 결과"""
    stock_code: str
    total_score: float = 0
    disclosure_score: float = 0  # 공시 점수 (최대 40점)
    financial_score: float = 0   # 재무 점수 (최대 20점)
    disclosures: List[DisclosureInfo] = field(default_factory=list)
    has_negative: bool = False


class DartFilter:
    """DART 기반 필터 및 점수 계산"""

    # 긍정적 공시 키워드 (시초가 상승 요인)
    POSITIVE_KEYWORDS = {
        '실적': ['매출', '영업이익', '순이익', '실적', '어닝', '턴어라운드', '흑자전환'],
        '계약': ['계약체결', '수주', '공급계약', 'MOU', '협약', '납품'],
        '투자': ['투자', '출자', '지분취득', '인수', '증자'],
        '기술': ['특허', '기술이전', '개발완료', '상용화', '허가'],
        '배당': ['배당', '주주환원', '자사주', '소각'],
        '대형': ['대규모', '역대최대', '신기록']
    }

    # 부정적 공시 키워드 (필터링 대상)
    NEGATIVE_KEYWORDS = [
        '횡령', '배임', '소송', '과징금', '영업정지',
        '관리종목', '상장폐지', '감사의견', '적자', '손실',
        '부도', '파산', '회생', '워크아웃', '자본잠식',
        '불성실', '투자주의', '매매거래정지', '계약해지',
        '투자경고', '투자위험', '사임', '해임', '담보제공'
    ]

    # 카테고리별 기본 점수
    CATEGORY_SCORES = {
        '실적': 20,
        '계약': 15,
        '투자': 12,
        '기술': 10,
        '배당': 8,
        '대형': 18,
        '기타': 5
    }

    def __init__(self, api_key: str = None):
        """
        Args:
            api_key: DART API 키. 없으면 환경변수에서 가져옴
        """
        self.api_key = api_key or os.environ.get('DART_API_KEY', '')
        self.base_url = 'https://opendart.fss.or.kr/api'
        self._cache = {}  # 공시 캐시
        self._corp_code_cache = {}  # 회사코드 캐시

        if not self.api_key:
            print("  [DART] 경고: DART_API_KEY가 설정되지 않았습니다.")

    def is_available(self) -> bool:
        """API 사용 가능 여부"""
        return bool(self.api_key)

    def get_recent_disclosures(self, hours_back: int = 14) -> List[DisclosureInfo]:
        """
        최근 공시 수집 (기본: 전일 18:00 ~ 당일 08:30, 약 14시간)

        Args:
            hours_back: 몇 시간 전까지 수집할지

        Returns:
            공시 리스트
        """
        if not self.is_available():
            return []

        now = datetime.now()
        yesterday = (now - timedelta(days=1)).strftime('%Y%m%d')
        today = now.strftime('%Y%m%d')

        all_disclosures = []

        # 어제 + 오늘 공시 수집
        for date in [yesterday, today]:
            disclosures = self._fetch_disclosures(date)
            all_disclosures.extend(disclosures)

        # 시간 필터링 (전일 18:00 ~ 당일 08:30)
        filtered = self._filter_by_time(all_disclosures)

        # 긍정적 공시만 선별
        positive = self._filter_positive(filtered)

        return positive

    def _fetch_disclosures(self, date: str) -> List[Dict]:
        """특정 날짜의 공시 가져오기"""
        cache_key = f"disc_{date}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        url = f"{self.base_url}/list.json"
        params = {
            'crtfc_key': self.api_key,
            'bgn_de': date,
            'end_de': date,
            'page_count': 100
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            if data.get('status') == '000':
                result = data.get('list', [])
                self._cache[cache_key] = result
                return result
            else:
                return []

        except Exception as e:
            print(f"  [DART] 공시 조회 실패 ({date}): {e}")
            return []

    def _filter_by_time(self, disclosures: List[Dict]) -> List[Dict]:
        """시간 필터링 (전일 18:00 ~ 당일 08:30)"""
        now = datetime.now()
        yesterday_18 = (now - timedelta(days=1)).replace(hour=18, minute=0, second=0)
        today_0830 = now.replace(hour=8, minute=30, second=0)

        filtered = []

        for disc in disclosures:
            try:
                rcept_dt = disc.get('rcept_dt', '')
                rcept_no = disc.get('rcept_no', '')

                if not rcept_dt:
                    continue

                # 접수번호에서 시간 추출 (rcept_no 끝 6자리가 시간)
                if len(rcept_no) >= 14:
                    time_str = rcept_no[-6:]
                    hour = int(time_str[:2])
                    minute = int(time_str[2:4])

                    disc_date = datetime.strptime(rcept_dt, '%Y%m%d')
                    disc_datetime = disc_date.replace(hour=hour, minute=minute)

                    if yesterday_18 <= disc_datetime <= today_0830:
                        filtered.append(disc)
                else:
                    # 시간 정보 없으면 날짜만으로 판단
                    disc_date = datetime.strptime(rcept_dt, '%Y%m%d')
                    if disc_date.date() >= (now - timedelta(days=1)).date():
                        filtered.append(disc)

            except Exception:
                continue

        return filtered

    def _filter_positive(self, disclosures: List[Dict]) -> List[DisclosureInfo]:
        """긍정적 공시만 필터링하고 DisclosureInfo로 변환"""
        positive = []

        for disc in disclosures:
            report_nm = disc.get('report_nm', '')

            # 부정적 키워드 체크 (제외)
            is_negative = any(neg in report_nm for neg in self.NEGATIVE_KEYWORDS)
            if is_negative:
                continue

            # 긍정적 키워드 체크
            matched_category = None
            for category, keywords in self.POSITIVE_KEYWORDS.items():
                if any(kw in report_nm for kw in keywords):
                    matched_category = category
                    break

            if matched_category:
                info = DisclosureInfo(
                    corp_code=disc.get('corp_code', ''),
                    corp_name=disc.get('corp_name', ''),
                    stock_code=disc.get('stock_code', '').replace('A', ''),
                    report_nm=report_nm,
                    rcept_dt=disc.get('rcept_dt', ''),
                    rcept_no=disc.get('rcept_no', ''),
                    category=matched_category,
                    amount=self._extract_amount(report_nm),
                    is_positive=True
                )
                positive.append(info)

        return positive

    def _extract_amount(self, text: str) -> int:
        """공시 내용에서 금액 추출 (억원 단위)"""
        try:
            patterns = [
                r'(\d+[,\d]*)\s*억\s*원',
                r'(\d+[,\d]*)\s*억',
                r'(\d+[,\d]*\.?\d*)\s*조\s*원',
                r'(\d+[,\d]*\.?\d*)\s*조',
            ]

            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    amount_str = match.group(1).replace(',', '')
                    if '조' in pattern:
                        return int(float(amount_str) * 10000)
                    else:
                        return int(amount_str)

            return 0
        except Exception:
            return 0

    def check_negative_disclosure(self, stock_code: str, days_back: int = 7) -> bool:
        """
        부정적 공시 여부 체크

        Args:
            stock_code: 종목코드 (6자리)
            days_back: 며칠 전까지 체크할지

        Returns:
            부정적 공시가 있으면 True
        """
        if not self.is_available():
            return False

        # 최근 공시 가져오기
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y%m%d')

        disclosures = self._fetch_company_disclosures(stock_code, start_date, end_date)

        for disc in disclosures:
            report_nm = disc.get('report_nm', '')
            if any(neg in report_nm for neg in self.NEGATIVE_KEYWORDS):
                return True

        return False

    def _fetch_company_disclosures(self, stock_code: str, start_date: str, end_date: str) -> List[Dict]:
        """특정 회사의 공시 가져오기"""
        # 회사코드 조회 (stock_code → corp_code)
        corp_code = self._get_corp_code(stock_code)
        if not corp_code:
            return []

        url = f"{self.base_url}/list.json"
        params = {
            'crtfc_key': self.api_key,
            'corp_code': corp_code,
            'bgn_de': start_date,
            'end_de': end_date,
            'page_count': 100
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            if data.get('status') == '000':
                return data.get('list', [])
            return []

        except Exception:
            return []

    def _get_corp_code(self, stock_code: str) -> Optional[str]:
        """종목코드로 회사코드 조회"""
        # TODO: corpCode.xml 파일에서 매핑 필요
        # 현재는 공시 리스트에서 매칭
        return None

    def calculate_score(self, stock_code: str, disclosures: List[DisclosureInfo] = None,
                       market_cap: int = 0) -> DartScore:
        """
        종목별 DART 점수 계산

        Args:
            stock_code: 종목코드 (6자리)
            disclosures: 공시 리스트 (없으면 자동 수집)
            market_cap: 시가총액 (원)

        Returns:
            DartScore 객체
        """
        if disclosures is None:
            disclosures = self.get_recent_disclosures()

        # 해당 종목 공시 필터링
        stock_disclosures = [
            d for d in disclosures
            if d.stock_code == stock_code or d.stock_code == stock_code.replace('A', '')
        ]

        result = DartScore(stock_code=stock_code, disclosures=stock_disclosures)

        if not stock_disclosures:
            return result

        # 공시 점수 계산 (최대 40점)
        disclosure_score = 0
        for disc in stock_disclosures:
            base_score = self.CATEGORY_SCORES.get(disc.category, 5)

            # 금액 가산점 (시총 대비)
            amount_bonus = 0
            if disc.amount > 0 and market_cap > 0:
                market_cap_in_100m = market_cap / 100000000  # 억원 단위
                ratio = (disc.amount / market_cap_in_100m) * 100

                if ratio >= 20:
                    amount_bonus = 10
                elif ratio >= 10:
                    amount_bonus = 7
                elif ratio >= 5:
                    amount_bonus = 5
                elif ratio >= 1:
                    amount_bonus = 3

            disclosure_score += (base_score + amount_bonus)

        result.disclosure_score = min(disclosure_score, 40)  # 최대 40점
        result.total_score = result.disclosure_score

        return result

    def filter_stocks(self, stock_codes: List[str],
                     exclude_negative: bool = True,
                     min_disclosure_score: float = 0) -> List[str]:
        """
        종목 필터링

        Args:
            stock_codes: 종목코드 리스트
            exclude_negative: 부정적 공시 종목 제외 여부
            min_disclosure_score: 최소 공시 점수

        Returns:
            필터링된 종목코드 리스트
        """
        if not self.is_available():
            return stock_codes

        disclosures = self.get_recent_disclosures()
        filtered = []

        for code in stock_codes:
            # 부정적 공시 체크
            if exclude_negative and self.check_negative_disclosure(code):
                continue

            # 점수 체크
            if min_disclosure_score > 0:
                score = self.calculate_score(code, disclosures)
                if score.disclosure_score < min_disclosure_score:
                    continue

            filtered.append(code)

        return filtered

    def get_positive_stocks(self) -> List[Tuple[str, DartScore]]:
        """
        긍정적 공시가 있는 종목 리스트 반환

        Returns:
            [(stock_code, DartScore), ...] 리스트
        """
        if not self.is_available():
            return []

        disclosures = self.get_recent_disclosures()

        # 종목별로 그룹핑
        stock_scores = {}
        for disc in disclosures:
            code = disc.stock_code
            if not code:
                continue

            if code not in stock_scores:
                stock_scores[code] = DartScore(stock_code=code)

            stock_scores[code].disclosures.append(disc)

        # 점수 계산
        results = []
        for code, score in stock_scores.items():
            score.disclosure_score = sum(
                self.CATEGORY_SCORES.get(d.category, 5) for d in score.disclosures
            )
            score.disclosure_score = min(score.disclosure_score, 40)
            score.total_score = score.disclosure_score
            results.append((code, score))

        # 점수순 정렬
        results.sort(key=lambda x: x[1].total_score, reverse=True)

        return results


# 싱글톤 인스턴스
_dart_filter_instance = None


def get_dart_filter(api_key: str = None) -> DartFilter:
    """DartFilter 싱글톤 인스턴스 반환"""
    global _dart_filter_instance

    if _dart_filter_instance is None:
        _dart_filter_instance = DartFilter(api_key)

    return _dart_filter_instance
