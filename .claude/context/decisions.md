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

## team_b (Beta Contrarian) 비활성화 (2026-04-19)

**결정**: `data/arena/strategy_config.json`에서 `largecap_contrarian.enabled = false`. team_b는 더 이상 장전 종목 선정/매매를 수행하지 않으며, leaderboard에서 `archived_teams`로 이동.

**배경**:
- 4/10 ~ 4/17 8거래일 연속 운영 결과: 총 31거래, 승 5 / 패 26, 승률 8.6%
- 누적 수익률 -15.93%, 8일 연속 손실일, ELO 1000 → 780
- 최근 3일 모두 최하위 랭킹 (4/16 rank 6, 4/17 rank 6, 그 전부터 rank 4~5 지속)
- 2026-04 시장은 명백한 상승장 — RSI≤35 역발상 진입 조건이 구조적으로 역풍을 맞는 환경

**대안**:
- **파라미터 조정 후 재활성화** (RSI 임계값 완화, 시장모드 필터 강화): 기각 — 근본 원인이 "전략 철학 vs 현재 시장국면"의 미스매치라 파라미터 튜닝으로는 해결 안 됨. 하락장/횡보장 전환 신호가 확인되면 그때 복귀 검토.
- **유지** (ELO 자체 보정을 기다림): 기각 — 매일 자본 손실이 실제로 발생하는 paper trading이라 기회비용 큼.

**근거**: 8팀 체제(a/c/d/e/f/g/h/i)로 전략 다양성 확보됨. team_e(frontier_gap), team_f(volatility), team_g(turtle), team_h(sector)가 이미 활성화되어 있어 역발상 슬롯의 공백이 즉시 문제되지 않음.

**영향**:
- Arena 운영 팀 수: 9팀 → 8팀 (team_b 제외)
- 레거시 문서(`.claude/commands/arena.md`, `.claude/harness/registry.md`)의 "4팀 a/b/c/d" 서술은 별도 정리 필요
- leaderboard.json 구조 변경: `archived_teams` 키 추가. 대시보드가 이 섹션을 별도 렌더링하도록 추후 조정 고려.

**복귀 조건**:
- KOSPI 추세 전환 (예: 20일선 하향 이탈 + RSI 30 이하 저점 형성)
- 또는 전략 자체를 새 카테고리로 재설계 (예: 변동성 축소 + 공매도 잔고 급증 조합)

---

## 데이터 정합성 인프라 4종 도입 (2026-04-30 ~ 05-01)

`verify_facts.py` 가 자동 등재한 ISSUE-015~018 일괄 처리. 한 세션에서 누적 결함의 근본 원인 → 가드 → 보정 → 검증을 일관 적용했다. 4건 모두 운영 중 발견된 실제 결함이며, 해결책은 모두 코드 + 데이터 + 검증 도구 3축으로 적용됨.

### 1) Arena run_daily 멱등성 가드 (ISSUE-015/018, f39ea2e + 7333e69)

**결정**: `arena_manager.run_daily()` 진입점에 `daily/<date>/arena_report.json` 존재 체크 → skip + `--force` 플래그. 1회성 정정 스크립트 `scripts/dedupe_arena_data.py` 로 누적 데이터 재구성.

**배경**:
- 04-30 운영 후 verify_facts 가 W_DUPLICATE_RUNS, W_TRADE_COUNT_MISMATCH 등재.
- portfolio.update_after_day 의 `+=` 연산자와 `leaderboard.daily_history.append`, ELO 라운드로빈 업데이트 등 9곳이 중복 호출 시 이중 누적되는 구조.
- 04-10 에 1회, 04-30 에 2회 (cron + 수동 workflow_dispatch) 중복 실행 발견 → team_a/b/c/d 에서 5~10건씩 거래수 차이.

**대안 비교**:
- (a) `_load_portfolio` 에서 daily 기반 자동 보정 (issues.md 권고 2): 기각 — 매 로드마다 전 일자 trades.json 합산 비용 + 일관성 검증 부담. 진입점 1회 차단이 더 작은 수술.
- (b) `force=True` 시 자동 dedupe 후 재실행: 기각 — 복잡도 큼, 사용자가 명시적으로 dedupe 후 재실행하는 게 안전. force 시 경고만 출력.
- (c) 그대로 두고 운영자 규칙으로 해결: 기각 — 2026-04-30 자체가 그 규칙이 깨진 사례.

**근거**: 누적 지점 9곳을 모두 idempotent 하게 만드는 비용보다, 진입점 1곳 차단이 훨씬 작고 검증 가능. 이미 `daily/<date>/arena_report.json` 가 사실상 "그 날 실행됨" 의 자연스러운 마커.

**영향**:
- Arena cron + 수동 디스패치 동시 발생해도 두 번째는 `status: skipped, reason: already_run` 으로 종료
- dedupe 스크립트 적용 결과: team_a 85→80건 / team_d 85→75건 / leaderboard 18→15 entries / 8팀 ELO 재조정 (team_a 1241→1188, team_f 1025→908 등)
- 백업: `*.backup_YYYYMMDD_HHMMSS` (.gitignore 추가)

**검증 대기**: 2026-05-04 (월) 16:10 KST cron + 수동 재실행 시도 시 "skip" 메시지 출력 확인.

### 2) 시뮬레이터 슬리피지 0.2% 도입 (ISSUE-016/017, c2a625a)

**결정**: `TradingSimulator.SLIPPAGE_PCT = 0.2` 신규 상수. 진입가 +0.2%, 룰 기반 청산가(trailing/profit/loss 폴백) -0.2%. 종가 청산 및 분봉 first_hit_price 는 시장가 그대로.

