# Issue Tracking

> 모든 문제는 기록하고 재발 방지

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
