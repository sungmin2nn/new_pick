"""
동일 테마 중복 캡 — BNF/Bollinger 등 후보 정렬 후 상위 N개 자르기 전 적용.

배경:
  team_d (theme_policy) 의 동일 그룹 캡(c38d53c)이 효과가 있었다.
  같은 패턴을 종목별 테마 역인덱스(_stock_to_themes.json) 기반으로
  다른 전략에도 적용한다.

데이터 소스:
  data/theme_cache/_stock_to_themes.json (scripts.build_stock_theme_index 로 생성)
  - 시점 무관 정적 스냅샷 (테마 정의 변동 시 재생성 필요)
  - backtest 시 lookahead bias 가능성 — 단기 backtest 에서 실용적 trade-off
"""

import json
import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')

INDEX_PATH = Path(__file__).parent.parent.parent / "data" / "theme_cache" / "_stock_to_themes.json"

_index_cache: Optional[Dict[str, List[str]]] = None
_index_path_loaded: Optional[Path] = None


def load_stock_themes(path: Path = INDEX_PATH, force_reload: bool = False) -> Dict[str, List[str]]:
    """
    {stock_code: [theme_code, ...]} 매핑 반환.

    파일이 없거나 깨졌으면 빈 dict — 호출부는 캡 비활성으로 처리.
    """
    global _index_cache, _index_path_loaded
    if _index_cache is not None and _index_path_loaded == path and not force_reload:
        return _index_cache

    if not path.exists():
        logger.warning(f"[theme_cap] 역인덱스 없음: {path} — 캡 비활성")
        _index_cache = {}
        _index_path_loaded = path
        return _index_cache

    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
    except Exception as e:
        logger.warning(f"[theme_cap] 역인덱스 로드 실패: {e} — 캡 비활성")
        _index_cache = {}
        _index_path_loaded = path
        return _index_cache

    mapping: Dict[str, List[str]] = {}
    for code, info in raw.items():
        if code == '_meta' or not isinstance(info, dict):
            continue
        themes = info.get('themes') or []
        mapping[code] = [t['code'] for t in themes if isinstance(t, dict) and t.get('code')]

    _index_cache = mapping
    _index_path_loaded = path
    return _index_cache


def apply_theme_cap(
    items: List[T],
    get_code: Callable[[T], str],
    top_n: int,
    max_per_theme: Optional[int] = 2,
    log_prefix: str = "",
) -> List[T]:
    """
    정렬된 후보 리스트에서 동일 테마 중복을 제한하며 top_n개 선정.

    Args:
        items: 점수 내림차순으로 이미 정렬된 후보 리스트
        get_code: 후보에서 종목코드 6자리 문자열 추출 함수
        top_n: 최종 선정 수
        max_per_theme: 테마 하나당 최대 몇 종목 (None/0 이면 캡 비활성, 그냥 [:top_n])
        log_prefix: 로그 접두 (전략명 등)

    Returns:
        길이 ≤ top_n 의 리스트. 캡으로 인해 후보 풀 부족 시 더 짧을 수 있음.

    Notes:
        - 종목이 다수 테마 소속이면 그 모든 테마 카운터에 +1 (보수적 캡)
        - 테마 인덱스에 없는 종목 (=정보 없음) 은 캡 적용 없이 통과
    """
    if not items:
        return []
    if not max_per_theme or max_per_theme <= 0:
        return items[:top_n]

    stock_themes = load_stock_themes()
    if not stock_themes:
        return items[:top_n]

    selected: List[T] = []
    theme_count: Dict[str, int] = {}
    skipped: List[str] = []

    for item in items:
        if len(selected) >= top_n:
            break

        code = get_code(item)
        themes = stock_themes.get(code, [])

        # 테마 정보 없는 종목 = 캡 미적용 통과
        if not themes:
            selected.append(item)
            continue

        # 어느 테마든 캡 도달 시 스킵
        blocking = next(
            (t for t in themes if theme_count.get(t, 0) >= max_per_theme),
            None,
        )
        if blocking is not None:
            skipped.append(f"{code}(theme:{blocking})")
            continue

        selected.append(item)
        for t in themes:
            theme_count[t] = theme_count.get(t, 0) + 1

    if skipped:
        prefix = f"[{log_prefix}] " if log_prefix else ""
        logger.info(
            f"{prefix}theme_cap: {len(skipped)}건 제외 → {', '.join(skipped[:5])}"
            + ("..." if len(skipped) > 5 else "")
        )
    if len(selected) < top_n:
        prefix = f"[{log_prefix}] " if log_prefix else ""
        logger.info(f"{prefix}theme_cap 적용 후 {len(selected)}/{top_n}건 (대체 풀 부족)")

    return selected
