#!/bin/bash

# ═══════════════════════════════════════════════════════════════════
# Quality Gate Hook - 배포 전 품질 게이트 물리적 차단
# ═══════════════════════════════════════════════════════════════════
#
# 사용법:
#   ./gate_hook.sh <score_file.json>
#   ./gate_hook.sh --check-latest
#
# 반환값:
#   0 - 통과 (배포 진행 가능)
#   1 - 불통 (배포 차단)
#
# ═══════════════════════════════════════════════════════════════════

set -e

# 설정
HARNESS_DIR="$(dirname "$0")"
SCORE_HISTORY="$HARNESS_DIR/score_history.json"
QUALITY_GATE="$HARNESS_DIR/quality_gate.md"

# 색상
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ─────────────────────────────────────────────────────────────────
# 함수: 에러 출력
# ─────────────────────────────────────────────────────────────────
error() {
    echo -e "${RED}[GATE ERROR]${NC} $1" >&2
}

# ─────────────────────────────────────────────────────────────────
# 함수: 성공 출력
# ─────────────────────────────────────────────────────────────────
success() {
    echo -e "${GREEN}[GATE PASS]${NC} $1"
}

# ─────────────────────────────────────────────────────────────────
# 함수: 경고 출력
# ─────────────────────────────────────────────────────────────────
warn() {
    echo -e "${YELLOW}[GATE WARN]${NC} $1"
}

# ─────────────────────────────────────────────────────────────────
# 함수: 점수 파일 검증
# ─────────────────────────────────────────────────────────────────
validate_score_file() {
    local score_file="$1"

    if [ ! -f "$score_file" ]; then
        error "점수 파일을 찾을 수 없습니다: $score_file"
        return 1
    fi

    # JSON 유효성 검사
    if ! python3 -c "import json; json.load(open('$score_file'))" 2>/dev/null; then
        error "유효하지 않은 JSON 파일: $score_file"
        return 1
    fi

    return 0
}

# ─────────────────────────────────────────────────────────────────
# 함수: 과락 체크
# ─────────────────────────────────────────────────────────────────
check_cutlines() {
    local score_file="$1"

    # Python으로 점수 파싱 및 과락 체크
    python3 << EOF
import json
import sys

# 커트라인 정의
CUTLINES = {
    "functionality": 24,
    "security": 18,
    "code_quality": 10,
    "ux_usability": 14,
    "performance": 7,
    "documentation": 3
}

# 과락 시 즉시 불통 영역
CRITICAL_AREAS = ["functionality", "security"]

try:
    with open("$score_file") as f:
        data = json.load(f)

    scores = data.get("scores", {})
    total = data.get("total", 0)
    cutline = data.get("cutline", 80)

    failed_areas = []
    critical_fail = False

    for area, cutline_score in CUTLINES.items():
        area_data = scores.get(area, {})
        score = area_data.get("score", 0)

        if score < cutline_score:
            failed_areas.append({
                "area": area,
                "score": score,
                "cutline": cutline_score,
                "critical": area in CRITICAL_AREAS
            })
            if area in CRITICAL_AREAS:
                critical_fail = True

    # 결과 출력
    if critical_fail:
        print("CRITICAL_FAIL")
        for f in failed_areas:
            if f["critical"]:
                print(f"CRITICAL:{f['area']}:{f['score']}/{f['cutline']}")
        sys.exit(1)

    if failed_areas:
        print("AREA_FAIL")
        for f in failed_areas:
            print(f"FAIL:{f['area']}:{f['score']}/{f['cutline']}")
        sys.exit(1)

    if total < cutline:
        print(f"TOTAL_FAIL:{total}/{cutline}")
        sys.exit(1)

    print(f"PASS:{total}/{cutline}")
    sys.exit(0)

except Exception as e:
    print(f"ERROR:{e}")
    sys.exit(1)
EOF

    return $?
}

