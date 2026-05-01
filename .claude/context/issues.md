# Issue Tracking

> 모든 문제는 기록하고 재발 방지

---

## [ISSUE-013] Arena 매매 카드 청산 사유 미표시 — 데이터 키 불일치
- **발생일**: 2026-04-30
- **에이전트**: 데이터 검증 (모달 재설계 후속)
- **증상**: Arena 8팀 카드의 매매 상세에서 "사유 · 수량 · 시간" 영역의 사유가 항상 비어 표시 (" · 12주 · ⏱ 1시간 30분")
- **원인**: `js/phase8/arena.js:921` 이 `t.exit_reason` 참조하나, `data/arena/{tid}/daily/{date}/trades.json`의 실제 키는 `exit_type` (332/332건 전수 검증, exit_reason 키 0건)
- **해결**: `exitLabel(t)` 헬퍼 추가 — `EXIT_TYPE_LABEL = { profit: '익절', loss: '손절', close: '종가청산' }`. exit_reason 우선, 없으면 exit_type 매핑. 커밋 c500659
- **예방**: 화면 코드에서 데이터 키 참조 시 schema와 교차 검증 필요. 본 이슈는 시간 데이터 검증 중 부수 발견됨 (332건 시간 데이터 자체는 100% 정상: HH:MM, 09:00~15:30, 역전 0건)
- **상태**: resolved

---

## [ISSUE-001] 리스크 지표 계산 단위 불일치
- **발생일**: 2026-04-05
- **에이전트**: dev-agent-analytics
- **증상**: Sharpe, Sortino, Alpha 비율이 비정상적으로 큰 값 출력
- **원인**: 수익률이 % 단위(예: 2.5)인데 무위험수익률은 소수점(0.00014)으로 계산
- **해결**: 모든 수익률을 100으로 나눠 소수점 단위로 통일
- **예방**: 금융 계산 시 단위 변환 체크리스트 적용
- **상태**: resolved

---

## [ISSUE-002] pykrx 데이터 미반환
- **발생일**: 2026-04-05
- **에이전트**: domain-data-collector-agent
- **증상**: pykrx로 KOSPI 지수 데이터 조회 시 빈 값 반환
- **원인**: pykrx 라이브러리 일시적 오류 또는 API 제한
- **해결**: 네이버 금융 스크래핑으로 대체 (fetch_kospi_index.py)
- **예방**: 데이터 수집 시 폴백 소스 항상 준비
- **상태**: resolved

---

## [ISSUE-003] GitHub Pages 캐시 미갱신
- **발생일**: 2026-04-05
- **에이전트**: utility-cicd-agent
- **증상**: 코드 푸시 후에도 대시보드에 변경사항 미반영
- **원인**: 브라우저 캐시 및 CSS/JS 버전 파라미터 미갱신
- **해결**: ?v=12로 버전 번호 업데이트
- **예방**: 배포 시 자동 버전 번호 증가 스크립트 적용
- **상태**: resolved

---

## [ISSUE-004] paper-trading-select 만성 0종목 선정 (CRITICAL)
- **발생일**: 2026-04-10 (재발 - 04-08부터 지속)
- **에이전트**: Arena 종목 선정 (paper-trading-select.yml)
- **증상**: 4개 전략 중 momentum, largecap_contrarian, dart_disclosure가 매일 0종목 선정. theme_policy만 정상 작동
- **원인**: ① cron이 08:00 KST (장 시작 09:00 이전) → naver finance 페이지의 등락률이 pre-market 시점에 0 또는 stale. ② DART_API_KEY env 누락. ③ paper-trading.yml(16:10)이 이미 동일 작업 수행 중 → 중복 + 덮어쓰기 (16:10이 만든 후보를 다음날 08:00이 0종목으로 박살)
- **해결**: cron을 16:30 KST로 이동 (장 마감 후 30분, naver 종가 안정화 시점). DART_API_KEY env 추가. checker.py에 candidates_{date}_all.json 폴백 추가. **추가 권장**: paper-trading-select 자체 폐지 (paper-trading.yml에 통합)
- **예방**: 워크플로우 추가 시 데이터 소스 가용 시점 검증, 중복 작업 발견 시 즉시 통합
- **상태**: resolved (2026-04-10 commit cadbe6f, 부분 — 폐지는 검증 후 진행)

