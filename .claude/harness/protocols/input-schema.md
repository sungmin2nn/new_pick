# Input Schema Protocol

모든 에이전트에 전달되는 입력의 표준 형식

## Standard Input Structure

```json
{
  "request_id": "string (UUID)",
  "timestamp": "ISO 8601 datetime",
  "source": {
    "type": "user | agent | system",
    "agent_id": "string (if agent)",
    "layer": "L1 | L2 | L3"
  },
  "task": {
    "type": "string (task classification)",
    "description": "string (natural language)",
    "priority": "critical | high | normal | low",
    "deadline": "ISO 8601 datetime (optional)"
  },
  "context": {
    "shared_state": "object (from context/state.json)",
    "previous_results": "array (from upstream agents)",
    "constraints": "array of strings"
  },
  "parameters": {
    "domain_specific": "object (varies by agent)"
  }
}
```

## Task Types

### Core Layer (L1)
| Agent | Valid Task Types |
|-------|-----------------|
| orchestrator | `orchestrate`, `analyze`, `delegate`, `integrate` |
| audit-agent | `audit`, `validate`, `review`, `assess` |
| state-manager | `record`, `summarize`, `cleanup`, `get-context` |
| dashboard-agent | `update`, `inject-status`, `validate`, `snapshot` |

### Domain Layer (L2)
| Agent | Valid Task Types |
|-------|-----------------|
| data-collector-agent | `collect`, `fetch`, `aggregate`, `sync` |
| score-optimizer-agent | `optimize`, `analyze`, `tune`, `validate` |
| backtest-agent | `backtest`, `analyze`, `compare`, `report` |
| monitor-agent | `monitor`, `alert`, `track`, `notify` |
| innovator-agent | `innovate`, `propose`, `brainstorm`, `evaluate` |
| news-tracker-agent | `track`, `summarize`, `analyze`, `alert` |

### Utility Layer (L3)
| Agent | Valid Task Types |
|-------|-----------------|
| dev-agent | `code`, `review`, `test`, `debug`, `refactor` |
| research-agent | `search`, `research`, `analyze`, `summarize` |
| business-agent | `write`, `format`, `report`, `document` |
| test-agent | `test`, `coverage`, `setup`, `validate` |
| cicd-agent | `manage`, `monitor`, `analyze`, `deploy` |

## Priority Levels

| Level | Description | SLA |
|-------|-------------|-----|
| `critical` | 시스템 장애, 긴급 수정 | 즉시 |
| `high` | 중요 기능, 마감 임박 | 1시간 내 |
| `normal` | 일반 작업 | 당일 |
| `low` | 개선, 최적화 | 여유 |

## Context Passing

### Shared State Access
```json
{
  "context": {
    "shared_state": {
      "current_phase": "data_collection",
      "target_stocks": ["005930", "000660"],
      "date_range": {
        "start": "2025-01-01",
        "end": "2025-12-31"
      }
    }
  }
}
```

### Previous Results Reference
```json
{
  "context": {
    "previous_results": [
      {
        "agent": "data-collector-agent",
        "request_id": "abc-123",
        "summary": "collected 252 trading days",
        "output_path": "context/data/stock_data.json"
      }
    ]
  }
}
```

## Domain-Specific Parameters

### data-collector-agent
```json
{
  "parameters": {
    "source": "pykrx | dart | naver",
    "stock_codes": ["005930"],
    "date_range": {"start": "2025-01-01", "end": "2025-12-31"},
    "data_types": ["ohlcv", "fundamental", "news"]
  }
}
```

### score-optimizer-agent
```json
{
  "parameters": {
    "scoring_system": "135point",
    "current_weights": {...},
    "optimization_target": "sharpe_ratio | returns | stability",
    "constraints": {"max_weight": 0.3, "min_samples": 100}
  }
}
```

### backtest-agent
```json
{
  "parameters": {
    "strategy": "momentum | value | combined",
    "period": {"start": "2020-01-01", "end": "2025-12-31"},
    "initial_capital": 100000000,
    "commission": 0.00015,
    "benchmark": "KOSPI"
  }
}
```

## Validation Rules

1. `request_id`는 필수, UUID 형식
2. `task.type`은 해당 에이전트의 유효 타입만 허용
3. `priority`가 `critical`/`high`인 경우 `deadline` 권장
4. `context.constraints`는 문자열 배열
5. `parameters`는 에이전트별 스키마 준수
