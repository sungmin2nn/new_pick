# 프로젝트 의사결정 기록

## Arena 정상화 + 레거시 폐지 결정 (2026-04-10)

### 1. 4팀 1,000만원 동시 리셋

**결정**: team_a, team_b, team_c, team_d 모두 portfolio.json을 1,000만원으로 동시 리셋. leaderboard ELO 1000 초기화, daily_history 비움.

**배경**:
- ISSUE-004로 momentum/contrarian/dart는 만성 0종목 → team_a/b만 매매하던 불공정 상태
- team_c/d는 portfolio.json 자체가 없었음 (ISSUE-005)
- 04-09 1일치 결과(team_a +24%, team_b -12%)는 team_c/d 부재 환경의 산물 → 통계적 의미 없음

**대안**: team_a/b 결과 보존 + team_c/d만 신규 초기화. 기각 — 시작 시점 불공정.

**근거**: ELO 시스템은 동일 시작 조건에서 통계 의미. 정상화된 파이프라인 위에서 처음부터 공정 경쟁.

---

### 2. paper-trading-select cron 16:30 KST로 이동 (장 마감 후)

**결정**: cron `0 23 * * 0-4` (08:00 KST) → `30 7 * * 1-5` (16:30 KST)

**배경**:
- 08:00 KST는 KOSPI 개장(09:00) 이전 — naver finance pre-market 데이터는 등락률 0 또는 stale
- 04-08, 04-09, 04-10 연속 0종목 선정 (momentum/contrarian/dart)
- 사용자 의도: "장시작 전 종목 선정" — 의미상 "다음 거래일 시초가 매매용 후보 선정"
- 16:30 (장 마감 15:30 + 30분 버퍼)는 naver 종가 안정화 + 다음 거래일 매매까지 17시간 분석 여유

**대안**: 09:30 KST (개장 후 30분). 기각 — 이미 매매가 시작된 후라 장전 종목 선정 의미 상실.

---

### 3. 레거시 1세대 모닝스캔 시스템 폐지 (Phase 1)

**결정**: morning-scan.yml + afternoon-collect.yml + 14개 Python 모듈 + auto_reporter 산출물 삭제 예정 (검증 후)

**삭제 대상**:
- 워크플로우: morning-scan.yml, afternoon-collect.yml
- Python: stock_screener, database, disclosure_collector, investor_collector, market_data, market_sentiment, naver_investor, news_collector, technical_analysis, export_history, auto_reporter, paper_trading/scheduler.py
- HTML: system_guide.html
- 산출물: data/dashboard_report.html (stale), data/project_report.html (없음), data/knowledge_base.json (없음)

**유지 대상**:
- Arena 전체 (`paper_trading/arena/`, `strategies/`, `multi_strategy_runner.py`, `simulator.py`, `selector.py`, `checker.py`)
- BNF 전체 (`paper_trading/bnf/`)
- 공통: naver_market.py, intraday_collector.py, telegram_notifier.py, error_logger.py, utils.py, project_logger.py, config.py
- 대시보드: index.html (Arena), bnf_dashboard.html

**배경**:
- 1세대(모닝스캔) → 2세대(BNF) → 3세대(Arena) 진화 과정에서 1세대 비활성화 누락
- 사용자가 1세대 운영 중인 사실을 모르고 있었음 (ISSUE-007)
- 매일 6+회 미인지 워크플로우 실행 → GitHub Actions 부하, git log 오염

**검증 절차** (실행 중):
- Agent A (audit-agent, L1): 의존성 추적 + mv 시뮬레이션
- Agent B (backtest-agent, L2): pykrx 04-01~04-10 보강+신규 전략 백테스트
- Agent C (test+cicd, L3): GitHub end-to-end 체크리스트 작성

**리스크**: paper-trading.yml의 try/except로 감싼 AutoReporter 호출 1곳. 삭제 전 제거 필요.

---

### 4. Arena 6팀 확장 로드맵 (Phase 2 + Phase 3)

**결정**: 단타 framework 직교성 분석 후 신규 2팀 추가 (총 6팀). Team G(변동성 돌파)는 보류.

**6팀 구성**:
| # | 팀 | 분류 | 보강/신규 |
|---|---|---|---|
| 1 | Alpha Momentum | Trend | 보강 (MA5, 거래량 배수) |
| 2 | Beta Contrarian | Mean Reversion | 보강 (RSI, 시장모드) |
| 3 | Gamma Disclosure | Catalyst | 보강 (시점가산, 시너지) |
| 4 | Delta Theme | Sector | 보강 (대장주, 수급) |
| 5 | **Echo Flow** | **Order Flow** | **신규** (외국인+기관 동반 순매수) |
| 6 | **Frontier Gap** | **Gap Trading** | **신규** (시초가 갭 + 골든타임) |

