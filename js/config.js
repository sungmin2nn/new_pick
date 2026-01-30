// 설정
const CONFIG = {
    MAX_SCORE: 145,
    SCORE_FIELDS: [
        { key: 'disclosure', label: '공시', max_score: 20 },
        { key: 'news', label: '뉴스', max_score: 15 },
        { key: 'theme_keywords', label: '테마', max_score: 15 },
        { key: 'investor', label: '투자자', max_score: 15 },
        { key: 'trading_value', label: '거래대금', max_score: 15 },
        { key: 'market_cap', label: '시총', max_score: 15 },
        { key: 'price_momentum', label: '가격', max_score: 15 },
        { key: 'volume_surge', label: '거래량', max_score: 15 },
        { key: 'turnover_rate', label: '회전율', max_score: 10 },
        { key: 'material_overlap', label: '중복도', max_score: 5 },
        { key: 'news_timing', label: '시간대', max_score: 5 }
    ],
    MOBILE_FIELDS: ['disclosure', 'news', 'theme_keywords', 'investor'], // 모바일에서 기본 표시할 필드
    LEADING_BONUS: 5
};

// 시스템 정보 (자동 문서화)
const SYSTEM_INFO = {
    version: '2.0.0',
    lastUpdated: '2026-01-30',
    features: [
        {
            icon: '🎯',
            title: '핵심 기능',
            items: [
                '공시 수집 및 분석',
                '뉴스 모니터링',
                '테마 키워드 매칭',
                '투자자 동향 분석',
                '시장 데이터 분석'
            ]
        },
        {
            icon: '⚙️',
            title: '점수 체계',
            items: [
                `총점: ${CONFIG.MAX_SCORE}점 (대장주 보너스 +${CONFIG.LEADING_BONUS}점)`,
                ...CONFIG.SCORE_FIELDS.map(f => `${f.label}: 최대 ${f.max_score}점`)
            ]
        },
        {
            icon: '🕐',
            title: '실행 시간',
            items: [
                '매일 08:30 - 장전 종목 선정',
                '실시간 데이터 업데이트',
                '자동 백테스팅 및 분석'
            ]
        },
        {
            icon: '📊',
            title: '백테스팅 설정',
            items: [
                '초기 투자금: 1,000,000원',
                '종목당 제한: 100,000원',
                '익절 목표: +3%',
                '손절 목표: -2%',
                '고가 종목: 1주만 매수 옵션'
            ]
        }
    ]
};
