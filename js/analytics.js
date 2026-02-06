// Analytics Engine - 백테스팅 데이터 분석

const Analytics = {
    /**
     * 기간 내 모든 intraday 데이터 로드 및 거래 내역 생성
     */
    async loadIntradayData(startDate, endDate, initialCapital = 1000000, maxPerStock = 100000, buyExpensive = true) {
        const tradingDays = Utils.getDateRange(startDate, endDate);
        const trades = [];
        const equityCurve = [{ date: Utils.formatDate(startDate), capital: initialCapital }];

        let capital = initialCapital;

        for (const day of tradingDays) {
            try {
                const dateStr = Utils.formatDateToYYYYMMDD(day);
                const response = await fetch(`data/intraday/intraday_${dateStr}.json`);

                if (!response.ok) {
                    console.log(`[Analytics] ${dateStr} 데이터 없음`);
                    continue;
                }

                const data = await response.json();
                const stocks = Object.values(data.stocks || {});
                const dateFormatted = Utils.formatDate(day);

                for (const stock of stocks) {
                    const pl = stock.profit_loss_analysis;
                    if (!pl) continue;

                    // Entry Check 정보
                    const entryCheck = pl.entry_check || {};
                    const shouldBuy = pl.should_buy !== false;
                    const skipReason = pl.skip_reason || entryCheck.skip_reason || null;

                    const openingPrice = pl.opening_price;

                    // 주식 수 및 투자금 계산
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

                    // 매도가 결정 (actual_result 내부에서도 탐색)
                    const ar = pl.actual_result || {};
                    let sellPrice = 0;
                    let result = 'none';

                    if (pl.first_hit === 'profit') {
                        sellPrice = pl.profit_target_price || ar.profit_target_price || pl.closing_price || ar.closing_price || openingPrice;
                        result = 'profit';
                    } else if (pl.first_hit === 'loss') {
                        sellPrice = pl.loss_target_price || ar.loss_target_price || pl.closing_price || ar.closing_price || openingPrice;
                        result = 'loss';
                    } else {
                        sellPrice = pl.closing_price || ar.closing_price || openingPrice;
                        result = 'none';
                    }

                    // sellPrice가 없으면 거래 스킵
                    if (!sellPrice) continue;

                    // 손익 계산
                    const sellAmount = shares * sellPrice;
                    const profit = sellAmount - investAmount;
                    const returnPercent = investAmount > 0 ? (profit / investAmount) * 100 : 0;

                    // 자본 업데이트
                    capital = capital - investAmount + sellAmount;

                    trades.push({
                        date: dateFormatted,
                        stock_code: stock.code,
                        stock_name: stock.name,
                        selection_score: stock.selection_score || 0,
                        selection_reason: stock.selection_reason || '-',
                        should_buy: shouldBuy,
                        skip_reason: skipReason,
                        buy_price: openingPrice,
                        sell_price: sellPrice,
                        shares: shares,
                        invest_amount: investAmount,
                        sell_amount: sellAmount,
                        profit: profit,
                        return_percent: returnPercent,
                        result: result,
                        first_hit_time: pl.first_hit_time,
                        capital_after: capital,
                        actual_result: pl.actual_result,
                        virtual_result: pl.virtual_result
                    });
                }

                equityCurve.push({ date: dateFormatted, capital: capital });

            } catch (e) {
                console.warn(`[Analytics] ${Utils.formatDateToYYYYMMDD(day)} 처리 실패:`, e);
            }
        }

        return { trades, equityCurve, finalCapital: capital };
    },

    /**
     * 전체 성과 통계 계산
     */
    calculateOverallStats(trades, finalCapital, initialCapital) {
        const totalTrades = trades.length;
        const profitTrades = trades.filter(t => t.result === 'profit');
        const lossTrades = trades.filter(t => t.result === 'loss');
        const noneTrades = trades.filter(t => t.result === 'none');

        // 미달 세부 구분
        const noneProfitTrades = noneTrades.filter(t => t.return_percent > 0);
        const noneLossTrades = noneTrades.filter(t => t.return_percent < 0);
        const noneNeutralTrades = noneTrades.filter(t => t.return_percent === 0);

        const winRate = totalTrades > 0 ? (profitTrades.length / totalTrades * 100) : 0;
        const totalReturn = initialCapital > 0 ? ((finalCapital - initialCapital) / initialCapital * 100) : 0;

        const avgWin = profitTrades.length > 0
            ? profitTrades.reduce((sum, t) => sum + t.return_percent, 0) / profitTrades.length
            : 0;

        const avgLoss = lossTrades.length > 0
            ? lossTrades.reduce((sum, t) => sum + t.return_percent, 0) / lossTrades.length
            : 0;

        // 연승/연패 계산
        let currentStreak = 0;
        let maxWinStreak = 0;
        let maxLossStreak = 0;
        let streakType = null;

        trades.forEach(trade => {
            if (trade.result === 'profit') {
                if (streakType === 'win') {
                    currentStreak++;
                } else {
                    currentStreak = 1;
                    streakType = 'win';
                }
                maxWinStreak = Math.max(maxWinStreak, currentStreak);
            } else if (trade.result === 'loss') {
                if (streakType === 'loss') {
                    currentStreak++;
                } else {
                    currentStreak = 1;
                    streakType = 'loss';
                }
                maxLossStreak = Math.max(maxLossStreak, currentStreak);
            } else {
                currentStreak = 0;
                streakType = null;
            }
        });

        return {
            finalCapital,
            totalReturn,
            totalTrades,
            winRate,
            profitCount: profitTrades.length,
            lossCount: lossTrades.length,
            noneCount: noneTrades.length,
            noneProfitCount: noneProfitTrades.length,
            noneLossCount: noneLossTrades.length,
            noneNeutralCount: noneNeutralTrades.length,
            avgWin,
            avgLoss,
            maxWinStreak,
            maxLossStreak
        };
    },

    /**
     * 점수대별 성과 분석
     */
    analyzeByScoreRange(trades) {
        const ranges = [
            { label: '0-50점', min: 0, max: 50 },
            { label: '51-80점', min: 51, max: 80 },
            { label: '81-100점', min: 81, max: 100 },
            { label: '101점+', min: 101, max: 999 }
        ];

        return ranges.map(range => {
            const filtered = trades.filter(t =>
                t.selection_score >= range.min && t.selection_score <= range.max
            );

            const profitCount = filtered.filter(t => t.result === 'profit').length;
            const winRate = filtered.length > 0 ? (profitCount / filtered.length * 100) : 0;
            const avgReturn = filtered.length > 0
                ? filtered.reduce((sum, t) => sum + t.return_percent, 0) / filtered.length
                : 0;

            return {
                range: range.label,
                count: filtered.length,
                winRate,
                avgReturn
            };
        }).filter(r => r.count > 0);
    },

    /**
     * 일자별 성과 분석
     */
    analyzeByDate(trades) {
        const byDate = {};

        trades.forEach(trade => {
            if (!byDate[trade.date]) {
                byDate[trade.date] = {
                    date: trade.date,
                    trades: [],
                    profitCount: 0,
                    lossCount: 0,
                    noneCount: 0,
                    totalReturn: 0
                };
            }

            byDate[trade.date].trades.push(trade);
            if (trade.result === 'profit') byDate[trade.date].profitCount++;
            if (trade.result === 'loss') byDate[trade.date].lossCount++;
            if (trade.result === 'none') byDate[trade.date].noneCount++;
            byDate[trade.date].totalReturn += trade.return_percent;
        });

        return Object.values(byDate).sort((a, b) => b.date.localeCompare(a.date));
    },

    /**
     * 요일별 패턴 분석
     */
    analyzeByDayOfWeek(trades) {
        const days = ['월', '화', '수', '목', '금'];
        const byDay = {};

        days.forEach(day => {
            byDay[day] = {
                day,
                trades: [],
                profitCount: 0,
                lossCount: 0,
                noneProfitCount: 0,  // 미달(수익): 0% ~ +3%
                noneLossCount: 0,    // 미달(손실): -2% ~ 0%
                noneNeutralCount: 0  // 미달(유지): 정확히 0%
            };
        });

        trades.forEach(trade => {
            const day = Utils.getDayOfWeek(trade.date);
            if (byDay[day]) {
                byDay[day].trades.push(trade);
                if (trade.result === 'profit') {
                    byDay[day].profitCount++;
                } else if (trade.result === 'loss') {
                    byDay[day].lossCount++;
                } else if (trade.result === 'none') {
                    // 미달 세부 구분
                    if (trade.return_percent > 0) {
                        byDay[day].noneProfitCount++;
                    } else if (trade.return_percent < 0) {
                        byDay[day].noneLossCount++;
                    } else {
                        byDay[day].noneNeutralCount++;
                    }
                }
            }
        });

        return days.map(day => {
            const data = byDay[day];
            const count = data.trades.length;
            const winRate = count > 0 ? (data.profitCount / count * 100) : 0;
            const avgReturn = count > 0
                ? data.trades.reduce((sum, t) => sum + t.return_percent, 0) / count
                : 0;

            return {
                day,
                count,
                profitCount: data.profitCount,
                lossCount: data.lossCount,
                noneProfitCount: data.noneProfitCount,
                noneLossCount: data.noneLossCount,
                noneNeutralCount: data.noneNeutralCount,
                winRate,
                avgReturn
            };
        }).filter(d => d.count > 0);
    },

    /**
     * 선정사유 정규화 (유사한 사유 그룹핑)
     */
    normalizeReason(reason) {
        if (!reason) return '기타';

        // 소문자 변환 후 처리
        const normalized = reason.toLowerCase();

        // 공시 관련
        if (normalized.includes('공시')) {
            return '공시 관련';
        }

        // AI/반도체 테마 (여러 표현 통합)
        if (normalized.includes('ai') || normalized.includes('반도체')) {
            return 'AI·반도체 테마';
        }

        // 방산 테마
        if (normalized.includes('방산')) {
            return '방산 테마';
        }

        // 뉴스 관련
        if (normalized.includes('뉴스')) {
            // 긍정 뉴스
            if (normalized.includes('긍정')) {
                return '뉴스 (긍정)';
            }
            // 중립 뉴스
            if (normalized.includes('중립')) {
                return '뉴스 (중립)';
            }
            return '뉴스 관련';
        }

        // 기타
        return '기타';
    },

    /**
     * 선정사유별 성과 분석
     */
    analyzeByReason(trades) {
        const byReason = {};

        trades.forEach(trade => {
            const normalizedReason = this.normalizeReason(trade.selection_reason);

            if (!byReason[normalizedReason]) {
                byReason[normalizedReason] = {
                    reason: normalizedReason,
                    trades: [],
                    profitCount: 0,
                    lossCount: 0
                };
            }

            byReason[normalizedReason].trades.push(trade);
            if (trade.result === 'profit') byReason[normalizedReason].profitCount++;
            if (trade.result === 'loss') byReason[normalizedReason].lossCount++;
        });

        return Object.values(byReason).map(data => {
            const count = data.trades.length;
            const winRate = count > 0 ? (data.profitCount / count * 100) : 0;
            const avgReturn = count > 0
                ? data.trades.reduce((sum, t) => sum + t.return_percent, 0) / count
                : 0;

            return {
                reason: data.reason,
                count,
                winRate,
                avgReturn
            };
        }).sort((a, b) => b.count - a.count);
    },

    /**
     * 시간대별 익절/손절 패턴 분석
     */
    analyzeByTimeOfDay(trades) {
        const timeSlots = [
            { label: '09:00-09:30', start: '09:00', end: '09:30' },
            { label: '09:30-10:00', start: '09:30', end: '10:00' },
            { label: '10:00-10:30', start: '10:00', end: '10:30' },
            { label: '10:30-11:00', start: '10:30', end: '11:00' },
            { label: '11:00-11:30', start: '11:00', end: '11:30' },
            { label: '11:30-12:00', start: '11:30', end: '12:00' },
            { label: '12:00-12:30', start: '12:00', end: '12:30' },
            { label: '12:30-13:00', start: '12:30', end: '13:00' },
            { label: '13:00-13:30', start: '13:00', end: '13:30' },
            { label: '13:30-14:00', start: '13:30', end: '14:00' },
            { label: '14:00-14:30', start: '14:00', end: '14:30' },
            { label: '14:30-15:00', start: '14:30', end: '15:00' },
            { label: '15:00-15:30', start: '15:00', end: '15:30' }
        ];

        return timeSlots.map(slot => {
            const profitHits = trades.filter(t =>
                t.result === 'profit' &&
                t.first_hit_time &&
                t.first_hit_time >= slot.start &&
                t.first_hit_time < slot.end
            ).length;

            const lossHits = trades.filter(t =>
                t.result === 'loss' &&
                t.first_hit_time &&
                t.first_hit_time >= slot.start &&
                t.first_hit_time < slot.end
            ).length;

            return {
                timeSlot: slot.label,
                profitHits,
                lossHits
            };
        });
    },

    /**
     * 수익률 분포 분석
     */
    analyzeReturnDistribution(trades) {
        const buckets = [
            { label: '-10% 이하', min: -Infinity, max: -10 },
            { label: '-10% ~ -5%', min: -10, max: -5 },
            { label: '-5% ~ -3%', min: -5, max: -3 },
            { label: '-3% ~ -1%', min: -3, max: -1 },
            { label: '-1% ~ 0%', min: -1, max: 0 },
            { label: '0% ~ 1%', min: 0, max: 1 },
            { label: '1% ~ 3%', min: 1, max: 3 },
            { label: '3% ~ 5%', min: 3, max: 5 },
            { label: '5% ~ 10%', min: 5, max: 10 },
            { label: '10% 이상', min: 10, max: Infinity }
        ];

        return buckets.map(bucket => {
            const count = trades.filter(t =>
                t.return_percent >= bucket.min && t.return_percent < bucket.max
            ).length;

            return {
                bucket: bucket.label,
                count
            };
        });
    },

    /**
     * 오늘의 종목 조회 (최신 날짜의 상위 5개)
     */
    async getTodayStocks() {
        try {
            const response = await fetch('data/history.json');
            if (!response.ok) return [];

            const historyData = await response.json();
            if (!historyData.dates || historyData.dates.length === 0) return [];

            const latestDate = historyData.dates[0];
            const stocks = historyData.data_by_date[latestDate] || [];

            return stocks.slice(0, 5).map((stock, index) => ({
                rank: index + 1,
                code: stock.stock_code || stock.code,
                name: stock.stock_name || stock.name,
                score: stock.total_score || 0,
                reason: stock.selection_reason || '-',
                date: latestDate
            }));

        } catch (error) {
            console.error('[Analytics] 오늘의 종목 조회 실패:', error);
            return [];
        }
    },

    /**
     * 오늘의 종목 조회 (Entry Check 정보 포함)
     */
    async getTodayStocksWithEntryCheck() {
        try {
            // 1. 먼저 morning_candidates.json에서 오늘 날짜 확인
            let morningData = null;
            let morningDate = null;
            try {
                const morningResponse = await fetch('data/morning_candidates.json');
                if (morningResponse.ok) {
                    morningData = await morningResponse.json();
                    morningDate = morningData.date; // "2026-02-06" 형식
                }
            } catch (e) {
                console.log('[Analytics] morning_candidates.json 로드 실패');
            }

            // 2. 오늘 날짜의 intraday 파일 탐색
            const today = new Date();
            let intradayData = null;
            let intradayDateStr = null;

            // 최근 7일 내 데이터 탐색
            for (let i = 0; i < 7; i++) {
                const d = new Date(today);
                d.setDate(d.getDate() - i);
                const dateStr = Utils.formatDateToYYYYMMDD(d);

                try {
                    const response = await fetch(`data/intraday/intraday_${dateStr}.json`);
                    if (response.ok) {
                        intradayData = await response.json();
                        intradayDateStr = dateStr;
                        break;
                    }
                } catch (e) {
                    continue;
                }
            }

            // 3. morning_candidates가 intraday보다 최신이면 morning_candidates 사용
            if (morningData && morningDate) {
                const morningDateClean = morningDate.replace(/-/g, ''); // "20260206"

                // intraday가 없거나, morning이 더 최신이면 morning 사용
                if (!intradayData || (intradayDateStr && morningDateClean > intradayDateStr)) {
                    console.log('[Analytics] morning_candidates.json 사용 (더 최신):', morningDate);

                    const candidates = morningData.candidates || [];
                    return candidates.map(stock => ({
                        date: morningDate,
                        code: stock.code,
                        name: stock.name,
                        score: stock.total_score || 0,
                        reason: stock.selection_reason || '-',
                        shouldBuy: true, // 장전 선정 종목은 기본 매수
                        skipReason: null,
                        entryPrice: stock.current_price,
                        entryTime: null,
                        actualResult: null, // 아직 결과 없음
                        virtualResult: null
                    }));
                }
            }

            // 4. intraday 데이터 사용 (기존 로직)
            if (!intradayData || !intradayData.stocks) {
                return [];
            }

            const stocks = Object.values(intradayData.stocks);

            // 날짜 포맷: "20260204" → "2026-02-04"
            const rawDate = intradayData.date || '';
            const formattedDate = rawDate.length === 8
                ? `${rawDate.slice(0,4)}-${rawDate.slice(4,6)}-${rawDate.slice(6,8)}`
                : rawDate;

            return stocks.map(stock => {
                const pl = stock.profit_loss_analysis || {};
                const entryCheck = pl.entry_check || {};

                return {
                    date: formattedDate,
                    code: stock.code,
                    name: stock.name,
                    score: stock.selection_score || 0,
                    reason: stock.selection_reason || '-',
                    shouldBuy: pl.should_buy !== false,
                    skipReason: pl.skip_reason || entryCheck.skip_reason,
                    entryPrice: entryCheck.entry_price || pl.opening_price,
                    entryTime: entryCheck.entry_time,
                    actualResult: pl.actual_result,
                    virtualResult: pl.virtual_result
                };
            });

        } catch (error) {
            console.error('[Analytics] Entry Check 데이터 조회 실패:', error);
            return [];
        }
    }
};
