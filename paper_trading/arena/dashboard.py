"""
Arena 대시보드 - JSON 데이터 기반
index.html이 JS로 직접 JSON을 읽어 렌더링함
이 모듈은 GitHub Actions에서 데이터 검증/보조용
"""

import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))

ARENA_DIR = Path(__file__).parent.parent.parent / "data" / "arena"
DATA_DIR = Path(__file__).parent.parent.parent / "data"


def generate_arena_dashboard() -> str:
    """
    아레나 대시보드 데이터 검증
    index.html이 JS로 직접 JSON을 읽으므로 별도 HTML 생성 불필요
    """
    print("[Dashboard] index.html이 JS 기반으로 JSON 데이터를 직접 로드합니다.")
    print(f"  - 리더보드: {ARENA_DIR / 'leaderboard.json'}")
    print(f"  - 팀 포트폴리오: {ARENA_DIR / 'team_*/portfolio.json'}")
    print(f"  - 헬스체크: {ARENA_DIR / 'healthcheck/'}")

    # 데이터 존재 여부 확인
    lb_path = ARENA_DIR / "leaderboard.json"
    if lb_path.exists():
        print(f"  ✓ 리더보드 데이터 있음")
    else:
        print(f"  ✗ 리더보드 데이터 없음 (첫 실행 전)")

    team_dirs = ["team_a", "team_b", "team_c", "team_d"]
    for tid in team_dirs:
        pf_path = ARENA_DIR / tid / "portfolio.json"
        if pf_path.exists():
            print(f"  ✓ {tid} 포트폴리오 있음")
        else:
            print(f"  ✗ {tid} 포트폴리오 없음")

    return "index.html"


if __name__ == "__main__":
    generate_arena_dashboard()
