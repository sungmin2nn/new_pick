# BNF-Style Trading Simulator

BNF 방식의 트레이딩 시뮬레이터 - 분할 매수/매도 및 트레일링 스탑 로직 구현

## 주요 특징

### 1. 트레일링 스탑 (Trailing Stop Logic)
- **초기 손절**: -3% (진입가 기준)
- **본전 이동**: 수익 3% 이상 시 손절선을 0% (본전)으로 이동
- **트레일링 시작**: 수익 5% 이상 시 고점 대비 -2% 트레일링
- **강화 트레일링**: 수익 10% 이상 시 고점 대비 -3% 트레일링

### 2. 분할 매수 (Split Entry)
분봉 데이터를 분석하여 3회에 걸쳐 진입:

- **1차 진입 (30%)**: 하락 후 첫 반등 신호 (첫 양봉 확인)
- **2차 진입 (40%)**: 1차 진입 후 +1% 이상 상승 확인
- **3차 진입 (30%)**: 2차 진입 후 고점에서 -1% 풀백 시 진입

### 3. 분할 매도 (Split Exit)
3회에 걸쳐 단계적 청산:

- **1차 청산 (30%)**: +5% 목표 도달 시
- **2차 청산 (40%)**: +10% 목표 도달 또는 트레일링 스탑 히트
- **3차 청산 (30%)**: 트레일링 스탑 히트 또는 15:20 장 마감 전 강제 청산

## 사용법

### 기본 사용

```python
from paper_trading.bnf.simulator import BNFSimulator
from intraday_collector import IntradayCollector

# 시뮬레이터 초기화
simulator = BNFSimulator(capital=1_000_000)  # 초기 자본 100만원

# 분봉 데이터 수집
collector = IntradayCollector()
minute_data = collector.get_minute_data(code="095340", date_str="20260330")

# 시뮬레이션 실행
result = simulator.simulate_trade(
    code="095340",
    name="ISC",
    date_str="20260330",
    minute_data=minute_data,
    entry_amount=1_000_000
)

# 결과 출력
if result:
    simulator.print_detailed_result(result)
```

### 트레일링 스탑 계산

```python
simulator = BNFSimulator()

# 트레일링 스탑 가격 계산
stop_price = simulator.calculate_trailing_stop(
    entry_price=100000,      # 진입가
    current_high=115000,     # 현재까지 최고가
    profit_pct=15.0          # 현재 수익률
)

print(f"트레일링 스탑: {stop_price:,}원")
# 출력: 트레일링 스탑: 111,550원 (고점 115,000원 대비 -3%)
```

### 진입점 탐색

```python
# 분할 매수 진입점 탐색
entries = simulator.find_entry_points(
    minute_data=minute_data,
    entry_amount=1_000_000
)

for entry in entries:
    print(f"{entry.entry_num}차: {entry.time} | "
          f"{entry.price:,}원 x {entry.quantity}주 | "
          f"{entry.reason}")
```

### 청산점 탐색

```python
# 분할 매도 청산점 탐색
exits = simulator.find_exit_points(
    entries=entries,
    minute_data=minute_data
)

for exit_point in exits:
    print(f"{exit_point.exit_num}차: {exit_point.time} | "
          f"{exit_point.price:,}원 | "
          f"{exit_point.profit_pct:+.2f}% | "
          f"{exit_point.reason}")
```

## 결과 데이터 구조

### BNFTradeResult

```python
@dataclass
class BNFTradeResult:
    code: str                           # 종목 코드
    name: str                           # 종목 이름
    date: str                           # 거래일

    # 진입 정보
    entries: List[EntryPoint]           # 진입 내역
    total_entry_amount: int             # 총 투자금
    total_quantity: int                 # 총 수량
    avg_entry_price: float              # 평균 진입가

    # 청산 정보
    exits: List[ExitPoint]              # 청산 내역
    total_exit_amount: int              # 총 회수금

    # 손익 정보
    total_profit_pct: float             # 총 수익률
    total_profit_amount: int            # 총 손익

    # 장중 최고/최저
    max_profit_pct: float               # 최대 수익률
    max_loss_pct: float                 # 최대 손실률

    # 트레일링 스탑 추적
    trailing_stop_history: List[Dict]   # 트레일링 스탑 히스토리
```

### EntryPoint

```python
@dataclass
class EntryPoint:
    entry_num: int          # 1차, 2차, 3차
    time: str               # 체결 시간
    price: int              # 체결 가격
    weight: float           # 비중 (0.3, 0.4, 0.3)
    amount: int             # 투자 금액
    quantity: int           # 매수 수량
    reason: str             # 진입 사유
```

