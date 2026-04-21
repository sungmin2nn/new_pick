# 통합 가이드: 단축 터틀 돌파 (5/10일 신고가)

> **승급 후보** — Strategy Lab에서 모든 승급 기준을 통과한 전략입니다.
> 본 문서는 **자동 생성**되었으며, **수동 검토 후** news-trading-bot 정식 통합을 결정해야 합니다.

**생성일**: 2026-04-11 06:22
**전략 ID**: `turtle_breakout_short`
**평가 기간**: 1w (20260329 ~ 20260410)
**종합 점수**: **92.1 / 100**

---

## 1. 전략 개요

| 항목 | 값 |
|------|-----|
| 이름 | 단축 터틀 돌파 (5/10일 신고가) |
| 카테고리 | breakout |
| 리스크 등급 | medium |
| 참신성 | 6/10 |
| 출처 수 | 2 |

### 가설
N일 신고가 돌파 + 거래량 동반 종목은 추세 지속 가능성

### 기존 전략과의 차이
Echo Frontier와 다름: Echo는 시초가 갭 비율, 본 전략은 N일 신고가 돌파. Volatility BO와 다름: VB는 전일 변동폭 K배, 본 전략은 절대 신고가. Alpha Momentum과 다름: Alpha는 MA5 위 + 거래량 3배 (스무딩), 본 전략은 N일 신고가 돌파 (단순 신기록). Donchian Channel 클래식 전략의 단축 버전.

### 기대 수익 원천
신고가 갱신 + 거래량 동반의 추세 추종 효과

---

## 2. 승급 근거

### 통과한 기준
- ✓ return >= 5.0%
- ✓ sharpe >= 1.0
- ✓ WR >= 50%
- ✓ MDD >= -15.0%
- ✓ trades >= 10
- ✓ PF >= 1.5

### 메트릭 요약 (평가 기간 기준)

| 메트릭 | 값 |
|--------|-----|
| 총 수익률 | **+17.63%** |
| Sharpe Ratio | 15.27 |
| 승률 | 62.2% |
| 최대 드로다운 | -1.39% |
| Profit Factor | 2.74 |
| 거래 수 | 45 |
| 최대 연속 패 | 1 |
| 거래일 수 | 9 |

### 경고 / 주의
- ⚠️ Sharpe 15.3 > 15.0 → 짧은 기간 과대평가 의심

---

## 3. 데이터 의존도

- `KRX_OHLCV`

**중요**: 통합 전 위 데이터 소스가 news-trading-bot에서 이미 검증되었는지 확인하세요.
- KRX OpenAPI: ✅ 검증됨 (`paper_trading/utils/krx_api.py`)
- Naver Investor: ✅ 검증됨 (`paper_trading/utils/naver_investor.py`)
- DART: ✅ 검증됨 (`paper_trading/utils/dart_utils.py`)
- 기타: 추가 검증 필요

---

## 4. 통합 단계 (수동 수행)

### Step 1: 코드 검토
```bash
# Strategy Lab의 원본 파일 열람
code zip1/strategy-lab/strategies/turtle_breakout_short.py
```

- [ ] `select_stocks()` 로직 이해
- [ ] `get_params()` 반환값 확인
- [ ] 외부 의존성(KRXClient/NaverInvestor/DartFilter) 재확인

### Step 2: 파일 복사
```bash
cp zip1/strategy-lab/strategies/turtle_breakout_short.py \
   zip1/news-trading-bot/paper_trading/strategies/turtle_breakout_short.py
```

### Step 3: Import 경로 조정
원본은 `from lab import BaseStrategy, Candidate` 사용.
news-trading-bot에서는:
```python
from .base import BaseStrategy, Candidate
from .registry import StrategyRegistry

@StrategyRegistry.register
class TurtleBreakoutShortStrategy(BaseStrategy):
    ...
```

### Step 4: `paper_trading/strategies/__init__.py`에 추가
```python
from .turtle_breakout_short import TurtleBreakoutShortStrategy
__all__ = [..., 'TurtleBreakoutShortStrategy']
```

### Step 5: (선택) Arena 팀 등록
`paper_trading/arena/team.py`의 `TEAM_CONFIGS`에 추가하여
기존 5팀과 경쟁시킬 수 있습니다:
```python
"team_f": {
    "team_id": "team_f",
    "team_name": "Foxtrot TurtleBreakoutShortStrategy",
    "strategy_id": "turtle_breakout_short",
    "emoji": "⚡",
    "description": "단축 터틀 돌파 (5/10일 신고가)",
},
```

### Step 6: 검증 백테스트
```bash
cd zip1/news-trading-bot
python3 scripts/run_backtest.py 20260323 20260410
```
Strategy Lab 결과와 일치해야 합니다.

### Step 7: Paper Trading (실시간 무자본 검증)
최소 1주일 paper trading으로 실시간 데이터에서도 시그널이 나오는지 확인.

---

## 5. 리스크 경고

### 백테스트 한계 (정직)
- **일봉 시뮬 기반**: 장 중 가격 경로를 모름 → 익절선 도달 판정이 과대평가될 수 있음
- **슬리피지/스프레드 미반영**: 실전 체결가와 차이 발생
- **짧은 기간 샘플**: 9일 데이터로는 통계적 신뢰도 제한적
- **Sharpe 과대평가 가능**: Sharpe 15.3는 1주 기간 특성

### 통합 전 필수 확인
- [ ] 위 메트릭이 과적합(overfitting)이 아닌지 재검증
- [ ] 1개월 이상 기간으로 재백테스트
- [ ] paper trading 1주 이상
- [ ] 최대 drawdown 구간 수동 검토
- [ ] 거래 빈도가 실제 운영 가능한 수준인지

### 통합 후 모니터링
- 첫 2주: 일일 성과 확인 + 이상 거래 검토
- 첫 1개월: 주간 리뷰 + 백테스트 vs 실전 diff 분석
- 첫 3개월: 승급 시 사용한 메트릭 재계산 + watchlist/reject 전환 여부

---

## 6. 출처 및 참고자료

1. **[verified]** Way of the Turtle — Curtis Faith
   (type: book)
   > Turtle Trading System 원본 정리. Richard Dennis 시스템.
2. **[high]** Modern Turtle Trading Strategy: Updated Rules & Backtest
   https://tosindicators.com/research/modern-turtle-trading-strategy-rules-and-backtest
   (type: blog_en)
   > 현대 시장에서 System 2 (55일)가 System 1 (20일)보다 우수. 단축 버전 주의.

---

## 7. 승인 기록

**자동 생성**: Strategy Lab / 2026-04-11 06:22:31
**승급 평가 파일**: `data/promotions/turtle_breakout_short_20260411.json`
**Strategy Lab commit**: (git rev-parse HEAD)

### 수동 승인 서명
- [ ] 코드 리뷰 완료: 날짜 ___________ / 서명 ___________
- [ ] 재백테스트 완료: 날짜 ___________ / 결과 ___________
- [ ] Paper trading 완료: 날짜 ___________ / 기간 ___________
- [ ] **news-trading-bot 정식 통합 승인**: 날짜 ___________

---

*이 가이드는 자동으로 생성되었으며, 사람의 최종 판단 없이는 정식 통합하지 마세요.*
