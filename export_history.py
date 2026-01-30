"""
과거 데이터를 JSON으로 내보내는 스크립트
GitHub Pages에서 사용할 수 있도록 최근 30일 데이터를 JSON 파일로 생성
"""

import json
import os
import glob
from datetime import datetime
from database import Database
from utils import format_kst_time

def export_history():
    """최근 30일 데이터를 JSON으로 내보내기 (DB + intraday 파일)"""
    db = Database()

    # 1. DB에서 데이터 로드
    recent_data = db.get_recent_candidates(days=30)

    # 날짜별로 그룹화
    data_by_date = {}
    for item in recent_data:
        date = item['date']
        if date not in data_by_date:
            data_by_date[date] = []
        data_by_date[date].append(item)

    # 2. intraday 파일 스캔하여 DB에 없는 날짜 추가
    intraday_files = glob.glob('data/intraday/intraday_*.json')
    intraday_count = 0

    for filepath in sorted(intraday_files, reverse=True):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                intraday_data = json.load(f)

            # 날짜 형식 변환: 20260128 -> 2026-01-28
            date_str = intraday_data['date']
            formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

            # 이미 DB에 있는 날짜면 스킵
            if formatted_date in data_by_date:
                continue

            # intraday 데이터를 morning_candidates 형식으로 변환
            converted_stocks = []
            for code, stock_info in intraday_data['stocks'].items():
                converted_stocks.append({
                    'date': formatted_date,
                    'stock_code': code,
                    'stock_name': stock_info['name'],
                    'total_score': stock_info.get('selection_score', 0),
                    'selection_reason': stock_info.get('selection_reason', ''),
                    # 점수 세부사항은 intraday에 없으므로 0으로 설정
                    'disclosure_score': 0,
                    'news_score': 0,
                    'theme_score': 0,
                    'investor_score': 0,
                    'trading_value_score': 0,
                    'market_cap_score': 0,
                    'price_momentum_score': 0,
                    'volume_surge_score': 0,
                    'turnover_rate_score': 0,
                    'material_overlap_score': 0,
                    'news_timing_score': 0,
                    'matched_themes': '[]',
                    'news_mentions': 0,
                    # 가격 정보는 장 시작가 사용
                    'current_price': stock_info['profit_loss_analysis']['opening_price'],
                    'price_change_percent': 0,
                    'trading_value': 0,
                    'volume': 0,
                    'market_cap': 0
                })

            if converted_stocks:
                data_by_date[formatted_date] = converted_stocks
                intraday_count += 1

        except Exception as e:
            print(f"⚠️  {filepath} 처리 중 오류: {e}")
            continue

    # JSON 파일로 저장
    result = {
        'generated_at': format_kst_time(format_str='%Y-%m-%dT%H:%M:%S'),
        'dates': sorted(data_by_date.keys(), reverse=True),
        'data_by_date': data_by_date
    }

    output_path = 'data/history.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"✅ 히스토리 내보내기 완료: {output_path}")
    print(f"   - 날짜 수: {len(data_by_date)}일 (DB: {len(data_by_date) - intraday_count}, intraday: {intraday_count})")
    print(f"   - 총 종목 수: {sum(len(stocks) for stocks in data_by_date.values())}개")

    return output_path

if __name__ == '__main__':
    export_history()
