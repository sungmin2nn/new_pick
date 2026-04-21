# Research Log — Phase 2.2~2.5 (외부 자료 발굴)

> 작성: 2026-04-11
> 검색 도구: WebSearch (한국/영어/커뮤니티)
> 평가자: Claude Code session

---

## 1. 발굴 카테고리

| # | 카테고리 | 검색 횟수 | 신뢰성 ★~★★★★★ | 코드화 가치 |
|---|---------|----------|------|------------|
| A | 한국 단타 블로그/유튜브 | 2 | ★★★ (관행/팁) | 부분적 |
| B | 영어 학술 (SSRN/MDPI) | 4 | ★★★★★ (동료심사) | 높음 |
| C | 영어 일반 트레이딩 사이트 | 2 | ★★★ (검증된 룰) | 중간 |
| D | 커뮤니티 (Reddit) | 1 | ★★ (개인) | 낮음 |

---

## 2. 발견된 전략 후보 (출처 + 신뢰성)

### A1. Market Intraday Momentum (MIM) — KOSPI 검증 ⭐⭐⭐⭐⭐
- **출처**: [Market Intraday Momentum with New Measures for Trading Cost: Evidence from KOSPI Index](https://www.mdpi.com/1911-8074/15/11/523) (MDPI Journal of Risk and Financial Management, 2022)
- **신뢰성**: VERIFIED (동료심사 학술지)
- **핵심**: KOSPI 인덱스 30분 데이터 10년+ 분석. 첫 30분 + overnight 수익률 → 마지막 30분 수익률 예측. 거래비용 반영 후도 알파 유의.
- **트레이딩 룰**: `signal = overnight_return + first_30min_return`, `signal > 0 → 마지막 30분 long`
- **한국 시장 적합성**: 매우 높음 (직접 검증)
- **데이터 의존도**: KOSPI 분봉 (6일 한계로 일봉 갭 근사)

### A2. First Half-Hour Predicts Last Half-Hour — Korean Evidence ⭐⭐⭐⭐⭐
- **출처**: [Intraday Momentum: The First Half-Hour Return Predicts the Last Half-Hour Return](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2552752) (Gao, Han, Li, Zhou, SSRN, 2015) + [SNU Open Repository: Intraday Momentum In the Korean stock market](https://s-space.snu.ac.kr/handle/10371/166309) (서울대 학위논문)
- **신뢰성**: VERIFIED (top finance journal + SNU thesis)
- **핵심**: 첫 30분 수익률이 마지막 30분 수익률을 예측. 한국 시장(KODEX 200)에서도 검증 — 특히 2008년 위기 시 두드러짐.
- **트레이딩 룰**: 첫 30분 수익률 > 0 → 마지막 30분 진입
- **변동성 의존**: 변동성 높을 때 R² ↑ (3.3%)

### A3. Overnight Positive / Intraday Negative ETF — Korean ⭐⭐⭐⭐
- **출처**: [Intraday Return Reversals: Empirical Evidence from the Korean ETF Market](https://www.preprints.org/manuscript/201905.0306/v1) (Preprints, 2019)
- **신뢰성**: HIGH (preprint, 검증 가능 저자)
- **핵심**: 한국 KOSPI 200 ETF의 overnight 수익률 양수, intraday 수익률 음수. Short selling 제약과 disagreement hypothesis로 설명.
- **트레이딩 룰**: 종가 매수 → 다음날 시초가 매도 (overnight long)
- **한국 시장 적합성**: 매우 높음 (특화 연구)
- **공매도 제약 활용**: 한국 시장 고유 inefficiency

### A4. End-of-Day Reversal (EODR) — 미국, 적용 검토 ⭐⭐⭐⭐
- **출처**: [End-of-Day Reversal](https://www3.nd.edu/~zda/EOD.pdf) (Baltussen, Da, Soebhag, Notre Dame)
- **신뢰성**: VERIFIED (저자 자료, working paper)
- **핵심**: 인트라데이 패자가 마지막 30분에 reversal. 일평균 0.24% long-short return.
- **메커니즘**: 전문 공매도자의 overnight margin/inventory 부담으로 마지막 30분에 short cover → 패자 가격 상승
- **한국 적용**: 검증 필요 (한국 공매도 제약 강하므로 효과 다를 수 있음)

### B1. Volatility Breakout (Larry Williams) ⭐⭐⭐⭐⭐
- **출처**: 책 "Long-Term Secrets to Short-Term Trading" (1999)
- **신뢰성**: VERIFIED (clas sic)
- **상태**: ✅ 이미 코드화 (Phase 2.1)

### B2. Opening Range Breakout (ORB) ⭐⭐⭐
- **출처**: 다수 (Quantified Strategies, Forex Tester 등)
- **신뢰성**: HIGH (다수 검증)
- **핵심**: 첫 5/15/30분 high/low 돌파 시 진입
- **현황**: 미국 시장에서는 alpha 사라짐 (널리 알려짐). 한국 시장 검증 필요.

### B3. Turtle Trading 20-day High ⭐⭐⭐⭐
- **출처**: Richard Dennis (1980s), 다수 백테스트
- **신뢰성**: VERIFIED (역사적 검증)
- **핵심**: 20일 (또는 55일) 신고가 돌파 시 long, 10일/20일 신저가 시 청산
- **한국 적용**: 단타에는 너무 길지만 (스윙 3~10일) 단축 버전 가능

### C1. 한국 단타 골든타임 9~9:30 거래량 ⭐⭐⭐
- **출처**: [주식투자/단타매매 기법 - 나무위키](https://namu.wiki/w/%EC%A3%BC%EC%8B%9D%ED%88%AC%EC%9E%90/%EB%8B%A8%ED%83%80%EB%A7%A4%EB%A7%A4%20%EA%B8%B0%EB%B2%95) + [9시 땡 단타 자리](https://lilys.ai/ko/notes/243639) + 다수 한국 블로그
- **신뢰성**: MEDIUM (관행적 지식, 학술 검증 부족)
- **핵심**: 9시~9:30 거래량 폭발 종목, 첫 1~2분에 일중 거래량 40~50% 나오는 종목
- **시그널**: 첫 5분 거래량 / 일평균 거래량 > 임계값
- **한국 시장 특화**: ✓ (개장 시간 골든타임은 한국 시장 고유 패턴)

### C2. 매물대 돌파 (Resistance Breakout) ⭐⭐⭐
- **출처**: [전고점 돌파 매매 기법과 원칙](https://brunch.co.kr/@bjbw/9) + [돌파 매매 핵심 전략](https://db20711.com/entry/돌파-매매-핵심-전략)
- **신뢰성**: MEDIUM (관행)
- **핵심**: 최근 N일 고점 돌파 + 거래량 surge
- **유사도**: Turtle Trading 단타 버전

---

## 3. 합법성 검증

| 출처 유형 | 합법성 | 비고 |
|----------|-------|------|
| 학술 논문 (MDPI/SSRN) | ✅ 합법 | 인용 표시로 사용 가능 |
| 책 (Larry Williams) | ✅ 합법 | 아이디어/공식만 인용, 코드 직접 복사 X |
| 한국 블로그 (브런치/나무위키) | ✅ 합법 | 인용 표시 |
| 트레이딩 사이트 | ✅ 합법 | 일반 공개 정보 |
| Reddit | ✅ 합법 | 공개 토론 |

**시세조종 / 허위공시 / 자전거래 관련 전략은 일체 제외.**

---

## 4. 코드화 결정 (Phase 2 1차)

이미 코드화 (Phase 2.1, 5개):
1. ✓ volatility_breakout_lw
2. ✓ sector_rotation
3. ✓ foreign_flow_momentum
4. ✓ news_catalyst_timing
5. ✓ multi_signal_hybrid

**외부 리서치로 추가 코드화 (Phase 2.4~2.5, 5개)**:
6. **kospi_intraday_momentum** — A1 (MIM 학술 검증)
7. **overnight_etf_reversal** — A3 (한국 ETF 학술 검증)
8. **opening_30min_volume_burst** — C1 (한국 단타 골든타임)
9. **eod_reversal_korean** — A4 (Baltussen 논문 한국 적용)
10. **turtle_breakout_short** — B3 (단축 버전, 5/10일 고가)

→ 총 10개 신규 전략 (기존 6 + 신규 10 = 16개 전략)

---

## 5. 출처 신뢰성 분포

| 신뢰성 등급 | 전략 수 |
|-----------|--------|
| VERIFIED (★★★★★) | 6 |
| HIGH (★★★★) | 2 |
| MEDIUM (★★★) | 2 |
| LOW (★★) | 0 |

→ 평균 ★★★★ 이상. 각 전략 메타데이터에 정확한 출처 + 등급 명시.

---

## 6. 한계 + 향후

- **분봉 6일 한계**: MIM, EODR 같은 분봉 의존 전략은 정밀 backtest 제약. 일봉 갭 근사로 진행.
- **한국 시장 검증 필요**: EODR, ORB, Turtle은 미국 데이터로 검증된 것. 한국 backtest로 재검증 필수.
- **앙상블 후보**: multi_signal_hybrid + 학술 기반 전략들의 조합은 Phase 7에서 별도 검증.