**근거**:
- 단타 framework 8개 카테고리 중 1~7번 실현 가능, 5(Order Flow)/6(Gap)/7(Volatility)이 빠진 영역
- ELO 안정성: 6팀 = 15쌍 매칭 (충분한 통계, 너무 복잡하지 않음)
- 신호 직교성: Echo Flow와 Frontier Gap은 기존 4팀과 신호 거의 안 겹침
- 전문 자료 (Andrew Aziz, Linda Raschke, Market Wizards): Gap-up + High Relative Volume이 단타 #1 setup, 외국인 매수 동반이 한국 시장 가장 안정적

**보류**: Team G(Volatility Breakout, Larry Williams) — Team A momentum과 부분 상관, Phase 2 결과 보고 변별력 부족 시 추가.

**기각**: News Momentum (Team C와 신호 겹침 → Team C 보강으로 흡수), VWAP (분봉 정밀도 한계), Pair Trading (단타 부적합), Scalping (시뮬레이션 한계).

---

### 5. 검증 우선 원칙

**결정**: 모든 작업 전 1차(local agent) + 2차(GitHub end-to-end) 검증 필수

**배경**: 사용자 명시 — "삭제작업을 해도 문제없는 지 돌려본다", "전략을 4월1일부터의 네이버 데이터를 파악해서 검증". 사용자 요청 — "에이전트를 통해서 해줘", "하네스 프로세스도 활용하고"

**프로세스**:
1. 1차: Agent A/B/C 병렬 실행, local에서 수행
2. 2차: GitHub Actions 실제 실행 + 사용자가 체크리스트 따라 수동 검증 (트리거→데이터→대시보드→텔레그램)
3. 양 단계 통과 후 작업 진행

---

## 대시보드 개선 (2026-04-05)

### 1. 리스크 지표 선정

**결정**: Sharpe Ratio, Sortino Ratio, Calmar Ratio를 핵심 지표로 선정

**배경**:
- 전문 투자 분석 프로그램 수준의 대시보드 구축 필요
- 리스크 조정 수익률 평가가 백테스트 핵심

**선정 근거**:
- **Sharpe Ratio**: 업계 표준 위험조정수익률 지표, 전체 변동성 대비 초과수익률 측정
- **Sortino Ratio**: 하방 위험만 고려, 상방 변동성 제외로 더 정확한 위험 평가
- **Calmar Ratio**: 연간 수익률 / 최대낙폭(MDD), 극단적 손실 대비 수익성 평가
- **추가 지표**: MDD, Alpha, Beta, Win Rate, Profit Factor 등 15개 지표 포함

**대안**:
- Information Ratio: 벤치마크 대비 초과수익 평가 (현재 보류, 향후 추가 가능)
- Omega Ratio: 복잡도 높음, 우선순위 낮음

**영향**:
- analytics.js에 15개 함수 구현
- 대시보드에 8개 핵심 통계 카드 표시

---

### 2. 벤치마크 데이터 방식

**결정**: 정적 JSON 파일 방식 채택 (40일 KOSPI 데이터)

**배경**:
- Alpha, Beta 계산에 시장 수익률(KOSPI) 필요
- 실시간 API vs 정적 데이터 선택 필요

**선정 근거**:
- **정적 JSON 장점**:
  - 빠른 로딩 속도 (네트워크 요청 불필요)
  - 오프라인 동작 가능
  - API 의존성 제거 (장애 위험 없음)
  - 백테스트 기간과 일치하는 데이터 보장

- **API 방식 단점**:
  - 네트워크 지연
  - API 키 관리 필요
  - 장애 시 대시보드 전체 오류
  - CORS 문제 가능성

**구현**:
- benchmark.js에 40일 KOSPI 데이터 하드코딩
- 7개 함수 제공: getKOSPIData, getKOSPIReturns, calculateBeta, calculateAlpha 등
- 데이터 기간: 2024-01-02 ~ 2024-02-28 (실제 백테스트 기간과 동기화 필요)

**향후 개선**:
- 백테스트 결과 JSON에 벤치마크 데이터 포함 검토
- 데이터 업데이트 자동화 스크립트 추가 가능

---

