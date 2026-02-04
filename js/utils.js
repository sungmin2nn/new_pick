// Utility Functions

const Utils = {
    /**
     * Format date to YYYY-MM-DD
     */
    formatDate(date) {
        if (typeof date === 'string') {
            date = new Date(date);
        }
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    },

    /**
     * Format date to YYYYMMDD (for intraday file names)
     */
    formatDateToYYYYMMDD(date) {
        if (typeof date === 'string') {
            date = new Date(date);
        }
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}${month}${day}`;
    },

    /**
     * Parse YYYYMMDD string to Date
     */
    parseYYYYMMDD(dateStr) {
        const year = parseInt(dateStr.substr(0, 4));
        const month = parseInt(dateStr.substr(4, 2)) - 1;
        const day = parseInt(dateStr.substr(6, 2));
        return new Date(year, month, day);
    },

    /**
     * Get day of week in Korean
     */
    getDayOfWeek(date) {
        if (typeof date === 'string') {
            date = new Date(date);
        }
        const days = ['일', '월', '화', '수', '목', '금', '토'];
        return days[date.getDay()];
    },

    /**
     * Format number with thousand separators
     */
    formatNumber(num) {
        if (num === null || num === undefined || isNaN(num) || !isFinite(num)) return '-';
        return num.toLocaleString('ko-KR');
    },

    /**
     * Format currency (KRW)
     */
    formatCurrency(amount) {
        if (amount === null || amount === undefined || isNaN(amount) || !isFinite(amount)) return '-';
        return amount.toLocaleString('ko-KR') + '원';
    },

    /**
     * Format percentage
     */
    formatPercent(value, decimals = 2) {
        if (value === null || value === undefined || isNaN(value) || !isFinite(value)) return '-';
        return value.toFixed(decimals) + '%';
    },

    /**
     * Format percentage with color class
     */
    formatPercentWithColor(value, decimals = 2) {
        if (value === null || value === undefined || isNaN(value) || !isFinite(value)) return '-';
        const sign = value >= 0 ? '+' : '';
        const colorClass = value >= 0 ? 'positive' : 'negative';
        return `<span class="price-change ${colorClass}">${sign}${value.toFixed(decimals)}%</span>`;
    },

    /**
     * Get date range array (excluding weekends)
     */
    getDateRange(startDate, endDate) {
        const dates = [];
        const start = new Date(startDate);
        const end = new Date(endDate);

        for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
            const dayOfWeek = d.getDay();
            // Exclude weekends (0 = Sunday, 6 = Saturday)
            if (dayOfWeek !== 0 && dayOfWeek !== 6) {
                dates.push(new Date(d));
            }
        }

        return dates;
    },

    /**
     * Calculate date N days ago
     */
    daysAgo(days) {
        const date = new Date();
        date.setDate(date.getDate() - days);
        return date;
    },

    /**
     * Get start of year
     */
    startOfYear() {
        const now = new Date();
        return new Date(now.getFullYear(), 0, 1);
    },

    /**
     * Get start of month
     */
    startOfMonth() {
        const now = new Date();
        return new Date(now.getFullYear(), now.getMonth(), 1);
    },

    /**
     * Truncate text with ellipsis
     */
    truncate(text, maxLength) {
        if (!text) return '';
        if (text.length <= maxLength) return text;
        return text.substring(0, maxLength - 3) + '...';
    },

    /**
     * Debounce function
     */
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    /**
     * Export data to CSV
     */
    exportToCSV(data, filename) {
        if (!data || data.length === 0) {
            alert('내보낼 데이터가 없습니다.');
            return;
        }

        // Get headers from first row
        const headers = Object.keys(data[0]);

        // Build CSV content
        let csv = headers.join(',') + '\n';

        data.forEach(row => {
            const values = headers.map(header => {
                let value = row[header];
                // Escape commas and quotes
                if (typeof value === 'string' && (value.includes(',') || value.includes('"'))) {
                    value = '"' + value.replace(/"/g, '""') + '"';
                }
                return value;
            });
            csv += values.join(',') + '\n';
        });

        // Create download link
        const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);

        link.setAttribute('href', url);
        link.setAttribute('download', filename);
        link.style.visibility = 'hidden';

        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }
};
