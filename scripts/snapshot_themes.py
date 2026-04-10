"""
테마 스냅샷 - 매일 16:30 KST naver 테마 페이지 저장

목적:
- naver 테마 페이지는 현재 상태만 보여줌 (history 없음)
- Phase 2D Team D 보강(테마 내 대장주 식별)을 위해 일별 스냅샷 누적
- 7~14일 누적 후 Team D 보강 가능

저장 위치: data/theme_snapshots/themes_{YYYYMMDD}.json
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from paper_trading.utils.naver_theme import NaverThemeCrawler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
SNAPSHOT_DIR = PROJECT_ROOT / "data" / "theme_snapshots"


def main():
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(KST).strftime('%Y%m%d')
    out_path = SNAPSHOT_DIR / f"themes_{today}.json"

    logger.info(f"테마 스냅샷 시작 ({today})")
    crawler = NaverThemeCrawler(cache_hours=0)  # 강제 fresh fetch

    try:
        # 1. 전체 테마 리스트 (등락률 포함)
        themes = crawler.get_theme_list(force_refresh=True)
        logger.info(f"  테마 수: {len(themes)}")

        # 2. 상위 테마는 종목 리스트도 함께 저장
        hot_themes = crawler.get_hot_themes(top_n=20, min_change=0)

        snapshot = {
            'date': today,
            'fetched_at': datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S'),
            'theme_count': len(themes),
            'themes': themes,
            'hot_themes': hot_themes,
        }

        # 3. 상위 20개 테마의 종목 리스트 fetch
        theme_stocks = {}
        for ht in hot_themes[:20]:
            code = ht.get('code', '')
            name = ht.get('name', '')
            if not code:
                continue
            try:
                stocks = crawler.get_theme_stocks(code, theme_name=name)
                if stocks:
                    theme_stocks[code] = {
                        'name': name,
                        'change_pct': ht.get('change_pct', 0),
                        'stocks': stocks,
                    }
            except Exception as e:
                logger.debug(f"테마 종목 fetch 실패 {code}: {e}")
        snapshot['theme_stocks'] = theme_stocks
        logger.info(f"  핫 테마 종목 수집: {len(theme_stocks)}개")

        # 4. 저장
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2, default=str)

        logger.info(f"  저장: {out_path}")
        logger.info(f"테마 스냅샷 완료")
        return 0

    except Exception as e:
        logger.error(f"테마 스냅샷 오류: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