---

## [ISSUE-005] team_c/team_d portfolio.json 미생성
- **발생일**: 2026-04-10
- **에이전트**: Arena (paper-trading.yml)
- **증상**: data/arena/team_c/portfolio.json, team_d/portfolio.json 파일 자체가 부재. leaderboard에는 두 팀이 trades=0으로 기록
- **원인**: team_c/d가 ISSUE-004로 인해 0종목 → 매매 시뮬레이션 불가 → portfolio 초기화 코드가 실행 안 됨
- **해결**: 4팀 모두 1,000만원으로 동시 리셋 (공정 동시 시작). leaderboard ELO 1000 초기화, daily_history 비움
- **예방**: 신규 팀 추가 시 portfolio.json 초기 생성을 무조건 1회 보장하는 init 스크립트
- **상태**: resolved (2026-04-10 commit cadbe6f)

---

## [ISSUE-006] paper-trading-check status_*.json 미생성
- **발생일**: 2026-04-10
- **에이전트**: paper_trading.checker
- **증상**: 헬스체크가 status_{date}.json 파일 없음으로 fail 표시. 실제로는 checker가 파일을 만들지 않음
- **원인**: checker._load_candidates가 레거시 candidates_{date}.json만 찾고 다중전략 구조의 candidates_{date}_all.json은 무시 → 후보 0개 반환 → status 파일 안 씀
- **해결**: checker._load_candidates에 다중전략 통합 파일 폴백 추가, 모든 전략의 후보를 dedup하여 합침
- **예방**: 데이터 구조 변경(레거시 → 다중전략) 시 모든 consumer를 함께 마이그레이션
- **상태**: resolved (2026-04-10 commit cadbe6f)

---

## [ISSUE-012] BNF 시뮬 _business_days_between datetime/date 비교 TypeError로 5일간 시뮬 정지
- **발생일**: 2026-04-23 (잠복 → 노출), 2026-04-27 (수정)
- **에이전트**: scripts/run_bnf_simulation.py `_business_days_between`
- **증상**: 04-23 ~ 04-27 BNF Trading Simulation 워크플로우 6번 연속 failure (실행 35초 만에 즉사). positions.json `updated_at: 2026-04-22 17:17:46` 이후 5일간 정지. 가격 갱신/손절·익절/신규 진입/쿨다운 등록 전부 멈춤. P0 가드(ISSUE-011)도 실행 자체가 안 되어 검증 불가 상태
- **원인**:
  ```
  TypeError: can't compare datetime.datetime to datetime.date  (line 50)
  ```
  `_business_days_between(date_str, target_date)` 안에서 `isinstance(target_date, _date)` 체크로 `tgt`를 결정. 그러나 `datetime.datetime`이 `datetime.date`의 서브클래스이므로 datetime 입력에도 isinstance가 True 반환 → tgt에 datetime 그대로 들어감 → src(date)와 비교에서 충돌. 이건 P0 패치 이전부터 잠복하던 버그였으나, 04-22까지는 candidates.json이 매일 fresh해서 stale 검증 분기를 한 번도 안 탔음. 04-23부터 cand_date가 1일 묵으며 분기 활성화 → 노출
- **해결**: 2026-04-27 수정 (`commit ddae5b7`):
  ```python
  if isinstance(target_date, _dt):       # datetime을 먼저 좁힘
      tgt = target_date.date()
  elif isinstance(target_date, _date):
      tgt = target_date
  ```
- **검증 (수동 트리거 결과)**: 핫픽스 후 즉시 시뮬 정상 가동.
  - 5일간 묵었던 4건 청산 일괄 처리: 로킷 손절 -4.44%, 삼천당 손절 -6.41% (이전 -19.05% 대비 1/3로 축소 — 추세 회복 + 슬리피지 가드 효과), 앱클론 익절 +13.76%, 오름 보유 유지 +7.16%
  - **쿨다운 자동 등록 확증**: `cooldown_until: {'376900': '2026-05-04', '000250': '2026-05-04'}` (손절 후 +5영업일)
  - 신규 진입 2종목이 비-바이오 (성호전자, SK오션플랜트) → 섹터 캡 작동 추정
  - 누적 수익률 +10.40% → +11.25%
