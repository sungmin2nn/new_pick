"""
장전 종목 선정 시스템
매일 08:30 실행되어 당일 주목할 종목을 선정
"""

import json
import os
from datetime import datetime, timedelta
import config
from market_data import MarketDataCollector
from news_collector import NewsCollector
from database import Database

class StockScreener:
    def __init__(self):
        self.candidates = []
        self.news_data = []
        self.market_collector = MarketDataCollector()
        self.news_collector = NewsCollector()
        self.db = Database()

    def fetch_market_data(self):
        """코스피/코스닥 전종목 데이터 수집"""
        return self.market_collector.get_market_data()

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
        self.news_data = self.news_collector.get_stock_news()
        return self.news_data

    def calculate_score(self, stock):
        """종목별 점수 계산 (총 100점 - 뉴스 중심)"""
        score = 0
        score_detail = {}

        # 1. 뉴스 점수 (50점) - 핵심!
        news_score = self.calculate_news_score(stock)
        score += news_score
        score_detail['news'] = news_score

        # 2. 테마/키워드 점수 (30점)
        theme_score = self.calculate_theme_score(stock)
        score += theme_score
        score_detail['theme_keywords'] = theme_score

        # 3. 외국인/기관 점수 (20점) - 추후 구현
        investor_score = 10  # 임시로 기본 10점
        score += investor_score
        score_detail['investor'] = investor_score

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

        # 뉴스에서도 테마 키워드 찾기
        for news in self.news_data:
            if stock_name in news.get('title', '') or stock_name in news.get('summary', ''):
                title = news.get('title', '')
                summary = news.get('summary', '')
                text = title + ' ' + summary

                for theme, keywords in config.THEME_KEYWORDS.items():
                    for keyword in keywords:
                        if keyword in text:
                            matched_themes.append(theme)
                            break

        # 저장
        stock['matched_themes'] = list(set(matched_themes))

        # 테마 매칭 개수에 따른 점수 (30점)
        theme_count = len(set(matched_themes))
        if theme_count >= 3:
            return 30
        elif theme_count == 2:
            return 25
        elif theme_count == 1:
            return 20
        else:
            return 10

    def calculate_news_score(self, stock):
        """뉴스 점수 계산 (50점 - 시초가 매매 핵심 지표)"""
        stock_name = stock.get('name', '')

        # 뉴스에서 종목명 언급 횟수
        mention_count = 0
        for news in self.news_data:
            title = news.get('title', '')
            summary = news.get('summary', '')
            if stock_name in title or stock_name in summary:
                mention_count += 1

        # 저장
        stock['news_mentions'] = mention_count

        # 언급 횟수에 따른 점수 (뉴스 많을수록 시초가 관심 집중)
        if mention_count >= 5:
            return 50
        elif mention_count >= 4:
            return 45
        elif mention_count >= 3:
            return 40
        elif mention_count >= 2:
            return 30
        elif mention_count >= 1:
            return 20
        else:
            return 0

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
        """결과 저장 (JSON + DB)"""
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

        print(f"  ✓ JSON 저장 완료: {output_path}")

        # 데이터베이스에도 저장
        self.db.save_candidates(stocks)

        print(f"  ✓ 선정 종목 수: {len(stocks)}개")

        return output_path

    def print_summary(self, stocks):
        """결과 요약 출력"""
        print("\n" + "="*60)
        print(f"🎯 장전 종목 선정 완료 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("="*60)

        for i, stock in enumerate(stocks[:10], 1):
            print(f"\n{i}. {stock.get('name', 'N/A')} ({stock.get('code', 'N/A')}) - {stock.get('market', 'N/A')}")
            print(f"   현재가: {stock.get('current_price', 0):,}원 ({stock.get('price_change_percent', 0):+.2f}%)")
            print(f"   거래대금: {stock.get('trading_value', 0)/100000000:.0f}억원")
            print(f"   총점: {stock.get('total_score', 0):.0f}점")
            score_detail = stock.get('score_detail', {})
            print(f"   - 뉴스: {score_detail.get('news', 0)}점 | 테마: {score_detail.get('theme_keywords', 0)}점 | 투자자: {score_detail.get('investor', 0)}점")

            themes = stock.get('matched_themes', [])
            if themes:
                print(f"   - 테마: {', '.join(themes)}")

            news_count = stock.get('news_mentions', 0)
            if news_count > 0:
                print(f"   - 뉴스 언급: {news_count}회")

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
