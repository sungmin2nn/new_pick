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

        # 긍정/부정 키워드 사전
        self.positive_keywords = [
            '급등', '상승', '호재', '신고가', '강세', '증가', '성장', '확대',
            '수주', '계약', '흑자', '개선', '돌파', '상승세', '랠리', '최고',
            '긍정', '호조', '상향', '목표가', '매수', '투자의견'
        ]

        self.negative_keywords = [
            '급락', '하락', '악재', '신저가', '약세', '감소', '축소', '적자',
            '부진', '우려', '경고', '하락세', '최저', '부정', '하향', '매도',
            '손실', '적자', '파산', '구조조정'
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
        """전일 18:00 ~ 당일 08:30 사이 뉴스인지 확인"""
        news_time = self._parse_news_time(pub_time_str)
        if not news_time:
            return True  # 시간 파싱 실패 시 포함

        now = datetime.now()
        yesterday_18 = (now - timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
        today_0830 = now.replace(hour=8, minute=30, second=0, microsecond=0)

        return yesterday_18 <= news_time <= today_0830

    def _analyze_sentiment(self, text):
        """뉴스 감성 분석 (긍정/부정/중립)"""
        positive_count = sum(1 for keyword in self.positive_keywords if keyword in text)
        negative_count = sum(1 for keyword in self.negative_keywords if keyword in text)

        if positive_count > negative_count:
            return 'positive', positive_count - negative_count
        elif negative_count > positive_count:
            return 'negative', negative_count - positive_count
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

                        # 시간 필터링 (전일 18:00 ~ 당일 08:30)
                        if not self._is_relevant_time(pub_time):
                            continue

                        # 감성 분석
                        full_text = title + ' ' + summary
                        sentiment, score = self._analyze_sentiment(full_text)

                        all_news.append({
                            'title': title,
                            'summary': summary,
                            'link': link,
                            'pub_time': pub_time,
                            'source': 'naver_stock',
                            'sentiment': sentiment,
                            'sentiment_score': score
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

                        # 시간 필터링
                        if not self._is_relevant_time(pub_time):
                            continue

                        # 감성 분석
                        full_text = title + ' ' + summary
                        sentiment, score = self._analyze_sentiment(full_text)

                        all_news.append({
                            'title': title,
                            'summary': summary,
                            'link': link,
                            'pub_time': pub_time,
                            'source': 'naver_featured',
                            'sentiment': sentiment,
                            'sentiment_score': score
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
