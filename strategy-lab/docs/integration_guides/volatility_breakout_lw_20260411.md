# 통합 가이드: 변동성 돌파 (Larry Williams)

> **승급 후보** — Strategy Lab에서 모든 승급 기준을 통과한 전략입니다.
> 본 문서는 **자동 생성**되었으며, **수동 검토 후** news-trading-bot 정식 통합을 결정해야 합니다.

**생성일**: 2026-04-11 06:22
**전략 ID**: `volatility_breakout_lw`
**평가 기간**: 1w (20260329 ~ 20260410)
**종합 점수**: **98.0 / 100**

---

## 1. 전략 개요

| 항목 | 값 |
|------|-----|
| 이름 | 변동성 돌파 (Larry Williams) |
| 카테고리 | breakout |
| 리스크 등급 | medium |
| 참신성 | 7/10 |
| 출처 수 | 2 |

### 가설
전일 변동폭의 K배만큼 시초가에서 상승 돌파하면 당일 추세가 이어진다

### 기존 전략과의 차이
Echo Frontier와 다름: Echo는 '전일 종가→시초가' 갭 비율(2~5%)을 트리거로 사용. 본 전략은 '전일 (high-low) × K' 절대 가격폭을 시초가에 더한 가격을 트리거. 갭이 거의 없는 종목에서도 발동 가능하고, 변동성 자체를 직접 측정한다는 점이 본질적으로 다름.

### 기대 수익 원천
장중 추세 지속성, 거래량 동반 시 상승 가능성 ↑

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
| 총 수익률 | **+35.25%** |
| Sharpe Ratio | 38.67 |
| 승률 | 86.7% |
| 최대 드로다운 | 0.00% |
| Profit Factor | 10.79 |
| 거래 수 | 45 |
| 최대 연속 패 | 0 |
| 거래일 수 | 9 |

### 경고 / 주의
- ⚠️ Sharpe 38.7 > 15.0 → 짧은 기간 과대평가 의심

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
code zip1/strategy-lab/strategies/volatility_breakout_lw.py
```

- [ ] `select_stocks()` 로직 이해
- [ ] `get_params()` 반환값 확인
- [ ] 외부 의존성(KRXClient/NaverInvestor/DartFilter) 재확인

### Step 2: 파일 복사
```bash
cp zip1/strategy-lab/strategies/volatility_breakout_lw.py \
   zip1/news-trading-bot/paper_trading/strategies/volatility_breakout_lw.py
```

### Step 3: Import 경로 조정
원본은 `from lab import BaseStrategy, Candidate` 사용.
news-trading-bot에서는:
```python
from .base import BaseStrategy, Candidate
from .registry import StrategyRegistry

@StrategyRegistry.register
class VolatilityBreakoutLwStrategy(BaseStrategy):
    ...
```

### Step 4: `paper_trading/strategies/__init__.py`에 추가
```python
from .volatility_breakout_lw import VolatilityBreakoutLwStrategy
__all__ = [..., 'VolatilityBreakoutLwStrategy']
```

### Step 5: (선택) Arena 팀 등록
`paper_trading/arena/team.py`의 `TEAM_CONFIGS`에 추가하여
기존 5팀과 경쟁시킬 수 있습니다:
```python
"team_f": {
    "team_id": "team_f",
    "team_name": "Foxtrot VolatilityBreakoutLwStrategy",
    "strategy_id": "volatility_breakout_lw",
    "emoji": "⚡",
    "description": "변동성 돌파 (Larry Williams)",
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
- **Sharpe 과대평가 가능**: Sharpe 38.7는 1주 기간 특성

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

1. **[verified]** Long-Term Secrets to Short-Term Trading — Larry Williams
   (type: book)
   > 원전. K=0.5 권장.
2. **[high]** news-trading-bot-handoff.md Section 6.2
   (type: handoff_guide)
   > 신규 전략 후보로 명시됨.

---

## 7. 승인 기록

**자동 생성**: Strategy Lab / 2026-04-11 06:22:31
**승급 평가 파일**: `data/promotions/volatility_breakout_lw_20260411.json`
**Strategy Lab commit**: (git rev-parse HEAD)

### 수동 승인 서명
- [ ] 코드 리뷰 완료: 날짜 ___________ / 서명 ___________
- [ ] 재백테스트 완료: 날짜 ___________ / 결과 ___________
- [ ] Paper trading 완료: 날짜 ___________ / 기간 ___________
- [ ] **news-trading-bot 정식 통합 승인**: 날짜 ___________

---

*이 가이드는 자동으로 생성되었으며, 사람의 최종 판단 없이는 정식 통합하지 마세요.*