### ExitPoint

```python
@dataclass
class ExitPoint:
    exit_num: int           # 1차, 2차, 3차
    time: str               # 체결 시간
    price: int              # 체결 가격
    weight: float           # 청산 비중
    quantity: int           # 청산 수량
    profit_pct: float       # 개별 수익률
    profit_amount: int      # 개별 손익
    reason: str             # 청산 사유
```

## 테스트

### 테스트 실행

```bash
# 종합 테스트 (트레일링 스탑 로직 + 전체 시뮬레이션)
python3 -m paper_trading.bnf.test_simulator

# 직접 실행 (샘플 데이터로 테스트)
python3 -m paper_trading.bnf.simulator
```

### 테스트 결과 예시

```
[트레일링 스탑 로직 테스트]
======================================================================

진입가: 100,000원

현재가        수익률        손절가        설명
----------------------------------------------------------------------
  100,000원     0.0%    97,000원 (-3.0%) 초기 진입 (0%)
  102,000원     2.0%    97,000원 (-3.0%) 소폭 상승 (2%)
  103,000원     3.0%   100,000원 (+0.0%) 본전 이동 시점 (3%)
  105,000원     5.0%   102,900원 (+2.9%) 트레일링 시작 (5%)
  108,000원     8.0%   105,840원 (+5.8%) 트레일링 중 (8%)
  110,000원    10.0%   106,700원 (+6.7%) -3% 트레일링 시작 (10%)
  115,000원    15.0%   111,550원 (+11.6%) 고수익 (15%)
======================================================================

[진입 내역]
  1차: 09:10 | 226,987원 x 1주 = 300,000원 (30%) | 첫 반등 신호 (양봉 전환)
  2차: 09:12 | 229,314원 x 1주 = 400,000원 (40%) | 상승 확인 (+1.03%)
  3차: 10:15 | 299,845원 x 1주 = 300,000원 (30%) | 풀백 진입 (-3.99% from high)
  → 평균 진입가: 252,048.67원 (총 3주)

[청산 내역]
  1차: 10:15 | 264,651원 x 0주 = +0원 (+5.00%) | +5.0% 목표 도달
  2차: 10:16 | 277,253원 x 1주 = +25,204원 (+10.00%) | +10.0% 목표 도달
  3차: 10:23 | 291,808원 x 2주 = +79,518원 (+15.77%) | 트레일링 스탑 (+15.77%)

[최종 손익]
  총 투자금: 756,146원
  총 회수금: 860,869원
  순손익: +104,722원
  수익률: +13.85%
  장중 최대수익: +57.79%
  장중 최대손실: 0.00%
```

## 파라미터 커스터마이징

시뮬레이터의 매매 파라미터는 클래스 변수로 정의되어 있어 쉽게 수정 가능:

```python
simulator = BNFSimulator()

# 트레일링 스탑 파라미터 조정
simulator.INITIAL_STOP = -2.5          # 초기 손절 -2.5%
simulator.TRAIL_PERCENT_1 = 1.5        # 5~10%: 고점 대비 -1.5%
simulator.TRAIL_PERCENT_2 = 2.5        # 10% 이상: 고점 대비 -2.5%

# 진입/청산 비중 조정
simulator.ENTRY_WEIGHTS = [0.4, 0.4, 0.2]  # 40%, 40%, 20%
simulator.EXIT_WEIGHTS = [0.2, 0.5, 0.3]   # 20%, 50%, 30%

# 청산 목표 조정
simulator.EXIT_TARGETS = [3.0, 7.0, None]  # 1차 +3%, 2차 +7%
```

## 데이터 포맷

### 분봉 데이터 (minute_data)

```python
[
    {
        'time': '09:00:00',      # 시간 (HH:MM:SS)
        'open': 240000,          # 시가
        'high': 242000,          # 고가
        'low': 239000,           # 저가
        'close': 241000,         # 종가
        'volume': 5000           # 거래량
    },
    ...
]
```

## 주의사항

1. **분봉 데이터 필수**: 이 시뮬레이터는 분봉 데이터를 기반으로 정확한 진입/청산 시점을 계산합니다.
2. **실시간 데이터**: IntradayCollector는 네이버 금융의 제약으로 당일 장중 데이터만 수집 가능합니다.
3. **과거 데이터**: 과거 데이터 테스트를 위해서는 저장된 분봉 데이터를 사용하거나 test_simulator.py처럼 시뮬레이션 데이터를 생성해야 합니다.

## 라이선스

이 코드는 news-trading-bot 프로젝트의 일부입니다.
