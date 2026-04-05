# Benchmark 모듈 사용 가이드

## 개요
`js/benchmark.js` 모듈은 KOSPI 지수 데이터를 관리하고, 전략 수익률과 벤치마크를 비교 분석하는 기능을 제공합니다.

## 데이터 구조

### 일별 데이터
- **기간**: 2026-01-28 ~ 2026-03-30
- **백테스트 실제 거래 기간과 정확히 매칭**
- **형식**: `{ close: 종가, return: 누적수익률(%) }`
- **기준점**: 2026-01-28 (return: 0.0%)

### 월별 데이터
- **기간**: 2026-01 ~ 2026-04
- **형식**: `{ close: 종가, return: 누적수익률(%) }`

## 주요 기능

### 1. 기간별 벤치마크 데이터 조회

```javascript
// 특정 기간의 KOSPI 데이터 가져오기
const startDate = '2026-01-28';
const endDate = '2026-03-27';

const benchmark = Benchmark.getBenchmarkReturns(startDate, endDate);

console.log(benchmark);
// 출력:
// {
//   dates: ['2026-01-28', '2026-01-29', ...],
//   returns: [0.0, 0.26, 0.09, ...],  // 누적 수익률 %
//   cumulative: [0.0, 0.26, 0.09, ...],  // 동일
//   closes: [2596.45, 2603.12, ...]  // 종가
// }
```

### 2. 전략과 벤치마크 비교

```javascript
// equityCurve: Analytics.loadIntradayData()의 결과
// 형식: [{ date: '2026-01-28', capital: 1000000 }, ...]

const comparison = Benchmark.compareToBenchmark(equityCurve, 1000000);

console.log(comparison);
// 출력:
// {
//   strategy: {
//     dates: [...],
//     returns: [0.0, 1.5, 2.3, ...],  // 전략 누적 수익률 %
//     finalReturn: 5.2  // 최종 수익률 %
//   },
//   benchmark: {
//     dates: [...],
//     returns: [0.0, 0.26, 0.09, ...],  // KOSPI 누적 수익률 %
//     finalReturn: 7.71  // 최종 수익률 %
//   },
//   comparison: {
//     outperformance: -2.51,  // 전략 - 벤치마크 (%)
//     outperformancePct: -32.56,  // 초과성과 비율 (%)
//     betterThanBenchmark: false  // 벤치마크 초과 여부
//   }
// }
```

### 3. Chart.js용 데이터 준비

```javascript
// 차트에 바로 사용 가능한 형태로 변환
const chartData = Benchmark.prepareChartData(equityCurve, 1000000);

// Chart.js로 렌더링
const ctx = document.getElementById('benchmarkChart').getContext('2d');
new Chart(ctx, {
    type: 'line',
    data: chartData,  // labels + datasets 포함
    options: {
        responsive: true,
        plugins: {
            legend: { display: true }
        },
        scales: {
            y: {
                ticks: {
                    callback: function(value) {
                        return value.toFixed(1) + '%';
                    }
                }
            }
        }
    }
});

// comparison 정보도 함께 제공
console.log(chartData.comparison);
// { outperformance: -2.51, outperformancePct: -32.56, betterThanBenchmark: false }
```

### 4. 통계 계산

```javascript
const stats = Benchmark.calculateStats(equityCurve, 1000000);

console.log(stats);
// 출력:
// {
//   finalReturn: 5.2,        // 전략 최종 수익률 %
//   benchmarkReturn: 7.71,   // 벤치마크 최종 수익률 %
//   outperformance: -2.51,   // 초과성과 %
//   sharpeRatio: 0.42,       // 샤프 비율 (간이 계산)
//   maxDrawdown: 3.2,        // 최대 낙폭 %
//   volatility: 1.85         // 변동성 (표준편차 %)
// }
```

### 5. 특정 날짜 데이터 조회

```javascript
const data = Benchmark.getDataByDate('2026-02-06');

console.log(data);
// { close: 2618.45, return: 0.85 }
```

### 6. 평균 수익률 계산

```javascript
const avgReturn = Benchmark.getAverageReturn('2026-02-01', '2026-02-28');

console.log(avgReturn);
// 0.12  (일평균 0.12% 수익)
```

### 7. 데이터 정보 확인

```javascript
const info = Benchmark.getDataInfo();

console.log(info);
// {
//   dataPoints: 40,
//   startDate: '2026-01-28',
//   endDate: '2026-03-30',
//   minClose: 2596.45,
//   maxClose: 2802.78,
//   totalReturn: 7.95
// }
```

## 실제 사용 예시 (Dashboard)

### backtest_dashboard.html에 통합