- **예방**:
  - datetime/date 헬퍼 추가 시 항상 isinstance(_dt) 분기를 먼저 둘 것 (date의 서브클래스 함정)
  - 새 분기 추가 시 그 분기를 한 번이라도 호출하는 단위/회귀 테스트 작성 (이번 stale 분기는 운영 환경에서 자연 발현 후 처음 깨짐)
  - GitHub Actions failure 알림을 24h 내에 수신할 수 있는 채널 설정 (5일간 모름 = 운영 위험)
- **상태**: resolved (2026-04-27, 시뮬 부활 + 가드 4종 동작 확증)

---

## [ISSUE-011] BNF 04-22 전원 손절 (-25.3만원) — 섹터 집중 + 재진입 덫 + 슬리피지
- **발생일**: 2026-04-22 (증상), 2026-04-23 (원인 규명 및 수정)
- **에이전트**: paper_trading.bnf (낙폭과대 자동매매)
- **증상**: 하루 4건 청산 전부 손절 (-12.46% 평균). 삼천당제약 -19% 최대 손실. 누적 수익률 +20.59% → +10.40%로 3일간 -305,600원 드로다운. MDD -8.45% 전부 이 구간 집중
- **원인 (5축 병렬 분석으로 규명)**:
  1. **섹터 매크로** — 시장 상승장(코스닥 종합 +5.09%) 중 **바이오/헬스케어 독자 약세** (KOSDAQ 제약 -1.25%, 헬스케어 +0.72% 정체). BNF 낙폭 정렬이 자연히 바이오를 상위로 몰아 포트 편중(바이오 승률 37.5% vs 기타 63.6%)
  2. **종목 고유 이벤트** — 삼천당제약 2026-04-20 장마감 후 코스닥 불성실공시법인 지정(벌점 5점) → 04-22 시가 -16% 갭하락, 장중 -24%까지 흘러 -19% 마감. 관리종목 리스크 부각
  3. **코드 3대 결함 (확증)**:
     - `position.py:137-146` 재진입 쿨다운 부재 → 삼천당 5연패, 로킷 3회 연속 진입
     - `run_bnf_selection.py:110-113` 시총/거래대금만 필터, 섹터 캡·관리종목 제외 없음
     - `position.py:258-259` 손절 체결가를 종가 그대로 기록 → 진입가 -3% 룰이 실체는 -7~-19%로 엇나감
  4. **진입 패턴** — 실패 3종목 모두 **거래량 동반 반등 없는 계단식 하락 중 진입**. 승리 종목(큐리옥스)은 진입 직전 +21.8% V자 반등 + 거래량 동반이 있었음
- **해결 (P0 4종)**:
  - `paper_trading/bnf/position.py`: `COOLDOWN_BUSINESS_DAYS=5` 손절 후 동일 종목 재진입 금지. `MAX_STOP_LOSS_SLIPPAGE_PCT=-7.0` 손절 체결가 슬리피지 상한 (진입가 기준 -7% 아래는 -7%로 클램프)
  - `scripts/run_bnf_selection.py`: 관리종목/투자경고 제외 (base_info 엔드포인트 `SECT_TP_NM` 기반, 빈 응답 시 5일 폴백). 이름 휴리스틱 섹터 분류기 13개 카테고리 + 바이오 13개 키워드
  - `scripts/run_bnf_simulation.py`: `SECTOR_CAP=2` 동일 섹터 보유 상한(기존 보유 + 오늘 진입 합산), "기타" 섹터 예외. `GAP_DOWN_SKIP_PCT=-5.0` 시가 갭하락 진입 스킵
