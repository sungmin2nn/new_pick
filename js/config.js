// 설정
const CONFIG = {
    MAX_SCORE: 145,
    SCORE_FIELDS: [
        { key: 'disclosure', label: '공시' },
        { key: 'news', label: '뉴스' },
        { key: 'theme_keywords', label: '테마' },
        { key: 'investor', label: '투자자' },
        { key: 'trading_value', label: '거래대금' },
        { key: 'market_cap', label: '시총' },
        { key: 'price_momentum', label: '가격' },
        { key: 'volume_surge', label: '거래량' },
        { key: 'turnover_rate', label: '회전율' },
        { key: 'material_overlap', label: '중복도' },
        { key: 'news_timing', label: '시간대' }
    ],
    MOBILE_FIELDS: ['disclosure', 'news', 'theme_keywords', 'investor'], // 모바일에서 기본 표시할 필드
    LEADING_BONUS: 5
};
