#!/usr/bin/env python3
"""
볼린저밴드 스윙 종목 선정 실행 스크립트

- 워크플로우(bollinger-swing.yml)에서 호출
- KRX OpenAPI로 전종목 fetch (시총/거래대금/양봉 필터)
- pykrx로 필터 통과 종목 히스토리 fetch (BB/RSI/거래량 계산)
- 결과: data/bnf/bollinger_candidates.json + bollinger_candidates_{date}.json
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from paper_trading.bnf.bollinger_selector import BollingerSelector


def main():
    print("=" * 60)
    print("볼린저밴드 스윙 종목 선정")
    print("=" * 60)

    selector = BollingerSelector(data_dir="data/bnf")
    candidates = selector.select()

    print("\n" + "=" * 60)
    print(f"선정 완료: {len(candidates)}개")
    if candidates:
        for c in candidates[:10]:
            print(
                f"  {c['rank']:2d}. {c['name']} ({c['code']}) "
                f"%%B={c['percent_b']:.3f} RSI={c['rsi']:.1f} "
                f"가격={c['price']:,}"
            )
    else:
        print("  조건 충족 종목 없음")
    print("=" * 60)


if __name__ == "__main__":
    main()
