"""
P3-3c: ShadowLogger 단위 테스트.

검증 항목:
1. variant_id 화이트리스트 — 외부 ID 거부
2. append_signal — 신규/중복(멱등)/검증 위반
3. update_positions — overwrite, atomic, 검증
4. append_trade — 신규/중복(position_id)/날짜 순서 위반
5. Read API — list_signals/get_open_positions/list_trades + since 필터
6. 변형별 디렉토리 격리 — kospi_v6 / kosdaq_v5 충돌 없음
7. atomic write — temp 파일 잔존 없음
8. SHADOW_DRY_RUN — import 시 True 강제

격리: tempfile.TemporaryDirectory 로 매 테스트마다 신규 dir.
실제 data/paper_trading_shadow/ 는 건드리지 않음.

실행:
    cd zip1/news-trading-bot
    python -m paper_trading.test_shadow_logger
"""

import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from paper_trading.shadow import (
    ShadowLogger, ShadowLogError, VARIANT_WHITELIST, SHADOW_DRY_RUN
)


# ============================================================
# 픽스처 (간단한 sample dict 생성)
# ============================================================

def _sig(variant="squeeze_play_kospi_v6", code="005930",
         signal_date="20260510", entry="20260511", exit_="20260516"):
    return {
        "variant_id": variant,
        "code": code,
        "name": "삼성전자",
        "signal_date": signal_date,
        "expected_entry_date": entry,
        "exit_planned_date": exit_,
        "rank": 1,
        "score": 78.5,
        "signal_close_price": 78900,
        "recommended_holding_days": 5,
        "score_detail": {
            "percent_b": 0.12,
            "spread_pct": 4.5,
            "ma200_rising": True,
            "is_positive_candle": True,
        },
        "metadata": {"universe_size": 53},
    }


def _pos(variant="squeeze_play_kospi_v6", code="005930",
         entry="20260511", exit_="20260516", fill="filled"):
    return {
        "position_id": f"pos_{variant}_{entry}_{code}",
        "variant_id": variant,
        "code": code,
        "name": "삼성전자",
        "signal_date": "20260510",
        "entry_date": entry,
        "exit_planned_date": exit_,
        "remaining_days": 4,
        "signal_close_price": 78900,
        "expected_open_price": 79058,
        "actual_open_price": 79100,
        "open_slippage_pct": 0.05,
        "fill_status": fill,
        "intraday_high": 79500,
        "intraday_low": 78300,
        "current_close": 79200,
        "unrealized_return_pct": 0.13,
        "kill_switch_state": "ok",
    }


def _trade(variant="squeeze_play_kospi_v6", code="005930",
           position_id=None, signal_date="20260510",
           entry="20260511", exit_="20260516"):
    return {
        "position_id": position_id or f"pos_{variant}_{entry}_{code}",
        "variant_id": variant,
        "code": code,
        "name": "삼성전자",
        "signal_date": signal_date,
        "entry_date": entry,
        "exit_date": exit_,
        "holding_days_planned": 5,
        "holding_days_actual": 5,
        "signal_close_price": 78900,
        "entry_open_price": 79100,
        "exit_close_price": 81300,
        "expected_entry_price": 79058,
        "expected_exit_price": 81300,
        "open_slippage_pct": 0.05,
        "close_slippage_pct": 0.0,
        "return_pct": 2.78,
        "expected_return_pct": 2.83,
        "return_diff_pct": -0.05,
        "intraday_high": 81500,
        "intraday_low": 78800,
        "max_profit_pct": 3.04,
        "max_loss_pct": -0.38,
        "exit_type": "close_multiday",
    }


# ============================================================
# 테스트
# ============================================================

def test_shadow_dry_run_is_true():
    """패키지 import 시 SHADOW_DRY_RUN 은 True 강제."""
    assert SHADOW_DRY_RUN is True, "SHADOW_DRY_RUN must be True (운영 가드)"
    print("  [OK] SHADOW_DRY_RUN=True 강제됨")


def test_variant_whitelist():
    """화이트리스트 외 variant_id 는 instantiation 에서 거부."""
    assert "squeeze_play_kospi_v6" in VARIANT_WHITELIST
    assert "squeeze_play_kosdaq_v5" in VARIANT_WHITELIST
    with tempfile.TemporaryDirectory() as td:
        try:
            ShadowLogger("invalid_variant", log_root=Path(td))
        except ShadowLogError:
            print("  [OK] 화이트리스트 외 variant_id 거부")
            return
        raise AssertionError("invalid variant_id 가 통과됨")


