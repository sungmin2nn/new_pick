# Squeeze Play Shadow Logs — Schema

> P3-3c (DEC-005, plan `.claude/context/plans/squeeze-play-shadow-4w.md`)
>
> 4주 paper trading shadow 운영의 일일 데이터 기록 스키마.
> 모든 timestamp 는 **KST ISO 8601** (`+09:00`).

---

## 0. 위치 / 권한

- 디렉토리: `zip1/news-trading-bot/data/paper_trading_shadow/` (격리)
- DEFAULT 경로 환경변수: `SHADOW_LOG_DIR` (없으면 default 사용)
- 파일 권한: 소유자 r/w (실주문 모듈은 import 금지 — `SHADOW_DRY_RUN = True` 강제)
- 변형(variant) 별 하위 디렉토리 분리 — 충돌·교차오염 방지:
  - `data/paper_trading_shadow/squeeze_play_kospi_v6/`
  - `data/paper_trading_shadow/squeeze_play_kosdaq_v5/`

---

## 1. `shadow_signals.jsonl` (append-only)

매일 16:00 (KRX 종가 확정 후) 스캔에서 발견된 시그널 1건 = 1줄.
멱등 키: `(signal_date, variant_id, code)`. 중복 append 시 무시.

```jsonc
{
  "schema_version": 1,
  "timestamp": "2026-05-11T16:30:00+09:00",   // 시그널 생성 시각
  "signal_date": "20260510",                   // T-1 (종가 기준일, YYYYMMDD)
  "expected_entry_date": "20260511",           // T (다음 거래일)
  "variant_id": "squeeze_play_kospi_v6",       // squeeze_play_{kospi_v6,kosdaq_v5}
  "code": "005930",
  "name": "삼성전자",
  "rank": 1,                                    // 변형 내 순위 (1=최상위)
  "score": 78.5,                                // 0~80 (squeeze_play_base.score_candidate)
  "score_detail": {
    "percent_b": 0.12,
    "spread_pct": 4.5,
    "ma200_rising": true,
    "is_positive_candle": true
  },
  "signal_close_price": 78900,                 // T-1 종가 (원 단위)
  "recommended_holding_days": 5,
  "exit_planned_date": "20260516",             // T+4 (5거래일째 종가 청산)
  "metadata": {
    "universe_size": 53,
    "scan_duration_sec": 12.4,
    "backtest_baseline_win_rate": 65.4         // 검증 기준점 (DEC-005)
  }
}
```

**필드 상세**

| 필드 | 타입 | 필수 | 비고 |
|------|------|------|------|
| schema_version | int | ✓ | 현 1. 마이그레이션 시 증분 |
| signal_date | str | ✓ | YYYYMMDD, 종가 기준일 (T-1) |
| variant_id | str | ✓ | whitelist: `squeeze_play_kospi_v6` / `squeeze_play_kosdaq_v5` |
| code | str | ✓ | 6자리 종목코드 |
| score | float | ✓ | 0~80 |
| signal_close_price | int | ✓ | 양수 |
| score_detail | object | ✓ | 변형 필터 통과 근거 |
| metadata | object | - | 진단용 free-form |

---

## 2. `shadow_positions.json` (overwrite, 현재 보유 상태)

매일 장 마감 후 갱신. **append 가 아니라 전체 덮어쓰기** (현재 상태 스냅샷).

```jsonc
{
  "schema_version": 1,
  "as_of": "2026-05-11T15:30:00+09:00",
  "open_positions": [
    {
      "position_id": "pos_squeeze_play_kospi_v6_20260511_005930",
      "variant_id": "squeeze_play_kospi_v6",
      "code": "005930",
      "name": "삼성전자",
      "signal_date": "20260510",
      "entry_date": "20260511",
      "exit_planned_date": "20260516",
      "remaining_days": 4,                     // 청산까지 남은 거래일
      "signal_close_price": 78900,             // T-1 종가 (시그널 시점)
      "expected_open_price": 79058,            // signal × (1+0.2% slip), 백테스트 가정
      "actual_open_price": 79100,              // T 시초 실측
      "open_slippage_pct": 0.05,               // (actual - expected) / expected × 100
      "fill_status": "filled",                  // filled | partial | rejected | skipped
      "intraday_high": 79500,                  // 보유 시작 후 누적 고가
      "intraday_low": 78300,                   // 보유 시작 후 누적 저가
      "current_close": 79200,                  // 가장 최근 종가
      "unrealized_return_pct": 0.13,           // (current - actual_open) / actual_open × 100
      "kill_switch_state": "ok"                 // ok | warn-loss-10 | halted
    }
  ]
}
```

**fill_status 값**

| 값 | 의미 |
|----|------|
| `filled` | 시초 매수 가정 체결 OK |
| `partial` | 시초 거래 미체결 추정 (호가 spread 큼 등) — 향후 확장 |
| `rejected` | 거래정지 / 상장폐지 / 데이터 결측 |
| `skipped` | universe 정책상 진입 불가 (예: kill switch 발동) |

