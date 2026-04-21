"""
Phase 2.1 전략 검증 테스트.

단위 테스트가 아니라 import / 인스턴스화 / 메타데이터 / 중복 검사
전체 파이프라인이 통과하는지 확인하는 smoke test.

실행:
    cd zip1/strategy-lab
    python3 -m tests.test_phase2_strategies
"""

from __future__ import annotations

import importlib
import sys
import traceback


STRATEGY_MODULES = [
    # Phase 2.1 (handoff 후보)
    "strategies.volatility_breakout_lw",
    "strategies.sector_rotation",
    "strategies.foreign_flow_momentum",
    "strategies.news_catalyst_timing",
    "strategies.multi_signal_hybrid",
    # Phase 2.4-2.5 (외부 리서치)
    "strategies.kospi_intraday_momentum",
    "strategies.overnight_etf_reversal",
    "strategies.opening_30min_volume_burst",
    "strategies.eod_reversal_korean",
    "strategies.turtle_breakout_short",
]


def test_imports():
    """모든 전략 모듈이 import 가능한지."""
    print("\n[TEST] Strategy imports")
    failed = []
    for m in STRATEGY_MODULES:
        try:
            importlib.import_module(m)
            print(f"  ✓ {m}")
        except Exception as e:
            print(f"  ✗ {m}: {e}")
            failed.append(m)
    return len(failed) == 0


def test_metadata():
    """모든 전략이 METADATA를 정의하고 필수 필드가 있는지."""
    print("\n[TEST] Metadata completeness")
    failed = []
    for m in STRATEGY_MODULES:
        mod = importlib.import_module(m)
        meta = getattr(mod, "METADATA", None)
        if meta is None:
            print(f"  ✗ {m}: METADATA 없음")
            failed.append(m)
            continue
        required = ["id", "name", "category", "risk_level",
                    "hypothesis", "differs_from_existing"]
        missing = [r for r in required if not getattr(meta, r, None)]
        if missing:
            print(f"  ✗ {m}: missing {missing}")
            failed.append(m)
            continue
        if not meta.sources:
            print(f"  ✗ {m}: sources 비어있음")
            failed.append(m)
            continue
        print(f"  ✓ {m}: id={meta.id}, sources={len(meta.sources)}")
    return len(failed) == 0


def test_instantiation():
    """전략 클래스 인스턴스화 + select_stocks 메서드 존재."""
    print("\n[TEST] Strategy instantiation")
    failed = []
    for m in STRATEGY_MODULES:
        try:
            mod = importlib.import_module(m)
            strategy_classes = [
                v for v in vars(mod).values()
                if isinstance(v, type)
                and hasattr(v, "STRATEGY_ID")
                and v.__module__ == m
            ]
            if not strategy_classes:
                print(f"  ✗ {m}: 전략 클래스 없음")
                failed.append(m)
                continue
            cls = strategy_classes[0]
            instance = cls()
            assert hasattr(instance, "select_stocks"), "select_stocks 없음"
            assert hasattr(instance, "get_params"), "get_params 없음"
            params = instance.get_params()
            assert isinstance(params, dict), "get_params dict 아님"
            print(f"  ✓ {cls.__name__} (params: {len(params)})")
        except Exception as e:
            print(f"  ✗ {m}: {e}")
            traceback.print_exc()
            failed.append(m)
    return len(failed) == 0


