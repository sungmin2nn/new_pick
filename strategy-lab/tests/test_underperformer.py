"""
Phase 7.A.1 — 부진 전략 자동 식별 테스트
========================================
UnderperformerDetector의 3축 (수익률/MDD/일관성) 판정과
멀티-기간 집계를 케이스별로 검증한다.

실행:
    python tests/test_underperformer.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lab.underperformer import (  # noqa: E402
    Severity,
    UnderperformerCriteria,
    UnderperformerDetector,
    UnderperformerFlag,
)


def _row(**overrides):
    base = dict(
        strategy_id="test_strategy",
        strategy_name="테스트 전략",
        period="1w",
        start_date="20260329",
        end_date="20260410",
        total_return_pct=10.0,
        sharpe_ratio=2.0,
        win_rate=0.60,
        max_drawdown_pct=-5.0,
        num_trades=20,
        profit_factor=2.0,
        trading_days=9,
    )
    base.update(overrides)
    return base


def test_healthy_strategy_not_flagged():
    d = UnderperformerDetector()
    r = d.detect(_row())
    assert r.is_underperformer is False, f"건강한 전략이 잘못 부진으로 판정됨: {r.summary()}"
    assert r.severity == Severity.NONE.value
    assert r.flags == []
    assert r.weakness_score == 0.0


def test_low_return_mild():
    d = UnderperformerDetector()
    r = d.detect(_row(total_return_pct=1.0))  # 3.0 미만
    assert r.is_underperformer is True
    assert UnderperformerFlag.LOW_RETURN.value in r.flags
    assert r.severity == Severity.MILD.value
    assert r.weakness_score > 0


def test_deep_drawdown_mild():
    d = UnderperformerDetector()
    r = d.detect(_row(max_drawdown_pct=-18.0))  # -10 보다 더 나쁨
    assert r.is_underperformer is True
    assert UnderperformerFlag.DEEP_DRAWDOWN.value in r.flags
    assert r.severity == Severity.MILD.value


def test_consistency_only_mild():
    d = UnderperformerDetector()
    # 수익률/MDD는 OK, 일관성만 미달 (승률 + PF + Sharpe 모두 낮음)
    r = d.detect(_row(win_rate=0.30, profit_factor=1.0, sharpe_ratio=0.2))
    assert r.is_underperformer is True
    # 3개 일관성 플래그 all set
    assert UnderperformerFlag.LOW_WIN_RATE.value in r.flags
    assert UnderperformerFlag.LOW_PROFIT_FACTOR.value in r.flags
    assert UnderperformerFlag.LOW_SHARPE.value in r.flags
    # 하지만 3축 중 1축 (일관성 축)만 미달 → MILD
    assert r.severity == Severity.MILD.value


def test_two_axes_moderate():
    d = UnderperformerDetector()
    r = d.detect(
        _row(total_return_pct=1.0, max_drawdown_pct=-15.0)  # 2축 미달
    )
    assert r.severity == Severity.MODERATE.value


def test_three_axes_severe():
    d = UnderperformerDetector()
    r = d.detect(
        _row(
            total_return_pct=-5.0,       # 수익률 미달
            max_drawdown_pct=-20.0,      # 낙폭 미달
            win_rate=0.25,               # 일관성 미달
            profit_factor=0.8,
            sharpe_ratio=-0.5,
        )
    )
    assert r.severity == Severity.SEVERE.value
    assert r.weakness_score > 50  # 심각 → 스코어 높음


def test_inactive_no_trades():
    d = UnderperformerDetector()
    r = d.detect(_row(num_trades=0, total_return_pct=0.0, win_rate=0.0))
    assert r.is_underperformer is True
    assert r.severity == Severity.INACTIVE.value
    assert r.flags == [UnderperformerFlag.INACTIVE.value]


def test_sharpe_clipped_at_sanity():
    # Sharpe 50은 과대평가 → 상한 15로 clip → low_sharpe(0.5) 초과
    d = UnderperformerDetector()
    r = d.detect(_row(sharpe_ratio=50.0))
    assert UnderperformerFlag.LOW_SHARPE.value not in r.flags


def test_custom_criteria():
    # 엄격한 기준
    c = UnderperformerCriteria(low_return_pct=10.0, deep_drawdown_pct=-3.0)
    d = UnderperformerDetector(c)
    r = d.detect(_row(total_return_pct=8.0, max_drawdown_pct=-5.0))
    assert r.is_underperformer is True
    assert UnderperformerFlag.LOW_RETURN.value in r.flags
    assert UnderperformerFlag.DEEP_DRAWDOWN.value in r.flags


def test_multi_period_fail_aggregation():
    d = UnderperformerDetector()
    reports = d.detect_batch(
        [
            _row(strategy_id="bad", period="1w", total_return_pct=-2.0),
            _row(strategy_id="bad", period="1m", total_return_pct=-5.0),
            _row(strategy_id="bad", period="3m", total_return_pct=1.0),
            _row(strategy_id="good", period="1w"),
            _row(strategy_id="good", period="1m"),
        ]
    )
    multi = d.aggregate_multi_period(reports)
    by_id = {m.strategy_id: m for m in multi}

    assert by_id["bad"].multi_period_fail is True
    assert by_id["bad"].underperform_periods == 3
    assert by_id["bad"].total_periods == 3

    assert by_id["good"].multi_period_fail is False
    assert by_id["good"].underperform_periods == 0


def test_multi_period_needs_minimum_periods():
    # 기간이 1개뿐이면 multi_period_fail은 False여야 함
    c = UnderperformerCriteria(multi_period_min_periods=2)
    d = UnderperformerDetector(c)
    reports = d.detect_batch([_row(strategy_id="single", total_return_pct=-10.0)])
    multi = d.aggregate_multi_period(reports)
    assert multi[0].multi_period_fail is False
    assert multi[0].total_periods == 1


def test_weakness_score_monotonic():
    # 수익률이 낮을수록 약점 점수가 (단조)증가해야 함
    d = UnderperformerDetector()
    scores = [
        d.detect(_row(total_return_pct=v)).weakness_score
        for v in [10.0, 5.0, 3.0, 0.0, -5.0, -15.0]
    ]
    for prev, nxt in zip(scores, scores[1:]):
        assert nxt >= prev, f"약점 점수 단조성 위반: {scores}"


def test_report_serialization_round_trip():
    import json

    d = UnderperformerDetector()
    r = d.detect(_row(total_return_pct=-2.0, max_drawdown_pct=-20.0))
    js = json.dumps(r.to_dict(), ensure_ascii=False)
    back = json.loads(js)
    assert back["strategy_id"] == r.strategy_id
    assert back["is_underperformer"] is True
    assert back["severity"] == r.severity


TESTS = [
    test_healthy_strategy_not_flagged,
    test_low_return_mild,
    test_deep_drawdown_mild,
    test_consistency_only_mild,
    test_two_axes_moderate,
    test_three_axes_severe,
    test_inactive_no_trades,
    test_sharpe_clipped_at_sanity,
    test_custom_criteria,
    test_multi_period_fail_aggregation,
    test_multi_period_needs_minimum_periods,
    test_weakness_score_monotonic,
    test_report_serialization_round_trip,
]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")

    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