- **회고 시뮬 검증 (27건 trade_history)**:
  - 원본 손실 합계 -106.46% → P0 적용 -24.97% (**76.5% 감소**)
  - 쿨다운 단독으로 9/14 손실 거래 차단 (삼천당 5연패/로킷 3연속 대부분)
  - 슬리피지 가드 7건 완화 (+27%p)
  - 섹터 캡은 쿨다운과 중첩되어 단독 기여는 낮음 (미래 리스크 방지용)
- **예방**:
  - 단일 낙폭 기준의 추세/조정 구분 불가 → 향후 "거래량 동반 반등" 확인 필터 고려
  - 불성실공시법인 지정은 관리종목과 별개 플래그 → DART 공시 스캔 별도 구현 필요 (P1)
  - 섹터 분류 휴리스틱은 "기타" 47% 차지 — KRX 업종 매핑 도입 시 개선 (P1)
- **상태**: resolved (2026-04-23, 회고 시뮬 76% 손실 감소 확증)

---

## [ISSUE-010] team_i (Hybrid) 가 team_a (Alpha Momentum) 결과를 3일 연속 100% 복제
- **발생일**: 관측 확정 2026-04-23 (증상 확인: 20260420, 20260421, 20260422 모두 5종목 완전 일치)
- **에이전트**: paper_trading.strategies.hybrid_alpha_delta.HybridAlphaDeltaStrategy
- **증상**: team_i의 일일 수익률/승률/거래수/선정 종목 5개가 team_a와 완전히 동일. team_i의 리더보드 통계(ELO 1093, best_day 18.13%)가 team_a의 복제본 — 독립 전략으로서의 정보량 0
- **원인**:
  1. **점수 스케일 불균형** — momentum(Alpha) 상위 점수 65~82점 vs theme_policy(Delta) 상위 점수 53~58점. Alpha가 구조적으로 40% 높은 스케일. 가중평균(0.65×Alpha + 0.35×Delta)에서 Delta-only 후보는 수학적으로 불가능할 정도로 불리 (Delta 최고 58.6 × 0.35 = 20.5 vs Alpha 5위 65.8 × 0.65 = 42.8)
  2. **겹침 0** — Alpha top 10과 Delta top 10이 관측 기간 내내 한 종목도 공유하지 않음 (momentum은 종목 단위 모멘텀, theme_policy는 섹터/테마 단위 선별 — 선정 기준이 근본적으로 달라 자연스럽게 교집합 희박). OVERLAP_BONUS(+10)는 늘 발동 안 함
  3. 결과적으로 "가중평균 상위 top_n" 선정이 Alpha-only 상위 N개를 그대로 따라감
- **해결**: 2026-04-23 `hybrid_alpha_delta.py` 수정:
  - Alpha/Delta 점수를 각각 min-max 정규화하여 0~100 스케일로 통일 (스케일 불균형 제거)
  - 최종 편성을 **Alpha 슬롯 3 + Delta 슬롯 2**로 강제 배분. 겹치는 후보는 Alpha 슬롯에 배치, Delta 슬롯은 delta-only 상위에서 충원, 한쪽 부족 시 반대쪽으로 백필
  - OVERLAP_BONUS 로직 유지 (겹치는 날이 오면 가산)
- **예방**: 서브 전략들의 점수 스케일이 이질적인 경우 가중평균만으로는 다양성 보장 불가. "슬롯 기반 편성" 또는 "정규화 + 최소 할당" 패턴이 기본. 향후 추가되는 Hybrid 계열 전략에 이 원칙 적용
- **후속 필요**: team_i의 누적 통계(portfolio/leaderboard)는 복제 기간 데이터 기반 — 공정 비교를 위해 리셋 여부 사용자 결정 대기
- **상태**: resolved (2026-04-23, 전략 로직 수정 완료. 앞으로 결과는 team_a와 독립)

---

