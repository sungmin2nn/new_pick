# Analytics.js - 추가된 전문 리스크 지표 함수

## 구현 완료 (2026-04-05)

### 1. 리스크 조정 수익률 지표

#### calculateSharpeRatio(trades, riskFreeRate = 0.035)
- **목적**: 위험 대비 수익률 측정
- **공식**: (평균수익률 - 무위험수익률) / 표준편차
- **환산**: 일간 → 연간 (√252)
- **기본값**: 무위험수익률 3.5% (연)
- **해석**: 
  - > 1.0: 양호
  - > 2.0: 우수
  - > 3.0: 매우 우수

#### calculateSortinoRatio(trades, riskFreeRate = 0.035)
- **목적**: 하락 위험만 고려한 수익률 측정
- **공식**: (평균수익률 - 무위험수익률) / 하락편차
- **특징**: 상승 변동성 제외, 손실 변동성만 패널티
- **해석**: Sharpe 대비 일반적으로 높은 값

#### calculateCalmarRatio(trades, initialCapital, finalCapital, years)
- **목적**: 최대 낙폭 대비 복리 수익률
- **공식**: CAGR / |MDD|
- **CAGR**: ((최종/초기)^(1/년) - 1) × 100
- **해석**: 
  - > 0.5: 양호
  - > 1.0: 우수
  - > 3.0: 매우 우수

### 2. 리스크 측정 지표

#### calculateMaxDrawdown(trades, initialCapital)
- **목적**: 최대 낙폭 계산
- **공식**: min((자본 - 최고점) / 최고점) × 100
- **반환**: 음수 (%)
- **해석**: -10% 이내 권장, -20% 초과 시 위험

#### calculateMaxConsecutiveLosses(trades)
- **목적**: 최대 연속 손실 횟수
- **특징**: 'loss' 결과만 카운트, 'none'은 유지
- **해석**: 5회 이하 권장, 10회 초과 시 전략 재검토

### 3. 시계열 분석 함수

#### calculateDrawdownSeries(equityCurve)
- **목적**: 드로우다운 시계열 생성 (차트용)
- **입력**: [{ date, capital }, ...]
- **출력**: [{ date, capital, peak, drawdown }, ...]
- **활용**: 
  - 드로우다운 차트 시각화
  - 회복 기간 분석

#### calculateMonthlyReturns(trades)
- **목적**: 월별 수익률 계산 (히트맵용)
- **출력**: [{ yearMonth, year, month, tradesCount, returnPercent }, ...]
- **활용**: 
  - 월별 성과 히트맵
  - 계절성 패턴 분석

### 4. 분포 분석 함수 (개선)

#### analyzeReturnDistribution(trades)
- **개선점**: 
  - 10 → 16개 버킷으로 세분화
  - 통계량 추가 (왜도, 첨도)
- **출력**: 
  ```javascript
  {
    distribution: [{ bucket, count, percentage }, ...],
    stats: { mean, median, stdDev, skewness, kurtosis }
  }
  ```
- **활용**: 
  - 히스토그램 차트
  - 정규분포 대비 검증

### 5. 벤치마크 비교 함수

#### calculateAlphaBeta(strategyReturns, benchmarkReturns, riskFreeRate = 0.035)
- **목적**: 시장 대비 성과 측정
- **Alpha**: 시장 대비 초과 수익률
  - 공식: Rs - (Rf + β × (Rm - Rf))
  - 양수: 시장 초과 수익
- **Beta**: 시장 민감도
  - 공식: Cov(Rs, Rm) / Var(Rm)
  - < 1: 시장보다 변동성 낮음
  - = 1: 시장과 동일
  - > 1: 시장보다 변동성 높음
- **Correlation**: 상관계수 (-1 ~ 1)

### 6. 보조 함수

#### calculateTradingDays(trades)
- 거래일 수 계산 (중복 제거)

#### calculateCorrelation(arr1, arr2)
- 피어슨 상관계수 계산

#### calculateMedian(arr)
- 중앙값 계산

