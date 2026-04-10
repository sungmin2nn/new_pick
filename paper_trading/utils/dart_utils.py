"""
DART API 유틸리티 모듈
- 공시 정보 수집 및 필터링
- 재무 건전성 체크
- 전략 통합용 인터페이스
"""

import os
import requests
from dotenv import load_dotenv

# .env 파일에서 환경변수 로드
load_dotenv()
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
    """DART 기반 필터 및 점수 계산 (Phase 2C 정제)

    개선 (2026-04-10):
    - 회사명 boilerplate 제외 (증권사/리츠/자산운용 등)
    - 공시 종류(corp_cls) Y(유가)/K(코스닥)만 허용 - ETF/펀드 제외
    - 보고서명 패턴 정제 (정기보고서/수익률공시 등 제외)
    - 카테고리별 최소 금액 임계값 적용
    """

    # 긍정적 공시 키워드 (시초가 상승 요인) - Phase 2C 구체화
    POSITIVE_KEYWORDS = {
        '실적': ['매출액또는손익구조', '영업(잠정)실적', '잠정실적', '확정실적',
                '영업이익증가', '흑자전환', '턴어라운드'],
        '계약': ['단일판매ㆍ공급계약', '단일판매·공급계약', '단일판매', '공급계약체결',
                '수주공시', 'MOU체결', '판매계약'],
        '투자': ['타법인주식및출자증권취득', '주식등의대량보유', '유상증자결정',
                '제3자배정', '신규시설투자', '자기주식매수'],
        '기술': ['신규특허', '기술이전계약', '개발완료', '품목허가', '임상승인',
                '신약허가', '제품승인'],
        '배당': ['현금ㆍ현물배당결정', '현금배당', '주식배당결정',
                '자기주식취득결정', '자기주식소각결정', '주주환원'],
        '대형': ['대규모기업집단', '대규모투자', '역대최대'],
    }

    # 부정적 공시 키워드 (필터링 대상)
    NEGATIVE_KEYWORDS = [
        '횡령', '배임', '소송', '과징금', '영업정지',
        '관리종목', '상장폐지', '감사의견', '적자', '손실',
        '부도', '파산', '회생', '워크아웃', '자본잠식',
        '불성실', '투자주의', '매매거래정지', '계약해지',
        '투자경고', '투자위험', '사임', '해임', '담보제공'
    ]

    # ===== Phase 2C: 회사명 boilerplate 제외 패턴 =====
    # 이런 회사들은 정기적으로 수익률/거래실적 등을 공시 → 단타 매매와 무관
    EXCLUDE_CORP_PATTERNS = [
        '증권', '자산운용', '투자신탁', '인베스트먼트', '인베스트',
        '리츠', '리얼티', 'REITs', 'REIT',
        'KODEX', 'TIGER', 'KBSTAR', 'ARIRANG', 'KOSEF', 'SOL', 'HANARO',
        '스팩', 'SPAC', '제X호', '코아',
        '신탁', '캐피탈', '저축은행',
    ]

    # ===== Phase 2C: 보고서명 boilerplate 제외 패턴 =====
    EXCLUDE_REPORT_PATTERNS = [
        '거래실적', '수익률공시', '월간운용보고', '분기영업실적',
        '주식등의대량보유상황보고서',  # 5% 보고는 시세 영향 약함
        '특수관계인',
        '임원ㆍ주요주주특정증권등소유상황보고서',
        '최대주주변경', '대주주변경',
        '의결권', '주주총회',
        '정정', '취소', '연기',
    ]

    # ===== Phase 2C: 카테고리별 최소 금액 임계값 (억원) =====
    # 너무 작은 계약/투자는 시세 영향 미미 → 배제
    MIN_AMOUNT_BY_CATEGORY = {
        '계약': 50,    # 단일 공급계약 50억 이상만
        '투자': 100,   # 투자/지분취득 100억 이상만
        '실적': 0,     # 실적은 금액 무관 (별도 분석)
        '기술': 0,     # 기술/특허는 금액 무관
        '배당': 0,     # 배당은 금액 무관
        '대형': 500,   # 대형 카테고리는 500억 이상
    }

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

    def get_recent_disclosures(self, hours_back: int = 14,
                                target_date: str = None) -> List[DisclosureInfo]:
        """
        최근 공시 수집 (기본: 전일 18:00 ~ 당일 08:30, 약 14시간)

        Args:
            hours_back: 몇 시간 전까지 수집할지
            target_date: 기준일 (YYYYMMDD). None이면 오늘.
                        backtest 시 과거 날짜 지정 가능 (Phase 7G fix)

        Returns:
            공시 리스트
        """
        if not self.is_available():
            return []

        # 기준일 (target_date 우선, 없으면 오늘)
        if target_date:
            target_dt = datetime.strptime(target_date, '%Y%m%d')
        else:
            target_dt = datetime.now()

        yesterday = (target_dt - timedelta(days=1)).strftime('%Y%m%d')
        today = target_dt.strftime('%Y%m%d')

        all_disclosures = []

        # 어제 + 오늘(기준일) 공시 수집
        for date in [yesterday, today]:
            disclosures = self._fetch_disclosures(date)
            all_disclosures.extend(disclosures)

        # 시간 필터링 (전일 18:00 ~ 당일 08:30)
        filtered = self._filter_by_time(all_disclosures, target_date=target_date)

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

    def _filter_by_time(self, disclosures: List[Dict], target_date: str = None) -> List[Dict]:
        """
        날짜 기반 필터링 (전일 + 당일 공시 포함)

        Args:
            disclosures: raw 공시 리스트
            target_date: 기준일 (YYYYMMDD). None이면 오늘.

        NOTE: DART rcept_no의 끝 6자리는 시간(HHMMSS)이 아니라 일련번호(serial)임.
        DART API는 공시 시각을 별도로 제공하지 않으므로, rcept_dt(날짜)만으로
        필터링한다. 전일~당일 공시를 모두 포함하여 누락을 방지.
        """
        if target_date:
            target_dt = datetime.strptime(target_date, '%Y%m%d')
        else:
            target_dt = datetime.now()
        yesterday = (target_dt - timedelta(days=1)).date()

        filtered = []

        for disc in disclosures:
            try:
                rcept_dt = disc.get('rcept_dt', '')

                if not rcept_dt:
                    continue

                disc_date = datetime.strptime(rcept_dt, '%Y%m%d').date()

                # 전일 또는 당일 공시만 포함
                if disc_date >= yesterday:
                    filtered.append(disc)

            except Exception as e:
                print(f"  [DART] 공시 시간 필터링 오류 (rcept_dt={disc.get('rcept_dt', '?')}): {e}")
                continue

        return filtered

    def _filter_positive(self, disclosures: List[Dict]) -> List[DisclosureInfo]:
        """긍정적 공시만 필터링하고 DisclosureInfo로 변환 (Phase 2C 정제)

        필터 순서:
        1. corp_cls 검증 (Y/K만 - 유가증권/코스닥)
        2. 회사명 boilerplate 제외 (증권사/리츠/ETF 등)
        3. 보고서명 boilerplate 제외 (거래실적/수익률공시 등)
        4. 부정적 키워드 제외
        5. 긍정적 키워드 매칭
        6. 카테고리별 최소 금액 임계값 검증
        """
        positive = []

        for disc in disclosures:
            corp_cls = disc.get('corp_cls', '')
            corp_name = disc.get('corp_name', '')
            stock_code = disc.get('stock_code', '').replace('A', '')
            report_nm = disc.get('report_nm', '')

            # 1. corp_cls 검증: Y(유가증권) or K(코스닥)만 통과
            #    N(코넥스), E(기타) 제외
            if corp_cls and corp_cls not in ('Y', 'K'):
                continue

            # 단축코드 없는 종목 제외 (펀드/REITs 등은 단축코드가 없거나 비표준)
            if not stock_code or len(stock_code) != 6:
                continue

            # 2. 회사명 boilerplate 제외
            if any(pat in corp_name for pat in self.EXCLUDE_CORP_PATTERNS):
                continue

            # 3. 보고서명 boilerplate 제외
            if any(pat in report_nm for pat in self.EXCLUDE_REPORT_PATTERNS):
                continue

            # 4. 부정적 키워드 체크
            if any(neg in report_nm for neg in self.NEGATIVE_KEYWORDS):
                continue

            # 5. 긍정적 키워드 매칭
            matched_category = None
            for category, keywords in self.POSITIVE_KEYWORDS.items():
                if any(kw in report_nm for kw in keywords):
                    matched_category = category
                    break

            if not matched_category:
                continue

            # 6. 카테고리별 최소 금액 임계값
            amount = self._extract_amount(report_nm)
            min_amount = self.MIN_AMOUNT_BY_CATEGORY.get(matched_category, 0)
            if min_amount > 0 and amount > 0 and amount < min_amount:
                continue

            info = DisclosureInfo(
                corp_code=disc.get('corp_code', ''),
                corp_name=corp_name,
                stock_code=stock_code,
                report_nm=report_nm,
                rcept_dt=disc.get('rcept_dt', ''),
                rcept_no=disc.get('rcept_no', ''),
                category=matched_category,
                amount=amount,
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
        except Exception as e:
            print(f"  [DART] 금액 추출 오류: {e}")
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

        except Exception as e:
            print(f"  [DART] 회사 공시 조회 실패 ({stock_code}): {e}")
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

    def get_positive_stocks(self, target_date: str = None) -> List[Tuple[str, DartScore]]:
        """
        긍정적 공시가 있는 종목 리스트 반환

        Args:
            target_date: 기준일 (YYYYMMDD). None이면 오늘. (Phase 7G backtest 지원)

        Returns:
            [(stock_code, DartScore), ...] 리스트
        """
        if not self.is_available():
            return []

        disclosures = self.get_recent_disclosures(target_date=target_date)

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
