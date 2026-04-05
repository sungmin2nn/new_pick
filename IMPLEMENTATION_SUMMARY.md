# 구현 요약 (Implementation Summary)

> 시스템 구현 상세 및 현재 상태

**최종 업데이트**: 2026-04-06

---

## 현재 시스템 상태

### 운영 현황

| 구분 | 상태 | 설명 |
|------|------|------|
| 종목 선정 | **자동 실행** | 매일 08:30 |
| 결과 수집 | **자동 실행** | 매일 16:30 |
| 대시보드 | **운영 중** | GitHub Pages |
| 데이터 축적 | **진행 중** | 일별 JSON |

### 대시보드 구성

```
📊 페이퍼 트레이딩 (index.html)
    └─ 메인 대시보드, 4가지 전략

📉 BNF 낙폭과대 (bnf_dashboard.html)
    └─ 분할 매수/매도 전략

📚 가이드 (system_guide.html)
    └─ 시스템 사용법
```

---

## 점수 시스템 (145점 만점)

| 항목 | 배점 | 상태 | 데이터 소스 |
|------|------|------|-------------|
| 공시 | 40점 | 구현됨 | DART API |
| 뉴스 | 25점 | 구현됨 | 네이버 금융 |
| 거래대금 | 15점 | 구현됨 | pykrx |
| 테마 | 15점 | 구현됨 | 키워드 매칭 |
| 거래량급증 | 10점 | 구현됨 | pykrx |
| 투자자 | 10점 | 구현됨 | pykrx |
| 시가총액 | 10점 | 구현됨 | pykrx |
| 회전율 | 5점 | 구현됨 | 계산 |
| 재료중복도 | 5점 | 구현됨 | 계산 |
| 뉴스시간대 | 5점 | 구현됨 | 시간 분석 |
| 가격모멘텀 | 5점 | 구현됨 | pykrx |

---

## 자동화 시스템

### GitHub Actions 워크플로우

```yaml
# 종목 선정 (morning-scan.yml)
schedule: "30 23 * * 0-4"  # UTC (= KST 08:30)
작업:
  1. Python 환경 설정
  2. stock_screener.py 실행
  3. morning_candidates.json 생성
  4. GitHub Pages 배포

# 결과 수집 (intraday.yml)
schedule: "30 7 * * 1-5"  # UTC (= KST 16:30)
작업:
  1. intraday_collector.py 실행
  2. 장중 데이터 수집
  3. 익절/손절 분석
  4. 결과 JSON 저장
```

---

## 주요 파일

### 핵심 실행 파일

| 파일 | 역할 | 실행 시점 |
|------|------|----------|
| stock_screener.py | 종목 선정 엔진 | 매일 08:30 |
| intraday_collector.py | 장중 데이터 수집 | 매일 16:30 |

### 데이터 수집 모듈

| 파일 | 역할 |
|------|------|
| market_data.py | 시장 데이터 (pykrx) |
| disclosure_collector.py | DART 공시 수집 |
| news_collector.py | 네이버 금융 뉴스 |
| investor_collector.py | 외국인/기관 수급 |

### 설정 및 유틸

| 파일 | 역할 |
|------|------|
| config.py | 점수 가중치, 테마 키워드 |
| database.py | SQLite 관리 |
| export_history.py | 히스토리 JSON 출력 |

### 대시보드

| 파일 | 설명 |
|------|------|
| index.html | 페이퍼 트레이딩 대시보드 |
| bnf_dashboard.html | BNF 낙폭과대 대시보드 |
| system_guide.html | 시스템 가이드 |

### JavaScript 모듈

```
js/
├── api.js        # API 호출
├── charts.js     # 차트 컴포넌트
├── config.js     # 설정
├── dashboard.js  # 대시보드 로직
├── table.js      # 테이블 렌더링
└── utils.js      # 유틸리티
```

---

## 데이터 구조

### 종목 선정 결과 (morning_candidates.json)

```json
{
  "date": "2026-04-06",
  "candidates": [
    {
      "code": "005930",
      "name": "삼성전자",
      "price": 72000,
      "total_score": 85,
      "disclosure_score": 40,
      "news_score": 20,
      "theme_score": 15,
      "selection_reason": "실적 개선 공시 + AI 테마"
    }
  ]
}
```

### 장중 데이터 (intraday_YYYYMMDD.json)

```json
{
  "date": "20260406",
  "stocks": {
    "005930": {
      "code": "005930",
      "name": "삼성전자",
      "open_price": 72000,
      "high_price": 74500,
      "low_price": 71500,
      "close_price": 73800,
      "profit_loss_analysis": {
        "first_hit": "profit",
        "profit_hit_time": "09:42",
        "closing_percent": 2.5
      }
    }
  }
}
```

### 페이퍼 트레이딩 결과 (results.json)

```json
{
  "daily_results": [
    {
      "date": "20260406",
      "total_trades": 5,
      "wins": 3,
      "losses": 1,
      "close_exits": 1,
      "total_return": 2.5,
      "win_rate": 60,
      "cumulative_return": 15.3
    }
  ]
}
```

---

## 매매 규칙

### 페이퍼 트레이딩

```
[진입]
- 시점: 시초가 (09:00~09:05)
- 종목: 점수 상위 5개
- 금액: 종목당 20만원

[청산]
- 익절: +5% 도달
- 손절: -3% 도달
- 시간 청산: 15:20 (미도달 시)
```

### BNF 낙폭과대

```
[진입 조건]
- 전일 -5% 이상 급락
- 거래대금 500억 이상

[분할 매수]
- 1차: -5% → 30%
- 2차: -7% → 40%
- 3차: -10% → 30%

[청산]
- 트레일링 스탑: 고점 -2%
- 분할 매도: +3%, +5%, +7%
```

---

## 외부 API

### DART API
- **용도**: 공시 데이터 수집
- **설정**: GitHub Secrets → DART_API_KEY
- **문서**: https://opendart.fss.or.kr/

### pykrx
- **용도**: 시장 데이터, 수급 데이터
- **설치**: requirements.txt에 포함
- **주의**: KRX 서버 상태에 따라 오류 발생 가능

### 네이버 금융
- **용도**: 뉴스 수집
- **방식**: 웹 스크래핑
- **주의**: 사이트 구조 변경 시 수정 필요

---

## 문제 해결

### 공시 점수 0점
```
원인: DART_API_KEY 미설정 또는 공시 없음
해결:
1. GitHub Secrets 확인
2. 해당 시간대 공시 유무 확인
```

### 데이터 수집 실패
```
원인: pykrx/네이버 서버 오류
해결:
1. 잠시 후 재시도
2. 로그 확인 후 수동 실행
```

### 대시보드 캐시
```
원인: 브라우저 캐시
해결:
1. 강제 새로고침 (Ctrl+Shift+R)
2. CSS/JS에 ?v=버전 파라미터 추가
```

---

## 변경 이력

### 2026-04-06
- 백테스트 관련 파일 삭제 (backtest_dashboard.html, analytics.js 등)
- 문서 전면 개편

### 2026-04-05
- 대시보드 업그레이드
- BNF 테마 스타일 적용

### 2026-01-29
- 145점 점수 시스템 완성
- 시스템 가이드 추가
- GitHub Actions 자동화

---

## 다음 단계

### 진행 중
- [x] 데이터 축적 (자동 실행)
- [ ] 주간 리포트 확인

### 예정
- [ ] 1개월 데이터 분석
- [ ] 전략별 성과 비교
- [ ] 모의투자 시작

---

**마지막 업데이트**: 2026-04-06