**kill_switch_state**

| 값 | 의미 |
|----|------|
| `ok` | 정상 |
| `warn-loss-{N}` | 누적 N% 손실 도달 (예: warn-loss-10) |
| `halted` | 일시 정지 (사용자 결정) |

---

## 3. `shadow_intraday.jsonl` (append-only, 선택적)

장중 분/시간봉 스냅샷. P3-3c 단계에서는 **스키마만 정의**, writer 는 노옵.
실제 기록은 P3-3d (tick runner) 또는 P3-3e (주간 리포트 단계)에서.

```jsonc
{
  "schema_version": 1,
  "timestamp": "2026-05-12T13:30:00+09:00",
  "position_id": "pos_squeeze_play_kospi_v6_20260511_005930",
  "current_price": 79400,
  "high_so_far": 79600,
  "low_so_far": 78300,
  "minute_bar": {
    "open": 79350, "high": 79450, "low": 79320, "close": 79400, "volume": 12345
  }
}
```

---

## 4. `shadow_trades.jsonl` (append-only, T+4 종가 청산 시)

청산 직후 1줄 추가. ML/리포트 친화 raw record. **백테스트 vs 실측 diff** 핵심.
멱등 키: `position_id`.

```jsonc
{
  "schema_version": 1,
  "timestamp": "2026-05-16T15:30:00+09:00",
  "position_id": "pos_squeeze_play_kospi_v6_20260511_005930",
  "variant_id": "squeeze_play_kospi_v6",
  "code": "005930",
  "name": "삼성전자",

  "signal_date": "20260510",
  "entry_date": "20260511",
  "exit_date": "20260516",
  "holding_days_planned": 5,
  "holding_days_actual": 5,                    // 휴장으로 변동 가능

  "signal_close_price": 78900,
  "entry_open_price": 79100,                   // 실측 시초가
  "exit_close_price": 81300,                   // 실측 청산가 (5거래일째 종가)

  "expected_entry_price": 79058,               // 백테스트 가정 (시초 + 0.2% slip)
  "expected_exit_price": 81300,                // 백테스트 가정 (종가 그대로)
  "open_slippage_pct": 0.05,                   // 매수 슬리피지 (백테스트 대비)
  "close_slippage_pct": 0.0,                   // 매도 슬리피지

  "return_pct": 2.78,                           // 실측 수익률
  "expected_return_pct": 2.83,                 // 백테스트 가정
  "return_diff_pct": -0.05,                    // 실측 - 가정 (음수 = 실측이 백테스트보다 나쁨)

  "intraday_high": 81500,                      // 보유 구간 누적 고가
  "intraday_low": 78800,                       // 보유 구간 누적 저가
  "max_profit_pct": 3.04,                      // 보유 구간 최대 수익률
  "max_loss_pct": -0.38,                       // 보유 구간 최대 손실률

  "exit_type": "close_multiday"                // 시뮬레이터 TradeResult 와 일치
}
```

**검증 가설(P3-3 §1) 매핑**

- H1 (진입 가능률): `fill_status="filled"` 비율
- H2 (슬리피지): `open_slippage_pct`, `close_slippage_pct` 평균
- H3 (누적 수익): Σ `return_pct` vs 백테스트 ±30%
- H4 (KOSDAQ 일별 -10% 위반): `return_pct < -10` 일별 카운트

---

## 5. 검증 규칙 (logger 자체 검증)

`ShadowLogger` 의 모든 append/update 는 다음 규칙 강제:

1. `variant_id` 는 whitelist (`squeeze_play_kospi_v6`, `squeeze_play_kosdaq_v5`) 외 거부
2. 가격(원 단위) 필드는 모두 양의 정수
3. `score_detail.percent_b` 는 `0 ≤ x ≤ 1.5` (이론상 음수/1초과 가능하지만 워닝)
4. `signal_date < expected_entry_date < exit_planned_date` 순서
5. JSON 직렬화 실패 → 즉시 raise (silent corruption 방지)
6. 디렉토리는 atomic write (tempfile + rename) — 갱신 중 크래시 방어
7. `SHADOW_DRY_RUN = True` 가 모듈 import 시 assert. 운영 코드에서 변경 금지.

---

## 6. 멱등성

- `append_signal(...)`: `(signal_date, variant_id, code)` 가 이미 있으면 silent ignore
- `append_trade(...)`: `position_id` 가 이미 있으면 silent ignore (중복 청산 방지)
- `update_positions(...)`: 항상 덮어쓰기 (멱등 보장)
- 같은 날짜 재실행 시 안전 — tick runner (P3-3d) 가 매일 한 번 호출

---

## 7. 마이그레이션 정책

- `schema_version` 증분 시 reader 가 분기 처리
- 1 → 2 변경: 기존 .jsonl 보존, 새 파일은 v2 로 생성, reader 는 라인별 dispatch
- 4주 운영 중 schema 변경 안 함 (P3-3 종료 후 재설계)
