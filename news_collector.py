"""
네이버 금융 뉴스 수집
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time

class NewsCollector:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        self.session = requests.Session()

    def get_stock_news(self):
        """네이버 금융 주요 뉴스 수집"""
        print("📰 뉴스 수집 중...")

        all_news = []

        try:
            # 네이버 금융 증시 뉴스
            url = 'https://finance.naver.com/news/news_list.naver?mode=LSS3D&section_id=101&section_id2=258&section_id3=401'

            response = self.session.get(url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')

            # 뉴스 리스트 추출
            news_list = soup.find('ul', {'class': 'newsList'})

            if news_list:
                items = news_list.find_all('li')

                for item in items:
                    try:
                        title_tag = item.find('a', {'class': 'tit'})
                        if not title_tag:
                            continue

                        title = title_tag.text.strip()
                        link = 'https://finance.naver.com' + title_tag.get('href', '')

                        # 요약
                        summary_tag = item.find('span', {'class': 'txt'})
                        summary = summary_tag.text.strip() if summary_tag else ''

                        # 시간
                        time_tag = item.find('span', {'class': 'wdate'})
                        pub_time = time_tag.text.strip() if time_tag else ''

                        all_news.append({
                            'title': title,
                            'summary': summary,
                            'link': link,
                            'pub_time': pub_time,
                            'source': 'naver_stock'
                        })

                    except Exception as e:
                        continue

            print(f"  ✓ 네이버 금융 뉴스: {len(all_news)}개")

        except Exception as e:
            print(f"  ⚠️  네이버 금융 뉴스 수집 실패: {e}")

        # 추가 뉴스 소스 (증권사 리서치, 특징주 등)
        try:
            # 특징주 뉴스
            url = 'https://finance.naver.com/news/news_list.naver?mode=LSS3D&section_id=101&section_id2=258&section_id3=402'

            response = self.session.get(url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')

            news_list = soup.find('ul', {'class': 'newsList'})

            if news_list:
                items = news_list.find_all('li')

                for item in items[:20]:  # 상위 20개만
                    try:
                        title_tag = item.find('a', {'class': 'tit'})
                        if not title_tag:
                            continue

                        title = title_tag.text.strip()
                        link = 'https://finance.naver.com' + title_tag.get('href', '')

                        summary_tag = item.find('span', {'class': 'txt'})
                        summary = summary_tag.text.strip() if summary_tag else ''

                        time_tag = item.find('span', {'class': 'wdate'})
                        pub_time = time_tag.text.strip() if time_tag else ''

                        all_news.append({
                            'title': title,
                            'summary': summary,
                            'link': link,
                            'pub_time': pub_time,
                            'source': 'naver_featured'
                        })

                    except Exception as e:
                        continue

            print(f"  ✓ 특징주 뉴스: {len(all_news)}개 (누적)")

        except Exception as e:
            print(f"  ⚠️  특징주 뉴스 수집 실패: {e}")

        print(f"  ✓ 총 {len(all_news)}개 뉴스 수집 완료")
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
