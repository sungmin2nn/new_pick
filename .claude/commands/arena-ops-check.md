# Arena 운영 점검 에이전트

일일 시스템 운영이 정상적으로 수행되었는지 전체 파이프라인을 점검합니다.

## 인자
- `$ARGUMENTS` : 날짜 (YYYYMMDD, 없으면 오늘)

## 점검 항목

### 1. GitHub Actions 실행 상태
```bash
# 최근 워크플로우 실행 결과 확인
gh run list --limit 10 --json name,status,conclusion,createdAt
```

점검 대상 워크플로우:
| 워크플로우 | 예상 시간 | 점검 |
|-----------|----------|------|
| `paper-trading-select.yml` | 08:00 KST | 실행됐나? 성공했나? |
| `paper-trading-check.yml` | 10/12/14/17시 | 몇 번 실행? 실패 있나? |
| `paper-trading.yml` | 16:10 KST | Arena 메인 성공? |
| `bnf-simulation.yml` | 09:30/15:30 | BNF 정상? |

실패한 워크플로우가 있으면:
```bash
gh run view {run_id} --log-failed
```
로 에러 원인을 확인하고 보고합니다.

### 2. 종목 선정 점검
```
data/paper_trading/candidates_{date}_all.json     ← 존재 여부
data/paper_trading/candidates_{date}_{strategy}.json ← 전략별 존재 여부
```

확인 사항:
- 4개 전략 모두 candidates 파일 생성됐나?
- 각 전략 종목 수가 0이 아닌가?
- 선정 시간이 08:00~09:00 사이인가?

### 3. 매매 시뮬레이션 점검
```
data/arena/daily/{date}/arena_report.json    ← Arena 리포트
data/arena/team_*/daily/{date}/trades.json   ← 팀별 매매 기록
data/arena/team_*/daily/{date}/summary.json  ← 팀별 요약
```

확인 사항:
- arena_report.json 존재하고 status가 'success'인가?
- 4팀 모두 매매 기록이 있나?
- 시뮬레이션 결과에 이상값(수익률 ±50% 초과 등)은 없나?

### 4. 집계/정산 점검
```
data/arena/team_*/portfolio.json    ← 포트폴리오 업데이트됐나?
data/arena/leaderboard.json         ← 리더보드에 오늘 날짜 엔트리 있나?
```

확인 사항:
- portfolio.json의 last_updated가 오늘인가?
- 포트폴리오 current_capital이 음수가 아닌가?
- leaderboard daily_history에 오늘 날짜가 있나?
- ELO 레이팅이 정상 범위(500~1500)인가?

### 5. 텔레그램 알림 점검
GitHub Actions 로그에서 텔레그램 전송 결과를 확인합니다:
```bash
# 최근 paper-trading.yml 실행의 텔레그램 스텝 로그
gh run view {run_id} --log | grep -A5 "Telegram"
```

확인 사항:
- "알림 전송 완료" 메시지가 있나?
- "전송 실패" 또는 에러가 있나?
- 헬스체크 알림도 정상 전송됐나?

### 6. 대시보드 데이터 점검
index.html이 읽는 JSON 파일들의 무결성:

```
data/arena/leaderboard.json        ← JSON 파싱 가능?
data/arena/team_*/portfolio.json   ← JSON 파싱 가능?
data/arena/healthcheck/health_{date}.json ← 존재?
```

확인 사항:
- 모든 JSON 파일이 유효한 형식인가?
- 리더보드 데이터와 포트폴리오 데이터가 일치하나?
- 대시보드에서 빈 상태로 보일 항목은 없나?

### 7. 헬스체크 로그 점검
```
data/arena/healthcheck/health_{date}.json
```

- 오늘 헬스체크 몇 번 실행됐나?
- unhealthy 또는 warning 상태가 있었나?
- 이슈가 있었다면 해결됐나?

### 8. Git 커밋 점검
```bash
# 오늘 자동 커밋 확인
git log --oneline --since="today" --author="github-actions"
```

확인 사항:
- 종목 선정 커밋이 있나?
- Arena 결과 커밋이 있나?
- 헬스체크 커밋이 있나?

## 출력 형식

```
⚙️ Arena 운영 점검 보고서 ({date})

1. GitHub Actions
   ✅ paper-trading-select: 성공 (08:02)
   ✅ paper-trading-check: 4/4 성공
   ✅ paper-trading: 성공 (16:15)
   ✅ bnf-simulation: 2/2 성공

2. 종목 선정
   ✅ 4개 전략 모두 선정 완료
   - momentum: 5개 | contrarian: 5개 | dart: 3개 | theme: 5개

3. 매매 시뮬레이션
   ✅ 4팀 모두 정상 실행
   - Team A: 5건 | Team B: 5건 | Team C: 3건 | Team D: 5건

4. 집계/정산
   ✅ 포트폴리오 업데이트 완료
   ✅ 리더보드 갱신 완료

5. 텔레그램
   ✅ 결과 알림 전송 완료
   ✅ 헬스체크 알림 없음 (정상)

6. 대시보드
   ✅ JSON 데이터 무결성 확인
   ✅ 모든 탭 데이터 정상

7. 헬스체크
   ✅ 5회 실행, 모두 healthy

8. Git 커밋
   ✅ 종목 선정 커밋 확인
   ✅ Arena 결과 커밋 확인

종합: ✅ 전체 정상 운영 (8/8 통과)
```

이슈 발견 시:
```
❌ {항목}: {문제 설명}
   원인: {분석}
   조치: {권고 사항}
```

## 결과 저장
```
data/arena/daily/{date}/ops_check.json
```
