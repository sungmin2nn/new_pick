// 데이터 로딩 API
const API = {
    // 전역 변수
    currentData: [],
    allHistoryData: {},
    availableDates: [],

    // 히스토리 데이터 로드
    async loadHistory() {
        try {
            let response = await fetch('data/history.json');
            if (!response.ok) {
                response = await fetch('history.json');
            }

            if (response.ok) {
                const historyData = await response.json();
                this.allHistoryData = historyData.data_by_date || {};
                this.availableDates = historyData.dates || [];
                console.log('[API] 히스토리 로드 완료:', this.availableDates.length, '개 날짜');
                return true;
            }
            return false;
        } catch (error) {
            console.error('[API] 히스토리 로드 에러:', error);
            return false;
        }
    },

    // 종목 데이터 로드
    async loadStocks(selectedDate) {
        try {
            // 날짜 선택 시 히스토리에서 로드
            if (selectedDate && this.allHistoryData[selectedDate]) {
                this.currentData = this.allHistoryData[selectedDate].map((item, index) => ({
                    ...item,
                    code: item.stock_code || item.code,
                    name: item.stock_name || item.name,
                    rank: index + 1,
                    date: selectedDate,
                    score_detail: {
                        disclosure: item.disclosure_score || 0,
                        news: item.news_score || 0,
                        theme_keywords: item.theme_score || 0,
                        investor: item.investor_score || 0,
                        trading_value: item.trading_value_score || 0,
                        market_cap: item.market_cap_score || 0,
                        price_momentum: item.price_momentum_score || 0,
                        volume_surge: item.volume_surge_score || 0,
                        turnover_rate: item.turnover_rate_score || 0,
                        material_overlap: item.material_overlap_score || 0,
                        news_timing: item.news_timing_score || 0
                    }
                }));
                return this.currentData;
            }

            // 최신 데이터 로드
            let response = await fetch('data/morning_candidates.json');
            if (!response.ok) {
                response = await fetch('morning_candidates.json');
            }

            if (!response.ok) {
                throw new Error(`데이터 로드 실패 (HTTP ${response.status})`);
            }

            const data = await response.json();
            this.currentData = (data.candidates || []).map((item, index) => ({
                ...item,
                rank: index + 1,
                date: data.date
            }));

            return this.currentData;
        } catch (error) {
            console.error('[API] 데이터 로드 에러:', error);
            throw error;
        }
    }
};
