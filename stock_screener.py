"""
장전 종목 선정 시스템
매일 08:30 실행되어 당일 주목할 종목을 선정
"""

import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import config
from utils import get_kst_now, format_kst_time
from market_data import MarketDataCollector
from news_collector import NewsCollector
from disclosure_collector import DisclosureCollector
from investor_collector import InvestorCollector
from database import Database

# .env 파일에서 환경변수 로드
load_dotenv()

class StockScreener:
    def __init__(self):
        self.candidates = []
        self.news_data = []
        self.disclosure_data = []
        self.investor_data = {}
        self.market_collector = MarketDataCollector()
        self.news_collector = NewsCollector()
        self.investor_collector = InvestorCollector()

        # DART API 키 (환경변수에서 읽기)
        dart_api_key = os.environ.get('DART_API_KEY', '')
        self.disclosure_collector = DisclosureCollector(dart_api_key) if dart_api_key else None

        self.db = Database()

    def fetch_market_data(self):
        """코스피/코스닥 전종목 데이터 수집"""
        return self.market_collector.get_market_data()

    def apply_filters(self, stocks):
        """최소 필터링 조건 적용 (극소형만 제외)"""
        print("\n🔍 최소 필터 적용 중...")
        filtered = []

        for stock in stocks:
            # 극소형 제외 (거래대금 100억 미만)
            if stock.get('trading_value', 0) < config.MIN_TRADING_VALUE:
                continue

            # 극소형 제외 (시가총액 100억 미만)
            if stock.get('market_cap', 0) < config.MIN_MARKET_CAP:
                continue

            # 폭락주 제외 (등락률 -30% 미만)
            if stock.get('price_change_percent', 0) < config.MIN_PRICE_CHANGE:
                continue

            # 페니스탁 제외 (100원 미만)
            current_price = stock.get('current_price', 0)
            if current_price < config.MIN_PRICE:
                continue

            # 극단적 고가 제외 (100만원 초과)
            if current_price > config.MAX_PRICE:
                continue

            filtered.append(stock)

        print(f"  ✓ 필터링 완료: {len(filtered)}개 종목 (기존 대비 완화)")
        return filtered

    def fetch_news(self):
        """뉴스 데이터 수집"""
        self.news_data = self.news_collector.get_stock_news()
        return self.news_data

    def fetch_disclosures(self):
        """공시 데이터 수집"""
        if self.disclosure_collector:
            self.disclosure_data = self.disclosure_collector.get_recent_disclosures()
            if len(self.disclosure_data) == 0:
                print("  ⚠️  시간대(전일 18:00~당일 08:30)에 긍정적 공시가 없습니다.")
        else:
            print("\n⚠️  DART API 키가 설정되지 않았습니다. 공시 점수는 0점으로 처리됩니다.")
            print("   GitHub Secrets 또는 .env 파일에 DART_API_KEY를 설정해주세요.")
            self.disclosure_data = []
        return self.disclosure_data

    def fetch_investor_data(self):
        """외국인/기관 매매 데이터 수집"""
        self.investor_data = self.investor_collector.get_investor_data()
        return self.investor_data

    def calculate_score(self, stock):
        """종목별 점수 계산 (총 120점)"""
        score = 0
        score_detail = {}
        reasons = []

        # 1. 공시 점수 (40점) - 최우선!
        disclosure_score = self.calculate_disclosure_score(stock)
        score += disclosure_score
        score_detail['disclosure'] = disclosure_score
        if disclosure_score > 0:
            disclosures = stock.get('disclosures', [])
            if disclosures:
                categories = [d.get('disclosure_category', '기타') for d in disclosures[:2]]
                reasons.append(f"{'·'.join(set(categories))} 공시")

        # 2. 뉴스 점수 (25점)
        news_score = self.calculate_news_score(stock)
        score += news_score
        score_detail['news'] = news_score
        if stock.get('news_mentions', 0) > 0:
            sentiment = "긍정" if stock.get('positive_news', 0) > stock.get('negative_news', 0) else "중립"
            reasons.append(f"뉴스 {stock.get('news_mentions')}건 ({sentiment})")

        # 3. 테마/키워드 점수 (15점)
        theme_score = self.calculate_theme_score(stock)
        score += theme_score
        score_detail['theme_keywords'] = theme_score
        if stock.get('matched_themes'):
            themes = '·'.join(stock.get('matched_themes', [])[:2])
            reasons.append(f"{themes} 테마")

        # 4. 외국인/기관 점수 (10점)
        investor_score = self.calculate_investor_score(stock)
        score += investor_score
        score_detail['investor'] = investor_score
        if investor_score > 0:
            if stock.get('foreign_buy', 0) > 0:
                reasons.append("외국인 순매수")
            if stock.get('institution_buy', 0) > 0:
                reasons.append("기관 순매수")

        # 5. 거래대금 점수 (15점) - 신규!
        trading_value_score = self.calculate_trading_value_score(stock)
        score += trading_value_score
        score_detail['trading_value'] = trading_value_score

        # 6. 시가총액 점수 (10점) - 신규!
        market_cap_score = self.calculate_market_cap_score(stock)
        score += market_cap_score
        score_detail['market_cap'] = market_cap_score

        # 7. 가격 모멘텀 점수 (5점)
        momentum_score = self.calculate_price_momentum_score(stock)
        score += momentum_score
        score_detail['price_momentum'] = momentum_score

        # 8. 거래량 급증 점수 (10점) - 신규!
        volume_surge_score = self.calculate_volume_surge_score(stock)
        score += volume_surge_score
        score_detail['volume_surge'] = volume_surge_score

        # 9. 회전율 점수 (5점) - 신규!
        turnover_score = self.calculate_turnover_rate_score(stock)
        score += turnover_score
        score_detail['turnover_rate'] = turnover_score

        # 10. 재료 중복도 점수 (5점) - 신규!
        overlap_score = self.calculate_material_overlap_score(stock, disclosure_score, news_score, theme_score)
        score += overlap_score
        score_detail['material_overlap'] = overlap_score

        # 11. 뉴스 시간대 점수 (5점) - 신규!
        news_timing_score = self.calculate_news_timing_score(stock)
        score += news_timing_score
        score_detail['news_timing'] = news_timing_score

        # 선정 사유 저장
        stock['selection_reason'] = ' / '.join(reasons) if reasons else '-'

        return score, score_detail

    def calculate_theme_score(self, stock):
        """테마/키워드 점수 계산 (20점)"""
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

        # 공시에서도 테마 키워드 찾기
        for disclosure in stock.get('disclosures', []):
            report_nm = disclosure.get('report_nm', '')
            for theme, keywords in config.THEME_KEYWORDS.items():
                for keyword in keywords:
                    if keyword in report_nm:
                        matched_themes.append(theme)
                        break

        # 저장
        stock['matched_themes'] = list(set(matched_themes))

        # 테마 매칭 개수에 따른 점수 (15점, 기존 20점 → 15점)
        theme_count = len(set(matched_themes))
        if theme_count >= 3:
            return 15
        elif theme_count == 2:
            return 12
        elif theme_count == 1:
            return 8
        else:
            return 3  # 테마 없어도 최소 3점

    def calculate_disclosure_score(self, stock):
        """공시 점수 계산 (40점 - 시초가 매매 핵심 지표)"""
        if not self.disclosure_collector or not self.disclosure_data:
            stock['disclosure_count'] = 0
            stock['disclosures'] = []
            return 0

        stock_code = stock.get('code', '')
        market_cap = stock.get('market_cap', 0)

        score, disclosures = self.disclosure_collector.calculate_disclosure_score(
            stock_code, self.disclosure_data, market_cap
        )

        # 저장
        stock['disclosure_count'] = len(disclosures)
        stock['disclosures'] = [
            {
                'report_nm': d.get('report_nm', ''),
                'category': d.get('disclosure_category', ''),
                'rcept_dt': d.get('rcept_dt', ''),
                'amount': d.get('amount', 0)
            }
            for d in disclosures
        ]

        return score

    def calculate_news_score(self, stock):
        """뉴스 점수 계산 (30점 - 감성 분석 반영)"""
        stock_name = stock.get('name', '')

        # 뉴스에서 종목명 언급 횟수 및 감성 분석
        mention_count = 0
        positive_mentions = 0
        negative_mentions = 0
        sentiment_scores = []

        for news in self.news_data:
            title = news.get('title', '')
            summary = news.get('summary', '')
            if stock_name in title or stock_name in summary:
                mention_count += 1

                # 감성 정보 수집
                sentiment = news.get('sentiment', 'neutral')
                sentiment_score = news.get('sentiment_score', 0)

                if sentiment == 'positive':
                    positive_mentions += 1
                    sentiment_scores.append(sentiment_score)
                elif sentiment == 'negative':
                    negative_mentions += 1
                    sentiment_scores.append(-sentiment_score)
                else:
                    sentiment_scores.append(0)

        # 저장
        stock['news_mentions'] = mention_count
        stock['positive_news'] = positive_mentions
        stock['negative_news'] = negative_mentions

        if mention_count == 0:
            return 0

        # 기본 점수 (언급 횟수 기반)
        if mention_count >= 5:
            base_score = 20
        elif mention_count >= 4:
            base_score = 18
        elif mention_count >= 3:
            base_score = 15
        elif mention_count >= 2:
            base_score = 12
        else:
            base_score = 8

        # 감성 보너스/페널티 (최대 ±10점)
        avg_sentiment = sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0
        sentiment_bonus = min(max(avg_sentiment * 2, -10), 10)

        # 부정 뉴스가 많으면 대폭 감점
        if negative_mentions > positive_mentions:
            sentiment_bonus = min(sentiment_bonus, -5)

        final_score = base_score + sentiment_bonus

        # 최종 점수는 0~25점 범위 (기존 30점 → 25점)
        return max(0, min(25, final_score))

    def calculate_trading_value_score(self, stock):
        """거래대금 점수 계산 (15점 만점)"""
        trading_value = stock.get('trading_value', 0)

        for threshold, score in config.TRADING_VALUE_TIERS:
            if trading_value >= threshold:
                return score

        return 0  # 100억 미만

    def calculate_market_cap_score(self, stock):
        """시가총액 점수 계산 (10점 만점)"""
        market_cap = stock.get('market_cap', 0)

        for threshold, score in config.MARKET_CAP_TIERS:
            if market_cap >= threshold:
                return score

        return 0  # 100억 미만

    def calculate_price_momentum_score(self, stock):
        """가격 모멘텀 점수 계산 (5점 만점)"""
        price_change = stock.get('price_change_percent', 0)

        for threshold, score in config.PRICE_MOMENTUM_TIERS:
            if price_change >= threshold:
                return score

        return 0  # -10% 미만 (폭락)

    def calculate_volume_surge_score(self, stock):
        """거래량 급증 점수 계산 (10점 만점)"""
        current_volume = stock.get('volume', 0)
        avg_volume = stock.get('avg_volume_20d', 1)

        if avg_volume == 0:
            return 0

        volume_ratio = current_volume / avg_volume

        for threshold, score in config.VOLUME_SURGE_TIERS:
            if volume_ratio >= threshold:
                return score

        return 0

    def calculate_turnover_rate_score(self, stock):
        """회전율 점수 계산 (5점 만점)"""
        trading_value = stock.get('trading_value', 0)
        market_cap = stock.get('market_cap', 1)

        if market_cap == 0:
            return 0

        # 회전율 = (거래대금 / 시가총액) * 100
        turnover_rate = (trading_value / market_cap) * 100

        for threshold, score in config.TURNOVER_RATE_TIERS:
            if turnover_rate >= threshold:
                return score

        return 0

    def calculate_material_overlap_score(self, stock, disclosure_score, news_score, theme_score):
        """재료 중복도 점수 계산 (5점 만점)"""
        # 공시, 뉴스, 테마 각각 점수가 있는지 확인
        has_disclosure = disclosure_score > 0
        has_news = news_score > 0
        has_theme = theme_score > 3  # 테마 최소 점수 3점 이상

        material_count = sum([has_disclosure, has_news, has_theme])

        if material_count >= 3:
            return config.MATERIAL_OVERLAP_BONUS['all_three']
        elif material_count == 2:
            return config.MATERIAL_OVERLAP_BONUS['two']
        else:
            return config.MATERIAL_OVERLAP_BONUS['one']

    def calculate_news_timing_score(self, stock):
        """뉴스 시간대 점수 계산 (5점 만점)"""
        from datetime import datetime, timedelta

        # 종목이 언급된 뉴스 찾기
        stock_name = stock.get('name', '')
        relevant_news = []

        for news in self.news_data:
            title = news.get('title', '')
            summary = news.get('summary', '')
            if stock_name in title or stock_name in summary:
                relevant_news.append(news)

        if not relevant_news:
            return 0

        # 가장 최신 뉴스의 시간대 확인
        now = datetime.now()
        today_morning_start = now.replace(hour=6, minute=0, second=0, microsecond=0)
        today_morning_end = now.replace(hour=8, minute=30, second=0, microsecond=0)
        yesterday_evening_start = (now - timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
        yesterday_evening_end = (now - timedelta(days=1)).replace(hour=23, minute=59, second=0, microsecond=0)
        yesterday_afternoon_start = (now - timedelta(days=1)).replace(hour=15, minute=0, second=0, microsecond=0)
        yesterday_afternoon_end = (now - timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)

        best_score = 0

        for news in relevant_news:
            pub_time_str = news.get('pub_time', '')
            if not pub_time_str:
                continue

            try:
                # 시간 파싱
                if '.' in pub_time_str:  # "2024.01.28 07:30" 형식
                    news_time = datetime.strptime(pub_time_str, '%Y.%m.%d %H:%M')
                elif ':' in pub_time_str:  # "07:30" 형식 (오늘)
                    time_parts = pub_time_str.split(':')
                    hour = int(time_parts[0])
                    minute = int(time_parts[1])
                    news_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                else:
                    continue

                # 시간대별 점수
                if today_morning_start <= news_time <= today_morning_end:
                    best_score = max(best_score, config.NEWS_TIMING_BONUS['morning'])
                elif yesterday_evening_start <= news_time <= yesterday_evening_end:
                    best_score = max(best_score, config.NEWS_TIMING_BONUS['evening'])
                elif yesterday_afternoon_start <= news_time <= yesterday_afternoon_end:
                    best_score = max(best_score, config.NEWS_TIMING_BONUS['afternoon'])
                else:
                    best_score = max(best_score, config.NEWS_TIMING_BONUS['other'])

            except Exception:
                continue

        return best_score

    def calculate_investor_score(self, stock):
        """외국인/기관 점수 계산 (10점)"""
        stock_code = stock.get('code', '')

        if not self.investor_data or stock_code not in self.investor_data:
            stock['foreign_buy'] = 0
            stock['institution_buy'] = 0
            return 0

        score = self.investor_collector.calculate_investor_score(stock_code, self.investor_data)

        # 저장
        investor_info = self.investor_data.get(stock_code, {})
        stock['foreign_buy'] = investor_info.get('foreign_buy', 0)
        stock['institution_buy'] = investor_info.get('institution_buy', 0)

        return score

    def identify_leading_stocks(self, stocks):
        """테마별 대장주 식별"""
        print("\n👑 대장주 식별 중...")

        # 테마별로 종목 그룹핑
        theme_stocks = {}
        for stock in stocks:
            themes = stock.get('matched_themes', [])
            for theme in themes:
                if theme not in theme_stocks:
                    theme_stocks[theme] = []
                theme_stocks[theme].append(stock)

        # 테마별 대장주 결정 (시총 * 거래대금 기준)
        leading_stocks = set()
        for theme, theme_stock_list in theme_stocks.items():
            if len(theme_stock_list) < 2:  # 종목이 1개면 자동 대장주
                if theme_stock_list:
                    leading_stocks.add(theme_stock_list[0]['code'])
                continue

            # 시총 * 거래대금으로 정렬
            sorted_stocks = sorted(
                theme_stock_list,
                key=lambda x: x.get('market_cap', 0) * x.get('trading_value', 0),
                reverse=True
            )

            # 1위 종목이 대장주
            if sorted_stocks:
                leading_stock = sorted_stocks[0]
                leading_stocks.add(leading_stock['code'])
                print(f"  ✓ {theme} 대장주: {leading_stock.get('name')} (시총 {leading_stock.get('market_cap', 0)/1000000000000:.1f}조)")

        return leading_stocks

    def rank_stocks(self, stocks):
        """종목 점수 계산 및 순위 매기기"""
        print("\n📈 점수 계산 및 순위 매기기...")

        scored_stocks = []
        for stock in stocks:
            score, score_detail = self.calculate_score(stock)
            stock['total_score'] = score
            stock['score_detail'] = score_detail
            scored_stocks.append(stock)

        # 대장주 식별
        leading_stocks = self.identify_leading_stocks(scored_stocks)

        # 대장주 가산점 부여
        for stock in scored_stocks:
            if stock['code'] in leading_stocks:
                stock['is_leading'] = True
                stock['total_score'] += 5  # 대장주 가산점 5점
                print(f"  ⭐ 대장주 가산점: {stock.get('name')} (+5점)")
            else:
                stock['is_leading'] = False

        # 점수순 정렬
        scored_stocks.sort(key=lambda x: x['total_score'], reverse=True)

        return scored_stocks[:config.TOP_N]

    def save_results(self, stocks):
        """결과 저장 (JSON + DB)"""
        print("\n💾 결과 저장 중...")

        # 디렉토리 생성
        os.makedirs(config.OUTPUT_DIR, exist_ok=True)

        # 각 종목에 메타데이터 추가
        for stock in stocks:
            stock['score_metadata'] = self.generate_score_metadata(stock)

        # JSON 파일로 저장
        output_path = os.path.join(config.OUTPUT_DIR, config.JSON_FILE)

        result = {
            'generated_at': format_kst_time(format_str='%Y-%m-%dT%H:%M:%S'),
            'date': format_kst_time(format_str='%Y-%m-%d'),
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

    def generate_score_metadata(self, stock):
        """각 점수의 메타데이터 생성"""
        score_detail = stock.get('score_detail', {})
        metadata = {}

        # 공시 메타데이터
        disclosure_count = stock.get('disclosure_count', 0)
        metadata['disclosure'] = {
            'value': score_detail.get('disclosure', 0),
            'status': 'success' if disclosure_count > 0 else 'no_data',
            'count': disclosure_count,
            'message': f"{disclosure_count}건 수집" if disclosure_count > 0 else "공시 없음"
        }

        # 뉴스 메타데이터
        news_count = stock.get('news_mentions', 0)
        positive = stock.get('positive_news', 0)
        negative = stock.get('negative_news', 0)
        metadata['news'] = {
            'value': score_detail.get('news', 0),
            'status': 'success' if news_count > 0 else 'no_data',
            'count': news_count,
            'positive': positive,
            'negative': negative,
            'message': f"{news_count}건 (긍정 {positive})" if news_count > 0 else "뉴스 없음"
        }

        # 테마 메타데이터
        themes = stock.get('matched_themes', [])
        metadata['theme_keywords'] = {
            'value': score_detail.get('theme_keywords', 0),
            'status': 'success' if themes else 'no_match',
            'matched_themes': themes,
            'message': ', '.join(themes) if themes else "테마 매칭 없음"
        }

        # 투자자 메타데이터
        foreign = stock.get('foreign_buy', 0)
        institution = stock.get('institution_buy', 0)
        investor_msg = []
        if foreign > 0:
            investor_msg.append("외국인 순매수")
        if institution > 0:
            investor_msg.append("기관 순매수")

        metadata['investor'] = {
            'value': score_detail.get('investor', 0),
            'status': 'success' if (foreign > 0 or institution > 0) else 'no_data',
            'foreign_buy': foreign,
            'institution_buy': institution,
            'message': ', '.join(investor_msg) if investor_msg else "순매수 없음"
        }

        # 나머지 점수들은 항상 성공 (계산된 값)
        for key in ['trading_value', 'market_cap', 'price_momentum', 'volume_surge',
                    'turnover_rate', 'material_overlap', 'news_timing']:
            metadata[key] = {
                'value': score_detail.get(key, 0),
                'status': 'success',
                'message': 'OK'
            }

        return metadata

    def print_summary(self, stocks):
        """결과 요약 출력"""
        print("\n" + "="*60)
        print(f"🎯 장전 종목 선정 완료 - {format_kst_time(format_str='%Y-%m-%d %H:%M')}")
        print("="*60)

        for i, stock in enumerate(stocks[:10], 1):
            # 대장주 표시
            leading_badge = " 👑대장주" if stock.get('is_leading', False) else ""
            print(f"\n{i}. {stock.get('name', 'N/A')} ({stock.get('code', 'N/A')}) - {stock.get('market', 'N/A')}{leading_badge}")
            print(f"   현재가: {stock.get('current_price', 0):,}원 ({stock.get('price_change_percent', 0):+.2f}%)")
            print(f"   거래대금: {stock.get('trading_value', 0)/100000000:.0f}억원")
            print(f"   총점: {stock.get('total_score', 0):.0f}점/145점")
            score_detail = stock.get('score_detail', {})
            print(f"   - 공시: {score_detail.get('disclosure', 0):.0f}점 | 뉴스: {score_detail.get('news', 0):.0f}점 | 테마: {score_detail.get('theme_keywords', 0):.0f}점 | 투자자: {score_detail.get('investor', 0):.0f}점")
            print(f"   - 거래대금: {score_detail.get('trading_value', 0):.0f}점 | 시총: {score_detail.get('market_cap', 0):.0f}점 | 모멘텀: {score_detail.get('price_momentum', 0):.0f}점")
            print(f"   - 거래량: {score_detail.get('volume_surge', 0):.0f}점 | 회전율: {score_detail.get('turnover_rate', 0):.0f}점 | 재료중복: {score_detail.get('material_overlap', 0):.0f}점 | 뉴스시간: {score_detail.get('news_timing', 0):.0f}점")

            # 공시 정보
            disclosure_count = stock.get('disclosure_count', 0)
            if disclosure_count > 0:
                print(f"   - 공시: {disclosure_count}건")
                for disc in stock.get('disclosures', [])[:3]:  # 최대 3건만 표시
                    amount = disc.get('amount', 0)
                    amount_str = f" ({amount}억원)" if amount > 0 else ""
                    print(f"     · [{disc.get('category', 'N/A')}] {disc.get('report_nm', 'N/A')}{amount_str}")

            # 테마
            themes = stock.get('matched_themes', [])
            if themes:
                print(f"   - 테마: {', '.join(themes)}")

            # 뉴스
            news_count = stock.get('news_mentions', 0)
            positive_news = stock.get('positive_news', 0)
            negative_news = stock.get('negative_news', 0)
            if news_count > 0:
                print(f"   - 뉴스 언급: {news_count}회 (긍정 {positive_news}, 부정 {negative_news})")

            # 외국인/기관
            foreign_buy = stock.get('foreign_buy', 0)
            institution_buy = stock.get('institution_buy', 0)
            if foreign_buy > 0 or institution_buy > 0:
                print(f"   - 외국인: {foreign_buy:,}주 | 기관: {institution_buy:,}주")

        if len(stocks) > 10:
            print(f"\n... 외 {len(stocks) - 10}개 종목")

    def run(self):
        """메인 실행 함수"""
        print("🚀 장전 종목 선정 시스템 시작")
        print(f"⏰ 실행 시간 (KST): {format_kst_time()}")

        try:
            # 1. 시장 데이터 수집
            stocks = self.fetch_market_data()

            # 2. 공시 데이터 수집 (최우선!)
            self.fetch_disclosures()

            # 3. 뉴스 데이터 수집
            self.fetch_news()

            # 4. 외국인/기관 매매 데이터 수집
            self.fetch_investor_data()

            # 5. 필터링 적용
            filtered_stocks = self.apply_filters(stocks)

            # 6. 점수 계산 및 순위
            ranked_stocks = self.rank_stocks(filtered_stocks)

            # 7. 결과 저장
            self.save_results(ranked_stocks)

            # 8. 결과 출력
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
