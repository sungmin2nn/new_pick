"""
장전 종목 선정 시스템
매일 08:30 실행되어 당일 주목할 종목을 선정
"""

import json
import os
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import pandas as pd
import config

class StockScreener:
    def __init__(self):
        self.candidates = []
        self.news_data = []

    def fetch_market_data(self):
        """코스피/코스닥 전종목 데이터 수집"""
        print("📊 시장 데이터 수집 중...")

        # 네이버 금융 API를 통한 시장 데이터 수집
        markets = ['KOSPI', 'KOSDAQ']
        all_stocks = []

        for market in markets:
            try:
                # 실제 구현시 네이버 금융 API 또는 한국투자증권 API 사용
                # 여기서는 구조만 작성
                url = f'https://finance.naver.com/sise/sise_market_sum.naver?sosok={0 if market == "KOSPI" else 1}'
                headers = {'User-Agent': 'Mozilla/5.0'}

                # 임시로 샘플 데이터 구조 반환
                # 실제로는 페이지 크롤링 또는 API 호출 필요
                print(f"  - {market} 데이터 수집")

            except Exception as e:
                print(f"  ⚠️  {market} 데이터 수집 실패: {e}")

        return all_stocks

    def apply_filters(self, stocks):
        """필터링 조건 적용"""
        print("\n🔍 필터링 적용 중...")
        filtered = []

        for stock in stocks:
            # 거래대금 체크
            if stock.get('trading_value', 0) < config.MIN_TRADING_VALUE:
                continue

            # 상승률 체크
            if stock.get('price_change_percent', 0) < config.MIN_PRICE_CHANGE:
                continue

            # 시가총액 체크
            if stock.get('market_cap', 0) < config.MIN_MARKET_CAP:
                continue

            # 주가 상한 체크
            if stock.get('current_price', 0) > config.MAX_PRICE:
                continue

            # 거래량 급증 체크
            avg_volume = stock.get('avg_volume_20d', 1)
            current_volume = stock.get('volume', 0)
            if current_volume < avg_volume * config.VOLUME_SPIKE_MULTIPLIER:
                continue

            filtered.append(stock)

        print(f"  ✓ 필터링 완료: {len(filtered)}개 종목 선정")
        return filtered

    def fetch_news(self):
        """뉴스 데이터 수집"""
        print("\n📰 뉴스 수집 중...")
        news_list = []

        for source_url in config.NEWS_SOURCES:
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                response = requests.get(source_url, headers=headers, timeout=10)
                soup = BeautifulSoup(response.text, 'html.parser')

                # 뉴스 제목과 링크 추출 (네이버 금융 구조에 맞게)
                # 실제 구현시 상세 파싱 필요
                print(f"  - 뉴스 소스 수집 완료")

            except Exception as e:
                print(f"  ⚠️  뉴스 수집 실패: {e}")

        self.news_data = news_list
        return news_list

    def calculate_score(self, stock):
        """종목별 점수 계산 (총 100점)"""
        score = 0
        score_detail = {}

        # 1. 가격 모멘텀 점수 (30점)
        price_change = stock.get('price_change_percent', 0)
        if price_change >= 10:
            price_score = 30
        elif price_change >= 7:
            price_score = 25
        elif price_change >= 5:
            price_score = 20
        elif price_change >= 3:
            price_score = 15
        else:
            price_score = 10

        score += price_score
        score_detail['price_momentum'] = price_score

        # 2. 거래량 점수 (25점)
        avg_volume = stock.get('avg_volume_20d', 1)
        current_volume = stock.get('volume', 0)
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

        if volume_ratio >= 3:
            volume_score = 25
        elif volume_ratio >= 2.5:
            volume_score = 20
        elif volume_ratio >= 2:
            volume_score = 15
        elif volume_ratio >= 1.5:
            volume_score = 10
        else:
            volume_score = 5

        score += volume_score
        score_detail['volume'] = volume_score

        # 3. 테마/키워드 점수 (25점)
        theme_score = self.calculate_theme_score(stock)
        score += theme_score
        score_detail['theme_keywords'] = theme_score

        # 4. 뉴스 점수 (20점)
        news_score = self.calculate_news_score(stock)
        score += news_score
        score_detail['news'] = news_score

        return score, score_detail

    def calculate_theme_score(self, stock):
        """테마/키워드 점수 계산"""
        stock_name = stock.get('name', '')
        stock_code = stock.get('code', '')

        # 종목명, 업종, 관련 뉴스에서 키워드 검색
        matched_themes = []

        for theme, keywords in config.THEME_KEYWORDS.items():
            for keyword in keywords:
                if keyword in stock_name:
                    matched_themes.append(theme)
                    break

        # 테마 매칭 개수에 따른 점수
        theme_count = len(set(matched_themes))
        if theme_count >= 3:
            return 25
        elif theme_count == 2:
            return 20
        elif theme_count == 1:
            return 15
        else:
            return 5

    def calculate_news_score(self, stock):
        """뉴스 점수 계산"""
        stock_name = stock.get('name', '')

        # 오늘 뉴스에서 종목명 언급 횟수
        mention_count = 0
        for news in self.news_data:
            if stock_name in news.get('title', ''):
                mention_count += 1

        # 언급 횟수에 따른 점수
        if mention_count >= 5:
            return 20
        elif mention_count >= 3:
            return 15
        elif mention_count >= 1:
            return 10
        else:
            return 5

    def rank_stocks(self, stocks):
        """종목 점수 계산 및 순위 매기기"""
        print("\n📈 점수 계산 및 순위 매기기...")

        scored_stocks = []
        for stock in stocks:
            score, score_detail = self.calculate_score(stock)
            stock['total_score'] = score
            stock['score_detail'] = score_detail
            scored_stocks.append(stock)

        # 점수순 정렬
        scored_stocks.sort(key=lambda x: x['total_score'], reverse=True)

        return scored_stocks[:config.TOP_N]

    def save_results(self, stocks):
        """결과 저장 (JSON)"""
        print("\n💾 결과 저장 중...")

        # 디렉토리 생성
        os.makedirs(config.OUTPUT_DIR, exist_ok=True)

        # JSON 파일로 저장
        output_path = os.path.join(config.OUTPUT_DIR, config.JSON_FILE)

        result = {
            'generated_at': datetime.now().isoformat(),
            'date': datetime.now().strftime('%Y-%m-%d'),
            'count': len(stocks),
            'candidates': stocks
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"  ✓ 저장 완료: {output_path}")
        print(f"  ✓ 선정 종목 수: {len(stocks)}개")

        return output_path

    def print_summary(self, stocks):
        """결과 요약 출력"""
        print("\n" + "="*60)
        print(f"🎯 장전 종목 선정 완료 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("="*60)

        for i, stock in enumerate(stocks[:10], 1):
            print(f"\n{i}. {stock.get('name', 'N/A')} ({stock.get('code', 'N/A')})")
            print(f"   총점: {stock.get('total_score', 0)}점")
            score_detail = stock.get('score_detail', {})
            print(f"   - 가격: {score_detail.get('price_momentum', 0)}점")
            print(f"   - 거래량: {score_detail.get('volume', 0)}점")
            print(f"   - 테마: {score_detail.get('theme_keywords', 0)}점")
            print(f"   - 뉴스: {score_detail.get('news', 0)}점")

        if len(stocks) > 10:
            print(f"\n... 외 {len(stocks) - 10}개 종목")

    def run(self):
        """메인 실행 함수"""
        print("🚀 장전 종목 선정 시스템 시작")
        print(f"⏰ 실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        try:
            # 1. 시장 데이터 수집
            stocks = self.fetch_market_data()

            # 2. 뉴스 데이터 수집
            self.fetch_news()

            # 3. 필터링 적용
            filtered_stocks = self.apply_filters(stocks)

            # 4. 점수 계산 및 순위
            ranked_stocks = self.rank_stocks(filtered_stocks)

            # 5. 결과 저장
            self.save_results(ranked_stocks)

            # 6. 결과 출력
            self.print_summary(ranked_stocks)

            print("\n✅ 작업 완료!")
            return True

        except Exception as e:
            print(f"\n❌ 오류 발생: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == '__main__':
    screener = StockScreener()
    screener.run()
