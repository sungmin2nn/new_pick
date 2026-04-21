# 🧪 Strategy Lab

> **단타 전략 실험실** — 새로운 한국 주식 단타 전략을 안전하게 발굴, 검증, 순위화하는 무한 실험실.

[![Status](https://img.shields.io/badge/status-Phase%201-cyan)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()
[![Python](https://img.shields.io/badge/python-3.10+-blue)]()

## 무엇인가

`news-trading-bot`이라는 자동매매 시스템에 정식으로 배포되기 전,
**검증되지 않은 단타 전략 아이디어를 안전하게 실험하는 별도 저장소**입니다.

```
[전략 발굴]
    ↓ (다양한 출처: 자체/블로그/논문/커뮤니티)
[코드화]
    ↓ (BaseStrategy 패턴)
[백테스트]
    ↓ (news-trading-bot 인프라 재사용)
[리더보드]
    ↓ (성과 순위 + 일관성 검증)
[승급 후보]
    ↓ (수동 승인 후)
[news-trading-bot 정식 통합]
```

## 디자인 원칙

1. **본 시스템과 분리** — strategy-lab은 별도 저장소, 실매매 직접 영향 없음
2. **중복 금지** — 기존 6개 전략(Alpha/Beta/Gamma/Delta/Echo/BNF)과 본질이 다른 것만
3. **출처 검증** — 모든 외부 자료는 신뢰성 등급 명시
4. **승급은 수동** — 사용자 검토 없이 자동으로 본 시스템에 들어가지 않음
5. **재현 가능성** — 모든 백테스트는 동일 조건에서 재현 가능

## 디렉토리 구조

```
strategy-lab/
├── README.md
├── requirements.txt
├── lab/                          # 코어 모듈
│   ├── __init__.py               # news-trading-bot import 라우팅
│   ├── metadata.py               # 전략 메타데이터 스키마
│   ├── experiments.py            # 실험 로그 시스템
│   └── duplicate_check.py        # 중복 검사
├── strategies/                    # 신규 전략 코드
│   └── _template.py
├── runner/                        # 백테스트 실행기
├── data/
│   ├── experiments/              # 실험 결과 누적 (gitignored)
│   ├── results/                  # 백테스트 raw 결과 (gitignored)
│   └── sources/                  # 외부 자료 출처 기록
├── docs/
│   ├── strategy_template.md
│   └── integration_guide.md
└── leaderboard.html              # 성과 리더보드 (Phase 4)
```

## 시작하기

### 사전 요구사항
- Python 3.10+
- `news-trading-bot` 저장소가 같은 부모 디렉토리에 위치 (`../news-trading-bot/`)
- KRX OpenAPI 키 (news-trading-bot의 `.env`에서 자동 로드)

### 설치
```bash
cd strategy-lab
pip install -r requirements.txt
```

### import 검증
```python
from lab import BaseStrategy, NTB_AVAILABLE, assert_ntb_available
assert_ntb_available()  # news-trading-bot import 확인
```

### 새 전략 만들기 (간단 예시)
```python
from lab.metadata import StrategyMetadata, StrategyCategory, RiskLevel
from lab.duplicate_check import check_strategy_metadata

meta = StrategyMetadata(
    id='my_new_strategy',
    name='나의 새 전략',
    category=StrategyCategory.MOMENTUM.value,
    risk_level=RiskLevel.MEDIUM.value,
    hypothesis='...',
    differs_from_existing='기존 X와 다른 점: ...',
)

# 중복 검사
result = check_strategy_metadata(meta)
if not result.passed:
    print(result.message)
```

## 현재 진행 상황

**Phase 1: 인프라 + 전략 템플릿** — 완료
- ✓ 폴더 구조
- ✓ news-trading-bot BaseStrategy import
- ✓ 메타데이터 스키마
- ✓ 실험 로그 시스템
- ✓ 중복 검사 로직
- ✓ git + README

**Phase 2~5**: 전략 발굴, 백테스트 실행기, 리더보드, 승급 시스템 (예정)

## 핵심 의존성

- [news-trading-bot](../news-trading-bot/) — `BaseStrategy`, `KRXClient`, `run_backtest.py`
- 컨텍스트 문서: `obsidian/ai-lab-showcase/news-trading-bot-handoff.md`

## 라이선스

MIT (단, 외부 리서치 인용은 원 출처 표기 의무)

---

**저장소**: 별도 GitHub 저장소로 분리 가능 (현재는 `kslee_ZIP` 모노레포에 위치)

**관리자**: claude-code-session
