"""
과거 데이터를 JSON으로 내보내는 스크립트
GitHub Pages에서 사용할 수 있도록 최근 30일 데이터를 JSON 파일로 생성
"""

import json
from datetime import datetime
from database import Database

def export_history():
    """최근 30일 데이터를 JSON으로 내보내기"""
    db = Database()

    # 최근 30일 데이터 조회
    recent_data = db.get_recent_candidates(days=30)

    # 날짜별로 그룹화
    data_by_date = {}
    for item in recent_data:
        date = item['date']
        if date not in data_by_date:
            data_by_date[date] = []
        data_by_date[date].append(item)

    # JSON 파일로 저장
    result = {
        'generated_at': datetime.now().isoformat(),
        'dates': sorted(data_by_date.keys(), reverse=True),
        'data_by_date': data_by_date
    }

    output_path = 'data/history.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"✅ 히스토리 내보내기 완료: {output_path}")
    print(f"   - 날짜 수: {len(data_by_date)}일")
    print(f"   - 총 종목 수: {len(recent_data)}개")

    return output_path

if __name__ == '__main__':
    export_history()
