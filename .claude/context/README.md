# Context Directory

이 디렉토리는 에이전트 작업 결과와 프로젝트 상태를 기록합니다.

## 파일 구조

```
.claude/context/
├── README.md          # 이 파일
├── state.json         # 현재 프로젝트 상태 및 에이전트 실행 결과
├── decisions.md       # 주요 의사결정 기록
└── issues.md          # 문제 추적 (향후 생성 예정)
```

## state.json

프로젝트의 현재 상태를 JSON 형식으로 기록합니다.

**필드 설명**:
- `current_phase`: 현재 단계 (planning, in_progress, completed, blocked)
- `last_updated`: 마지막 업데이트 시각 (ISO 8601 형식)
- `project`: 프로젝트 이름
- `task`: 현재 작업 설명
- `agent_results`: 에이전트 실행 결과 배열
  - `request_id`: 요청 고유 ID
  - `agent`: 실행된 에이전트 이름
  - `status`: 상태 (success, warning, error, in_progress)
  - `summary`: 결과 요약
- `artifacts`: 생성/수정된 파일 목록

**사용 예시**:
```bash
# 현재 상태 확인
cat .claude/context/state.json | jq '.current_phase'

# 에이전트 결과 확인
cat .claude/context/state.json | jq '.agent_results[] | select(.status=="error")'

# 아티팩트 목록 확인
cat .claude/context/state.json | jq -r '.artifacts[]'
```

## decisions.md

프로젝트의 주요 의사결정을 마크다운 형식으로 기록합니다.

**기록 내용**:
- 결정 사항 (무엇을 선택했는가)
- 배경 (왜 결정이 필요했는가)
- 선정 근거 (왜 이 선택을 했는가)
- 대안 및 검토 사항 (다른 선택지는 무엇이었는가)
- 영향 (이 결정이 프로젝트에 미치는 영향)

**작성 규칙**:
- 날짜별로 섹션 구분
- 기술적 결정에 집중 (비즈니스 로직, 아키텍처, 라이브러리 선택 등)
- 근거를 명확히 기록 (향후 회고 시 참고)

## issues.md

프로젝트의 문제 및 해결 과정을 추적합니다.

**형식**:
```markdown
## [ISSUE-001] 문제 제목
- **발생일**: YYYY-MM-DD
- **에이전트**: 발생한 에이전트명
- **증상**: 무엇이 잘못되었는지
- **원인**: 근본 원인 분석
- **해결**: 어떻게 해결했는지
- **예방**: 재발 방지 조치
- **상태**: open | resolved
```

## 업데이트 정책

- **state.json**: 에이전트 실행 시마다 자동 업데이트
- **decisions.md**: 주요 의사결정 시 수동 추가
- **issues.md**: 문제 발생 시 반드시 기록

## 보안

- 이 디렉토리는 **민감한 정보를 포함하지 않습니다**
- API 키, 비밀번호, 개인정보는 절대 기록하지 마세요
- 필요시 `.gitignore`에 추가하여 버전 관리에서 제외

## 참고

- 이 디렉토리는 State Manager Agent가 자동으로 관리합니다
- 수동 편집 시 JSON 포맷 오류에 주의하세요
- 정기적으로 백업하는 것을 권장합니다