**배경**:
- 운영 5일 이상 팀의 자본 MDD가 비현실적으로 낮음 (team_a 0.04%, team_e 0%).
- trades.json 검사 결과 손절가가 정확히 -3.0%, 트레일링/익절가도 정확한 % 단위로 체결됨.
- 시뮬에 호가/체결률 모형 부재 → "이상적 가격 매매" 환각.

**대안 비교**:
- (a) 슬리피지 정적 ±0.2% (선택): 결정적, 같은 입력 같은 결과. 단순/안전.
- (b) 확률적 슬리피지 (정규분포 등): 기각 — 결정적 백테스트 비교 어려워짐, 단기 운영용엔 과도.
- (c) KIS 모의투자로 전면 대체: 기각 — 도입 비용 큼, 별도 트랙(broker/kis/)으로 진행 예정.

**적용 제외 이유**:
- **종가 청산('close')**: 실제로 종가는 시장이 정한 값이라 그 가격에 매도 가능 (실 종가 매도)
- **분봉 first_hit_price**: 이미 시장 호가가 반영된 실제 터치 가격이라 추가 슬리피지 부적절

**근거**: 한국 주식 시장의 호가 단위(틱) + 체결 지연 + 시장 충격을 합산하면 0.1~0.3% 수준. 0.2% 는 보수적 중간값. 왕복 0.4% 는 일평균 ~5종목 매매 시 연간 약 100% 영향이라 실거래 비교에 충분한 마진.

**verify_facts 통합**: `W_SIM_NO_SLIPPAGE` 무조건 발행 → `TradingSimulator.SLIPPAGE_PCT == 0` 일 때만 발행하도록 동적 검사. 누군가 SLIPPAGE_PCT 를 0으로 되돌리면 자동 재발행.

### 3) ISSUE-017 자연 해소 대기 (옵션 A, c2a625a)

**결정**: 코드 fix 후 issues.md 상태를 `resolved` 가 아닌 `code_applied` 로 표시. 기존 trades.json 은 손대지 않고, 향후 거래일 누적으로 W_SUSPICIOUS_LOW_MDD 자연 해소를 기다림.

**대안 비교**:
- (a) 자연 해소 대기 (선택): 데이터 정직성 — 슬리피지 부재 시점의 trades.json 은 "그 시점 사실"로 보존.
- (b) 강제 close + verify_facts 임계치 조정: 기각 — 검증 기능 약화, 과거 데이터에 사후 보정 흔적 남김.
- (c) 메시지 수정 ("코드 fix 적용됨"): 기각 — 반쪽 해결, 사용자에게 혼란.

**근거**: 며칠 운영하면 슬리피지 적용된 새 거래가 누적되어 자본 MDD 가 0.1% 이상으로 자연 상승, 경고 자동 사라짐. 인위적 보정보다 시간이 해결.

**Trade-off**: 며칠간 W_SUSPICIOUS_LOW_MDD 2건 (team_a, team_e) 계속 보임. 사용자에게는 "이미 해결된 사안" 임을 issues.md 의 `code_applied` 상태와 state.json 의 `code_applied_pending_natural_resolve` 섹션으로 명시.

### 4) BNF/Bollinger 동일 테마 중복 캡 (d83da08)

**결정**: `MAX_PER_THEME = 2` (BNF/Bollinger 각각 클래스/모듈 상수, A/B 토글 가능). `paper_trading/utils/theme_cap.py` 의 `apply_theme_cap()` 헬퍼로 정렬된 후보 리스트에서 같은 테마 N개 초과 시 차단. 종목→테마 역인덱스(`data/theme_cache/_stock_to_themes.json`, 200테마/2189종목) 기반.

**배경**:
- team_d (theme_policy) 의 동일 그룹 캡 (`c38d53c`) 효과 검증됨. 같은 패턴을 다른 전략에도 적용 가능성 높음.
- BNF/Bollinger 가 낙폭 큰 순/볼린저 하단 순으로 정렬할 때 같은 섹터/테마 종목이 상위 5위 모두 차지하는 케이스가 종종 발생 → 분산 효과 상실.

**대안 비교**:
- (a) 정적 스냅샷 (`_stock_to_themes.json`, 선택): 빌드 1회 + 캡 적용 비용 거의 0. 단점: 신규 상장/테마 변동 반영 지연.
- (b) 매일 동적 빌드: 기각 — 60초 fetch 비용 매일 누적, ROI 낮음.
- (c) 시점별 스냅샷 + backtest 시 해당 시점 사용: 기각 — 인프라 복잡도 폭증, 단기 운영용엔 과도.

**근거**: backtest 의 lookahead bias 가능성은 있으나 단기 운영 (≤30일) 에서 테마 정의 자체는 거의 안 변함. 실용적 절충.

**graceful degrade**: 인덱스 파일 부재/깨짐 → 캡 비활성, 후보 그대로 통과. 인덱스에 없는 종목 → 캡 미적용 통과. 모든 실패 경로가 "캡 비활성" 으로 수렴.

**검증**: apply_theme_cap 단위 테스트 3건 통과 (cap=None 통과 / cap=2 + 5종목 same-theme → 정확히 2건 통과 + 3건 차단 / 인덱스 부재 종목 통과).

**Trade-off**: max_per_theme=2 가 너무 빡빡할 가능성. 운영 후 후보 풀이 자주 부족해지면 3 또는 None 으로 토글 검토.

---

## 참고 자료

- Sharpe Ratio: Sharpe, W. F. (1966). "Mutual Fund Performance"
- Sortino Ratio: Sortino, F. & Price, L. (1994)
- Calmar Ratio: Young, T. W. (1991)
- Chart.js Docs: https://www.chartjs.org/docs/latest/
