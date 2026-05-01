"""
종목 → 테마 역인덱스 생성 (Phase 1)

기존 data/theme_cache/theme_<code>.json 들을 뒤집어
data/theme_cache/_stock_to_themes.json 생성.

용법:
    python -m scripts.build_stock_theme_index            # 기존 캐시만 사용
    python -m scripts.build_stock_theme_index --refresh  # 누락 테마 fetch (~60s)
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from paper_trading.utils.naver_theme import NaverThemeCrawler


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--refresh', action='store_true',
                    help='theme_list.json 에는 있지만 캐시 없는 테마 fetch')
    args = ap.parse_args()

    crawler = NaverThemeCrawler()
    result = crawler.build_stock_to_themes_index(refresh_missing=args.refresh)

    meta = result['_meta']
    print(f"[stock_to_themes] 저장: {meta['source_cache_dir']}/_stock_to_themes.json")
    print(f"  테마 커버리지: {meta['themes_with_stocks']}/{meta['themes_total_known']} "
          f"({meta['coverage_pct']}%)")
    print(f"  종목 수: {meta['stocks_total']}")
    print(f"  누락 테마: {meta['themes_missing_count']}개")

    if meta['themes_missing_count'] > 0 and not args.refresh:
        print("  → --refresh 로 누락 테마 채울 수 있음")
    return 0


if __name__ == '__main__':
    sys.exit(main())
