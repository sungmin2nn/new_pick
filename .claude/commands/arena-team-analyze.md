# Arena 팀 분석 에이전트

특정 팀의 성과를 심층 분석하고 개선안을 제시합니다.

## 인자
- `$ARGUMENTS` : team_id (team_a | team_b | team_c | team_d)

## 분석 대상 데이터
```
data/arena/{team_id}/portfolio.json      ← 누적 포트폴리오
data/arena/{team_id}/journal.md          ← 학습 노트
data/arena/{team_id}/param_history.json  ← 파라미터 변경 이력
data/arena/{team_id}/daily/*/summary.json ← 일별 요약
data/arena/{team_id}/daily/*/trades.json  ← 매매 상세
data/arena/{team_id}/daily/*/selection.json ← 종목 선정
```

## 분석 항목

### 1. 성과 분석
- 최근 5~10일 수익률 트렌드
- 승률 변화 추이
- 평균 수익/손실 비율 (Profit Factor)
- 익절/손절/종가청산 비율
- 최대 연승/연패 분석

### 2. 종목 선정 분석
- 선정된 종목의 공통 특성
- 승리 종목 vs 패배 종목 차이점
- 놓친 기회 (선정 안 했지만 올랐을 종목)

### 3. 매매 타이밍 분석
- 익절 도달 시간 분포 (빠른 익절 vs 늦은 익절)
- 손절 도달 시간 분포
- 종가 청산 종목의 장중 최대 수익률

### 4. 파라미터 개선 제안
현재 전략 파라미터를 읽고:
```python
# 전략 파일에서 현재 파라미터 확인
paper_trading/strategies/{strategy_file}.py
```

개선 가능한 파라미터:
- 점수 가중치 (scoring weights)
- 필터 조건 (MIN_PRICE, MIN_TRADING_VALUE 등)
- 선정 종목 수
- 손익절 기준 (전략별로 다르게 가능)

**반드시 근거를 제시**: "최근 10일 데이터에서 X 조건 종목의 승률이 Y%이므로 Z를 권장"

### 5. 학습 노트 업데이트
분석 결과를 `data/arena/{team_id}/journal.md`에 추가:
```markdown
## {날짜} - 분석 에이전트 리포트
- 성과 요약: ...
- 발견된 패턴: ...
- 개선 제안: ...
- 적용 여부: (사용자 승인 대기)
```

## 출력 형식
```
[Team {team_id}] 분석 완료

📊 성과 요약
- 최근 N일 수익률: +X.XX%
- 승률: XX.X% (승N/패N)
- Profit Factor: X.XX

🔍 발견된 패턴
- (구체적 패턴 기술)

💡 개선 제안
1. (파라미터 변경 제안 + 근거)
2. (전략 수정 제안 + 근거)

📝 journal 업데이트: 완료
```
