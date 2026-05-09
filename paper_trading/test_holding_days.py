"""
P3-3a: TradingSimulator.holding_days 파라미터 단위 테스트.

DEC-005 squeeze play shadow 4주 운영을 위한 다일 보유 시뮬레이션 검증.

검증 항목:
1. holding_days 기본값(=1) 시 기존 동작 보존 — TRAILING_ENABLED 유지, 1일 path 사용
2. holding_days >= 2 시 TRAILING_ENABLED 자동 OFF (DEC-005 + ISSUE-014 회귀 방지)
3. holding_days < 1 또는 비-int → ValueError
4. holding_days=5 + 모킹된 일봉 5일 데이터 → close_multiday 결과
   - 진입가 = 첫날 시가 × (1+0.2%)
   - 청산가 = 5번째 날 종가 (슬리피지 미적용)
   - exit_date = 5번째 날 인덱스
   - max_profit/loss_pct = 5일 보유 구간 high/low 기반
5. 데이터 부족(rows<N) → None 반환

실행:
    cd zip1/news-trading-bot
    python -m paper_trading.test_holding_days
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from paper_trading.simulator import TradingSimulator, TradeResult
from paper_trading.selector import StockCandidate


def _make_candidate(code: str = "005930", name: str = "삼성전자") -> StockCandidate:
    """간단한 StockCandidate 생성 (필수 필드만)."""
    try:
        return StockCandidate(code=code, name=name, score=80.0, criteria={})
    except TypeError:
        # 시그니처가 다르면 dataclass introspection 으로 fallback
        from dataclasses import fields
        kwargs = {f.name: ("" if f.type is str else 0) for f in fields(StockCandidate)}
        kwargs["code"] = code
        kwargs["name"] = name
        if "score" in kwargs:
            kwargs["score"] = 80.0
        return StockCandidate(**kwargs)


def _make_ohlcv(rows: int) -> pd.DataFrame:
    """5일치 가짜 OHLCV. 시가 10000, 5일째 종가 11000 (+10%)."""
    dates = pd.date_range("2026-05-11", periods=rows, freq="B")
    data = {
        "시가":  [10000, 10100, 10200, 10300, 10400][:rows],
        "고가":  [10500, 10800, 11200, 11500, 11200][:rows],
        "저가":  [9800,  9900,  10100, 10250, 10800][:rows],
        "종가":  [10100, 10200, 10300, 10400, 11000][:rows],
        "거래량": [1_000_000] * rows,
    }
    return pd.DataFrame(data, index=dates)


def test_default_holding_days_one_preserves_trailing():
    """기본 holding_days=1 시 TRAILING_ENABLED 유지."""
    sim = TradingSimulator()
    assert sim.holding_days == 1, f"기본값은 1이어야 함, got {sim.holding_days}"
    assert sim.TRAILING_ENABLED is True, "1일 path는 트레일링 유지"
    print("  [OK] holding_days 기본값=1, TRAILING_ENABLED 보존")


def test_multiday_disables_trailing():
    """holding_days >= 2 시 TRAILING_ENABLED 자동 OFF."""
    sim = TradingSimulator(holding_days=5)
    assert sim.holding_days == 5
    assert sim.TRAILING_ENABLED is False, "다일 보유 시 트레일링 비활성화 (DEC-005)"
    print("  [OK] holding_days=5, TRAILING_ENABLED 자동 OFF")


def test_invalid_holding_days_raises():
    """holding_days가 0, 음수, 비-int → ValueError."""
    for bad in [0, -1, 1.5, "5", None]:
        try:
            TradingSimulator(holding_days=bad)
        except ValueError:
            continue
        except TypeError:
            # None은 isinstance(None, int)가 False라 ValueError 경로 — 혹시 TypeError나면 그것도 실패로 본다
            raise AssertionError(f"holding_days={bad!r} → ValueError 미발생 (TypeError 발생)")
        raise AssertionError(f"holding_days={bad!r} → ValueError 미발생")
    print("  [OK] holding_days 부적합값 ValueError 발생")


def test_multiday_simulation_5day_hold():
    """holding_days=5 시 5일째 종가 청산 + max profit/loss 계산."""
    sim = TradingSimulator(holding_days=5)
    sim.trade_date = "20260511"
    fake_df = _make_ohlcv(5)

    with patch("paper_trading.simulator.stock") as mock_stock:
        mock_stock.get_market_ohlcv.return_value = fake_df
        candidate = _make_candidate()
        result = sim._simulate_trade_multiday(candidate, investment=1_000_000)

    assert result is not None, "결과 None — 데이터 충분한데 None 반환"
    assert isinstance(result, TradeResult)
    # 진입가: 10000 * 1.002 = 10020
    assert result.entry_price == 10020, f"진입가 기대 10020, got {result.entry_price}"
    # 청산가: 5일째 종가 11000 그대로
    assert result.exit_price == 11000, f"청산가 기대 11000, got {result.exit_price}"
    assert result.exit_type == "close_multiday"
    assert result.exit_date == "20260515", f"exit_date 기대 20260515, got {result.exit_date!r}"
    # max_profit_pct: window_high=11500 (4일째) vs entry 10020 → +14.77%
    assert abs(result.max_profit_pct - 14.77) < 0.05, \
        f"max_profit_pct 기대 ~14.77, got {result.max_profit_pct}"
    # max_loss_pct: window_low=9800 (1일째) vs entry 10020 → -2.20%
    assert abs(result.max_loss_pct - (-2.2)) < 0.05, \
        f"max_loss_pct 기대 ~-2.20, got {result.max_loss_pct}"
    # return_pct: (11000-10020)/10020*100 = 9.78%
    assert abs(result.return_pct - 9.78) < 0.05, \
        f"return_pct 기대 ~9.78, got {result.return_pct}"
    print(f"  [OK] 5일 보유: entry={result.entry_price}, exit={result.exit_price}, "
          f"return={result.return_pct}%, max_p/l={result.max_profit_pct}/{result.max_loss_pct}%")


def test_multiday_insufficient_data_returns_none():
    """rows < holding_days 시 None 반환 (retroactive backfill 신호)."""
    sim = TradingSimulator(holding_days=5)
    sim.trade_date = "20260511"
    fake_df = _make_ohlcv(3)  # 3일치만

    with patch("paper_trading.simulator.stock") as mock_stock:
        mock_stock.get_market_ohlcv.return_value = fake_df
        candidate = _make_candidate()
        result = sim._simulate_trade_multiday(candidate, investment=1_000_000)

    assert result is None, f"데이터 부족 시 None이어야 함, got {result}"
    print("  [OK] 데이터 부족(rows=3 < N=5) → None 반환")


def test_get_daily_summary_includes_holding_days():
    """get_daily_summary가 holding_days와 close_multiday_exits를 포함해야 함."""
    sim = TradingSimulator(holding_days=5)
    sim.trade_date = "20260511"
    summary = sim.get_daily_summary()
    assert summary["holding_days"] == 5
    assert "close_multiday_exits" in summary
    assert summary["close_multiday_exits"] == 0  # 빈 results
    print("  [OK] get_daily_summary에 holding_days, close_multiday_exits 포함")


def main():
    print("=" * 60)
    print("P3-3a: TradingSimulator.holding_days 단위 테스트")
    print("=" * 60)

    tests = [
        test_default_holding_days_one_preserves_trailing,
        test_multiday_disables_trailing,
        test_invalid_holding_days_raises,
        test_multiday_simulation_5day_hold,
        test_multiday_insufficient_data_returns_none,
        test_get_daily_summary_includes_holding_days,
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
