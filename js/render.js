// 렌더링 함수
const Render = {
    // 점수 아이콘 생성
    getScoreIcon(metadata, stock, scoreType) {
        if (!metadata) {
            metadata = this.generateFallbackMetadata(stock, scoreType);
        }

        const status = metadata.status || 'success';
        const value = metadata.value || 0;
        const message = metadata.message || '';

        if (value === 0 && (status === 'no_data' || status === 'no_match')) {
            return `<span class="status-icon warning tooltip">⚠️<span class="tooltiptext">${message}</span></span>`;
        } else if (value > 0) {
            return `<span class="status-icon success tooltip">✅<span class="tooltiptext">${message}</span></span>`;
        } else if (status === 'error') {
            return `<span class="status-icon error tooltip">❌<span class="tooltiptext">${message}</span></span>`;
        }
        return '';
    },

    // 메타데이터 자동 생성
    generateFallbackMetadata(stock, scoreType) {
        const scoreDetail = stock.score_detail || {};
        const value = scoreDetail[scoreType] || stock[`${scoreType}_score`] || 0;

        const generators = {
            disclosure: () => {
                const count = stock.disclosure_count || 0;
                return {
                    value,
                    status: count > 0 ? 'success' : 'no_data',
                    message: count > 0 ? `${count}건 수집` : '공시 없음'
                };
            },
            news: () => {
                const count = stock.news_mentions || 0;
                const positive = stock.positive_news || 0;
                return {
                    value,
                    status: count > 0 ? 'success' : 'no_data',
                    message: count > 0 ? `${count}건 (긍정 ${positive})` : '뉴스 없음'
                };
            },
            theme_keywords: () => {
                const themes = stock.matched_themes || [];
                return {
                    value,
                    status: themes.length > 0 ? 'success' : 'no_match',
                    message: themes.length > 0 ? themes.join(', ') : '테마 매칭 없음'
                };
            },
            investor: () => {
                const foreign = stock.foreign_buy || 0;
                const institution = stock.institution_buy || 0;
                return {
                    value,
                    status: (foreign > 0 || institution > 0) ? 'success' : 'no_data',
                    message: foreign > 0 ? '외국인 순매수' : institution > 0 ? '기관 순매수' : '순매수 없음'
                };
            }
        };

        return generators[scoreType] ? generators[scoreType]() : {
            value,
            status: 'success',
            message: 'OK'
        };
    },

    // 데스크톱 테이블 렌더링
    renderDesktopTable(stocks) {
        const tbody = document.getElementById('stockTableBody');
        tbody.innerHTML = '';

        stocks.forEach(stock => {
            const changeClass = (stock.price_change_percent || 0) >= 0 ? 'positive' : 'negative';
            const changeSymbol = (stock.price_change_percent || 0) >= 0 ? '+' : '';

            const leadingBonus = stock.is_leading ? CONFIG.LEADING_BONUS : 0;
            const baseScore = Math.round(stock.total_score || 0) - leadingBonus;
            const totalScoreDisplay = leadingBonus > 0
                ? `<span class="tooltip">${baseScore}+${leadingBonus}<span class="tooltiptext">기본 ${baseScore}점 + 대장주 보너스 ${leadingBonus}점</span></span>`
                : `${Math.round(stock.total_score || 0)}`;

            const meta = stock.score_metadata || {};
            const row = document.createElement('tr');

            const scoreHtml = CONFIG.SCORE_FIELDS.map(field => {
                const score = Math.round(stock.score_detail?.[field.key] || stock[`${field.key}_score`] || 0);
                const icon = ['disclosure', 'news', 'theme_keywords', 'investor'].includes(field.key)
                    ? this.getScoreIcon(meta[field.key], stock, field.key)
                    : '';
                return `
                    <td>
                        <div class="score-with-status">
                            <span class="score-badge">${score}</span>
                            ${icon}
                        </div>
                    </td>
                `;
            }).join('');

            row.innerHTML = `
                <td>${stock.date || 'N/A'}</td>
                <td><span class="rank ${stock.rank <= 3 ? 'top3' : ''}">${stock.rank}</span></td>
                <td style="text-align: left;">
                    <div class="stock-name">${stock.name || 'N/A'} ${stock.is_leading ? '👑' : ''}</div>
                    <div class="stock-code">${stock.code || 'N/A'}</div>
                </td>
                <td><span class="score">${totalScoreDisplay}/<small>${CONFIG.MAX_SCORE}</small></span></td>
                ${scoreHtml}
                <td style="text-align: left; font-size: 0.75rem;">${stock.selection_reason || '-'}</td>
                <td>${(stock.current_price || 0).toLocaleString()}</td>
                <td><span class="price-change ${changeClass}">${changeSymbol}${(stock.price_change_percent || 0).toFixed(2)}%</span></td>
                <td>${Math.round((stock.trading_value || 0) / 100000000)}억</td>
            `;

            tbody.appendChild(row);
        });
    },

    // 모바일 카드 렌더링
    renderMobileCards(stocks) {
        const container = document.getElementById('mobileCards');
        container.innerHTML = '';

        stocks.forEach(stock => {
            const card = document.createElement('div');
            card.className = 'stock-card';

            const changeClass = (stock.price_change_percent || 0) >= 0 ? 'positive' : 'negative';
            const changeSymbol = (stock.price_change_percent || 0) >= 0 ? '+' : '';

            const leadingBonus = stock.is_leading ? CONFIG.LEADING_BONUS : 0;
            const totalScore = Math.round(stock.total_score || 0);

            const meta = stock.score_metadata || {};

            card.innerHTML = `
                <div class="stock-card-header">
                    <div class="stock-card-title">
                        <div class="stock-name">${stock.name || 'N/A'} ${stock.is_leading ? '👑' : ''}</div>
                        <div class="stock-code">${stock.code || 'N/A'}</div>
                    </div>
                    <div class="stock-card-score">${totalScore}</div>
                </div>
                <div class="stock-card-detail">
                    ${CONFIG.MOBILE_FIELDS.map(key => {
                        const field = CONFIG.SCORE_FIELDS.find(f => f.key === key);
                        const score = Math.round(stock.score_detail?.[key] || stock[`${key}_score`] || 0);
                        const icon = this.getScoreIcon(meta[key], stock, key);
                        return `
                            <div class="stock-card-item">
                                <span class="stock-card-label">${field.label}</span>
                                <span class="stock-card-value">${score} ${icon}</span>
                            </div>
                        `;
                    }).join('')}
                    <div class="stock-card-item">
                        <span class="stock-card-label">현재가</span>
                        <span class="stock-card-value">${(stock.current_price || 0).toLocaleString()}</span>
                    </div>
                    <div class="stock-card-item">
                        <span class="stock-card-label">등락률</span>
                        <span class="stock-card-value price-change ${changeClass}">${changeSymbol}${(stock.price_change_percent || 0).toFixed(2)}%</span>
                    </div>
                </div>
                <button class="expand-btn" onclick="this.nextElementSibling.classList.toggle('active')">
                    상세 점수 보기 ▼
                </button>
                <div class="stock-card-expanded">
                    <div class="score-grid">
                        ${CONFIG.SCORE_FIELDS.filter(f => !CONFIG.MOBILE_FIELDS.includes(f.key)).map(field => {
                            const score = Math.round(stock.score_detail?.[field.key] || stock[`${field.key}_score`] || 0);
                            return `
                                <div class="stock-card-item">
                                    <span class="stock-card-label">${field.label}</span>
                                    <span class="stock-card-value">${score}</span>
                                </div>
                            `;
                        }).join('')}
                    </div>
                </div>
            `;

            container.appendChild(card);
        });
    }
};
