// 백테스트 관리
const BacktestApp = {
    results: null,
    chart: null,

    setQuickPeriod(period) {
        const endDate = new Date();
        let startDate = new Date();

        switch(period) {
            case 'year':
                startDate = new Date(endDate.getFullYear(), 0, 1);
                break;
            case 'month':
                startDate = new Date(endDate.getFullYear(), endDate.getMonth(), 1);
                break;
            case 'week':
                startDate = new Date(endDate);
                startDate.setDate(endDate.getDate() - 7);
                break;
            case '30days':
                startDate = new Date(endDate);
                startDate.setDate(endDate.getDate() - 30);
                break;
            case '7days':
                startDate = new Date(endDate);
                startDate.setDate(endDate.getDate() - 7);
                break;
        }

        document.getElementById('periodStartDate').value = this.formatDate(startDate);
        document.getElementById('periodEndDate').value = this.formatDate(endDate);
    },

    formatDate(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    },

    formatDateToYYYYMMDD(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}${month}${day}`;
    },

    async runBacktest() {
        const startDateStr = document.getElementById('periodStartDate').value;
        const endDateStr = document.getElementById('periodEndDate').value;
        const initialCapital = parseFloat(document.getElementById('initialInvestment').value);
        const maxPerStock = parseFloat(document.getElementById('maxPerStock').value);
        const buyExpensive = document.getElementById('buyExpensiveStocks').checked;

        if (!startDateStr || !endDateStr) {
            alert('시작일과 종료일을 선택해주세요.');
            return;
        }

        if (initialCapital < 100000) {
            alert('투자금은 최소 10만원 이상이어야 합니다.');
            return;
        }

        if (maxPerStock < 10000) {
            alert('종목당 제한 금액은 최소 1만원 이상이어야 합니다.');
            return;
        }

        try {
            // 날짜 범위 생성
            const startDate = new Date(startDateStr);
            const endDate = new Date(endDateStr);
            const tradingDays = [];

            for (let d = new Date(startDate); d <= endDate; d.setDate(d.getDate() + 1)) {
                const dayOfWeek = d.getDay();
                if (dayOfWeek !== 0 && dayOfWeek !== 6) {
                    tradingDays.push(this.formatDateToYYYYMMDD(new Date(d)));
                }
            }

            // 각 날짜의 백테스팅 데이터 로드
            let capital = initialCapital;
            const trades = [];
            const equityCurve = [{date: startDateStr, capital: capital}];
            let consecutiveWins = 0;
            let consecutiveLosses = 0;
            let maxWinStreak = 0;
            let maxLossStreak = 0;
            let dailyReturns = [];

            for (const dateStr of tradingDays) {
                try {
                    const response = await fetch(`data/intraday/intraday_${dateStr}.json`);
                    if (!response.ok) continue;

                    const data = await response.json();
                    const stocks = Object.values(data.stocks || {});
                    const dateFormatted = `${dateStr.substr(0,4)}-${dateStr.substr(4,2)}-${dateStr.substr(6,2)}`;
                    const tradeDate = new Date(dateFormatted);

                    let dailyReturn = 0;
                    let dailyTradeCount = 0;

                    for (const stock of stocks) {
                        const pl = stock.profit_loss_analysis;
                        if (!pl) continue;

                        const openingPrice = pl.opening_price;

                        // 주식 수 계산
                        let shares = 0;
                        let investAmount = 0;

                        if (openingPrice > maxPerStock) {
                            if (buyExpensive) {
                                shares = 1;
                                investAmount = openingPrice;
                            } else {
                                continue;
                            }
                        } else {
                            shares = Math.floor(maxPerStock / openingPrice);
                            investAmount = shares * openingPrice;
                        }

                        if (investAmount > capital) {
                            continue;
                        }

                        // 실제 매도가 계산
                        let sellPrice = 0;
                        if (pl.first_hit === 'profit') {
                            sellPrice = pl.profit_target_price;
                        } else if (pl.first_hit === 'loss') {
                            sellPrice = pl.loss_target_price;
                        } else {
                            sellPrice = pl.closing_price;
                        }

                        // 실제 손익 계산
                        const sellAmount = shares * sellPrice;
                        const profit = sellAmount - investAmount;
                        const actualReturnPercent = (profit / investAmount) * 100;

                        // 자본 업데이트
                        capital = capital - investAmount + sellAmount;
                        dailyReturn += actualReturnPercent;
                        dailyTradeCount++;

                        trades.push({
                            date: dateFormatted,
                            stock_name: stock.name,
                            profit: profit,
                            return_percent: actualReturnPercent,
                            capital_after: capital
                        });

                        // 연승/연패 계산
                        if (profit > 0) {
                            consecutiveWins++;
                            consecutiveLosses = 0;
                            maxWinStreak = Math.max(maxWinStreak, consecutiveWins);
                        } else if (profit < 0) {
                            consecutiveLosses++;
                            consecutiveWins = 0;
                            maxLossStreak = Math.max(maxLossStreak, consecutiveLosses);
                        }
                    }

                    equityCurve.push({date: dateFormatted, capital: capital});
                    if (dailyTradeCount > 0) {
                        dailyReturns.push(dailyReturn / dailyTradeCount);
                    }

                } catch (e) {
                    console.warn(`${dateStr} 데이터 로드 실패:`, e);
                }
            }

            // 통계 계산
            this.results = this.calculateStatistics(trades, capital, initialCapital);

            // UI 업데이트
            this.displayResults(this.results);
            this.renderChart(equityCurve);

        } catch (error) {
            console.error('백테스팅 실행 실패:', error);
            alert('백테스팅 실행 중 오류가 발생했습니다.');
        }
    },

    calculateStatistics(trades, finalCapital, initialCapital) {
        const totalTrades = trades.length;
        const profitTrades = trades.filter(t => t.return_percent > 0);
        const lossTrades = trades.filter(t => t.return_percent < 0);

        const winRate = totalTrades > 0 ? (profitTrades.length / totalTrades * 100) : 0;
        const totalReturn = ((finalCapital - initialCapital) / initialCapital * 100);

        return {
            finalCapital,
            totalReturn,
            totalTrades,
            winRate,
            profitCount: profitTrades.length,
            lossCount: lossTrades.length
        };
    },

    displayResults(results) {
        document.getElementById('backtestResults').style.display = 'block';
        document.getElementById('btFinalCapital').textContent = results.finalCapital.toLocaleString() + '원';
        document.getElementById('btTotalReturn').textContent = results.totalReturn.toFixed(2) + '%';
        document.getElementById('btTotalReturn').style.color = results.totalReturn >= 0 ? '#f56565' : '#4299e1';
        document.getElementById('btTotalTrades').textContent = results.totalTrades + '건';
        document.getElementById('btWinRate').textContent = results.winRate.toFixed(2) + '%';
    },

    renderChart(equityCurve) {
        const ctx = document.getElementById('equityChart');
        if (!ctx) return;

        if (this.chart) {
            this.chart.destroy();
        }

        this.chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: equityCurve.map(d => d.date),
                datasets: [{
                    label: '자본',
                    data: equityCurve.map(d => d.capital),
                    borderColor: '#0066cc',
                    backgroundColor: 'rgba(0, 102, 204, 0.1)',
                    tension: 0.1,
                    fill: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: false,
                        ticks: {
                            callback: function(value) {
                                return value.toLocaleString() + '원';
                            }
                        }
                    }
                }
            }
        });
    }
};