## [ISSUE-009] team_e/f/g/h 장기간 0건 선정 — KRX 당일 데이터 누락 + fetch_date 폴백 미작동
- **발생일**: 관측 확정 2026-04-23 (증상 지속 기간: 최소 수 거래일 이상)
- **에이전트**: paper_trading.multi_strategy_runner._resolve_fetch_date, lab 전략 4종
- **증상**: frontier_gap (team_e), volatility_breakout_lw (team_f), turtle_breakout_short (team_g), sector_rotation (team_h) 4개 전략이 지속적으로 0건 선정. arena_report에 `no_candidates`로 기록. team_e/f/g/h 포트폴리오 last_updated가 2026-04-10 리셋 시점에서 정체
- **원인**:
  1. **1차 원인 (외부)** — KRX 공식 OpenAPI(`data-dbg.krx.co.kr`)가 2026-04-22 데이터를 다음 날까지도 업로드 안 함 (`get_stock_ohlcv(20260422)` → 0 rows). 04-10 ~ 04-21은 모두 949 rows 정상
  2. **2차 원인 (내부)** — `_resolve_fetch_date`가 `is_market_day`(한국 캘린더 기반 평일/공휴일)만 확인. 평일이면 KRX 실데이터 유무 체크 없이 그대로 리턴 → 04-22 fetch 시도 → 빈 결과 → 전략 0건
  3. momentum/theme/dart는 네이버 크롤링 및 DART API를 우선 경로로 쓰므로 KRX 공백에도 정상 동작. 영향은 "KRX OHLCV/지수 필수" 4전략에 국한
  4. (배경) pykrx 라이브러리는 2025-12-27 KRX 회원제 전환 이후 전면 무력화 상태 — 단, 이 프로젝트는 이미 `KRXClient`로 공식 OpenAPI 이전 완료되어 있었음. pykrx 오류 로그는 2차 폴백 경로에서 발생한 노이즈였음
- **해결**: `_resolve_fetch_date`에 KRX 실데이터 존재 확인 추가 (`KRXClient.get_stock_ohlcv` 결과 비어있지 않은 최근 거래일까지 거슬러 올라감). KRX 호출 실패/키 없음 시에는 기존 평일 체크 동작 유지. 진단 스크립트 `_diagnose_team_efgh.py`로 재현 및 검증 완료 — 4전략 전부 5건 선정 복구
- **예방**:
  - 외부 API 결과가 비어있어도 "평일이니 OK" 처리하던 로직 전반 재점검 필요 (DART/네이버도 유사 가능성)
  - arena 헬스체크에 "전 거래일 대비 선정 수 급락" 지표 추가 고려. 현재는 "팀 종목 선정 완료 또는 대기 중"이라는 느슨한 pass 기준이라 이 증상이 10일 넘게 조용히 지나감
  - pykrx 직접 import가 남아있는 코드(`paper_trading/strategies/frontier_gap.py` 등)는 장기적으로 폴백 경로에서 제거 또는 `KRXClient` 경유로 일원화
- **상태**: resolved (2026-04-23, paper_trading/multi_strategy_runner.py 패치)

---

## [ISSUE-008] team_b (largecap_contrarian) 상승장 구조적 역풍으로 비활성화
- **발생일**: 2026-04-17 (증상 확정) / 2026-04-19 (비활성화 조치)
- **에이전트**: paper_trading.strategies.largecap_contrarian (team_b)
- **증상**: 4/10 ~ 4/17 8거래일 연속 손실. 31거래 중 26패, 승률 8.6%, 누적 -15.93%, ELO 1000→780. 4/18 이후 daily 산출물 생성 중단 (config에서 제외되어 실행 자체 안 됨)
- **원인**: 전략 철학(RSI≤35 + 시장모드 필터 기반 역발상)과 현재 시장국면(상승장)의 구조적 미스매치. 상승장에서는 RSI 저점 진입 종목이 약세 지속되는 경향 — 파라미터 튜닝 수준으로는 해결 불가
- **해결**: 2026-04-19 `strategy_config.json`에서 `largecap_contrarian.enabled=false`. leaderboard.json에 `archived_teams` 섹션 추가하여 team_b 이동 (2026-04-22 정리). 결정 근거는 `.claude/context/decisions.md` 참조
- **예방**: ① 전략 도입 전 현 시장국면 적합성 점검 (상승장/하락장/횡보장별 백테스트). ② 8팀 체제로 전략 다양성(모멘텀/공시/테마/갭/변동성/터틀/섹터/하이브리드) 이미 확보됨. ③ 복귀 조건 명시 — KOSPI 20일선 하향 이탈 + RSI 30 저점 형성 시 재검토
- **상태**: resolved (2026-04-22, archive 처리 완료)