def test_duplicate_check():
    """모든 전략이 기존 6개와 중복되지 않는지."""
    print("\n[TEST] Duplicate check vs existing 6")
    from lab.duplicate_check import check_duplicate

    expectations = [
        # Phase 2.1
        ("volatility_breakout_lw", "breakout",
         ["daily_range_k", "open_breakout", "volume_surge_vs_yesterday"],
         ["KRX_OHLCV"], "Echo와 다른 본질"),
        ("sector_rotation", "theme",
         ["kospi_sector_strength", "market_cap_top_in_sector"],
         ["KRX_OHLCV", "KRX_INDEX"], "Delta와 다른 데이터 일관성"),
        ("foreign_flow_momentum", "flow",
         ["foreign_consecutive_buy", "foreign_5day_total"],
         ["KRX_OHLCV", "NAVER_INVESTOR"], "신규 데이터 소스"),
        ("news_catalyst_timing", "event",
         ["dart_disclosure", "gap_reaction", "volume_surge_after_news"],
         ["DART", "KRX_OHLCV"], "Gamma와 다른 시점/속도"),
        ("multi_signal_hybrid", "hybrid",
         ["dart_positive", "investor_net_buy", "volume_surge"],
         ["DART", "NAVER_INVESTOR", "KRX_OHLCV"], "메타 결합 전략"),
        # Phase 2.4-2.5 (외부 리서치)
        ("kospi_intraday_momentum", "momentum",
         ["overnight_return", "first_30min_proxy", "combined_signal"],
         ["KRX_OHLCV"], "MIM 학술 검증, Volatility BO와 시그널 차원 다름"),
        ("overnight_etf_reversal", "statistical",
         ["etf_brand", "intraday_weakness", "overnight_long"],
         ["KRX_OHLCV"], "한국 ETF overnight 효과, 진입/청산 시점 역방향"),
        ("opening_30min_volume_burst", "breakout",
         ["value_5day_surge_3x", "price_up", "absolute_value"],
         ["KRX_OHLCV"], "거래대금 surge 시그널 (Echo는 가격 갭, VB는 가격 변동폭)"),
        ("eod_reversal_korean", "contrarian",
         ["single_day_loss_3_to_8_pct", "intraday_recovery_ratio"],
         ["KRX_OHLCV"], "Beta(다일 RSI)/BNF(3거래일)와 시간 차원 다름 (단일일)"),
        ("turtle_breakout_short", "breakout",
         ["n_day_high_breakout", "volume_surge_vs_n_avg"],
         ["KRX_OHLCV"], "신고가 갱신 시그널 (Echo/VB/Alpha와 본질 다름)"),
    ]

    failed = []
    for sid, cat, signals, data, differs in expectations:
        r = check_duplicate(
            new_id=sid,
            new_category=cat,
            new_signals=signals,
            new_data=data,
            differs_from_existing=differs,
        )
        if not r.passed:
            print(f"  ✗ {sid}: {r.message}")
            failed.append(sid)
        else:
            print(f"  ✓ {sid}: {r.severity}")
    return len(failed) == 0


def test_metadata_save_load():
    """메타데이터 JSON 저장/로드."""
    print("\n[TEST] Metadata save/load roundtrip")
    from pathlib import Path
    from lab.metadata import StrategyMetadata

    test_dir = Path("/tmp/strategy-lab-test-meta")
    test_dir.mkdir(parents=True, exist_ok=True)

    failed = []
    for m in STRATEGY_MODULES:
        mod = importlib.import_module(m)
        meta = mod.METADATA
        try:
            saved = meta.save(test_dir)
            loaded = StrategyMetadata.load(saved)
            assert loaded.id == meta.id
            assert loaded.category == meta.category
            assert len(loaded.sources) == len(meta.sources)
            print(f"  ✓ {meta.id}")
        except Exception as e:
            print(f"  ✗ {meta.id}: {e}")
            failed.append(meta.id)

    # cleanup
    import shutil
    shutil.rmtree(test_dir, ignore_errors=True)
    return len(failed) == 0


def main() -> int:
    results = {
        "imports": test_imports(),
        "metadata": test_metadata(),
        "instantiation": test_instantiation(),
        "duplicate_check": test_duplicate_check(),
        "metadata_io": test_metadata_save_load(),
    }
    print("\n" + "=" * 50)
    print("=== 결과 요약 ===")
    for name, ok in results.items():
        icon = "✓" if ok else "✗"
        print(f"  {icon} {name}")
    print("=" * 50)
    all_passed = all(results.values())
    print(f"\n전체: {'PASS' if all_passed else 'FAIL'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
