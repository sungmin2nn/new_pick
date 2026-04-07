# Output Schema Protocol

모든 에이전트가 반환하는 출력의 표준 형식

## Standard Output Structure

```json
{
  "request_id": "string (echoed from input)",
  "agent_id": "string",
  "timestamp": "ISO 8601 datetime",
  "status": "success | partial | failed | pending",
  "result": {
    "summary": "string (1-3 sentences)",
    "data": "object | array (structured output)",
    "artifacts": [
      {
        "type": "file | code | report",
        "path": "string",
        "description": "string"
      }
    ]
  },
  "metadata": {
    "execution_time_ms": "number",
    "tokens_used": "number (optional)",
    "tools_invoked": ["string"]
  },
  "next_actions": [
    {
      "suggested_agent": "string",
      "task_type": "string",
      "reason": "string"
    }
  ],
  "errors": [
    {
      "code": "string",
      "message": "string",
      "recoverable": "boolean"
    }
  ]
}
```

## Status Codes

| Status | Description | Follow-up |
|--------|-------------|-----------|
| `success` | 완전 성공 | 다음 단계 진행 |
| `partial` | 일부 성공 | 누락 항목 확인 필요 |
| `failed` | 실패 | 오류 분석 및 재시도 |
| `pending` | 대기 중 (비동기) | 폴링 또는 콜백 |

## Result Formats by Agent

### orchestrator
```json
{
  "result": {
    "summary": "3개 에이전트에 작업 분배 완료",
    "data": {
      "delegated_tasks": [
        {"agent": "data-collector-agent", "status": "success"},
        {"agent": "score-optimizer-agent", "status": "success"},
        {"agent": "backtest-agent", "status": "pending"}
      ],
      "integration_status": "in_progress"
    }
  }
}
```

### audit-agent
```json
{
  "result": {
    "summary": "코드 리뷰 완료: 2개 경고, 0개 오류",
    "data": {
      "grade": "WARNING",
      "checklist_results": {
        "syntax": "PASS",
        "logic": "PASS",
        "security": "WARNING",
        "performance": "PASS"
      },
      "issues": [
        {
          "severity": "warning",
          "location": "src/api.py:45",
          "message": "SQL 파라미터화 권장",
          "suggestion": "cursor.execute(query, params)"
        }
      ]
    }
  }
}
```

### data-collector-agent
```json
{
  "result": {
    "summary": "삼성전자 2025년 OHLCV 데이터 252일치 수집",
    "data": {
      "records_collected": 252,
      "date_range": {"start": "2025-01-02", "end": "2025-12-30"},
      "data_quality": {"missing": 0, "duplicates": 0}
    },
    "artifacts": [
      {
        "type": "file",
        "path": "context/data/005930_ohlcv.csv",
        "description": "삼성전자 일봉 데이터"
      }
    ]
  }
}
```

### score-optimizer-agent
```json
{
  "result": {
    "summary": "가중치 최적화 완료: Sharpe 0.85 → 1.12",
    "data": {
      "optimized_weights": {
        "momentum": 0.25,
        "value": 0.20,
        "quality": 0.30,
        "growth": 0.25
      },
      "performance_improvement": {
        "sharpe_before": 0.85,
        "sharpe_after": 1.12,
        "improvement_pct": 31.8
      }
    }
  }
}
```

### backtest-agent
```json
{
  "result": {
    "summary": "5년 백테스트 완료: CAGR 18.5%, MDD -12.3%",
    "data": {
      "metrics": {
        "total_return": 142.5,
        "cagr": 18.5,
        "mdd": -12.3,
        "sharpe_ratio": 1.24,
        "win_rate": 58.3
      },
      "vs_benchmark": {
        "alpha": 8.2,
        "beta": 0.78,
        "information_ratio": 0.92
      }
    },
    "artifacts": [
      {
        "type": "report",
        "path": "context/reports/backtest_2020_2025.md",
        "description": "상세 백테스트 리포트"
      }
    ]
  }
}
```

### state-manager
```json
{
  "result": {
    "summary": "3개 에이전트 실행 컨텍스트 기록 완료",
    "data": {
      "recorded_states": [
        {
          "agent": "data-collector-agent",
          "request_id": "abc-123",
          "status": "success",
          "context_path": ".context/states/abc-123.json"
        },
        {
          "agent": "score-optimizer-agent",
          "request_id": "def-456",
          "status": "success",
          "context_path": ".context/states/def-456.json"
        },
        {
          "agent": "backtest-agent",
          "request_id": "ghi-789",
          "status": "pending",
          "context_path": ".context/states/ghi-789.json"
        }
      ],
      "shared_context_updated": true,
      "context_files": [
        ".context/state.json",
        ".context/decisions.md",
        ".context/findings.md"
      ]
    },
    "artifacts": [
      {
        "type": "file",
        "path": ".context/state.json",
        "description": "갱신된 전체 작업 상태"
      }
    ]
  }
}
```

### dev-agent
```json
{
  "result": {
    "summary": "data_processor.py 리팩토링 완료",
    "data": {
      "files_modified": ["src/data_processor.py", "tests/test_processor.py"],
      "lines_added": 45,
      "lines_removed": 78,
      "test_results": {"passed": 12, "failed": 0}
    },
    "artifacts": [
      {
        "type": "code",
        "path": "src/data_processor.py",
        "description": "리팩토링된 데이터 처리 모듈"
      }
    ]
  }
}
```

## Error Codes

| Code | Description | Recovery |
|------|-------------|----------|
| `E001` | 입력 검증 실패 | 입력 수정 후 재시도 |
| `E002` | 외부 API 오류 | 대기 후 재시도 |
| `E003` | 권한 부족 | 권한 확인 |
| `E004` | 타임아웃 | 분할 처리 |
| `E005` | 데이터 없음 | 조건 변경 |
| `E006` | 내부 오류 | 로그 확인 |

## Next Actions

```json
{
  "next_actions": [
    {
      "suggested_agent": "audit-agent",
      "task_type": "validate",
      "reason": "코드 변경 후 품질 검증 권장"
    },
    {
      "suggested_agent": "backtest-agent",
      "task_type": "backtest",
      "reason": "새 가중치로 성과 검증 필요"
    }
  ]
}
```

## Chaining Protocol

에이전트 간 결과 전달:

```
Agent A (output)
    ↓
{
  "result": {...},
  "next_actions": [{
    "suggested_agent": "Agent B",
    ...
  }]
}
    ↓
Agent B (input.context.previous_results)
    ↓
{
  "context": {
    "previous_results": [{
      "agent": "Agent A",
      "request_id": "...",
      "summary": "...",
      "output_path": "..."
    }]
  }
}
```
