"""
네이버 금융 뉴스 수집
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import re

class NewsCollector:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        self.session = requests.Session()

        # 긍정/부정 키워드 사전 (오탐 방지를 위해 구체화)
        # 강한 긍정 (가중치 2)
        self.strong_positive_keywords = [
            '급등', '폭등', '신고가', '52주 신고가', '역대 최고', '사상 최고',
            '대규모 수주', '대형 계약', '실적 호조', '어닝 서프라이즈',
            '목표가 상향', '투자의견 상향', '매수 추천', '강력 매수',
            '흑자 전환', '실적 개선', 'FDA 승인', '허가 획득'
        ]

        # 일반 긍정 (가중치 1)
        self.positive_keywords = [
            '상승세', '강세', '호재', '수주', '계약 체결', '공급 계약',
            '증가세', '성장세', '확대', '개선', '돌파', '랠리',
            '호조', '상향 조정', '긍정적', '매출 증가', '이익 증가'
        ]

        # 강한 부정 (가중치 2)
        self.strong_negative_keywords = [
            '급락', '폭락', '신저가', '52주 신저가', '역대 최저', '사상 최저',
            '대규모 손실', '적자 전환', '실적 쇼크', '어닝 쇼크',
            '목표가 하향', '투자의견 하향', '매도 추천', '파산', '상장폐지',
            '회계 부정', '횡령', '배임', '분식회계'
        ]

        # 일반 부정 (가중치 1)
        self.negative_keywords = [
            '하락세', '약세', '악재', '감소', '축소', '적자',
            '부진', '우려', '경고', '하향 조정', '부정적',
            '손실', '구조조정', '감원', '매출 감소', '이익 감소'
        ]

        # 오탐 방지: 부정문 앞에 붙는 키워드 (무시)
        self.negation_patterns = [
            '없이', '아닌', '못한', '않고', '않은', '제외', '불구'
        ]

    def _parse_news_time(self, time_str):
        """뉴스 시간 파싱 (예: '2024.01.28 07:30' 또는 '07:30')"""
        try:
            now = datetime.now()

            # "2024.01.28 07:30" 형식
            if '.' in time_str:
                return datetime.strptime(time_str, '%Y.%m.%d %H:%M')
            # "07:30" 형식 (오늘)
            elif ':' in time_str:
                time_parts = time_str.split(':')
                hour = int(time_parts[0])
                minute = int(time_parts[1])
                return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except Exception:
            return None

    def _is_relevant_time(self, pub_time_str):
        """
        장전 종목 선정에 유효한 뉴스 시간인지 확인
        - 전일 15:00 ~ 당일 09:00 (장후~장전 전체)
        - 장중 뉴스(09:00~15:00)는 전일 것만 포함
        """
        news_time = self._parse_news_time(pub_time_str)
        if not news_time:
            return True  # 시간 파싱 실패 시 포함

        now = datetime.now()

        # 현재 시간이 09:00 이전 (장전)
        if now.hour < 9:
            # 전일 15:00 ~ 당일 현재 시간
            yesterday_15 = (now - timedelta(days=1)).replace(hour=15, minute=0, second=0, microsecond=0)
            return yesterday_15 <= news_time <= now
        else:
            # 장중/장후: 전일 15:00 ~ 당일 09:00
            yesterday_15 = (now - timedelta(days=1)).replace(hour=15, minute=0, second=0, microsecond=0)
            today_0900 = now.replace(hour=9, minute=0, second=0, microsecond=0)
            return yesterday_15 <= news_time <= today_0900

    def _get_news_timing_category(self, pub_time_str):
        """
        뉴스 시간대 분류 (점수화용)
        - morning: 당일 06:00~08:30 (장전 최고)
        - evening: 전일 18:00~24:00 (장후)
        - afternoon: 전일 15:00~18:00 (장중 후반)
        - other: 기타
        """
        news_time = self._parse_news_time(pub_time_str)
        if not news_time:
            return 'other'

        now = datetime.now()
        hour = news_time.hour

        # 당일 뉴스인지 확인
        is_today = news_time.date() == now.date()

        if is_today and 6 <= hour < 9:
            return 'morning'  # 장전 (당일 06:00~09:00)
        elif not is_today and 18 <= hour <= 23:
            return 'evening'  # 장후 (전일 18:00~24:00)
        elif not is_today and 15 <= hour < 18:
            return 'afternoon'  # 장중 후반 (전일 15:00~18:00)
        else:
            return 'other'

    def _analyze_sentiment(self, text):
        """
        뉴스 감성 분석 (긍정/부정/중립)
        - 강한 키워드는 가중치 2, 일반 키워드는 가중치 1
        - 부정문 패턴 앞에 있는 키워드는 무시
        """
        positive_score = 0
        negative_score = 0
        matched_positive = []
        matched_negative = []

        # 강한 긍정 키워드 (가중치 2)
        for keyword in self.strong_positive_keywords:
            if keyword in text:
                # 부정문 패턴 체크
                idx = text.find(keyword)
                context = text[max(0, idx-5):idx]
                if not any(neg in context for neg in self.negation_patterns):
                    positive_score += 2
                    matched_positive.append(keyword)

        # 일반 긍정 키워드 (가중치 1)
        for keyword in self.positive_keywords:
            if keyword in text:
                idx = text.find(keyword)
                context = text[max(0, idx-5):idx]
                if not any(neg in context for neg in self.negation_patterns):
                    positive_score += 1
                    matched_positive.append(keyword)

        # 강한 부정 키워드 (가중치 2)
        for keyword in self.strong_negative_keywords:
            if keyword in text:
                idx = text.find(keyword)
                context = text[max(0, idx-5):idx]
                if not any(neg in context for neg in self.negation_patterns):
                    negative_score += 2
                    matched_negative.append(keyword)

        # 일반 부정 키워드 (가중치 1)
        for keyword in self.negative_keywords:
            if keyword in text:
                idx = text.find(keyword)
                context = text[max(0, idx-5):idx]
                if not any(neg in context for neg in self.negation_patterns):
                    negative_score += 1
                    matched_negative.append(keyword)

        # 점수 차이로 판단 (최소 2점 차이 필요)
        diff = positive_score - negative_score
        if diff >= 2:
            return 'positive', diff
        elif diff <= -2:
            return 'negative', abs(diff)
        else:
            return 'neutral', 0

    def get_stock_news(self):
        """네이버 금융 주요 뉴스 수집 (시간 필터링 + 감성 분석)"""
        print("📰 뉴스 수집 중...")

        all_news = []

        try:
            # 네이버 금융 증시 뉴스
            url = 'https://finance.naver.com/news/news_list.naver?mode=LSS3D&section_id=101&section_id2=258&section_id3=401'

            response = self.session.get(url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')

            # 뉴스 리스트 추출 (2026년 구조 변경 대응)
            news_list = soup.find('ul', {'class': 'realtimeNewsList'})

            if news_list:
                # dd 태그에서 뉴스 추출
                subjects = news_list.find_all('dd', {'class': 'articleSubject'})
                summaries = news_list.find_all('dd', {'class': 'articleSummary'})

                for i, subject in enumerate(subjects):
                    try:
                        title_tag = subject.find('a')
                        if not title_tag:
                            continue

                        title = title_tag.text.strip()
                        link = 'https://finance.naver.com' + title_tag.get('href', '')

                        # 요약 및 시간
                        summary = ''
                        pub_time = ''
                        if i < len(summaries):
                            summary_dd = summaries[i]
                            # 요약 텍스트 (span 제외)
                            for text in summary_dd.stripped_strings:
                                if text and not text in ['연합뉴스TV', '매일경제', '서울경제', '한국경제', '이데일리', '파이낸셜뉴스', '|']:
                                    summary = text
                                    break

                            # 시간
                            time_tag = summary_dd.find('span', {'class': 'wdate'})
                            pub_time = time_tag.text.strip() if time_tag else ''

                        # 시간 필터링 (전일 15:00 ~ 당일 09:00)
                        if not self._is_relevant_time(pub_time):
                            continue

                        # 감성 분석
                        full_text = title + ' ' + summary
                        sentiment, score = self._analyze_sentiment(full_text)

                        # 시간대 분류 (점수화용)
                        timing_category = self._get_news_timing_category(pub_time)

                        all_news.append({
                            'title': title,
                            'summary': summary,
                            'link': link,
                            'pub_time': pub_time,
                            'source': 'naver_stock',
                            'sentiment': sentiment,
                            'sentiment_score': score,
                            'timing_category': timing_category
                        })

                    except Exception as e:
                        continue

            print(f"  ✓ 네이버 금융 뉴스: {len(all_news)}개 (시간 필터링 적용)")

        except Exception as e:
            print(f"  ⚠️  네이버 금융 뉴스 수집 실패: {e}")

        # 추가 뉴스 소스 (증권사 리서치, 특징주 등)
        try:
            # 특징주 뉴스
            url = 'https://finance.naver.com/news/news_list.naver?mode=LSS3D&section_id=101&section_id2=258&section_id3=402'

            response = self.session.get(url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')

            news_list = soup.find('ul', {'class': 'realtimeNewsList'})

            if news_list:
                # dd 태그에서 뉴스 추출
                subjects = news_list.find_all('dd', {'class': 'articleSubject'})
                summaries = news_list.find_all('dd', {'class': 'articleSummary'})

                # 상위 30개
                for i, subject in enumerate(subjects[:30]):
                    try:
                        title_tag = subject.find('a')
                        if not title_tag:
                            continue

                        title = title_tag.text.strip()
                        link = 'https://finance.naver.com' + title_tag.get('href', '')

                        # 요약 및 시간
                        summary = ''
                        pub_time = ''
                        if i < len(summaries):
                            summary_dd = summaries[i]
                            # 요약 텍스트 (span 제외)
                            for text in summary_dd.stripped_strings:
                                if text and not text in ['연합뉴스TV', '매일경제', '서울경제', '한국경제', '이데일리', '파이낸셜뉴스', '|']:
                                    summary = text
                                    break

                            # 시간
                            time_tag = summary_dd.find('span', {'class': 'wdate'})
                            pub_time = time_tag.text.strip() if time_tag else ''

                        # 시간 필터링 (전일 15:00 ~ 당일 09:00)
                        if not self._is_relevant_time(pub_time):
                            continue

                        # 감성 분석
                        full_text = title + ' ' + summary
                        sentiment, score = self._analyze_sentiment(full_text)

                        # 시간대 분류 (점수화용)
                        timing_category = self._get_news_timing_category(pub_time)

                        all_news.append({
                            'title': title,
                            'summary': summary,
                            'link': link,
                            'pub_time': pub_time,
                            'source': 'naver_featured',
                            'sentiment': sentiment,
                            'sentiment_score': score,
                            'timing_category': timing_category
                        })

                    except Exception as e:
                        continue

            print(f"  ✓ 특징주 뉴스: {len(all_news)}개 (누적)")

        except Exception as e:
            print(f"  ⚠️  특징주 뉴스 수집 실패: {e}")

        # 긍정 뉴스 통계
        positive_count = sum(1 for n in all_news if n.get('sentiment') == 'positive')
        negative_count = sum(1 for n in all_news if n.get('sentiment') == 'negative')
        neutral_count = sum(1 for n in all_news if n.get('sentiment') == 'neutral')

        print(f"  ✓ 총 {len(all_news)}개 뉴스 수집 완료")
        print(f"    - 긍정: {positive_count}개 | 중립: {neutral_count}개 | 부정: {negative_count}개")

        return all_news

    def count_stock_mentions(self, stock_name, news_list):
        """특정 종목이 뉴스에 언급된 횟수 계산"""
        count = 0

        for news in news_list:
            title = news.get('title', '')
            summary = news.get('summary', '')

            if stock_name in title or stock_name in summary:
                count += 1

        return count

    def extract_keywords_from_news(self, news_list):
        """뉴스에서 주요 키워드 추출"""
        from collections import Counter
        import config

        all_keywords = []

        for news in news_list:
            title = news.get('title', '')
            summary = news.get('summary', '')
            text = title + ' ' + summary

            # 설정된 테마 키워드 찾기
            for theme, keywords in config.THEME_KEYWORDS.items():
                for keyword in keywords:
                    if keyword in text:
                        all_keywords.append((theme, keyword))

        # 가장 많이 언급된 테마
        theme_counter = Counter([theme for theme, _ in all_keywords])

        return theme_counter.most_common(10)


if __name__ == '__main__':
    # 테스트
    collector = NewsCollector()
    news = collector.get_stock_news()

    print(f"\n✅ 수집 완료: {len(news)}개 뉴스")

    if news:
        print("\n📰 최근 뉴스 5개:")
        for item in news[:5]:
            print(f"  - {item['title']}")
            print(f"    {item['pub_time']}")

        print("\n🔥 핫 테마:")
        keywords = collector.extract_keywords_from_news(news)
        for theme, count in keywords:
            print(f"  - {theme}: {count}회 언급")
