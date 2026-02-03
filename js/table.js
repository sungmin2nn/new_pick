// Table Utilities - 테이블 정렬/필터/검색

const TableUtils = {
    currentData: [],
    filteredData: [],
    sortConfig: { column: 'date', direction: 'desc' },
    filters: { result: 'all', reason: 'all', entry: 'all' },
    searchQuery: '',
    currentPage: 1,
    perPage: 50,

    /**
     * 테이블 초기화
     */
    init(trades) {
        this.currentData = trades;
        this.filteredData = [...trades];
        this.currentPage = 1;
        this.applyFiltersAndSort();
    },

    /**
     * 컬럼으로 정렬
     */
    sortBy(column) {
        // 같은 컬럼 클릭 시 방향 토글
        if (this.sortConfig.column === column) {
            this.sortConfig.direction = this.sortConfig.direction === 'asc' ? 'desc' : 'asc';
        } else {
            this.sortConfig.column = column;
            this.sortConfig.direction = 'desc';
        }

        this.applyFiltersAndSort();
    },

    /**
     * 필터 적용
     */
    applyFilters(filters) {
        this.filters = { ...this.filters, ...filters };
        this.currentPage = 1;
        this.applyFiltersAndSort();
    },

    /**
     * 검색
     */
    search(query) {
        this.searchQuery = query.toLowerCase();
        this.currentPage = 1;
        this.applyFiltersAndSort();
    },

    /**
     * 필터 및 정렬 적용
     */
    applyFiltersAndSort() {
        // 1. 필터링
        let filtered = [...this.currentData];

        // 결과 필터
        if (this.filters.result !== 'all') {
            filtered = filtered.filter(t => t.result === this.filters.result);
        }

        // 사유 필터
        if (this.filters.reason !== 'all') {
            filtered = filtered.filter(t => t.selection_reason === this.filters.reason);
        }

        // 매수여부 필터
        if (this.filters.entry !== 'all') {
            if (this.filters.entry === 'buy') {
                filtered = filtered.filter(t => t.should_buy !== false);
            } else if (this.filters.entry === 'skip') {
                filtered = filtered.filter(t => t.should_buy === false);
            }
        }

        // 검색
        if (this.searchQuery) {
            filtered = filtered.filter(t =>
                t.stock_name.toLowerCase().includes(this.searchQuery) ||
                t.stock_code.toLowerCase().includes(this.searchQuery)
            );
        }

        // 2. 정렬
        const column = this.sortConfig.column;
        const direction = this.sortConfig.direction;

        filtered.sort((a, b) => {
            let aVal, bVal;

            switch (column) {
                case 'date':
                    aVal = a.date;
                    bVal = b.date;
                    break;
                case 'name':
                    aVal = a.stock_name;
                    bVal = b.stock_name;
                    break;
                case 'code':
                    aVal = a.stock_code;
                    bVal = b.stock_code;
                    break;
                case 'score':
                    aVal = a.selection_score;
                    bVal = b.selection_score;
                    break;
                case 'return':
                    aVal = a.return_percent;
                    bVal = b.return_percent;
                    break;
                case 'profit':
                    aVal = a.profit;
                    bVal = b.profit;
                    break;
                case 'shares':
                    aVal = a.shares;
                    bVal = b.shares;
                    break;
                case 'shouldBuy':
                    aVal = a.should_buy ? 1 : 0;
                    bVal = b.should_buy ? 1 : 0;
                    break;
                default:
                    aVal = a.date;
                    bVal = b.date;
            }

            if (typeof aVal === 'string') {
                return direction === 'asc'
                    ? aVal.localeCompare(bVal)
                    : bVal.localeCompare(aVal);
            } else {
                return direction === 'asc'
                    ? aVal - bVal
                    : bVal - aVal;
            }
        });

        this.filteredData = filtered;
        this.render();
    },

    /**
     * 페이지 이동
     */
    goToPage(page) {
        const totalPages = Math.ceil(this.filteredData.length / this.perPage);
        if (page < 1 || page > totalPages) return;
        this.currentPage = page;
        this.render();
    },

    /**
     * 테이블 렌더링
     */
    render() {
        const tbody = document.getElementById('transactionTableBody');
        if (!tbody) return;

        // 페이지네이션 계산
        const start = (this.currentPage - 1) * this.perPage;
        const end = start + this.perPage;
        const pageData = this.filteredData.slice(start, end);

        // 테이블 행 생성
        tbody.innerHTML = pageData.map(trade => {
            const resultBadge = this.getResultBadge(trade.result);
            const entryBadge = this.getEntryBadge(trade.should_buy, trade.skip_reason);
            const returnClass = trade.return_percent >= 0 ? 'positive' : 'negative';
            const returnSign = trade.return_percent >= 0 ? '+' : '';

            return `
                <tr>
                    <td>${trade.date}</td>
                    <td style="text-align: left;">
                        <div style="font-weight: 600;">${trade.stock_name}</div>
                    </td>
                    <td style="font-family: var(--font-mono);">${trade.stock_code}</td>
                    <td><span class="score-badge">${trade.selection_score}</span></td>
                    <td style="text-align: left; font-size: 0.85rem;">${trade.selection_reason}</td>
                    <td>${entryBadge}</td>
                    <td>${Utils.formatNumber(trade.buy_price)}</td>
                    <td style="font-family: var(--font-mono);">${Utils.formatNumber(trade.shares)}주</td>
                    <td>${Utils.formatNumber(trade.sell_price)}</td>
                    <td>
                        <span class="price-change ${returnClass}">
                            ${returnSign}${trade.return_percent.toFixed(2)}%
                        </span>
                    </td>
                    <td>
                        <span class="price-change ${returnClass}">
                            ${returnSign}${Utils.formatNumber(Math.round(trade.profit))}
                        </span>
                    </td>
                    <td>${resultBadge}</td>
                </tr>
            `;
        }).join('');

        // 페이지네이션 렌더링
        this.renderPagination();

        // 헤더 정렬 표시 업데이트
        this.updateSortIndicators();
    },

    /**
     * 결과 뱃지 생성
     */
    getResultBadge(result) {
        const badges = {
            profit: '<span style="background: #f56565; color: white; padding: 2px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: 600;">익절</span>',
            loss: '<span style="background: #4299e1; color: white; padding: 2px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: 600;">손절</span>',
            none: '<span style="background: #a0aec0; color: white; padding: 2px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: 600;">미달</span>'
        };
        return badges[result] || badges.none;
    },

    /**
     * 매수여부 뱃지 생성
     */
    getEntryBadge(shouldBuy, skipReason) {
        if (shouldBuy !== false) {
            return '<span style="background: #48bb78; color: white; padding: 2px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: 600;">매수</span>';
        } else {
            const reason = skipReason || '조건미충족';
            return `<span style="background: #ed8936; color: white; padding: 2px 8px; border-radius: 3px; font-size: 0.75rem; font-weight: 600;" title="${reason}">스킵</span>`;
        }
    },

    /**
     * 페이지네이션 렌더링
     */
    renderPagination() {
        const pagination = document.getElementById('tablePagination');
        if (!pagination) return;

        const totalPages = Math.ceil(this.filteredData.length / this.perPage);
        if (totalPages <= 1) {
            pagination.innerHTML = '';
            return;
        }

        const buttons = [];

        // 이전 버튼
        if (this.currentPage > 1) {
            buttons.push(`<button onclick="TableUtils.goToPage(${this.currentPage - 1})">◀ 이전</button>`);
        }

        // 페이지 번호 (최대 5개 표시)
        const startPage = Math.max(1, this.currentPage - 2);
        const endPage = Math.min(totalPages, startPage + 4);

        for (let i = startPage; i <= endPage; i++) {
            const activeClass = i === this.currentPage ? 'active' : '';
            buttons.push(`<button class="${activeClass}" onclick="TableUtils.goToPage(${i})">${i}</button>`);
        }

        // 다음 버튼
        if (this.currentPage < totalPages) {
            buttons.push(`<button onclick="TableUtils.goToPage(${this.currentPage + 1})">다음 ▶</button>`);
        }

        pagination.innerHTML = buttons.join('');
    },

    /**
     * 정렬 표시 업데이트
     */
    updateSortIndicators() {
        // 모든 헤더에서 정렬 표시 제거
        const headers = document.querySelectorAll('.transaction-table th');
        headers.forEach(th => {
            th.classList.remove('sort-asc', 'sort-desc');
        });

        // 현재 정렬 컬럼에 표시 추가
        const columnMap = {
            date: 0,
            name: 1,
            code: 2,
            score: 3,
            shouldBuy: 5,
            shares: 7,
            return: 9,
            profit: 10
        };

        const columnIndex = columnMap[this.sortConfig.column];
        if (columnIndex !== undefined && headers[columnIndex]) {
            headers[columnIndex].classList.add(`sort-${this.sortConfig.direction}`);
        }
    },

    /**
     * 모든 선정사유 목록 가져오기
     */
    getAllReasons() {
        const reasons = new Set();
        this.currentData.forEach(trade => {
            if (trade.selection_reason) {
                reasons.add(trade.selection_reason);
            }
        });
        return Array.from(reasons).sort();
    },

    /**
     * 사유 필터 옵션 채우기
     */
    populateReasonFilter() {
        const select = document.getElementById('reasonFilter');
        if (!select) return;

        const reasons = this.getAllReasons();
        const options = ['<option value="all">모든 사유</option>'];

        reasons.forEach(reason => {
            options.push(`<option value="${reason}">${reason}</option>`);
        });

        select.innerHTML = options.join('');
    }
};