---

## [ISSUE-007] 모닝스캔 1세대 시스템이 백그라운드에서 운영 중 (사용자 미인지)
- **발생일**: 2026-04-10
- **에이전트**: morning-scan.yml + afternoon-collect.yml
- **증상**: 사용자는 Arena 4팀 + BNF만 운영 중이라고 인지. 실제로는 1세대 모닝스캔이 매일 5+회 실행되어 morning_candidates.json/history.json 갱신, intraday 데이터 수집, git 자동 커밋. github.com 자동 커밋 로그가 도배되고 있었음. auto_reporter.py가 만드는 dashboard_report.html(stale) 외 2개 산출물(project_report.html, knowledge_base.json)은 처음부터 생성된 적 없음
- **원인**: 시스템 진화 과정에서 1세대 → 2세대(BNF) → 3세대(Arena) 전환했으나 1세대 워크플로우 비활성화 누락. 기존 코드 동작 확인 안 한 채 새 시스템만 추가
- **해결**: 검증 후 레거시 14개 Python + 2개 워크플로우 + auto_reporter 산출물 일괄 삭제 (Phase 1 진행 예정, Agent 검증 중)
- **예방**: 시스템 세대 전환 시 항상 이전 세대 워크플로우 schedule 비활성화 체크리스트 적용. 정기적으로 `gh run list` 검토하여 미인지 워크플로우 식별
- **상태**: open (검증 후 삭제 진행)

---

## 템플릿

```markdown
## [ISSUE-XXX] 문제 제목
- **발생일**: YYYY-MM-DD
- **에이전트**: 발생한 에이전트명
- **증상**: 무엇이 잘못되었는지
- **원인**: 근본 원인 분석
- **해결**: 어떻게 해결했는지
- **예방**: 재발 방지 조치
- **상태**: open | resolved
```