def test_append_signal_new_and_idempotent():
    """신규 signal append → True / 동일 (date,code) 재시도 → False."""
    with tempfile.TemporaryDirectory() as td:
        lg = ShadowLogger("squeeze_play_kospi_v6", log_root=Path(td))
        sig = _sig()
        assert lg.append_signal(sig) is True, "첫 append 는 True"
        assert lg.append_signal(sig) is False, "동일 (date,code) 재시도는 False"

        # 같은 날짜, 다른 code → 새로 append
        sig2 = _sig(code="000660")
        sig2["name"] = "SK하이닉스"
        assert lg.append_signal(sig2) is True

        records = lg.list_signals()
        assert len(records) == 2, f"기대 2건, got {len(records)}"
        codes = {r["code"] for r in records}
        assert codes == {"005930", "000660"}
        print(f"  [OK] signal append 멱등: 2건 기록 (중복 1회 무시)")


def test_append_signal_validation_failures():
    """필수 필드 누락 / 날짜 순서 오류 / variant_id 불일치 → ShadowLogError."""
    with tempfile.TemporaryDirectory() as td:
        lg = ShadowLogger("squeeze_play_kospi_v6", log_root=Path(td))

        # 필수 필드 누락
        bad = _sig()
        del bad["signal_close_price"]
        try:
            lg.append_signal(bad)
            raise AssertionError("필수 필드 누락이 통과됨")
        except ShadowLogError:
            pass

        # 날짜 순서 오류 (entry < signal)
        bad = _sig(signal_date="20260520", entry="20260511", exit_="20260516")
        try:
            lg.append_signal(bad)
            raise AssertionError("날짜 역순이 통과됨")
        except ShadowLogError:
            pass

        # variant_id 불일치 (logger=v6, signal=v5)
        bad = _sig(variant="squeeze_play_kosdaq_v5")
        try:
            lg.append_signal(bad)
            raise AssertionError("variant_id 불일치가 통과됨")
        except ShadowLogError:
            pass

        # 음수 가격
        bad = _sig()
        bad["signal_close_price"] = -100
        try:
            lg.append_signal(bad)
            raise AssertionError("음수 가격이 통과됨")
        except ShadowLogError:
            pass

        print("  [OK] signal 검증: 필드 누락/날짜 역순/variant 불일치/음수 모두 거부")


def test_update_positions_overwrite():
    """update_positions 는 항상 덮어쓰기 (멱등)."""
    with tempfile.TemporaryDirectory() as td:
        lg = ShadowLogger("squeeze_play_kospi_v6", log_root=Path(td))

        # 2 포지션
        n = lg.update_positions([_pos(code="005930"), _pos(code="000660")])
        assert n == 2

        positions = lg.get_open_positions()
        assert len(positions) == 2

        # 1개로 덮어쓰기 → 결과 1개
        n = lg.update_positions([_pos(code="005930")])
        assert n == 1
        positions = lg.get_open_positions()
        assert len(positions) == 1, f"덮어쓰기 후 1개여야 함, got {len(positions)}"

        # 0개로 비우기
        n = lg.update_positions([])
        assert n == 0
        assert lg.get_open_positions() == []

        print("  [OK] positions overwrite: 2→1→0 순으로 갱신")


def test_update_positions_validation():
    """fill_status 화이트리스트 외, variant 불일치, 필드 누락 거부."""
    with tempfile.TemporaryDirectory() as td:
        lg = ShadowLogger("squeeze_play_kospi_v6", log_root=Path(td))

        bad = _pos(fill="weird_status")
        try:
            lg.update_positions([bad])
            raise AssertionError("fill_status 화이트리스트 외 통과")
        except ShadowLogError:
            pass

        bad = _pos(variant="squeeze_play_kosdaq_v5")
        try:
            lg.update_positions([bad])
            raise AssertionError("variant 불일치 통과")
        except ShadowLogError:
            pass

        print("  [OK] positions 검증: fill_status / variant 불일치 거부")


def test_append_trade_idempotent_by_position_id():
    """동일 position_id 두 번 append → 두 번째는 False."""
    with tempfile.TemporaryDirectory() as td:
        lg = ShadowLogger("squeeze_play_kospi_v6", log_root=Path(td))
        tr = _trade()
        assert lg.append_trade(tr) is True
        assert lg.append_trade(tr) is False, "동일 position_id 재시도는 False"

        # 다른 position_id → 추가
        tr2 = _trade(code="000660", position_id="pos_squeeze_play_kospi_v6_20260511_000660")
        assert lg.append_trade(tr2) is True

        trades = lg.list_trades()
        assert len(trades) == 2
        print(f"  [OK] trade append 멱등 (position_id 기준): 2건 기록")


def test_append_trade_date_order():
    """trade 날짜 순서: signal < entry <= exit 강제."""
    with tempfile.TemporaryDirectory() as td:
        lg = ShadowLogger("squeeze_play_kospi_v6", log_root=Path(td))

        # exit < entry
        bad = _trade(signal_date="20260510", entry="20260516", exit_="20260511")
        try:
            lg.append_trade(bad)
            raise AssertionError("exit < entry 통과")
        except ShadowLogError:
            pass

        # signal == entry (signal < entry 강제)
        bad = _trade(signal_date="20260511", entry="20260511", exit_="20260516")
        try:
            lg.append_trade(bad)
            raise AssertionError("signal == entry 통과")
        except ShadowLogError:
            pass

        print("  [OK] trade 날짜 순서: signal<entry<=exit 강제")


