# 장전 종목 선정 시스템 설정

# 필터 기준
MIN_TRADING_VALUE = 100_000_000_000  # 거래대금 1,000억 이상
MIN_PRICE_CHANGE = 3.0  # 상승률 +3% 이상
MIN_MARKET_CAP = 100_000_000_000  # 시가총액 1,000억 이상
MAX_PRICE = 100_000  # 주가 10만원 이하
VOLUME_SPIKE_MULTIPLIER = 1.5  # 평균 거래량 대비 1.5배 이상

# 점수 배점 (총 100점)
SCORE_WEIGHTS = {
    'price_momentum': 30,  # 가격 모멘텀
    'volume': 25,          # 거래량
    'theme_keywords': 25,  # 테마/키워드
    'news': 20             # 뉴스
}

# 테마 키워드
THEME_KEYWORDS = {
    'AI': ['인공지능', 'AI', '챗GPT', 'ChatGPT', '생성형AI', 'LLM', '딥러닝', '머신러닝'],
    '반도체': ['반도체', '파운드리', 'HBM', '메모리', '시스템반도체', 'AP', 'GPU'],
    '2차전지': ['2차전지', '배터리', 'EV', '전기차', '양극재', '음극재', '분리막', '전해액'],
    '바이오': ['바이오', '제약', '신약', '임상', 'FDA', '치료제', '백신'],
    '방산': ['방산', '국방', '방위산업', '무기', '미사일', '전투기'],
    '엔터': ['엔터', '엔터테인먼트', 'K-POP', 'K팝', '아이돌', '콘서트'],
    '게임': ['게임', '모바일게임', 'PC게임', '콘솔게임', '메타버스'],
    '수소': ['수소', '수소차', '연료전지', '그린수소'],
    '2차전지': ['리튬', 'LFP', 'NCM', 'NCA'],
}

# 뉴스 소스 URL
NEWS_SOURCES = [
    'https://finance.naver.com/news/news_list.naver?mode=LSS3D&section_id=101&section_id2=258&section_id3=401',  # 네이버 증시 뉴스
]

# 출력 설정
OUTPUT_DIR = 'data'
JSON_FILE = 'morning_candidates.json'
TOP_N = 20  # 상위 N개 선정
