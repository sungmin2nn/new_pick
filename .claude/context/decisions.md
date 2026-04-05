# 프로젝트 의사결정 기록

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
