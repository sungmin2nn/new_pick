# 🔮 장전 종목 선정 시스템

시초가 매매를 위한 자동 종목 선정 시스템입니다. 매일 08:30에 자동으로 실행되어 공시, 뉴스, 테마를 기반으로 주목할 종목을 선정합니다.

## 📊 주요 기능

- **자동 실행**: 매일 08:30 GitHub Actions를 통해 자동 실행
- **공시 기반 선정**: DART API를 통한 전일 18:00 ~ 당일 08:30 공시 수집
- **뉴스 분석**: 네이버 금융 뉴스 실시간 수집 및 언급 횟수 분석
- **테마 매칭**: AI, 반도체, 2차전지 등 주요 테마 자동 분류
- **대시보드**: GitHub Pages를 통한 실시간 대시보드 제공

## 🎯 점수 시스템 (총 100점)

| 항목 | 배점 | 설명 |
|------|------|------|
| 공시 | 40점 | DART 공시 개수 및 중요도 (실적, 계약, 투자 등) |
| 뉴스 | 30점 | 뉴스 언급 횟수 (5회 이상 30점) |
| 테마 | 20점 | 주요 테마 매칭 개수 (AI, 반도체 등) |
| 투자자 | 10점 | 외국인/기관 매매 정보 (추후 구현) |

## 🔧 설정 방법

### 1. DART API 키 설정 (필수)

DART API 키가 없으면 공시 점수가 0점 처리됩니다.

1. [DART 오픈API](https://opendart.fss.or.kr/) 접속
2. 회원가입 후 API 키 발급
3. GitHub Repository Settings > Secrets and variables > Actions
4. New repository secret 클릭
5. Name: `DART_API_KEY`, Value: 발급받은 API 키 입력

### 2. GitHub Pages 활성화

1. Repository Settings > Pages
2. Source: Deploy from a branch
3. Branch: master, Folder: / (root)
4. Save

### 3. GitHub Actions 권한 설정

1. Repository Settings > Actions > General
2. Workflow permissions: Read and write permissions 선택
3. Save

## 🚀 실행 방법

### 자동 실행 (GitHub Actions)

매일 08:30 KST에 자동으로 실행됩니다.

### 수동 실행 (GitHub Actions)

1. Actions 탭 이동
2. Morning Stock Scan 워크플로우 선택
3. Run workflow 클릭

### 로컬 실행

```bash
# 환경변수 설정
export DART_API_KEY='your_api_key_here'

# 의존성 설치
pip install -r requirements.txt

# 실행
python3 stock_screener.py
```

## 📁 파일 구조

```
.
├── stock_screener.py          # 메인 스크리너 로직
├── market_data.py             # 시장 데이터 수집
├── news_collector.py          # 뉴스 수집
├── disclosure_collector.py    # DART 공시 수집
├── database.py                # 데이터베이스 관리
├── config.py                  # 설정 파일
├── index.html                 # 대시보드
├── requirements.txt           # 의존성
└── .github/workflows/
    └── morning-scan.yml       # 자동 실행 워크플로우
```

## 📈 필터링 기준

| 항목 | 기준 |
|------|------|
| 거래대금 | 300억원 이상 |
| 시가총액 | 500억원 이상 |
| 주가 상한 | 10만원 이하 |
| 등락률 | 제한 없음 (전일 하락 종목도 포함) |

## 🔍 테마 키워드

- AI: 인공지능, ChatGPT, 생성형AI, LLM 등
- 반도체: HBM, 파운드리, 메모리, GPU 등
- 2차전지: 배터리, EV, 양극재, 음극재 등
- 바이오: 신약, 임상, FDA, 치료제 등
- 방산: 국방, 방위산업, 무기, 미사일 등
- 기타: 엔터, 게임, 수소 등

## 📊 대시보드

GitHub Pages를 통해 자동으로 배포됩니다.

URL: `https://[username].github.io/[repository-name]/`

기능:
- 실시간 종목 정보
- 점수별 필터링
- 컬럼별 정렬
- 통계 요약

## ⚠️ 주의사항

1. **투자 책임**: 이 시스템은 참고용이며, 투자 책임은 본인에게 있습니다
2. **데이터 정확성**: 크롤링 오류나 API 장애로 데이터가 부정확할 수 있습니다
3. **시장 변동성**: 시초가 매매는 높은 변동성이 있으니 주의하세요
4. **API 제한**: DART API는 일일 요청 제한이 있을 수 있습니다

## 🐛 문제 해결

### DART API 오류

```
⚠️  DART API 키가 설정되지 않았습니다
```

→ GitHub Secrets에 `DART_API_KEY` 설정 확인

### 뉴스 수집 0개

```
✓ 총 0개 뉴스 수집 완료
```

→ 네이버 금융 사이트 구조 변경 또는 네트워크 오류. 시간이 지나면 해결될 수 있습니다.

### 대시보드 로딩 중

→ GitHub Pages가 활성화되어 있는지 확인하고, `morning_candidates.json` 파일이 생성되었는지 확인

## 📝 라이선스

MIT License

## 🤝 기여

이슈 및 풀 리퀘스트 환영합니다!
