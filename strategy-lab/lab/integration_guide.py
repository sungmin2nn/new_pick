"""
Integration Guide Generator
=============================
승급된 전략에 대해 news-trading-bot 정식 통합 가이드를 자동 생성.

생성되는 문서에 포함:
- 전략 요약 (이름/출처/가설/카테고리/리스크)
- 승급 근거 (통과 기준 + 메트릭)
- 통합 단계 (파일 복사 / 팀 등록 / 검증 체크리스트)
- 리스크 경고 (일봉 시뮬 한계, 한국 시장 적합성 등)
- 사용자 체크리스트 (수동 승인 필수 — 자동 통합 금지)

저장 위치:
    docs/integration_guides/{strategy_id}_{date}.md

사용:
    from lab.integration_guide import IntegrationGuideGenerator
    gen = IntegrationGuideGenerator()
    gen.generate(promotion_result, strategy_metadata)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from lab.promotion import PromotionResult, PromotionStatus


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "docs" / "integration_guides"


class IntegrationGuideGenerator:
    """승급 전략의 news-trading-bot 통합 가이드 마크다운 생성기."""

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or DEFAULT_OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        promotion: PromotionResult,
        metadata: Optional[dict] = None,
    ) -> Optional[Path]:
        """
        승급 전략에 대해 가이드 생성.

        Args:
            promotion: PromotionResult — 평가 결과
            metadata: StrategyMetadata dict (optional) — 상세 정보 보강

        Returns:
            저장된 파일 경로. PROMOTED 아니면 None.
        """
        if promotion.status != PromotionStatus.PROMOTED.value:
            return None

        date_tag = datetime.now().strftime("%Y%m%d")
        filename = f"{promotion.strategy_id}_{date_tag}.md"
        path = self.output_dir / filename

        content = self._render(promotion, metadata)
        path.write_text(content, encoding="utf-8")
        return path

    def generate_batch(
        self,
        promotions: list,
        metadata_map: Optional[dict] = None,
    ) -> list:
        """여러 PROMOTED 전략에 대해 일괄 생성."""
        metadata_map = metadata_map or {}
        generated = []
        for p in promotions:
            if p.status != PromotionStatus.PROMOTED.value:
                continue
            meta = metadata_map.get(p.strategy_id)
            path = self.generate(p, meta)
            if path:
                generated.append(path)
        return generated

    # --------------------------------------------------------
    # Markdown templates
    # --------------------------------------------------------

    def _render(self, p: PromotionResult, meta: Optional[dict]) -> str:
        m = meta or {}
        sources_section = self._render_sources(m.get("sources", []))
        passed_list = "\n".join(f"- ✓ {c}" for c in p.passed_criteria)
        warnings_section = (
            "\n".join(f"- ⚠️ {w}" for w in p.warnings) if p.warnings else "- (없음)"
        )
        data_reqs = m.get("data_requirements", [])
        data_section = (
            "\n".join(f"- `{d}`" for d in data_reqs)
            if data_reqs
            else "- (미지정)"
        )

        strategy_file = f"strategies/{p.strategy_id}.py"

        return f"""# 통합 가이드: {p.strategy_name}

> **승급 후보** — Strategy Lab에서 모든 승급 기준을 통과한 전략입니다.
> 본 문서는 **자동 생성**되었으며, **수동 검토 후** news-trading-bot 정식 통합을 결정해야 합니다.

**생성일**: {datetime.now().strftime("%Y-%m-%d %H:%M")}
**전략 ID**: `{p.strategy_id}`
**평가 기간**: {p.period_label} ({p.start_date} ~ {p.end_date})
**종합 점수**: **{p.score:.1f} / 100**

---

## 1. 전략 개요

| 항목 | 값 |
|------|-----|
| 이름 | {p.strategy_name} |
| 카테고리 | {m.get("category", "미지정")} |
| 리스크 등급 | {m.get("risk_level", "미지정")} |
| 참신성 | {m.get("novelty_score", 0)}/10 |
| 출처 수 | {len(m.get("sources", []))} |

### 가설
{m.get("hypothesis", "(메타데이터 없음)")}

### 기존 전략과의 차이
{m.get("differs_from_existing", "(기술되지 않음)")}

### 기대 수익 원천
{m.get("expected_edge", "(기술되지 않음)")}

