# 팀 작업 프로세스 가이드

## 문제 발생 배경

2026-03-28, paper_trading 모듈 개발 시 기존 `intraday_collector.py`의 분봉 수집 기능을 파악하지 않고 새로운 코드를 작성하여 중복 및 기능 퇴보 발생.

**원인**: 기존 코드베이스 분석 부족

---

## 필수 체크리스트

### 1. 작업 시작 전 (MUST)

```
[ ] 관련 기존 코드 전체 검색 완료
    - grep -r "관련키워드" --include="*.py"
    - 유사 기능 파일 확인

[ ] 기존 모듈/함수 재사용 가능 여부 확인
    - 동일 기능 존재 시 → 재사용 또는 확장
    - 신규 개발 필요 시 → 사유 명시

[ ] 프로젝트 구조 파악
    - tree 또는 ls -la 로 전체 구조 확인
    - README, docs/ 폴더 확인
```

### 2. 코드 작성 전 (SHOULD)

```
[ ] 기존 코드와의 연동 방안 설계
[ ] 중복 코드 여부 재확인
[ ] 기존 데이터 흐름 파악
```

### 3. 코드 작성 후 (MUST)

```
[ ] 기존 기능과 충돌 여부 테스트
[ ] 기존 모듈 import 가능 여부 확인
[ ] 불필요한 중복 제거
```

---

## 파일별 역할 명시

| 파일 | 역할 | 비고 |
|------|------|------|
| `intraday_collector.py` | 분봉 데이터 수집 (네이버) | 당일 데이터만 |
| `stock_screener.py` | 장전 종목 선정 | 08:00 실행 |
| `paper_trading/selector.py` | 페이퍼 트레이딩 종목 선정 | 역추세 전략 |
| `paper_trading/simulator.py` | 매매 시뮬레이션 | intraday_collector 연동 |
| `paper_trading/scheduler.py` | 일일 스케줄러 | 16:10 실행 |
| `project_logger.py` | 의사결정/매매 로깅 | 자동 기록 |
| `auto_reporter.py` | 리포트 생성 | 일간/주간/월간 |

---

## 신규 기능 개발 프로세스

```
1. 요구사항 분석
   ↓
2. 기존 코드 검색 (CRITICAL)
   - grep, find, Glob 활용
   - 유사 기능 파일 모두 읽기
   ↓
3. 재사용 vs 신규 개발 결정
   - 재사용 가능 → 기존 코드 확장
   - 신규 필요 → 사유 문서화
   ↓
4. 설계 및 구현
   - 기존 모듈 import 우선
   - 중복 코드 금지
   ↓
5. 테스트 및 통합
   ↓
6. 문서 업데이트
```

---

## 에이전트별 책임

### dev-agent
- 코드 작성 전 기존 코드 분석 필수
- 중복 코드 작성 금지
- 기존 모듈 재사용 우선

### research-agent
- 코드베이스 탐색 시 전체 파일 목록 제공
- 유사 기능 파일 사전 파악

### audit-agent
- 중복 코드 감지
- 기존 기능과의 충돌 검증

---

## 실패 사례 및 교훈

### Case 1: paper_trading/simulator.py (2026-03-28)

**문제**:
- `intraday_collector.py`에 분봉 수집 + 익절/손절 분석 기능 존재
- 이를 파악하지 않고 일봉 기반 새 코드 작성
- 결과: 기능 퇴보 (정확한 체결 시간 → 추정 시간)

**원인**:
- 기존 코드베이스 검색 미흡
- 파일명만 보고 내용 확인 안함

**해결**:
- `intraday_collector` import하여 기존 기능 활용
- 당일: 분봉 기반 정확한 시간
- 과거: 일봉 기반 (백테스트용)

**교훈**:
> "새 코드 작성 전, 반드시 기존 코드 전체 검색"

---

## 코드 검색 명령어 모음

```bash
# 키워드로 전체 검색
grep -r "분봉\|minute" --include="*.py"

# 함수명 검색
grep -r "def analyze" --include="*.py"

# 클래스 검색
grep -r "class.*Collector" --include="*.py"

# import 관계 파악
grep -r "from.*import\|import " --include="*.py" | grep "파일명"

# 파일 구조 확인
find . -name "*.py" -type f | head -30
```

---

## 변경 이력

| 날짜 | 내용 | 담당 |
|------|------|------|
| 2026-03-28 | 초안 작성 | dev-agent |
| 2026-03-28 | simulator.py intraday_collector 통합 | dev-agent |
