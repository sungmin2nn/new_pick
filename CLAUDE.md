# news-trading-bot — 프로젝트 규칙

> 이 파일은 news-trading-bot 작업 시 자동 로드된다. 전역 `~/Desktop/Claude/se/.claude/CLAUDE.md` 의 규칙 위에 추가로 적용.

---

## 1. 데이터 분석 작업 분배 규칙 (환각 차단)

성과 데이터(Arena/BNF/Bollinger)에 대한 모든 분석은 다음 2-Layer 구조를 따른다.

### Layer 1 — 숫자는 결정적 코드로 (LLM 금지)

- 합산·평균·승률·MDD 같은 **계산은 절대 에이전트에 위임하지 않는다**.
- 단일 진실원천(SoT): `paper_trading/audit/verify_facts.py`
- 출력: `data/arena/_verified_facts.json` (매일 paper-trading.yml에서 자동 갱신)

### Layer 2 — 해석/권고만 LLM 에이전트로

- 에이전트는 `_verified_facts.json` **만 읽는다**.
- raw 파일(`data/arena/*/portfolio.json`, `daily/<date>/trades.json` 등) 직접 읽기·인용 금지.
- 인용한 모든 숫자는 `_verified_facts.json` 에서 가져왔음을 명시.

### 인용 규칙

- 단위는 항상 명시: `capital-basis %` vs `stock-basis %` (예: 일별 simulation.total_return 은 5종목 평균이라 자본 영향 아님 — 인용 금지)
- `_verified_facts.json` 에 없는 metric → "(미검증)" 표시 또는 인용 금지
- `warnings` 항목 무시 금지. severity ≥ warn 은 결론에 반드시 반영
- 의심되면 **`python -m paper_trading.audit.verify_facts` 를 먼저 다시 돌려라** (실시간 갱신)

### 위반 사례 (2026-04-30 발생)

- BNF 시스템과 Bollinger 시스템 파일 혼동 → 별개 시스템을 같은 것으로 분석
- 일별 `simulation.total_return` (5종목 평균) 을 자본 수익률로 오인용 → +43% → 환각으로 +169% 인용
- 5일 표본만 보고 "즉시 중단" 단정 → 다음 날 부호 전환 (team_f -3.31% → +5.92%)

이런 사례를 막기 위해 위 2-Layer 가 강제된다.

---

## 2. 전략 분석 표준 절차

사용자가 "전략 분석/지속 중단/성과 보고" 요청 시:

```
1. python -m paper_trading.audit.verify_facts          # 최신 검증값 갱신
2. data/arena/_verified_facts.json 읽기 (단일 입력)
3. (필요 시) 병렬 에이전트로 정성 해석 — 단, 위 JSON만 입력으로 전달
4. 결정 매트릭스 작성 — 각 숫자는 출처 필드명 명시
   예: "(verified_facts.arena.team_a.returns_capital_basis.cumulative_pct)"
```

5일 미만 표본 팀에 대한 "즉시 중단/교체" 권고 금지. 최소 10거래일 이상 또는 자본 MDD 5% 초과 시에만 즉시 결정.

---

## 3. 시뮬레이터 결함 (알려진)

`trades.json` 의 손절가/트레일링가가 정확한 % 단위 (e.g. 정확히 -3.0%) 로 체결됨 → 슬리피지·호가·체결률 모형 부재. 모든 % 수치는 보수적으로 해석한다 (실거래 시 일정 폭 깎임).

해결 경로: KIS 모의투자 연동 (옵션 3, Phase A→G). `obsidian/ai-lab-showcase/broker-api-setup.md` 참조.

---

## 4. 이슈 트래킹

`.claude/context/issues.md` 양식 그대로 사용. `verify_facts.py --update-issues` 로 검증 경고 자동 등재 가능 (코드 단위 dedupe).

---

## 5. 라우팅

전역 CLAUDE.md 의 라우팅 규칙(주식/매매/DART/135점/BNF → news-trading-bot/)을 따른다. 추가로:

- "검증/검산/숫자 맞아?" → verify_facts.py 직접 실행
- "환각/검증 실패" → 위 1번 규칙 위반 여부 점검