```html
<!-- 벤치마크 비교 섹션 추가 -->
<section class="benchmark-section">
    <h2>📊 벤치마크 비교</h2>
    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-label">전략 수익률</div>
            <div class="stat-value" id="strategyReturn">-</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">KOSPI 수익률</div>
            <div class="stat-value" id="benchmarkReturn">-</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">초과성과</div>
            <div class="stat-value" id="outperformance">-</div>
        </div>
    </div>
    <div class="chart-container-large">
        <canvas id="benchmarkChart"></canvas>
    </div>
</section>

<!-- 스크립트 -->
<script src="js/benchmark.js"></script>
<script>
async function loadBenchmarkComparison() {
    // 백테스트 데이터 로드
    const { trades, equityCurve, finalCapital } = await Analytics.loadIntradayData(
        '2026-01-28', '2026-03-27', 1000000
    );

    // 벤치마크 비교
    const comparison = Benchmark.compareToBenchmark(equityCurve, 1000000);

    if (comparison) {
        // 통계 표시
        document.getElementById('strategyReturn').textContent =
            comparison.strategy.finalReturn.toFixed(2) + '%';
        document.getElementById('benchmarkReturn').textContent =
            comparison.benchmark.finalReturn.toFixed(2) + '%';

        const outperf = comparison.comparison.outperformance;
        const outperfElem = document.getElementById('outperformance');
        outperfElem.textContent = (outperf > 0 ? '+' : '') + outperf.toFixed(2) + '%';
        outperfElem.style.color = outperf > 0 ? '#10b981' : '#ef4444';

        // 차트 렌더링
        const chartData = Benchmark.prepareChartData(equityCurve, 1000000);
        const ctx = document.getElementById('benchmarkChart').getContext('2d');
        new Chart(ctx, {
            type: 'line',
            data: chartData,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: true, position: 'top' },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return context.dataset.label + ': ' +
                                       context.parsed.y.toFixed(2) + '%';
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        ticks: {
                            callback: function(value) {
                                return value.toFixed(1) + '%';
                            }
                        }
                    }
                }
            }
        });
    }
}

// 페이지 로드 시 실행
loadBenchmarkComparison();
</script>
```

## 데이터 업데이트 방법

### 수동 업데이트 (정적 데이터)

```javascript
// 새로운 날짜 데이터 추가
Benchmark.addData('2026-04-01', 2808.34, 8.17);
Benchmark.addData('2026-04-02', 2814.56, 8.41);

// 월별 데이터 추가 (benchmark.js 파일 직접 수정)
KOSPI_MONTHLY_DATA: {
    "2026-05": { close: 2850.00, return: 10.24 }
}
```

### 향후 API 연동 (옵션)

```javascript
// 네이버 금융 API 연동 예시 (CORS 해결 필요)
async function fetchKOSPIData(date) {
    try {
        const response = await fetch(
            `https://finance.naver.com/api/sise/index_day.json?symbol=KOSPI&date=${date}`
        );
        const data = await response.json();

        // 데이터 파싱 후 Benchmark에 추가
        Benchmark.addData(date, data.close, data.return);
    } catch (error) {
        console.error('KOSPI 데이터 로드 실패:', error);
    }
}
```

## 주의사항

1. **데이터 형식**: 날짜는 반드시 `YYYY-MM-DD` 형식
2. **누적 수익률**: `return` 값은 기준점(2026-01-28) 대비 누적 수익률
3. **일별 수익률 계산**: 누적에서 일별로 변환하려면 차분(difference) 필요
4. **거래일 기준**: 주말/공휴일 데이터 없음 (백테스트 거래일과 동일)
5. **CORS 제약**: 브라우저에서 외부 API 직접 호출 시 CORS 에러 발생 가능

## 추가 개선 사항

### 1. 실시간 업데이트
- Python 백엔드에서 pykrx로 KOSPI 데이터 수집
- JSON 파일로 저장 후 프론트엔드에서 로드

### 2. 더 많은 통계
- 베타 계산
- 알파 계산
- 상관계수
- 추적오차(Tracking Error)

### 3. 다양한 벤치마크
- KOSDAQ 지수
- KRX 섹터 지수
- 테마 지수

## 문제 해결

### Q1. "해당 기간의 KOSPI 데이터 없음" 경고가 뜹니다.
**A**: `KOSPI_DAILY_DATA`에 해당 날짜 데이터가 없습니다. `benchmark.js`에서 데이터 범위를 확인하거나 `addData()`로 추가하세요.

### Q2. 차트가 표시되지 않습니다.
**A**:
- Chart.js 라이브러리가 로드되었는지 확인
- `equityCurve` 데이터가 올바른 형식인지 확인
- 브라우저 콘솔에서 에러 메시지 확인

### Q3. 수익률이 음수로 표시됩니다.
**A**: `return` 값은 기준점 대비 누적 수익률입니다. 기준점보다 낮으면 음수가 정상입니다.

## 라이센스
MIT License - news-trading-bot 프로젝트 내부 사용

## 문의
프로젝트 담당자에게 문의하세요.