#### calculateSkewness(arr, mean, stdDev)
- 왜도 계산 (비대칭성)
- 0: 대칭, +: 오른쪽 꼬리, -: 왼쪽 꼬리

#### calculateKurtosis(arr, mean, stdDev)
- 첨도 계산 (꼬리 두께)
- 0: 정규분포, +: 두꺼운 꼬리, -: 얇은 꼬리

---

## calculateOverallStats 확장

기존 함수에 추가된 필드:
```javascript
{
  // 기존 필드...
  maxConsecutiveLosses: number,  // 최대 연패
  sharpeRatio: number,            // 샤프 비율
  sortinoRatio: number,           // 소르티노 비율
  calmarRatio: number             // 칼마 비율
}
```

---

## 사용 예시

```javascript
// 백테스팅 후 종합 분석
const { trades, equityCurve, finalCapital } = await Analytics.loadIntradayData(
    startDate, endDate, 1000000
);

const stats = Analytics.calculateOverallStats(trades, finalCapital, 1000000);

console.log(`총 수익률: ${stats.totalReturn.toFixed(2)}%`);
console.log(`샤프 비율: ${stats.sharpeRatio.toFixed(2)}`);
console.log(`소르티노 비율: ${stats.sortinoRatio.toFixed(2)}`);
console.log(`칼마 비율: ${stats.calmarRatio.toFixed(2)}`);
console.log(`최대 연패: ${stats.maxConsecutiveLosses}회`);

// 드로우다운 차트용 데이터
const ddSeries = Analytics.calculateDrawdownSeries(equityCurve);

// 월별 성과 히트맵
const monthlyReturns = Analytics.calculateMonthlyReturns(trades);

// 수익률 분포
const distribution = Analytics.analyzeReturnDistribution(trades);
console.log(`평균: ${distribution.stats.mean.toFixed(2)}%`);
console.log(`중앙값: ${distribution.stats.median.toFixed(2)}%`);
console.log(`표준편차: ${distribution.stats.stdDev.toFixed(2)}%`);
console.log(`왜도: ${distribution.stats.skewness.toFixed(2)}`);
console.log(`첨도: ${distribution.stats.kurtosis.toFixed(2)}`);

// 벤치마크 비교 (예: KOSPI)
const kospiReturns = [/* KOSPI 일간 수익률 배열 */];
const alphaBeta = Analytics.calculateAlphaBeta(
    trades.map(t => t.return_percent),
    kospiReturns
);
console.log(`Alpha: ${alphaBeta.alpha.toFixed(2)}%`);
console.log(`Beta: ${alphaBeta.beta.toFixed(2)}`);
console.log(`Correlation: ${alphaBeta.correlation.toFixed(2)}`);
```

---

## 검증

테스트 파일: `test_analytics_functions.html`

브라우저에서 열면 12개 테스트 자동 실행:
1. ✓ calculateTradingDays
2. ✓ calculateSharpeRatio
3. ✓ calculateSortinoRatio
4. ✓ calculateMaxDrawdown
5. ✓ calculateCalmarRatio
6. ✓ calculateMaxConsecutiveLosses
7. ✓ calculateDrawdownSeries
8. ✓ calculateMonthlyReturns
9. ✓ analyzeReturnDistribution
10. ✓ calculateAlphaBeta
11. ✓ calculateOverallStats (Extended)
12. ✓ Helper Functions

---

## 참고 자료

- **Sharpe Ratio**: Sharpe, W. F. (1966). Mutual Fund Performance. Journal of Business.
- **Sortino Ratio**: Sortino, F. A. & Price, L. N. (1994). Performance Measurement in a Downside Risk Framework.
- **Calmar Ratio**: Young, T. W. (1991). Calmar Ratio: A Smoother Tool.
- **Alpha/Beta**: Capital Asset Pricing Model (CAPM), Sharpe (1964), Lintner (1965)

---

**작성자**: Dev Agent  
**날짜**: 2026-04-05  
**파일**: `/Users/kslee/Documents/kslee_ZIP/zip1/news-trading-bot/js/analytics.js`