---

## 2. 승급 근거

### 통과한 기준
{passed_list}

### 메트릭 요약 (평가 기간 기준)

| 메트릭 | 값 |
|--------|-----|
| 총 수익률 | **{p.total_return_pct:+.2f}%** |
| Sharpe Ratio | {p.sharpe_ratio:.2f} |
| 승률 | {p.win_rate * 100:.1f}% |
| 최대 드로다운 | {p.max_drawdown_pct:.2f}% |
| Profit Factor | {p.profit_factor:.2f} |
| 거래 수 | {p.num_trades} |
| 최대 연속 패 | {p.max_consecutive_losses} |
| 거래일 수 | {p.trading_days} |

### 경고 / 주의
{warnings_section}

---

## 3. 데이터 의존도

{data_section}

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
code zip1/strategy-lab/{strategy_file}
```

- [ ] `select_stocks()` 로직 이해
- [ ] `get_params()` 반환값 확인
- [ ] 외부 의존성(KRXClient/NaverInvestor/DartFilter) 재확인

### Step 2: 파일 복사
```bash
cp zip1/strategy-lab/{strategy_file} \\
   zip1/news-trading-bot/paper_trading/strategies/{p.strategy_id}.py
```

### Step 3: Import 경로 조정
원본은 `from lab import BaseStrategy, Candidate` 사용.
news-trading-bot에서는:
```python
from .base import BaseStrategy, Candidate
from .registry import StrategyRegistry

@StrategyRegistry.register
class {self._class_name(p.strategy_id)}(BaseStrategy):
    ...
```

### Step 4: `paper_trading/strategies/__init__.py`에 추가
```python
from .{p.strategy_id} import {self._class_name(p.strategy_id)}
__all__ = [..., '{self._class_name(p.strategy_id)}']
```

### Step 5: (선택) Arena 팀 등록
`paper_trading/arena/team.py`의 `TEAM_CONFIGS`에 추가하여
기존 5팀과 경쟁시킬 수 있습니다:
```python
"team_f": {{
    "team_id": "team_f",
    "team_name": "Foxtrot {self._class_name(p.strategy_id)}",
    "strategy_id": "{p.strategy_id}",
    "emoji": "⚡",
    "description": "{p.strategy_name}",
}},
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
- **짧은 기간 샘플**: {p.trading_days}일 데이터로는 통계적 신뢰도 제한적
- **Sharpe 과대평가 가능**: Sharpe {p.sharpe_ratio:.1f}는 1주 기간 특성

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

{sources_section}

---

## 7. 승인 기록

**자동 생성**: Strategy Lab / {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**승급 평가 파일**: `data/promotions/{p.strategy_id}_{datetime.now().strftime("%Y%m%d")}.json`
**Strategy Lab commit**: (git rev-parse HEAD)

### 수동 승인 서명
- [ ] 코드 리뷰 완료: 날짜 ___________ / 서명 ___________
- [ ] 재백테스트 완료: 날짜 ___________ / 결과 ___________
- [ ] Paper trading 완료: 날짜 ___________ / 기간 ___________
- [ ] **news-trading-bot 정식 통합 승인**: 날짜 ___________

---

*이 가이드는 자동으로 생성되었으며, 사람의 최종 판단 없이는 정식 통합하지 마세요.*
"""

    def _render_sources(self, sources: list) -> str:
        if not sources:
            return "- (출처 정보 없음)"
        lines = []
        for i, s in enumerate(sources, 1):
            title = s.get("title", "(제목 없음)")
            author = s.get("author", "")
            url = s.get("url", "")
            trust = s.get("trust_level", "unverified")
            stype = s.get("type", "other")
            line = f"{i}. **[{trust}]** {title}"
            if author:
                line += f" — {author}"
            if url:
                line += f"\n   {url}"
            line += f"\n   (type: {stype})"
            notes = s.get("notes", "")
            if notes:
                line += f"\n   > {notes}"
            lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def _class_name(strategy_id: str) -> str:
        """volatility_breakout_lw → VolatilityBreakoutLwStrategy"""
        parts = strategy_id.split("_")
        return "".join(p.capitalize() for p in parts) + "Strategy"


__all__ = [
    "IntegrationGuideGenerator",
    "DEFAULT_OUTPUT_DIR",
]
