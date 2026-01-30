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

        // 기본 기간 설정 (최근 30일)
        this.state.endDate = new Date();
        this.state.startDate = Utils.daysAgo(30);

        // 날짜 입력 필드에 설정
        document.getElementById('startDate').value = Utils.formatDate(this.state.startDate);
        document.getElementById('endDate').value = Utils.formatDate(this.state.endDate);

        // 이벤트 리스너 설정
        this.setupEventListeners();

        // 초기 데이터 로드
        await this.loadAndAnalyze();

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

            this.state.analytics = {
                stats,
                scoreRange,
                byDate,
                byDayOfWeek,
                byReason,
                byTimeOfDay,
                returnDist
            };

            // 3. UI 렌더링
            this.renderOverallStats(stats);
            this.renderCharts(stats);
            this.renderAnalytics();
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
    },

    /**
     * 차트 렌더링
     */
    renderCharts(stats) {
        // 자본 증가 곡선
        Charts.renderEquityCurve('equityChart', this.state.equityCurve);

        // 결과 분포
        Charts.renderResultDistribution('resultChart', stats.profitCount, stats.lossCount, stats.noneCount);
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
        // 차트
        Charts.renderDayOfWeekChart('dayOfWeekChart', data);

        // 테이블
        const table = document.getElementById('dayOfWeekTable');
        if (!table) return;

        const html = `
            <thead>
                <tr>
                    <th>요일</th>
                    <th>거래 수</th>
                    <th>승률</th>
                    <th>평균 수익률</th>
                </tr>
            </thead>
            <tbody>
                ${data.map(row => `
                    <tr>
                        <td>${row.day}요일</td>
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
     * 오늘의 종목 렌더링
     */
    async renderTodayStocks() {
        const container = document.getElementById('todayCards');
        if (!container) return;

        const stocks = await Analytics.getTodayStocks();

        if (stocks.length === 0) {
            container.innerHTML = '<p style="text-align: center; color: var(--text-secondary);">아직 데이터가 없습니다.</p>';
            return;
        }

        const html = stocks.map(stock => `
            <div class="today-card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                    <span class="rank ${stock.rank <= 3 ? 'top3' : ''}">${stock.rank}</span>
                    <span class="score-badge">${stock.score}점</span>
                </div>
                <div class="stock-name">${stock.name}</div>
                <div class="stock-code">${stock.code}</div>
                <div style="margin-top: 0.5rem; font-size: 0.85rem; color: var(--text-secondary);">
                    ${stock.reason}
                </div>
            </div>
        `).join('');

        container.innerHTML = html;
    },

    /**
     * 거래 내역 테이블 렌더링
     */
    renderTransactionTable() {
        TableUtils.init(this.state.trades);
        TableUtils.populateReasonFilter();
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
    }
};