# ─────────────────────────────────────────────────────────────────
# 함수: 최신 평가 결과 확인
# ─────────────────────────────────────────────────────────────────
check_latest() {
    if [ ! -f "$SCORE_HISTORY" ]; then
        error "score_history.json을 찾을 수 없습니다"
        return 1
    fi

    # 최신 평가 결과 추출
    local latest=$(python3 -c "
import json
with open('$SCORE_HISTORY') as f:
    data = json.load(f)
history = data.get('history', [])
if history:
    print(json.dumps(history[-1]))
else:
    print('NONE')
")

    if [ "$latest" = "NONE" ]; then
        warn "평가 기록이 없습니다. 배포 차단."
        return 1
    fi

    # 임시 파일로 저장 후 체크
    local tmp_file=$(mktemp)
    echo "$latest" > "$tmp_file"

    check_cutlines "$tmp_file"
    local result=$?

    rm -f "$tmp_file"
    return $result
}

# ─────────────────────────────────────────────────────────────────
# 함수: 결과 출력 및 배포 차단
# ─────────────────────────────────────────────────────────────────
print_result() {
    local result="$1"

    echo ""
    echo "═══════════════════════════════════════════════════════"

    case "$result" in
        PASS*)
            echo -e "${GREEN}       ✅ 품질 게이트 통과 - 배포 승인${NC}"
            echo "═══════════════════════════════════════════════════════"
            echo ""
            echo "  $result"
            echo ""
            return 0
            ;;
        CRITICAL_FAIL*)
            echo -e "${RED}       🛑 품질 게이트 불통 - 배포 차단${NC}"
            echo "═══════════════════════════════════════════════════════"
            echo ""
            echo "  [CRITICAL] 과락 영역 발견 - 즉시 불통"
            echo ""
            return 1
            ;;
        AREA_FAIL*)
            echo -e "${RED}       ⚠️ 품질 게이트 불통 - 배포 차단${NC}"
            echo "═══════════════════════════════════════════════════════"
            echo ""
            echo "  [FAIL] 과락 영역 발견"
            echo ""
            return 1
            ;;
        TOTAL_FAIL*)
            echo -e "${YELLOW}       ⚠️ 품질 게이트 불통 - 배포 차단${NC}"
            echo "═══════════════════════════════════════════════════════"
            echo ""
            echo "  [FAIL] 총점 커트라인 미달"
            echo "  $result"
            echo ""
            return 1
            ;;
        *)
            error "알 수 없는 결과: $result"
            return 1
            ;;
    esac
}

# ─────────────────────────────────────────────────────────────────
# 함수: 도움말
# ─────────────────────────────────────────────────────────────────
show_help() {
    cat << 'HELP'
Quality Gate Hook - 배포 전 품질 검증

사용법:
  ./gate_hook.sh <score_file.json>    # 특정 점수 파일로 검증
  ./gate_hook.sh --check-latest       # 최신 평가 결과로 검증
  ./gate_hook.sh --help               # 도움말

반환값:
  0 - 통과 (배포 진행 가능)
  1 - 불통 (배포 차단)

예시:
  # CI/CD 파이프라인에서 사용
  ./gate_hook.sh --check-latest && git push origin main

  # 특정 평가 결과로 검증
  ./gate_hook.sh evaluation_result.json && npm run deploy

커트라인:
  기능 동작: 24/30점
  보안: 18/20점 (과락 시 즉시 불통)
  코드 품질: 10/15점
  UX/사용성: 14/20점
  성능: 7/10점
  문서화: 3/5점
  총점: 80/100점 (Phase 2 기준)

HELP
}

# ═══════════════════════════════════════════════════════════════════
# 메인
# ═══════════════════════════════════════════════════════════════════

main() {
    case "${1:-}" in
        --help|-h)
            show_help
            exit 0
            ;;
        --check-latest)
            echo ""
            echo "═══════════════════════════════════════════════════════"
            echo "       품질 게이트 검증 중..."
            echo "═══════════════════════════════════════════════════════"
            echo ""

            result=$(check_latest 2>&1)
            exit_code=$?

            print_result "$result"
            exit $exit_code
            ;;
        "")
            error "점수 파일을 지정해주세요"
            echo "사용법: ./gate_hook.sh <score_file.json>"
            echo "또는:   ./gate_hook.sh --check-latest"
            exit 1
            ;;
        *)
            echo ""
            echo "═══════════════════════════════════════════════════════"
            echo "       품질 게이트 검증 중..."
            echo "═══════════════════════════════════════════════════════"
            echo ""

            if ! validate_score_file "$1"; then
                exit 1
            fi

            result=$(check_cutlines "$1" 2>&1)
            exit_code=$?

            print_result "$result"
            exit $exit_code
            ;;
    esac
}

main "$@"