def test_read_api_since_filter():
    """list_signals/list_trades 의 since_date 필터."""
    with tempfile.TemporaryDirectory() as td:
        lg = ShadowLogger("squeeze_play_kospi_v6", log_root=Path(td))
        # 3개 시그널 (다른 날짜)
        lg.append_signal(_sig(signal_date="20260510", entry="20260511", exit_="20260516"))
        lg.append_signal(_sig(code="000660", signal_date="20260512",
                              entry="20260513", exit_="20260518"))
        lg.append_signal(_sig(code="035420", signal_date="20260514",
                              entry="20260515", exit_="20260520"))

        all_sigs = lg.list_signals()
        assert len(all_sigs) == 3

        recent = lg.list_signals(since_date="20260513")
        # signal_date >= "20260513" → 20260514 만 매칭
        assert len(recent) == 1, f"since=20260513 → 1건 기대, got {len(recent)}"
        assert recent[0]["code"] == "035420"

        print(f"  [OK] read API since 필터: 3건 중 since=20260513 → 1건")


def test_variant_dir_isolation():
    """kospi_v6 / kosdaq_v5 는 별도 디렉토리, 교차 오염 없음."""
    with tempfile.TemporaryDirectory() as td:
        v6 = ShadowLogger("squeeze_play_kospi_v6", log_root=Path(td))
        v5 = ShadowLogger("squeeze_play_kosdaq_v5", log_root=Path(td))

        v6.append_signal(_sig())
        v5.append_signal(_sig(variant="squeeze_play_kosdaq_v5", code="247540"))

        assert len(v6.list_signals()) == 1
        assert len(v5.list_signals()) == 1
        assert v6.list_signals()[0]["code"] == "005930"
        assert v5.list_signals()[0]["code"] == "247540"

        # 디렉토리 분리 확인
        assert v6.signals_path.parent.name == "squeeze_play_kospi_v6"
        assert v5.signals_path.parent.name == "squeeze_play_kosdaq_v5"
        assert v6.signals_path != v5.signals_path

        print("  [OK] 변형별 디렉토리 격리: 교차 오염 0")


def test_atomic_write_no_temp_leftover():
    """update_positions 후 .tmp.* 임시 파일 잔존 없음."""
    with tempfile.TemporaryDirectory() as td:
        lg = ShadowLogger("squeeze_play_kospi_v6", log_root=Path(td))
        for _ in range(3):
            lg.update_positions([_pos()])

        leftovers = [p for p in lg.variant_dir.iterdir() if ".tmp." in p.name]
        assert leftovers == [], f"임시 파일 잔존: {leftovers}"

        # 정상 파일은 존재
        assert lg.positions_path.exists()
        # JSON 파싱 성공
        with open(lg.positions_path, "r") as f:
            data = json.load(f)
        assert data["schema_version"] == 1
        assert data["variant_id"] == "squeeze_play_kospi_v6"
        assert len(data["open_positions"]) == 1

        print("  [OK] atomic write: temp 파일 0, JSON 정상")


def test_intraday_snapshot_minimal():
    """append_intraday_snapshot 은 position_id 만 강제, 나머지는 free-form."""
    with tempfile.TemporaryDirectory() as td:
        lg = ShadowLogger("squeeze_play_kospi_v6", log_root=Path(td))

        snap = {
            "position_id": "pos_squeeze_play_kospi_v6_20260511_005930",
            "current_price": 79400,
            "high_so_far": 79600,
        }
        lg.append_intraday_snapshot(snap)
        assert lg.intraday_path.exists()

        # position_id 누락 시 거부
        try:
            lg.append_intraday_snapshot({"current_price": 79400})
            raise AssertionError("position_id 누락이 통과됨")
        except ShadowLogError:
            pass

        print("  [OK] intraday snapshot: 1건 기록, position_id 누락 거부")


def main():
    print("=" * 60)
    print("P3-3c: ShadowLogger 단위 테스트")
    print("=" * 60)

    tests = [
        test_shadow_dry_run_is_true,
        test_variant_whitelist,
        test_append_signal_new_and_idempotent,
        test_append_signal_validation_failures,
        test_update_positions_overwrite,
        test_update_positions_validation,
        test_append_trade_idempotent_by_position_id,
        test_append_trade_date_order,
        test_read_api_since_filter,
        test_variant_dir_isolation,
        test_atomic_write_no_temp_leftover,
        test_intraday_snapshot_minimal,
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