## [ISSUE-014] Arena portfolio.json vs daily/ 합산 capital 불일치
- **발생일**: 2026-04-30
- **에이전트**: verify_facts.py (자동 등재)
- **warning code**: `W_CAPITAL_MISMATCH`
- **scope**: team_a, team_b, team_d
- **증상**: portfolio.current_capital 과 (초기자본 + sum(daily/*/trades.json/total_return_amount)) 차이 0.1% 초과.
- **원인**: W_TRADE_COUNT_MISMATCH 와 동일 — 동일 날짜 재실행으로 portfolio 만 누적.
- **해결**: W_TRADE_COUNT_MISMATCH 해결과 함께 처리.
- **예방**: verify_facts.py 자동 감지.
- **상태**: open

---

## [ISSUE-015] leaderboard.daily_history 에 동일 일자 중복
- **발생일**: 2026-04-30
- **에이전트**: verify_facts.py (자동 등재)
- **warning code**: `W_DUPLICATE_RUNS`
- **scope**: leaderboard
- **증상**: leaderboard.json 의 daily_history 배열에서 같은 date 가 2회 이상.
- **원인**: arena_manager.run_daily 가 동일 일자에 여러 번 호출됨 (수동 재실행 또는 cron 중복).
- **해결**: run_daily idempotency 추가 + 1회성 daily_history dedupe 스크립트.
- **예방**: verify_facts.py 가 매일 자동 감지.
- **상태**: resolved (2026-04-30) — arena_manager.py 진입점 가드 추가, scripts/dedupe_arena_data.py 로 20260410 중복 2건 제거. verify_facts.py 재실행 시 W_DUPLICATE_RUNS 미발행 확인

---

## [ISSUE-016] 시뮬레이터 슬리피지/체결률 모형 부재
- **발생일**: 2026-04-30
- **에이전트**: verify_facts.py (자동 등재)
- **warning code**: `W_SIM_NO_SLIPPAGE`
- **scope**: global
- **증상**: trades.json 의 손절가가 정확히 -3.0%, 트레일링/익절가도 정확한 % 로 체결됨.
- **원인**: paper_trading/simulator.py 가 호가/체결률 모형 없이 이상적 가격 사용.
- **해결**: 단기: 슬리피지 ±0.2% 가정. 중기: KIS 모의투자(`broker/kis/`) 도입.
- **예방**: verify_facts.py 가 매번 W_SIM_NO_SLIPPAGE 발행 (해결 전까지).
- **상태**: resolved (2026-05-01) — TradingSimulator.SLIPPAGE_PCT=0.2 도입. 진입가 +0.2%, 룰 기반 청산가(trailing/profit/loss 폴백) -0.2% 적용 (왕복 -0.4%). 종가청산 및 분봉 first_hit 가격은 시장가 그대로. verify_facts 는 SLIPPAGE_PCT=0 일 때만 W_SIM_NO_SLIPPAGE 발행하도록 동적 검사로 변경. 중기 KIS 모의투자 연동은 별도 트랙

---

## [ISSUE-017] 자본 MDD 가 비현실적으로 낮음 — 시뮬 슬리피지 미반영 의심
- **발생일**: 2026-04-30
- **에이전트**: verify_facts.py (자동 등재)
- **warning code**: `W_SUSPICIOUS_LOW_MDD`
- **scope**: team_a, team_e
- **증상**: 운영 5일 이상인 팀의 자본 MDD < 0.1% (예: team_a 0.04%, team_e 0%).
- **원인**: trades.json 검사 결과 손절가/트레일링가가 정확한 % 단위로 체결됨. 시뮬에 슬리피지·호가·체결률 모형 없음.
- **해결**: (권고 1) simulator.py 에 진입가/청산가에 ±0.2% 슬리피지 가정 추가. (권고 2) KIS 모의투자 연동(옵션 3, Phase A→G) 으로 실거래 검증.
- **예방**: verify_facts.py 자동 감지. 모든 % 수치 보수적 해석 강제 (CLAUDE.md).
- **상태**: code_applied (2026-05-01) — 권고 1 코드 적용 (ISSUE-016 fix 와 동일 커밋, SLIPPAGE_PCT=0.2). 기존 trades.json 은 슬리피지 없는 상태로 보존 → team_a/team_e 의 MDD < 0.1% 경고는 현 데이터 기반이라 즉시 사라지지 않음. 향후 거래일이 누적되면 자연 해소 예상. 권고 2 (KIS 모의투자) 는 별도 트랙

---

## [ISSUE-018] Arena portfolio.json vs daily/ trades.json 거래수 불일치
- **발생일**: 2026-04-30
- **에이전트**: verify_facts.py (자동 등재)
- **warning code**: `W_TRADE_COUNT_MISMATCH`
- **scope**: team_a, team_b, team_c, team_d
- **증상**: portfolio.total_trades 가 daily/<date>/trades.json 합산보다 큼 (team_a/b/c/d 에서 5~10건씩 차이).
- **원인**: arena_manager.run_daily() 동일 날짜 재실행 시 portfolio.update_after_day 는 total_trades 를 누적(+=)하지만 save_daily_record 는 trades.json 을 덮어씀. idempotency 부재. leaderboard.daily_history 에서 동일 일자 중복 등장으로 확인됨.
- **해결**: (권고 1) run_daily 시작 시 daily/<date>/arena_report.json 존재 확인 후 skip + force 옵션. (권고 2) _load_portfolio 에서 daily 기반 자동 보정.
- **예방**: verify_facts.py 가 매일 W_TRADE_COUNT_MISMATCH + W_DUPLICATE_RUNS 로 자동 감지. issues.md 자동 등재 (dedupe).
- **상태**: resolved (2026-04-30) — 권고 1 적용 (arena_manager.run_daily 진입점 idempotency 가드). scripts/dedupe_arena_data.py 로 portfolio 9개 + leaderboard ELO/rank/MDD 재구성. team_a 80건/team_b 26건/team_c 41건/team_d 75건으로 trades.json 합산과 일치. ELO 재조정: team_a 1222→1188 외 7팀

---
