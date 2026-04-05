# 뉴스 트레이딩 봇 (News Trading Bot)

> **현재 단계**: 백테스팅 (전략 검증) → 모의투자 → 실매매

자동 종목 선정 및 페이퍼 트레이딩 시스템입니다. 매일 자동으로 종목을 선정하고, 실데이터 기반으로 성과를 측정하여 대시보드에 표시합니다.

---

## 프로젝트 로드맵

```
[Phase 1] 전략 수립 및 백테스팅 ◀── 현재 단계
    ↓
[Phase 2] 모의투자 (페이퍼 트레이딩)
    ↓
[Phase 3] 소액 실매매 (10~50만원)
    ↓
[Phase 4] 본격 자동매매
```

---

## 핵심 기능

### 1. 종목 선정 (매일 08:30)
- **공시 분석**: DART API로 전일~당일 공시 수집
- **뉴스 분석**: 네이버 금융 뉴스 실시간 수집
- **테마 매칭**: AI, 반도체, 2차전지 등 주요 테마 분류
- **145점 점수 시스템**: 다양한 지표 종합 평가

### 2. 성과 측정 (매일 16:30)
- **장중 데이터 수집**: 시초가, 고가, 저가, 종가
- **익절/손절 분석**: +3%/-1.5% 기준 자동 판정
- **결과 기록**: JSON 파일로 일별 데이터 축적

### 3. 대시보드 시각화
- **실시간 모니터링**: GitHub Pages로 자동 배포
- **성과 분석**: 승률, MDD, 손익비 등 통계
- **거래 내역**: 최근 거래 상세 기록

---

## 투자 전략

### 페이퍼 트레이딩 (index.html)
| 전략 | 설명 |
|------|------|
| **모멘텀** | 상승세 + 뉴스/공시 기반 |
| **대형주 역추세** | 전일 하락 대형주 반등 노림 |
| **DART 공시** | 호재 공시 발표 종목 |
| **테마/정책** | AI, 반도체 등 테마주 |

**매매 규칙**:
- 익절: +5%
- 손절: -3%
- 종가 청산: 15:20

### BNF 낙폭과대 (bnf_dashboard.html)
| 단계 | 규칙 |
|------|------|
| **진입** | -5% 이상 급락 종목 |
| **분할 매수** | 3회 분할 (1차→2차→3차) |
| **트레일링 스탑** | 고점 대비 -2% 이탈 시 |
| **분할 매도** | 반등 시 3회 분할 청산 |

---

## 점수 시스템 (145점 만점)

| 항목 | 배점 | 설명 |
|------|------|------|
| 공시 | 40점 | DART 공시 (실적, 계약, 투자) |
| 뉴스 | 25점 | 뉴스 언급 횟수 및 긍정도 |
| 테마 | 15점 | AI, 반도체, 2차전지 등 |
| 거래대금 | 15점 | tier 기반 점수 |
| 거래량급증 | 10점 | 평균 대비 급증 |
| 투자자 | 10점 | 외국인/기관 순매수 |
| 시가총액 | 10점 | tier 기반 점수 |
| 회전율 | 5점 | 거래대금/시가총액 |
| 재료중복도 | 5점 | 공시+뉴스+테마 동시 |
| 뉴스시간대 | 5점 | 장전 뉴스 우대 |
| 가격모멘텀 | 5점 | 전일 대비 등락률 |

---

## 파일 구조

```
news-trading-bot/
├── 대시보드
│   ├── index.html              # 페이퍼 트레이딩 대시보드
│   ├── bnf_dashboard.html      # BNF 낙폭과대 대시보드
│   └── system_guide.html       # 시스템 가이드
│
├── 핵심 모듈
│   ├── stock_screener.py       # 종목 선정 엔진
│   ├── intraday_collector.py   # 장중 데이터 수집
│   ├── market_data.py          # 시장 데이터
│   ├── disclosure_collector.py # DART 공시
│   ├── news_collector.py       # 뉴스 수집
│   └── investor_collector.py   # 외국인/기관
│
├── 페이퍼 트레이딩
│   └── paper_trading/
│       ├── selector.py         # 종목 선정
│       ├── simulator.py        # 시뮬레이션
│       └── checker.py          # 결과 체크
│
├── 설정
│   ├── config.py               # 점수 가중치
│   └── database.py             # SQLite 관리
│
├── 데이터
│   └── data/
│       ├── morning_candidates.json
│       ├── paper_trading/results.json
│       └── intraday/*.json
│
└── 자동화
    └── .github/workflows/
        ├── morning-scan.yml    # 08:30 종목 선정
        └── intraday.yml        # 16:30 결과 수집
```

---

## 설정 방법

### 1. DART API 키 (필수)
```bash
# GitHub Secrets 설정
DART_API_KEY=your_api_key_here
```
- [DART 오픈API](https://opendart.fss.or.kr/)에서 발급

### 2. GitHub Pages 활성화
1. Repository Settings → Pages
2. Source: Deploy from a branch
3. Branch: master, Folder: / (root)

### 3. Actions 권한 설정
1. Settings → Actions → General
2. Workflow permissions: Read and write

---

## 실행 방법

### 자동 실행 (권장)
- **08:30**: 종목 선정 자동 실행
- **16:30**: 결과 수집 자동 실행

### 수동 실행
```bash
# 종목 선정
python3 stock_screener.py

# 장중 데이터 수집
python3 intraday_collector.py
```

---

## 대시보드 URL

```
https://sungmin2nn.github.io/new_pick/
```

| 페이지 | 설명 |
|--------|------|
| `/index.html` | 페이퍼 트레이딩 대시보드 |
| `/bnf_dashboard.html` | BNF 낙폭과대 대시보드 |
| `/system_guide.html` | 시스템 가이드 |

---

## 주의사항

- 이 시스템은 **참고용 도구**입니다
- 투자 판단과 손실 책임은 **본인**에게 있습니다
- 반드시 **소액으로 시작**하세요
- 과거 성과가 미래를 보장하지 않습니다

---

## 문서

| 문서 | 설명 |
|------|------|
| [PROJECT_KNOWLEDGE_BASE.md](docs/PROJECT_KNOWLEDGE_BASE.md) | 프로젝트 히스토리, 의사결정 |
| [STRATEGY_AND_WORKFLOW.md](docs/STRATEGY_AND_WORKFLOW.md) | 전략 상세, GitHub Actions 플로우 |
| [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) | 구현 상세 |
| [system_guide.html](system_guide.html) | 사용자 가이드 |

---

## 라이선스

MIT License

---

**최종 업데이트**: 2026-04-06
