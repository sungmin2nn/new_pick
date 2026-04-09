# Arena 오케스트레이터

최상위 오케스트레이터로서 4팀 경쟁 트레이딩 시스템을 총괄합니다.

## 실행 흐름

### Step 1: 데이터 수집
```bash
cd /Users/kslee/Documents/kslee_ZIP/zip1/news-trading-bot
git pull origin master
```
최신 결과를 가져옵니다.

### Step 2: 운영 점검
`/arena-ops-check`를 먼저 실행하여:
- GitHub Actions 실행 상태
- 종목 선정 / 매매 / 정산 / 텔레그램 / 대시보드 전체 확인
- 이상이 있으면 보고 후 분석 진행 여부 확인

### Step 3: 현재 상태 파악
- `data/arena/leaderboard.json` → ELO 랭킹
- `data/arena/team_*/portfolio.json` → 각 팀 포트폴리오
- `data/arena/daily/최신날짜/arena_report.json` → 최근 결과
- `data/arena/healthcheck/` → 헬스체크 이슈

현재 전체 상황을 요약합니다.

### Step 4: 4팀 병렬 분석 (Agent 4개 동시 실행)
각 팀 에이전트에게 분석을 시킵니다:

**Team A (Alpha Momentum)** → `/arena-team-analyze` team_a
**Team B (Beta Contrarian)** → `/arena-team-analyze` team_b
**Team C (Gamma Disclosure)** → `/arena-team-analyze` team_c
**Team D (Delta Theme)** → `/arena-team-analyze` team_d

4개 에이전트를 **병렬로** 실행하여 각 팀의:
- 최근 매매 성과 분석
- 승/패 패턴 발견
- 파라미터 개선 제안
- 학습 노트 업데이트

### Step 5: 전체 평가 (심판 에이전트)
`/arena-judge` 를 호출하여:
- 4팀 비교 평가
- 전략 간 상관관계 분석
- 시장 환경 대비 성과 평가
- 전체 인사이트 도출
- 개선 권고안 작성

### Step 6: 결과 반영
- 각 팀 journal.md 업데이트
- 파라미터 변경 이력 기록 (승인된 것만)
- git commit & push

### Step 7: 사용자 보고
최종 결과를 보기 좋게 정리하여 보고합니다:
- 4팀 현황 요약
- 각 팀 분석 결과
- 심판 평가
- 다음 액션 아이템

## 주의사항
- 파라미터 변경은 사용자 확인 후 적용
- 전략 코드 수정은 제안만 하고 사용자 승인 필요
- 모든 변경은 param_history.json에 기록