### 3. 차트 라이브러리

**결정**: Chart.js 4.x 사용

**배경**:
- 기존 대시보드가 Chart.js 사용 중
- 4개 신규 차트 추가 필요 (Drawdown, Heatmap, Benchmark, Histogram)

**선정 근거**:
- **Chart.js 장점**:
  - 기존 코드베이스와 일관성 유지
  - 경량 (번들 크기 작음)
  - 문서화 우수
  - 금융 차트 구현 충분히 가능

- **대안 검토**:
  - D3.js: 과도한 러닝 커브, 오버엔지니어링
  - Plotly.js: 번들 크기 큼 (3MB+)
  - ApexCharts: Chart.js와 기능 중복, 마이그레이션 비용 높음

**구현**:
- charts.js에 4개 차트 컴포넌트 추가
- createDrawdownChart: 시간별 낙폭 시각화
- createMonthlyHeatmap: 월별 수익률 히트맵
- createBenchmarkChart: 전략 vs KOSPI 비교
- createReturnsHistogram: 수익률 분포 히스토그램

**커스터마이징**:
- 금융 특화 컬러 스킴 (녹색=수익, 빨강=손실)
- 툴팁 포맷팅 (%, KRW)
- 반응형 디자인

---

### 4. 아키텍처 구조

**결정**: 모듈화된 3-Layer 구조

**구조**:
```
Layer 1 (데이터): benchmark.js, backtest 결과 JSON
    ↓
Layer 2 (계산): analytics.js (15개 지표 함수)
    ↓
Layer 3 (시각화): charts.js (4개 차트), dashboard.js (UI 업데이트)
    ↓
Layer 4 (통합): backtest_dashboard.html (8개 카드 + 4개 차트 섹션)
```

**장점**:
- 관심사 분리 (SoC)
- 재사용성 (analytics.js 함수 독립적)
- 테스트 용이성
- 유지보수성

**파일 역할**:
- `analytics.js`: 순수 함수 (입력 → 계산 → 출력), 부수효과 없음
- `charts.js`: Chart.js 래퍼, 차트 생성만 담당
- `benchmark.js`: KOSPI 데이터 제공자
- `dashboard.js`: DOM 조작, 이벤트 핸들링

---

## 품질 이슈 및 해결

### Critical 이슈 (req-dashboard-005)

**발견 이슈** (audit-agent):
1. Sharpe Ratio 계산 단위 불일치 (일간 수익률 → 연간화 필요)
2. Sortino Ratio 계산 단위 불일치
3. Alpha 계산 단위 불일치

**해결** (req-dashboard-006):
- 모든 지표에 연간화 계수 적용: `√252` (주식 시장 연간 거래일)
- 공식 수정:
  - Sharpe = (평균수익률 - 무위험수익률) / 표준편차 × √252
  - Sortino = (평균수익률 - 목표수익률) / 하방편차 × √252
  - Alpha = (전략수익률 - 무위험수익률) - Beta × (시장수익률 - 무위험수익률) (연간화)

**검증**:
- 업계 표준 공식과 일치 확인
- 단위 테스트 통과
- 예상 범위 내 값 출력 (Sharpe: -3 ~ 3)

---

## 기술 스택

- **프론트엔드**: HTML5, CSS3, Vanilla JavaScript (ES6+)
- **차트**: Chart.js 4.4.0
- **데이터**: JSON (정적 파일)
- **배포**: 정적 사이트 (Node.js 서버 불필요)

---

## 다음 단계 (향후 개선)

1. **실시간 데이터 연동** (우선순위: 중)
   - 백테스트 결과 JSON에 벤치마크 데이터 포함
   - Python 백테스트 엔진에서 KOSPI 데이터 자동 수집

2. **추가 차트** (우선순위: 낮)
   - Underwater Chart (회복 기간 시각화)
   - Rolling Sharpe Ratio (시간별 Sharpe 변화)

3. **인터랙티브 기능** (우선순위: 중)
   - 날짜 범위 선택
   - 지표 on/off 토글
   - 차트 확대/축소

4. **성능 최적화** (우선순위: 낮)
   - 차트 렌더링 지연 로딩
   - 대용량 데이터 가상화

---

## 참고 자료

- Sharpe Ratio: Sharpe, W. F. (1966). "Mutual Fund Performance"
- Sortino Ratio: Sortino, F. & Price, L. (1994)
- Calmar Ratio: Young, T. W. (1991)
- Chart.js Docs: https://www.chartjs.org/docs/latest/
