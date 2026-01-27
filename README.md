# 🔮 장전 종목 선정 시스템

매일 아침 08:30에 자동으로 실행되어 당일 주목할 종목을 선정하는 시스템입니다.

## 📋 주요 기능

### 1. 자동 스크리닝
- **실행 시간**: 매일 08:30 (GitHub Actions)
- **대상**: 코스피/코스닥 전종목
- **필터링**: 거래대금, 상승률, 시가총액, 거래량 기준

### 2. 필터링 조건
- 거래대금 ≥ 1,000억원
- 상승률 ≥ +3%
- 시가총액 ≥ 1,000억원
- 주가 ≤ 10만원
- 거래량 급증 (평균 대비 1.5배 이상)

### 3. 점수 시스템 (100점 만점)
- **가격 모멘텀** (30점): 상승률 기반 점수
- **거래량** (25점): 평균 거래량 대비 배수
- **테마/키워드** (25점): AI, 반도체, 2차전지 등 주요 테마
- **뉴스** (20점): 뉴스 언급 빈도

### 4. 결과 저장
- JSON 파일 저장 (`data/morning_candidates.json`)
- SQLite 데이터베이스 저장
- 대시보드를 통한 시각화

## 🚀 설치 및 실행

### 로컬 실행

```bash
# 의존성 설치
pip install -r requirements.txt

# 스크리너 실행
python stock_screener.py

# 대시보드 열기
open index.html
```

### GitHub Actions 설정

1. 리포지토리를 GitHub에 푸시
2. Settings → Actions → General에서 Workflow permissions를 "Read and write permissions"로 설정
3. 매일 08:30에 자동 실행됨

## 📊 데이터 구조

### JSON 출력 형식

```json
{
  "generated_at": "2024-01-27T08:30:00",
  "date": "2024-01-27",
  "count": 20,
  "candidates": [
    {
      "code": "005930",
      "name": "삼성전자",
      "current_price": 75000,
      "price_change_percent": 5.2,
      "trading_value": 150000000000,
      "volume": 20000000,
      "market_cap": 500000000000000,
      "total_score": 85,
      "score_detail": {
        "price_momentum": 25,
        "volume": 20,
        "theme_keywords": 20,
        "news": 20
      }
    }
  ]
}
```

### 데이터베이스 스키마

```sql
CREATE TABLE morning_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    stock_code TEXT NOT NULL,
    stock_name TEXT NOT NULL,
    current_price REAL,
    price_change_percent REAL,
    trading_value REAL,
    volume REAL,
    market_cap REAL,
    total_score REAL,
    price_score REAL,
    volume_score REAL,
    theme_score REAL,
    news_score REAL,
    matched_themes TEXT,
    news_mentions INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE(date, stock_code)
);
```

## 🎯 사용 방법

### 대시보드

1. `index.html` 파일을 브라우저로 열기
2. 날짜 선택으로 과거 데이터 조회
3. 최소 점수 필터로 종목 필터링
4. 컬럼 클릭으로 정렬

### Python API

```python
from database import Database

# 데이터베이스 초기화
db = Database()

# 오늘 선정 종목 조회
today_candidates = db.get_candidates_by_date('2024-01-27')

# 최근 7일 데이터 조회
recent = db.get_recent_candidates(days=7)

# JSON으로 내보내기
db.export_to_json(date='2024-01-27', output_path='output.json')
```

## 🔧 설정 변경

`config.py` 파일에서 다음 항목들을 수정할 수 있습니다:

- 필터링 기준값
- 점수 배점
- 테마 키워드
- 선정 종목 수

## 📈 향후 개선 계획

- [ ] 실시간 API 연동 (한국투자증권, 키움증권 등)
- [ ] 백테스팅 기능 추가
- [ ] 알림 기능 (텔레그램, 이메일)
- [ ] 상세 차트 및 분석 추가
- [ ] 모바일 앱 개발

## 📝 라이선스

MIT License

## 🤝 기여

이슈 및 풀 리퀘스트는 언제든 환영합니다!
