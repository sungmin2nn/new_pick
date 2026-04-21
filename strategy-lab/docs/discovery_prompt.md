# Strategy Discovery Prompt

> Claude Code 세션이 schedule 스킬 / 수동 실행으로 **신규 전략 후보**를
> 자동 발굴할 때 따르는 가이드.
>
> **anthropic SDK 호출 X** — 모든 검색/추출/코드화는 Claude Code 세션 안에서만.

---

## 트리거 방법

### 자동 (schedule 스킬)
매주 월요일 09:00 KST에 아래 프롬프트로 Claude Code 세션이 실행됨:
```
zip1/strategy-lab/docs/discovery_prompt.md 를 읽고
이번 주 신규 전략 후보 3~5개 발굴해서 pending 큐에 추가.
```

### 수동
```
strategy-lab 신규 발굴 진행해줘. docs/discovery_prompt.md 참조.
```

---

## 발굴 단계

### 1. WebSearch 실행 (병렬 가능)

매 세션마다 **최소 3~5개 검색 쿼리** 실행. 다양성 확보를 위해 카테고리 로테이션:

| 회차 | 대상 영역 | 예시 쿼리 |
|------|----------|----------|
| 1 | 한국 단타 블로그 | `한국 주식 단타 전략 2026 신규` |
| 2 | 한국 유튜브 | `한국 데이트레이딩 전략 YouTube` |
| 3 | 영어 SSRN/arXiv | `intraday momentum Korean stock 2025 SSRN` |
| 4 | Reddit r/algotrading | `reddit algotrading mean reversion 2026` |
| 5 | 한국 학술 | `한국 주식시장 이상현상 단기 수익률 논문` |

**이미 코드화된 전략은 스킵**: 아래 16개 전략과 본질 중복되는 것은 pending 추가 금지.

```
기존 (news-trading-bot):
  alpha_momentum, beta_contrarian, gamma_disclosure,
  delta_theme, echo_frontier, bnf_fall

Strategy Lab (Phase 2):
  volatility_breakout_lw, sector_rotation, foreign_flow_momentum,
  news_catalyst_timing, multi_signal_hybrid, kospi_intraday_momentum,
  overnight_etf_reversal, opening_30min_volume_burst,
  eod_reversal_korean, turtle_breakout_short
```

### 2. 후보 추출

각 검색 결과에서 **명확한 시그널 규칙**이 있는 것만 추출:
- ✓ "첫 30분 거래량 > 5일 평균 × 3 → 매수" — **구체적**
- ✗ "좋은 종목을 사라" — **모호**
- ✗ "심리적 분석으로" — **비정량**

### 3. 신뢰성 평가

각 후보에 대해 `trust_level` 판정:

| 등급 | 조건 |
|------|------|
| **verified** | 동료심사 학술지, 책 (저자 검증 가능) |
| **high** | 증권사/공식 리서치, 검증 가능 저자의 블로그 |
| **medium** | 일반 블로그, 투자 커뮤니티 (다수 인용) |
| **low** | 익명 포스트, 단독 출처 |
| **unverified** | 검증 불가, 초기 관찰만 |

### 4. 기존 전략과 본질 중복 검사

아래 6가지 차원으로 확인:
1. **카테고리**: momentum/contrarian/breakout/event/theme/flow/pattern/statistical/hybrid
2. **핵심 시그널**: 같은 지표 사용? (예: MA5, RSI, DART, 외국인 수급)
3. **시간 차원**: 당일/1일/1주/1개월
4. **데이터 소스**: KRX OHLCV / DART / Naver investor / Naver theme
5. **진입/청산 규칙**
6. **기대 수익 원천**

→ 3개 이상 동일하면 **중복으로 판단, pending 추가 X**.

### 5. pending 큐에 추가

Python 스크립트에서 `DiscoveryQueue.add()` 호출:

```python
from lab.discovery import DiscoveryQueue, DiscoveryCandidate

q = DiscoveryQueue()
cand = DiscoveryCandidate(
    title="제목",
    source_type="blog_ko",
    source_url="https://...",
    source_author="저자",
    trust_level="high",
    category_guess="breakout",
    risk_level_guess="medium",
    hypothesis="한 줄 가설",
    rationale="상세 설명",
    expected_edge="기대 수익 원천",
    differs_from_existing_guess="기존 X와 다른 점",
    data_requirements=["KRX_OHLCV"],
    requires_intraday=False,
    target_holding_days=1,
    novelty_score=7,
    raw_snippet="원본에서 발췌한 핵심 문장",
)
q.add(cand)
```

### 6. 사용자 알림

세션 끝에 요약 출력:
```
[Discovery] 2026-04-11 발굴 결과
  - 검색: 5회
  - 후보 추출: 8개
  - 중복 필터링 후: 4개
  - pending 큐 추가: 4개

pending 큐 검토:
  python3 -m runner.discovery_cli review
```

---

## 품질 기준 (pending에 들어갈 자격)

하나라도 해당하면 **추가 X**:
- 가설이 추상적 / 검증 불가
- 데이터 요구사항이 불명확
- 차이점 설명 공백 (differs_from_existing_guess가 비어있거나 "다름")
- 신뢰성 low + 단일 출처
- 학술 논문인데 초록조차 한국 시장 무관
- 시세조종/허위공시 관련

---

## 다양성 규칙

매 세션 pending 추가 시 **카테고리 다양화** 우선:
- 이미 pending에 돌파(breakout) 3개 있으면 → 돌파는 skip
- 다른 카테고리 우선 수집

```python
from lab.discovery import DiscoveryQueue, DiscoveryStatus
q = DiscoveryQueue()
pending = q.list(DiscoveryStatus.PENDING)
category_counts = {}
for p in pending:
    category_counts[p.category_guess] = category_counts.get(p.category_guess, 0) + 1
# 카운트 많은 카테고리는 그 세션에 skip
```

---

## 예시 (과거 발굴 성공 사례)

Phase 2.2-2.5에서 발굴한 5개:

| 전략 | 출처 | 카테고리 | novelty |
|------|------|---------|---------|
| kospi_intraday_momentum | MDPI 학술지 | momentum | 8 |
| overnight_etf_reversal | 한국 ETF 학술 preprint | statistical | 9 |
| opening_30min_volume_burst | 나무위키 + 학술 | breakout | 7 |
| eod_reversal_korean | Notre Dame 논문 | contrarian | 8 |
| turtle_breakout_short | 클래식 시스템 | breakout | 6 |

패턴: **학술 검증 + 한국 시장 특화 + 명확한 시그널** 세 가지 교집합이 가장 좋음.

---

## 통합 흐름

```
[schedule 스킬 월요일 09:00]
    ↓
[Claude Code 세션 시작]
    ↓
이 문서(discovery_prompt.md) 읽음
    ↓
WebSearch 5회 병렬 실행
    ↓
각 결과에서 후보 추출 + 신뢰성 평가
    ↓
기존 16개와 중복 검사
    ↓
DiscoveryQueue.add() × N
    ↓
요약 출력 + 사용자 알림
    ↓
[세션 종료]

[사용자가 주중 아무 때나]
    ↓
python3 -m runner.discovery_cli review
    ↓
각 pending → approve/reject 결정
    ↓
approved는 수동 또는 자동으로 code 단계로
    ↓
Claude Code 세션에 "approved id XXX 코드화해줘" 요청
    ↓
strategies/{id}.py 자동 생성
    ↓
queue에서 coded 상태로 이동
    ↓
다음 weekly_pipeline에서 백테스트 포함
```
