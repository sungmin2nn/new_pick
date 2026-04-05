// Dashboard Controller - 메인 오케스트레이터

const Dashboard = {
    state: {
        startDate: null,
        endDate: null,
        initialCapital: 1000000,
        maxPerStock: 100000,
        buyExpensive: true,
        trades: [],
        equityCurve: [],
        finalCapital: 0,
        analytics: null,
        isLoading: false
    },

    /**
     * 초기화
     */
    async init() {
        console.log('[Dashboard] 초기화 시작');

        // 기본 기간 설정 (최근 7일)
        this.state.endDate = new Date();
        this.state.startDate = Utils.daysAgo(7);

        // 날짜 입력 필드에 설정
        document.getElementById('startDate').value = Utils.formatDate(this.state.startDate);
        document.getElementById('endDate').value = Utils.formatDate(this.state.endDate);

        // 이벤트 리스너 설정
        this.setupEventListeners();

        // 초기 데이터 로드
        await this.loadAndAnalyze();

        // 시스템 정보 렌더링
        this.renderSystemInfo();

        console.log('[Dashboard] 초기화 완료');
    },

    /**
     * 이벤트 리스너 설정
     */
    setupEventListeners() {
        // 날짜 변경
        document.getElementById('startDate').addEventListener('change', () => this.onDateChange());
        document.getElementById('endDate').addEventListener('change', () => this.onDateChange());

        // 검색
        const searchInput = document.getElementById('searchInput');
        if (searchInput) {
            searchInput.addEventListener('input', Utils.debounce((e) => {
                TableUtils.search(e.target.value);
            }, 300));
        }

        // 필터
        const resultFilter = document.getElementById('resultFilter');
        if (resultFilter) {
            resultFilter.addEventListener('change', (e) => {
                TableUtils.applyFilters({ result: e.target.value });
            });
        }

        const reasonFilter = document.getElementById('reasonFilter');
        if (reasonFilter) {
            reasonFilter.addEventListener('change', (e) => {
                TableUtils.applyFilters({ reason: e.target.value });
            });
        }

        // 매수여부 필터
        const entryFilter = document.getElementById('entryFilter');
        if (entryFilter) {
            entryFilter.addEventListener('change', (e) => {
                TableUtils.applyFilters({ entry: e.target.value });
            });
        }
    },

    /**
     * 날짜 변경 핸들러
     */
    onDateChange() {
        const startDateStr = document.getElementById('startDate').value;
        const endDateStr = document.getElementById('endDate').value;

        if (!startDateStr || !endDateStr) return;

        this.state.startDate = new Date(startDateStr);
        this.state.endDate = new Date(endDateStr);

        this.loadAndAnalyze();
    },

    /**
     * 빠른 기간 설정
     */
    setQuickPeriod(period) {
        const endDate = new Date();
        let startDate;

        switch (period) {
            case 'all':
                // 가장 오래된 intraday 파일 날짜 (2026-01-28)
                startDate = new Date('2026-01-28');
                break;
            case 'year':
                startDate = Utils.startOfYear();
                break;
            case 'month':
                startDate = Utils.startOfMonth();
                break;
            case '30days':
                startDate = Utils.daysAgo(30);
                break;
            case '7days':
                startDate = Utils.daysAgo(7);
                break;
            default:
                startDate = Utils.daysAgo(30);
        }

        this.state.startDate = startDate;
        this.state.endDate = endDate;

        document.getElementById('startDate').value = Utils.formatDate(startDate);
        document.getElementById('endDate').value = Utils.formatDate(endDate);

        this.loadAndAnalyze();
    },

    /**
     * 데이터 로드 및 분석
     */
    async loadAndAnalyze() {
        if (this.state.isLoading) return;

        try {
            this.state.isLoading = true;
            this.showLoading();

            console.log('[Dashboard] 데이터 로드 시작:',
                Utils.formatDate(this.state.startDate), '~', Utils.formatDate(this.state.endDate));

            // 1. Intraday 데이터 로드 및 백테스팅
            const result = await Analytics.loadIntradayData(
                this.state.startDate,
                this.state.endDate,
                this.state.initialCapital,
                this.state.maxPerStock,
                this.state.buyExpensive
            );

            this.state.trades = result.trades;
            this.state.equityCurve = result.equityCurve;
            this.state.finalCapital = result.finalCapital;

            console.log(`[Dashboard] ${this.state.trades.length}개 거래 로드됨`);

            // 거래 데이터가 없으면 안내 메시지 표시
            if (this.state.trades.length === 0) {
                this.showNoDataMessage();
            } else {
                this.hideNoDataMessage();
            }

            // 2. 통계 분석
            const stats = Analytics.calculateOverallStats(
                this.state.trades,
                this.state.finalCapital,
                this.state.initialCapital
            );

            const scoreRange = Analytics.analyzeByScoreRange(this.state.trades);
            const byDate = Analytics.analyzeByDate(this.state.trades);
            const byDayOfWeek = Analytics.analyzeByDayOfWeek(this.state.trades);
            const byReason = Analytics.analyzeByReason(this.state.trades);
            const byTimeOfDay = Analytics.analyzeByTimeOfDay(this.state.trades);
            const returnDist = Analytics.analyzeReturnDistribution(this.state.trades);

            // 새로운 리스크 지표 계산
            const drawdownSeries = Analytics.calculateDrawdownSeries(this.state.equityCurve);
            const monthlyReturns = Analytics.calculateMonthlyReturns(this.state.trades);

            // 벤치마크 비교
            const benchmarkComparison = Benchmark.compareToBenchmark(this.state.equityCurve, this.state.initialCapital);

            this.state.analytics = {
                stats,
                scoreRange,
                byDate,
                byDayOfWeek,
                byReason,
                byTimeOfDay,
                returnDist,
                drawdownSeries,
                monthlyReturns,
                benchmarkComparison
            };

            // 3. UI 렌더링
            this.renderOverallStats(stats);
            this.renderCharts(stats);
            this.renderAnalytics();
            this.renderAdvancedCharts();
            if (benchmarkComparison) {
                this.renderBenchmarkSection(benchmarkComparison);
            }
            await this.renderTodayStocks();
            this.renderTransactionTable();

            this.hideLoading();

        } catch (error) {
            console.error('[Dashboard] 로드 실패:', error);
            this.showError('데이터를 불러오는 중 오류가 발생했습니다.');
        } finally {
            this.state.isLoading = false;
        }
    },

    /**
     * 전체 성과 렌더링
     */
    renderOverallStats(stats) {
        document.getElementById('finalCapital').textContent = Utils.formatCurrency(stats.finalCapital);

        const totalReturnEl = document.getElementById('totalReturn');
        totalReturnEl.textContent = Utils.formatPercent(stats.totalReturn);
        totalReturnEl.style.color = stats.totalReturn >= 0 ? '#f56565' : '#4299e1';

        document.getElementById('totalTrades').textContent = Utils.formatNumber(stats.totalTrades) + '건';
        document.getElementById('winRate').textContent = Utils.formatPercent(stats.winRate);

        // 새로운 리스크 지표 렌더링
        document.getElementById('sharpeRatio').textContent = Utils.formatNumber(stats.sharpeRatio, 2);
        document.getElementById('sortinoRatio').textContent = Utils.formatNumber(stats.sortinoRatio, 2);
        document.getElementById('calmarRatio').textContent = Utils.formatNumber(stats.calmarRatio, 2);
        document.getElementById('maxConsecLosses').textContent = stats.maxConsecutiveLosses + '연패';
    },

    /**
     * 차트 렌더링
     */
    renderCharts(stats) {
        // 자본 증가 곡선
        Charts.renderEquityCurve('equityChart', this.state.equityCurve);

        // 결과 분포 (5단계)
        Charts.renderResultDistribution('resultChart',
            stats.profitCount,
            stats.lossCount,
            stats.noneProfitCount,
            stats.noneLossCount,
            stats.noneNeutralCount
        );
    },

    /**
     * 상세 분석 렌더링
     */
    renderAnalytics() {
        const analytics = this.state.analytics;

        // 점수대별
        this.renderScoreRangeTable(analytics.scoreRange);

        // 일자별
        this.renderDailyTable(analytics.byDate);

        // 요일별
        this.renderDayOfWeekAnalysis(analytics.byDayOfWeek);

        // 선정사유별
        this.renderReasonTable(analytics.byReason);

        // 시간대별
        Charts.renderTimeOfDayChart('timeOfDayChart', analytics.byTimeOfDay);

        // 수익률 분포
        Charts.renderReturnDistribution('returnDistChart', analytics.returnDist);
    },

    /**
     * 점수대별 테이블
     */
    renderScoreRangeTable(data) {
        const table = document.getElementById('scoreRangeTable');
        if (!table) return;

        const html = `
            <thead>
                <tr>
                    <th>점수대</th>
                    <th>거래 수</th>
                    <th>승률</th>
                    <th>평균 수익률</th>
                </tr>
            </thead>
            <tbody>
                ${data.map(row => `
                    <tr>
                        <td>${row.range}</td>
                        <td>${row.count}건</td>
                        <td>${Utils.formatPercent(row.winRate)}</td>
                        <td>${Utils.formatPercentWithColor(row.avgReturn)}</td>
                    </tr>
                `).join('')}
            </tbody>
        `;

        table.innerHTML = html;
    },

    /**
     * 일자별 테이블
     */
    renderDailyTable(data) {
        const table = document.getElementById('dailyTable');
        if (!table) return;

        const html = `
            <thead>
                <tr>
                    <th>날짜</th>
                    <th>거래 수</th>
                    <th>익절</th>
                    <th>손절</th>
                    <th>미달</th>
                    <th>합계 수익률</th>
                </tr>
            </thead>
            <tbody>
                ${data.map(row => `
                    <tr>
                        <td>${row.date} (${Utils.getDayOfWeek(row.date)})</td>
                        <td>${row.trades.length}건</td>
                        <td>${row.profitCount}</td>
                        <td>${row.lossCount}</td>
                        <td>${row.noneCount}</td>
                        <td>${Utils.formatPercentWithColor(row.totalReturn)}</td>
                    </tr>
                `).join('')}
            </tbody>
        `;

        table.innerHTML = html;
    },

    /**
     * 요일별 분석
     */
    renderDayOfWeekAnalysis(data) {
        // 테이블만 렌더링 (차트 제거)
        const table = document.getElementById('dayOfWeekTable');
        if (!table) return;

        const html = `
            <thead>
                <tr>
                    <th style="width: 8%;">요일</th>
                    <th style="width: 47%;">거래수 (익절/손절/미달수익/미달손실/미달유지)</th>
                    <th style="width: 20%;">승률</th>
                    <th style="width: 25%;">평균수익률</th>
                </tr>
            </thead>
            <tbody>
                ${data.map(row => `
                    <tr>
                        <td>${row.day}</td>
                        <td>${row.count} (${row.profitCount}/${row.lossCount}/${row.noneProfitCount}/${row.noneLossCount}/${row.noneNeutralCount})</td>
                        <td>${Utils.formatPercent(row.winRate)}</td>
                        <td>${Utils.formatPercentWithColor(row.avgReturn)}</td>
                    </tr>
                `).join('')}
            </tbody>
        `;

        table.innerHTML = html;
    },

    /**
     * 선정사유별 테이블
     */
    renderReasonTable(data) {
        const table = document.getElementById('reasonTable');
        if (!table) return;

        const html = `
            <thead>
                <tr>
                    <th>선정사유</th>
                    <th>거래 수</th>
                    <th>승률</th>
                    <th>평균 수익률</th>
                </tr>
            </thead>
            <tbody>
                ${data.map(row => `
                    <tr>
                        <td style="text-align: left;">${row.reason}</td>
                        <td>${row.count}건</td>
                        <td>${Utils.formatPercent(row.winRate)}</td>
                        <td>${Utils.formatPercentWithColor(row.avgReturn)}</td>
                    </tr>
                `).join('')}
            </tbody>
        `;

        table.innerHTML = html;
    },

    /**
     * 오늘 종목 탭 전환
     */
    switchTodayTab(tabType) {
        // 탭 버튼 활성화
        document.querySelectorAll('.today-tabs .tab-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        event.target.closest('.tab-btn').classList.add('active');

        // 탭 콘텐츠 전환
        document.querySelectorAll('.today-tab-content').forEach(content => {
            content.classList.remove('active');
        });
        document.getElementById(tabType + 'Tab').classList.add('active');
    },

    /**
     * 오늘의 종목 렌더링 (Entry Check 포함)
     */
    async renderTodayStocks() {
        const buyContainer = document.getElementById('buyCards');
        const skipContainer = document.getElementById('skipCards');
        if (!buyContainer || !skipContainer) return;

        const stocks = await Analytics.getTodayStocksWithEntryCheck();

        // 매수/스킵 분류
        const buyStocks = stocks.filter(s => s.shouldBuy);
        const skipStocks = stocks.filter(s => !s.shouldBuy);

        // 카운트 업데이트
        document.getElementById('buyCount').textContent = buyStocks.length;
        document.getElementById('skipCount').textContent = skipStocks.length;

        // 매수 종목 렌더링
        if (buyStocks.length === 0) {
            buyContainer.innerHTML = '<p style="text-align: center; color: var(--text-secondary);">매수 종목이 없습니다.</p>';
        } else {
            buyContainer.innerHTML = buyStocks.map((stock, index) => `
                <div class="today-card buy-card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                        <span class="rank ${index < 3 ? 'top3' : ''}">${index + 1}</span>
                        <span class="score-badge">${stock.score}점</span>
                    </div>
                    <div class="stock-name">${stock.name}</div>
                    <div class="stock-code">${stock.code}</div>
                    ${stock.date ? `<div style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 0.3rem;">📅 ${stock.date} (${Utils.getDayOfWeek(stock.date)})</div>` : ''}
                    <div class="entry-info buy">
                        <span class="entry-badge buy">📈 매수</span>
                        ${stock.entryPrice ? `<span class="entry-price">진입가: ${Utils.formatCurrency(stock.entryPrice)}</span>` : ''}
                    </div>
                    ${stock.actualResult ? `
                        <div class="result-info ${stock.actualResult.first_hit === 'profit' ? 'profit' : stock.actualResult.first_hit === 'loss' ? 'loss' : 'none'}">
                            결과: ${stock.actualResult.first_hit === 'profit' ? '익절 (+5%)' : stock.actualResult.first_hit === 'loss' ? '손절 (-3%)' : '미달 (' + stock.actualResult.closing_percent.toFixed(2) + '%)'}
                        </div>
                    ` : ''}
                    <div style="margin-top: 0.5rem; font-size: 0.85rem; color: var(--text-secondary);">
                        ${stock.reason}
                    </div>
                </div>
            `).join('');
        }

        // 스킵 종목 렌더링
        if (skipStocks.length === 0) {
            skipContainer.innerHTML = '<p style="text-align: center; color: var(--text-secondary);">스킵 종목이 없습니다.</p>';
        } else {
            skipContainer.innerHTML = skipStocks.map((stock, index) => `
                <div class="today-card skip-card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                        <span class="rank">${index + 1}</span>
                        <span class="score-badge">${stock.score}점</span>
                    </div>
                    <div class="stock-name">${stock.name}</div>
                    <div class="stock-code">${stock.code}</div>
                    ${stock.date ? `<div style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 0.3rem;">📅 ${stock.date} (${Utils.getDayOfWeek(stock.date)})</div>` : ''}
                    <div class="entry-info skip">
                        <span class="entry-badge skip">⏭️ 스킵</span>
                        <span class="skip-reason">${stock.skipReason || '조건 미충족'}</span>
                    </div>
                    ${stock.virtualResult ? `
                        <div class="virtual-result ${stock.virtualResult.first_hit === 'profit' ? 'profit' : stock.virtualResult.first_hit === 'loss' ? 'loss' : 'none'}">
                            (만약 매수했다면: ${stock.virtualResult.first_hit === 'profit' ? '익절' : stock.virtualResult.first_hit === 'loss' ? '손절' : stock.virtualResult.closing_percent.toFixed(2) + '%'})
                        </div>
                    ` : ''}
                    <div style="margin-top: 0.5rem; font-size: 0.85rem; color: var(--text-secondary);">
                        ${stock.reason}
                    </div>
                </div>
            `).join('');
        }
    },

    /**
     * 거래 내역 테이블 렌더링
     */
    renderTransactionTable() {
        TableUtils.init(this.state.trades);
        TableUtils.populateReasonFilter();
    },

    /**
     * 시스템 정보 렌더링
     */
    renderSystemInfo() {
        const container = document.getElementById('systemInfoContent');
        if (!container) return;

        const html = SYSTEM_INFO.features.map(feature => `
            <div class="info-card">
                <h3>${feature.icon} ${feature.title}</h3>
                <ul>
                    ${feature.items.map(item => `<li>${item}</li>`).join('')}
                </ul>
            </div>
        `).join('');

        container.innerHTML = `
            <div class="system-info-grid">
                ${html}
            </div>
        `;
    },

    /**
     * CSV 내보내기
     */
    exportToCSV() {
        if (this.state.trades.length === 0) {
            alert('내보낼 데이터가 없습니다.');
            return;
        }

        const data = this.state.trades.map(trade => ({
            '날짜': trade.date,
            '종목명': trade.stock_name,
            '종목코드': trade.stock_code,
            '총점': trade.selection_score,
            '선정사유': trade.selection_reason,
            '매수가': trade.buy_price,
            '수량': trade.shares,
            '매도가': trade.sell_price,
            '수익률': trade.return_percent.toFixed(2) + '%',
            '손익금액': trade.profit,
            '결과': trade.result === 'profit' ? '익절' : trade.result === 'loss' ? '손절' : '미달'
        }));

        const filename = `거래내역_${Utils.formatDate(this.state.startDate)}_${Utils.formatDate(this.state.endDate)}.csv`;
        Utils.exportToCSV(data, filename);
    },

    /**
     * 로딩 표시
     */
    showLoading() {
        const sections = document.querySelectorAll('section');
        sections.forEach(section => {
            section.style.opacity = '0.5';
            section.style.pointerEvents = 'none';
        });
    },

    /**
     * 로딩 숨기기
     */
    hideLoading() {
        const sections = document.querySelectorAll('section');
        sections.forEach(section => {
            section.style.opacity = '1';
            section.style.pointerEvents = 'auto';
        });
    },

    /**
     * 에러 표시
     */
    showError(message) {
        alert(message);
        this.hideLoading();
    },

    /**
     * 데이터 없음 메시지 표시
     */
    showNoDataMessage() {
        // 이미 메시지가 있으면 스킵
        if (document.getElementById('noDataMessage')) return;

        const message = document.createElement('div');
        message.id = 'noDataMessage';
        message.innerHTML = `
            <div style="
                background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%);
                border: 1px solid #ffc107;
                border-radius: 8px;
                padding: 1.5rem;
                margin: 1rem 0;
                text-align: center;
                color: #856404;
            ">
                <h3 style="margin: 0 0 0.5rem 0;">📭 선택한 기간에 거래 데이터가 없습니다</h3>
                <p style="margin: 0; font-size: 0.9rem;">
                    • 장중 데이터(intraday)는 매일 <b>16:30 KST</b> 이후에 수집됩니다<br>
                    • "전체" 버튼을 클릭하면 과거 데이터를 확인할 수 있습니다<br>
                    • 오늘 선정된 종목은 위의 "오늘의 종목" 섹션에서 확인하세요
                </p>
            </div>
        `;

        // 오늘의 종목 섹션 아래에 삽입
        const todaySection = document.querySelector('.today-section');
        if (todaySection) {
            todaySection.insertAdjacentElement('afterend', message);
        } else {
            const mainContent = document.querySelector('main');
            if (mainContent) {
                mainContent.insertBefore(message, mainContent.firstChild);
            }
        }
    },

    /**
     * 데이터 없음 메시지 숨기기
     */
    hideNoDataMessage() {
        const message = document.getElementById('noDataMessage');
        if (message) {
            message.remove();
        }
    },

    /**
     * 고급 차트 렌더링 (드로우다운, 월별 히트맵, 수익률 분포)
     */
    renderAdvancedCharts() {
        const analytics = this.state.analytics;

        // 드로우다운 차트
        if (analytics.drawdownSeries && analytics.drawdownSeries.length > 0) {
            Charts.renderDrawdownChart('drawdownChart', analytics.drawdownSeries);
        }

        // 월별 히트맵
        if (analytics.monthlyReturns && analytics.monthlyReturns.length > 0) {
            Charts.renderMonthlyHeatmap('monthlyHeatmap', analytics.monthlyReturns);
        }

        // 수익률 히스토그램
        if (analytics.returnDist && analytics.returnDist.distribution) {
            Charts.renderReturnHistogram('returnHistogram', analytics.returnDist.distribution);
        }
    },

    /**
     * 벤치마크 비교 섹션 렌더링
     */
    renderBenchmarkSection(comparison) {
        // KOSPI 수익률
        const kospiEl = document.getElementById('kospiReturn');
        if (kospiEl) {
            kospiEl.textContent = Utils.formatPercent(comparison.benchmark.totalReturn);
        }

        // Alpha (초과 성과)
        const alphaEl = document.getElementById('alphaValue');
        if (alphaEl) {
            const alpha = comparison.comparison.outperformance;
            alphaEl.textContent = Utils.formatPercent(alpha);
            alphaEl.style.color = alpha >= 0 ? '#10B981' : '#EF4444';
        }

        // Beta (계산 필요)
        const betaEl = document.getElementById('betaValue');
        if (betaEl) {
            // Beta 계산을 위해 일별 수익률 필요
            const strategyReturns = this.state.trades.map(t => t.return_percent);
            const benchmarkData = Benchmark.getBenchmarkReturns(
                this.state.equityCurve[0].date,
                this.state.equityCurve[this.state.equityCurve.length - 1].date
            );

            // 일별 수익률로 변환
            const benchmarkReturns = [];
            for (let i = 1; i < benchmarkData.cumulative.length; i++) {
                benchmarkReturns.push(benchmarkData.cumulative[i] - benchmarkData.cumulative[i - 1]);
            }

            const alphaBeta = Analytics.calculateAlphaBeta(strategyReturns, benchmarkReturns);
            betaEl.textContent = alphaBeta.beta.toFixed(2);
        }

        // 비교 차트
        const chartData = Benchmark.prepareChartData(this.state.equityCurve, this.state.initialCapital);
        if (chartData) {
            Charts.renderBenchmarkComparison('benchmarkChart', chartData.datasets[0].data.map((val, idx) => ({
                date: chartData.labels[idx],
                cumulativeReturn: val
            })), chartData.datasets[1].data.map((val, idx) => ({
                date: chartData.labels[idx],
                cumulativeReturn: val
            })));
        }
    }
};
