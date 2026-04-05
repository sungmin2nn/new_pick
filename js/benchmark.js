// Benchmark Module - KOSPI 지수 데이터 관리 및 비교 분석
// 전략 수익률과 KOSPI 벤치마크 비교를 위한 모듈
// 데이터 소스: 네이버 금융 (https://finance.naver.com/sise/sise_index_day.naver?code=KOSPI)
// 마지막 업데이트: 2026-04-05

const Benchmark = {
    /**
     * KOSPI 월별 종가 및 수익률 데이터 (2026년)
     * 실제 네이버 금융 데이터 기반
     */
    KOSPI_MONTHLY_DATA: {
        "2026-02": { close: 5677.25, return: 0.0 },      // 기준점 (2월 중순)
        "2026-03": { close: 5052.46, return: -11.0 },    // -11% (3월말 급락)
        "2026-04": { close: 5377.30, return: -5.28 }     // -5.28% (4/3 기준)
    },

    /**
     * KOSPI 일별 종가 데이터 (2026-02-09 ~ 2026-04-03)
     * 네이버 금융에서 직접 수집한 실제 데이터
     * 기준일: 2026-02-09 (종가: 5298.04)
     */
    KOSPI_DAILY_DATA: {
        // 2월 (2026-02-09 ~ 2026-02-27)
        "2026-02-09": { close: 5298.04, return: 0.0 },      // 기준일
        "2026-02-10": { close: 5301.69, return: 0.07 },
        "2026-02-11": { close: 5354.49, return: 1.07 },
        "2026-02-12": { close: 5522.27, return: 4.23 },
        "2026-02-13": { close: 5507.01, return: 3.94 },
        "2026-02-19": { close: 5677.25, return: 7.16 },
        "2026-02-20": { close: 5808.53, return: 9.64 },
        "2026-02-23": { close: 5846.09, return: 10.34 },
        "2026-02-24": { close: 5969.64, return: 12.68 },
        "2026-02-25": { close: 6083.86, return: 14.83 },
        "2026-02-26": { close: 6307.27, return: 19.05 },
        "2026-02-27": { close: 6244.13, return: 17.86 },

        // 3월 (2026-03-03 ~ 2026-03-31)
        "2026-03-03": { close: 5791.91, return: 9.32 },
        "2026-03-04": { close: 5093.54, return: -3.86 },    // 급락
        "2026-03-05": { close: 5583.90, return: 5.40 },
        "2026-03-06": { close: 5584.87, return: 5.41 },
        "2026-03-09": { close: 5251.87, return: -0.87 },
        "2026-03-10": { close: 5532.59, return: 4.43 },
        "2026-03-11": { close: 5609.95, return: 5.89 },
        "2026-03-12": { close: 5583.25, return: 5.38 },
        "2026-03-13": { close: 5487.24, return: 3.57 },
        "2026-03-16": { close: 5549.85, return: 4.75 },
        "2026-03-17": { close: 5640.48, return: 6.46 },
        "2026-03-18": { close: 5925.03, return: 11.83 },
        "2026-03-19": { close: 5763.22, return: 8.78 },
        "2026-03-20": { close: 5781.20, return: 9.12 },
        "2026-03-23": { close: 5405.75, return: 2.03 },
        "2026-03-24": { close: 5553.92, return: 4.83 },
        "2026-03-25": { close: 5642.21, return: 6.50 },
        "2026-03-26": { close: 5460.46, return: 3.07 },
        "2026-03-27": { close: 5438.87, return: 2.66 },
        "2026-03-30": { close: 5277.30, return: -0.39 },
        "2026-03-31": { close: 5052.46, return: -4.64 },    // 월말 급락

        // 4월 (2026-04-01 ~ )
        "2026-04-01": { close: 5478.70, return: 3.41 },
        "2026-04-02": { close: 5234.05, return: -1.21 },
        "2026-04-03": { close: 5377.30, return: 1.50 }
    },

    /**
     * 지정된 기간의 KOSPI 일별 수익률 데이터 반환
     *
     * @param {Date|string} startDate - 시작일
     * @param {Date|string} endDate - 종료일
     * @returns {Object} { dates: [], returns: [], cumulative: [], closes: [] }
     */
    getBenchmarkReturns(startDate, endDate) {
        const start = typeof startDate === 'string' ? new Date(startDate) : startDate;
        const end = typeof endDate === 'string' ? new Date(endDate) : endDate;

        const dates = [];
        const returns = [];
        const cumulative = [];
        const closes = [];

        // 일별 데이터에서 해당 기간 필터링
        for (const [dateStr, data] of Object.entries(this.KOSPI_DAILY_DATA)) {
            const date = new Date(dateStr);

            if (date >= start && date <= end) {
                dates.push(dateStr);
                returns.push(data.return);
                cumulative.push(data.return); // 이미 누적 수익률
                closes.push(data.close);
            }
        }

        return {
            dates,
            returns,
            cumulative,
            closes
        };
    },

    /**
     * 전략 수익률 데이터를 KOSPI 벤치마크와 비교
     *
     * @param {Array} equityCurve - 전략 자산 곡선 [{date, capital}, ...]
     * @param {Number} initialCapital - 초기 자본
     * @returns {Object} 비교 데이터
     */
    compareToBenchmark(equityCurve, initialCapital = 1000000) {
        if (!equityCurve || equityCurve.length === 0) {
            return null;
        }

        const startDate = equityCurve[0].date;
        const endDate = equityCurve[equityCurve.length - 1].date;

        // KOSPI 벤치마크 데이터 가져오기
        const benchmark = this.getBenchmarkReturns(startDate, endDate);

        if (benchmark.dates.length === 0) {
            console.warn('[Benchmark] 해당 기간의 KOSPI 데이터 없음');
            return null;
        }

        // 전략 수익률 계산
        const strategyReturns = equityCurve.map(item => ({
            date: item.date,
            capital: item.capital,
            returnPct: ((item.capital - initialCapital) / initialCapital * 100)
        }));

        // 최종 수익률 비교
        const finalStrategyReturn = strategyReturns[strategyReturns.length - 1].returnPct;
        const finalBenchmarkReturn = benchmark.cumulative[benchmark.cumulative.length - 1];
        const outperformance = finalStrategyReturn - finalBenchmarkReturn;

        return {
            strategy: {
                dates: strategyReturns.map(r => r.date),
                returns: strategyReturns.map(r => r.returnPct),
                finalReturn: finalStrategyReturn
            },
            benchmark: {
                dates: benchmark.dates,
                returns: benchmark.cumulative,
                finalReturn: finalBenchmarkReturn
            },
            comparison: {
                outperformance: outperformance,
                outperformancePct: finalBenchmarkReturn !== 0
                    ? (outperformance / Math.abs(finalBenchmarkReturn) * 100)
                    : 0,
                betterThanBenchmark: outperformance > 0
            }
        };
    },

    /**
     * 날짜별로 전략과 KOSPI를 정렬하여 차트용 데이터 생성
     *
     * @param {Array} equityCurve - 전략 자산 곡선
     * @param {Number} initialCapital - 초기 자본
     * @returns {Object} Chart.js용 데이터셋
     */
    prepareChartData(equityCurve, initialCapital = 1000000) {
        const comparison = this.compareToBenchmark(equityCurve, initialCapital);

        if (!comparison) {
            return null;
        }

        // 날짜 매칭: 전략 데이터와 벤치마크 데이터 병합
        const allDates = [...new Set([
            ...comparison.strategy.dates,
            ...comparison.benchmark.dates
        ])].sort();

        const strategyData = [];
        const benchmarkData = [];

        allDates.forEach(date => {
            // 전략 데이터 찾기
            const strategyIdx = comparison.strategy.dates.indexOf(date);
            if (strategyIdx !== -1) {
                strategyData.push(comparison.strategy.returns[strategyIdx]);
            } else {
                // 이전 값 유지 (데이터 없으면 null)
                strategyData.push(strategyData.length > 0 ? strategyData[strategyData.length - 1] : 0);
            }

            // 벤치마크 데이터 찾기
            const benchmarkIdx = comparison.benchmark.dates.indexOf(date);
            if (benchmarkIdx !== -1) {
                benchmarkData.push(comparison.benchmark.returns[benchmarkIdx]);
            } else {
                // 이전 값 유지
                benchmarkData.push(benchmarkData.length > 0 ? benchmarkData[benchmarkData.length - 1] : 0);
            }
        });

        return {
            labels: allDates,
            datasets: [
                {
                    label: '전략 수익률',
                    data: strategyData,
                    borderColor: '#00C6BE',
                    backgroundColor: 'rgba(0, 198, 190, 0.15)',
                    tension: 0.4,
                    fill: false,
                    pointRadius: 0,
                    pointHoverRadius: 6
                },
                {
                    label: 'KOSPI 벤치마크',
                    data: benchmarkData,
                    borderColor: '#FF6B6B',
                    backgroundColor: 'rgba(255, 107, 107, 0.15)',
                    tension: 0.4,
                    fill: false,
                    pointRadius: 0,
                    pointHoverRadius: 6,
                    borderDash: [5, 5]  // 점선
                }
            ],
            comparison: comparison.comparison
        };
    },

    /**
     * 벤치마크 비교 통계 계산
     *
     * @param {Array} equityCurve - 전략 자산 곡선
     * @param {Number} initialCapital - 초기 자본
     * @returns {Object} 통계 데이터
     */
    calculateStats(equityCurve, initialCapital = 1000000) {
        const comparison = this.compareToBenchmark(equityCurve, initialCapital);

        if (!comparison) {
            return null;
        }

        // 샤프 비율 계산 (간이 버전, 일별 수익률 표준편차 사용)
        const strategyReturns = comparison.strategy.returns;
        const avgReturn = strategyReturns.reduce((sum, r) => sum + r, 0) / strategyReturns.length;
        const variance = strategyReturns.reduce((sum, r) => sum + Math.pow(r - avgReturn, 2), 0) / strategyReturns.length;
        const stdDev = Math.sqrt(variance);
        const sharpeRatio = stdDev !== 0 ? (avgReturn / stdDev) : 0;

        // 최대 낙폭 (MDD) 계산
        let maxDrawdown = 0;
        let peak = -Infinity;

        strategyReturns.forEach(returnPct => {
            if (returnPct > peak) {
                peak = returnPct;
            }
            const drawdown = peak - returnPct;
            if (drawdown > maxDrawdown) {
                maxDrawdown = drawdown;
            }
        });

        return {
            finalReturn: comparison.strategy.finalReturn,
            benchmarkReturn: comparison.benchmark.finalReturn,
            outperformance: comparison.comparison.outperformance,
            sharpeRatio: sharpeRatio,
            maxDrawdown: maxDrawdown,
            volatility: stdDev
        };
    },

    /**
     * 특정 날짜의 KOSPI 데이터 조회
     *
     * @param {string} date - 날짜 (YYYY-MM-DD)
     * @returns {Object|null} { close, return }
     */
    getDataByDate(date) {
        return this.KOSPI_DAILY_DATA[date] || null;
    },

    /**
     * 날짜 범위의 KOSPI 평균 수익률 계산
     *
     * @param {Date|string} startDate - 시작일
     * @param {Date|string} endDate - 종료일
     * @returns {Number} 평균 일일 수익률 (%)
     */
    getAverageReturn(startDate, endDate) {
        const data = this.getBenchmarkReturns(startDate, endDate);

        if (data.returns.length === 0) {
            return 0;
        }

        // 일별 수익률 계산 (누적이 아닌 일간 변화)
        const dailyReturns = [];
        for (let i = 1; i < data.returns.length; i++) {
            dailyReturns.push(data.returns[i] - data.returns[i - 1]);
        }

        if (dailyReturns.length === 0) {
            return 0;
        }

        return dailyReturns.reduce((sum, r) => sum + r, 0) / dailyReturns.length;
    },

    /**
     * 데이터 업데이트 함수 (향후 API 연동 시 사용)
     *
     * @param {string} date - 날짜 (YYYY-MM-DD)
     * @param {Number} close - 종가
     * @param {Number} returnPct - 수익률 (%)
     */
    addData(date, close, returnPct) {
        this.KOSPI_DAILY_DATA[date] = {
            close: close,
            return: returnPct
        };

        console.log(`[Benchmark] 데이터 추가: ${date}, 종가: ${close}, 수익률: ${returnPct}%`);
    },

    /**
     * 전체 데이터 통계
     */
    getDataInfo() {
        const dates = Object.keys(this.KOSPI_DAILY_DATA).sort();
        const values = Object.values(this.KOSPI_DAILY_DATA);

        return {
            dataPoints: dates.length,
            startDate: dates[0],
            endDate: dates[dates.length - 1],
            minClose: Math.min(...values.map(v => v.close)),
            maxClose: Math.max(...values.map(v => v.close)),
            totalReturn: values[values.length - 1].return
        };
    }
};

// 모듈 정보 로그
console.log('[Benchmark] 모듈 로드 완료');
console.log('[Benchmark] 데이터 정보:', Benchmark.getDataInfo());
