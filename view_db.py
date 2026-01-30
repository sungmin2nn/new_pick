#!/usr/bin/env python3
"""
DB에 저장된 종목 데이터 조회 스크립트
"""

from database import Database
import sys

def view_all_dates():
    """저장된 모든 날짜 확인"""
    db = Database()
    dates = db.get_all_dates()

    print("\n" + "="*60)
    print("📅 저장된 날짜 목록")
    print("="*60)

    if not dates:
        print("저장된 데이터가 없습니다.")
        return

    for i, date in enumerate(dates, 1):
        data = db.get_candidates_by_date(date)
        print(f"{i}. {date} - {len(data)}개 종목")

    print("="*60)

def view_date(date):
    """특정 날짜의 종목 상세 조회"""
    db = Database()
    stocks = db.get_candidates_by_date(date)

    if not stocks:
        print(f"\n{date}에 저장된 데이터가 없습니다.")
        return

    print("\n" + "="*60)
    print(f"📊 {date} 선정 종목 ({len(stocks)}개)")
    print("="*60)

    for i, stock in enumerate(stocks, 1):
        print(f"\n{i}. {stock['stock_name']} ({stock['stock_code']})")
        print(f"   총점: {stock['total_score']:.1f}점")
        print(f"   선정이유: {stock['selection_reason']}")
        print(f"   점수 상세:")
        print(f"     - 공시: {stock['disclosure_score']}점")
        print(f"     - 뉴스: {stock['news_score']}점")
        print(f"     - 테마: {stock['theme_score']}점")
        print(f"     - 투자자: {stock['investor_score']}점")
        print(f"     - 거래대금: {stock['trading_value_score']}점")
        print(f"     - 시가총액: {stock['market_cap_score']}점")
        print(f"     - 가격모멘텀: {stock['price_momentum_score']}점")
        print(f"     - 거래량급증: {stock['volume_surge_score']}점")
        print(f"     - 회전율: {stock['turnover_rate_score']}점")
        print(f"     - 재료중복도: {stock['material_overlap_score']}점")
        print(f"     - 뉴스시간대: {stock['news_timing_score']}점")

    print("\n" + "="*60)

def view_recent(days=7):
    """최근 N일 데이터 조회"""
    db = Database()
    stocks = db.get_recent_candidates(days=days)

    if not stocks:
        print(f"\n최근 {days}일간 저장된 데이터가 없습니다.")
        return

    # 날짜별로 그룹화
    by_date = {}
    for stock in stocks:
        date = stock['date']
        if date not in by_date:
            by_date[date] = []
        by_date[date].append(stock)

    print("\n" + "="*60)
    print(f"📅 최근 {days}일 선정 종목")
    print("="*60)

    for date in sorted(by_date.keys(), reverse=True):
        stocks_on_date = by_date[date]
        print(f"\n[{date}] {len(stocks_on_date)}개 종목")
        for stock in stocks_on_date:
            print(f"  {stock['stock_name']:15s} | {stock['total_score']:5.1f}점 | {stock['selection_reason']}")

    print("\n" + "="*60)

def main():
    """메인 함수"""
    if len(sys.argv) == 1:
        # 인자 없으면 전체 날짜 목록 표시
        view_all_dates()
        print("\n사용법:")
        print("  python3 view_db.py               - 전체 날짜 목록")
        print("  python3 view_db.py 2026-01-30    - 특정 날짜 상세")
        print("  python3 view_db.py recent        - 최근 7일")
        print("  python3 view_db.py recent 30     - 최근 30일")

    elif len(sys.argv) == 2:
        arg = sys.argv[1]

        if arg == 'recent':
            view_recent(7)
        elif arg.startswith('2'):  # 날짜 형식 (2026-01-30)
            view_date(arg)
        else:
            print(f"알 수 없는 명령어: {arg}")

    elif len(sys.argv) == 3 and sys.argv[1] == 'recent':
        try:
            days = int(sys.argv[2])
            view_recent(days)
        except ValueError:
            print(f"올바른 숫자를 입력하세요: {sys.argv[2]}")

if __name__ == '__main__':
    main()
