"""
P3-3b: 스퀴즈 플레이 KOSPI v6 / KOSDAQ v5 변형 등록·필터 단위 테스트.

검증 항목:
1. 두 변형이 StrategyRegistry에 등록되어 있고 ID/메타데이터 정확
2. _squeeze_common.compute_indicators — BB, MA200, spread 계산 정확
3. passes_variant — v6/v5 필터 분기 동작
4. score_candidate — 점수 0~80 범위, %B 낮을수록·spread 좁을수록 점수 ↑
5. 변형 클래스 인스턴스화 시 상수 오버라이드 적용

데이터 fetch 통합 테스트는 별도 (P3-3d 시점에 실시간 KRX와 연결).

실행:
    cd zip1/news-trading-bot
    python -m paper_trading.test_squeeze_variants
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

# 등록 트리거 — __init__.py가 두 변형을 import 함
from paper_trading.strategies import (
    StrategyRegistry,
    SqueezePlayKospiV6Strategy,
    SqueezePlayKosdaqV5Strategy,
)
from paper_trading.strategies._squeeze_common import (
    KOSPI_TOP_53,
    KOSDAQ_TOP_35,
    compute_indicators,
    passes_variant,
    score_candidate,
)


def test_registry_has_both_variants():
    """StrategyRegistry에 두 변형이 등록되어야 함."""
    all_ids = {s["id"] for s in StrategyRegistry.list_strategies()}
    assert "squeeze_play_kospi_v6" in all_ids, f"v6 미등록: {all_ids}"
    assert "squeeze_play_kosdaq_v5" in all_ids, f"v5 미등록: {all_ids}"
    print("  [OK] 두 변형 모두 registry 등록 확인")


def test_variant_constants():
    """변형별 클래스 상수 (universe/필터/보유) 정확."""
    v6 = SqueezePlayKospiV6Strategy()
    v5 = SqueezePlayKosdaqV5Strategy()

    assert v6.UNIVERSE_MARKET == "KOSPI"
    assert len(v6.UNIVERSE) == 53, f"KOSPI universe size: {len(v6.UNIVERSE)}"
    assert v6.MA200_FILTER_ENABLED is True
    assert v6.SQUEEZE_FILTER_ENABLED is True
    assert v6.SQUEEZE_MAX_SPREAD_PCT == 10.0
    assert v6.RECOMMENDED_HOLDING_DAYS == 5

    assert v5.UNIVERSE_MARKET == "KOSDAQ"
    assert len(v5.UNIVERSE) == 35, f"KOSDAQ universe size: {len(v5.UNIVERSE)}"
    assert v5.MA200_FILTER_ENABLED is False  # KOSDAQ에서 MA200 부적합 (DEC-005)
    assert v5.SQUEEZE_FILTER_ENABLED is True
    assert v5.SQUEEZE_MAX_SPREAD_PCT == 15.0
    assert v5.RECOMMENDED_HOLDING_DAYS == 5

    print(f"  [OK] v6: KOSPI {len(v6.UNIVERSE)}종목, MA200+sqz@10%, 5일 보유")
    print(f"  [OK] v5: KOSDAQ {len(v5.UNIVERSE)}종목, sqz@15% 단독, 5일 보유")


def test_compute_indicators_basic_bb():
    """BB(20,2σ) %B 계산 검증."""
    # 종가 100,101,...,119 (등차) → MA20=109.5, std≈5.92, upper≈121.34, lower≈97.66
    closes = np.arange(100, 120, dtype=float)
    cache = compute_indicators(closes, current_close=119)
    assert cache["valid"] is True
    # %B = (119 - 97.66) / (121.34 - 97.66) ≈ 0.901
    assert 0.85 < cache["percent_b"] < 0.95, f"percent_b={cache['percent_b']}"
    assert "ma200" not in cache, "20개 데이터에 MA200 없어야 함"
    print(f"  [OK] BB %B = {cache['percent_b']:.3f} (등차 시계열 상단 근처)")


def test_compute_indicators_with_ma200():
    """MA200 + 5일전 비교 + spread% 계산."""
    # 205일 시계열, 처음 100 = 100, 다음 100 = 110, 마지막 5 = 120
    # 마지막 200일 평균 = (95×100 + 100×110 + 5×120) / 200 = ...
    closes = np.concatenate([
        np.full(100, 100.0),  # idx 0~99
        np.full(100, 110.0),  # idx 100~199
        np.full(5, 120.0),    # idx 200~204
    ])
    cache = compute_indicators(closes, current_close=120.0)
    assert cache["valid"] is True
    assert "ma200" in cache
    # 마지막 200개: idx 5~204 → 95×100 + 100×110 + 5×120 = 9500+11000+600 = 21100 / 200 = 105.5
    assert abs(cache["ma200"] - 105.5) < 0.01, f"ma200={cache['ma200']}"
    # 5일 전 MA200: idx 0~199 → 100×100 + 100×110 = 21000 / 200 = 105.0
    # ma200 (105.5) > ma200_5d (105.0) → rising
    assert cache["ma200_rising"] is True
    # 20MA = 마지막 20개 평균: idx 185~204 → 15×110 + 5×120 = 1650+600 = 2250/20 = 112.5
    # spread = |112.5 - 105.5| / 105.5 × 100 ≈ 6.64%
    assert 6.0 < cache["spread_pct"] < 7.5, f"spread_pct={cache['spread_pct']}"
    print(f"  [OK] MA200={cache['ma200']:.2f}, rising={cache['ma200_rising']}, "
          f"spread={cache['spread_pct']:.2f}%")


def test_passes_variant_v6_kospi():
    """v6 필터: %B<0.2 + 양봉 + MA200↑ + spread≤10%."""
    cache = {
        "valid": True, "percent_b": 0.15, "bb_middle": 100.0,
        "ma200": 95.0, "ma200_rising": True, "spread_pct": 5.26,
    }
    # 통과: 양봉 + 모든 조건 만족
    assert passes_variant(cache, current_close=98, is_positive_candle=True,
                          ma200_filter=True, squeeze_filter=True, squeeze_max_pct=10.0) is True

    # 거부: 음봉
    assert passes_variant(cache, 98, False, True, True, 10.0) is False

    # 거부: MA200 우하향
    cache_falling = {**cache, "ma200_rising": False}
    assert passes_variant(cache_falling, 98, True, True, True, 10.0) is False

    # 거부: 종가가 MA200 아래
    assert passes_variant(cache, 90, True, True, True, 10.0) is False

    # 거부: spread 11% > 10%
    cache_wide = {**cache, "spread_pct": 11.0}
    assert passes_variant(cache_wide, 98, True, True, True, 10.0) is False

    print("  [OK] v6 필터: %B/양봉/MA200↑/spread≤10% 모두 검증")


def test_passes_variant_v5_kosdaq():
    """v5 필터: %B<0.2 + 양봉 + spread≤15% (MA200 무시)."""
    cache = {
        "valid": True, "percent_b": 0.18, "bb_middle": 100.0,
        "ma200": 110.0, "ma200_rising": False,  # MA200 우하향이어도 통과해야 함
        "spread_pct": 9.09,
    }
    assert passes_variant(cache, 98, True, ma200_filter=False, squeeze_filter=True,
                          squeeze_max_pct=15.0) is True

    # 거부: spread 16% > 15%
    cache_wide = {**cache, "spread_pct": 16.0}
    assert passes_variant(cache_wide, 98, True, False, True, 15.0) is False

    # 거부: %B 0.21 > 0.2
    cache_high_pb = {**cache, "percent_b": 0.21}
    assert passes_variant(cache_high_pb, 98, True, False, True, 15.0) is False

    print("  [OK] v5 필터: %B/양봉/spread≤15% (MA200 무시) 모두 검증")


def test_score_candidate_ranges():
    """점수 단조성 — %B 낮을수록·spread 좁을수록 점수 ↑."""
    cache_hi = {"percent_b": 0.05, "spread_pct": 2.0}
    cache_lo = {"percent_b": 0.18, "spread_pct": 9.0}
    # 시가 100 → 종가 105 (5% 양봉)
    s_hi = score_candidate(cache_hi, current_close=105, open_price=100,
                           squeeze_max_pct=10.0, use_squeeze_score=True)
    s_lo = score_candidate(cache_lo, current_close=105, open_price=100,
                           squeeze_max_pct=10.0, use_squeeze_score=True)
    assert s_hi > s_lo, f"낮은 %B + 좁은 spread가 더 높아야: {s_hi} vs {s_lo}"
    assert 0 <= s_lo <= s_hi <= 80, f"점수 범위 [0,80] 위반: {s_lo}, {s_hi}"
    print(f"  [OK] score 단조성: %B 0.05+spread 2% → {s_hi:.1f}, "
          f"%B 0.18+spread 9% → {s_lo:.1f}")


def test_get_params_includes_holding():
    """get_params가 RECOMMENDED_HOLDING_DAYS를 노출 (시뮬레이터 라우팅용)."""
    v6 = SqueezePlayKospiV6Strategy()
    params = v6.get_params()
    assert params["recommended_holding_days"] == 5
    assert params["universe_size"] == 53
    assert params["ma200_filter"] is True
    assert params["squeeze_filter"] is True
    assert params["squeeze_max_spread_pct"] == 10.0
    print(f"  [OK] v6.get_params: holding=5, universe=53, ma200=ON, sqz=10%")


def main():
    print("=" * 60)
    print("P3-3b: 스퀴즈 변형 등록·필터 단위 테스트")
    print("=" * 60)

    tests = [
        test_registry_has_both_variants,
        test_variant_constants,
        test_compute_indicators_basic_bb,
        test_compute_indicators_with_ma200,
        test_passes_variant_v6_kospi,
        test_passes_variant_v5_kosdaq,
        test_score_candidate_ranges,
        test_get_params_includes_holding,
    ]
    passed = 0
    failed = []
    for t in tests:
        try:
            print(f"\n[테스트] {t.__name__}")
            t()
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {e}")
            failed.append((t.__name__, str(e)))
        except Exception as e:
            print(f"  [ERROR] {type(e).__name__}: {e}")
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))

    print(f"\n{'=' * 60}")
    print(f"결과: {passed}/{len(tests)} 통과")
    if failed:
        print("실패:")
        for name, msg in failed:
            print(f"  - {name}: {msg}")
        sys.exit(1)
    print("=" * 60)


if __name__ == "__main__":
    main()
