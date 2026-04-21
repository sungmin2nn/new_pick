# 주 1회 자동 실행 설정

Strategy Lab은 **두 개의 주간 파이프라인**을 사용합니다:

| 요일 | 파이프라인 | 역할 |
|---|---|---|
| **월요일 08:30** | `weekly_pipeline.py` | 백테스트 재실행 + 리더보드 갱신 + 승급 평가 |
| **금요일 09:00** | `friday_pipeline.py` | 개선 루프 (부진 식별 → 약점 분석 → v0.2 생성) + 앙상블 빌드 |

월요일은 "데이터 업데이트", 금요일은 "개선/조합 관점 재평가".

---

## 옵션 1: Claude Code `schedule` 스킬 (권장)

Claude Code 세션 안에서 다음 프롬프트로 스케줄 등록:

```
schedule 스킬로 매주 월요일 08:30 KST에 Strategy Lab weekly pipeline 실행:
  cd /Users/kslee/Documents/kslee_ZIP/zip1/strategy-lab
  python3 -m runner.weekly_pipeline --periods 1w --workers 4

완료 후 생성된 data/promotions/*.json의 승급 결과를 텔레그램 알림으로
요약 발송 (PROMOTED 전략 이름 + 점수).
```

schedule 스킬이 RemoteTrigger + CronCreate를 사용해 자동 등록합니다.

---

## 옵션 2: 시스템 cron (macOS crontab)

```bash
# crontab -e 에 추가
30 8 * * 1 cd /Users/kslee/Documents/kslee_ZIP/zip1/strategy-lab && \
  /usr/local/bin/python3 -m runner.weekly_pipeline --periods 1w --workers 4 \
  >> /tmp/strategy_lab_weekly.log 2>&1
```

설정 확인:
```bash
crontab -l
```

---

## 옵션 3: launchd (macOS 공식)

`~/Library/LaunchAgents/com.kslee.strategy-lab.weekly.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.kslee.strategy-lab.weekly</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
        <string>-m</string>
        <string>runner.weekly_pipeline</string>
        <string>--periods</string>
        <string>1w</string>
        <string>--workers</string>
        <string>4</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/kslee/Documents/kslee_ZIP/zip1/strategy-lab</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>1</integer>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>30</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/strategy_lab_weekly.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/strategy_lab_weekly.err</string>
</dict>
</plist>
```

로드:
```bash
launchctl load ~/Library/LaunchAgents/com.kslee.strategy-lab.weekly.plist
launchctl list | grep strategy-lab
```

---

## Friday Pipeline (Phase 7 개선 루프 + 앙상블)

금요일 파이프라인은 월요일 결과 위에 "개선/조합" 관점을 추가합니다:

```
1) identify_underperformers  — 부진 전략 자동 식별 (3축)
2) analyze_weakness          — 약점 구조 분석 (5축 + 가설)
3) tune_parameters           — v0.2 VariantSpec 자동 생성
4) build_ensembles           — 상위 N 선정 + 3방식 앙상블 빌드
```

### Claude Code schedule 스킬로 등록 (권장)

```
schedule 스킬로 매주 금요일 09:00 KST에 Strategy Lab Friday pipeline 실행:
  cd /Users/kslee/Documents/kslee_ZIP/zip1/strategy-lab
  python3 runner/friday_pipeline.py

완료 후 data/underperformers/, data/variants/, data/ensembles/ 최신 파일을
요약 출력 (부진 전략 수 + variant 수 + 앙상블 Sharpe).
```

### 시스템 cron (대안)

```bash
# crontab -e
0 9 * * 5 cd /Users/kslee/Documents/kslee_ZIP/zip1/strategy-lab && \
  /usr/local/bin/python3 runner/friday_pipeline.py \
  >> /tmp/strategy_lab_friday.log 2>&1
```

### 수동 실행

```bash
python3 runner/friday_pipeline.py              # 기본 (빠름, 6초 내외)
python3 runner/friday_pipeline.py --dry-run    # 실행 계획만
python3 runner/friday_pipeline.py --with-compare --parent eod_reversal_korean
                                               # v0.1 vs v0.2 실제 백테스트 (느림, 수 분)
```

---

## 결과 확인

### 월요일 파이프라인 출력:
- `data/results/matrix_YYYYMMDD_HHMMSS.json` — 백테스트 결과
- `data/leaderboard_data.js` — 리더보드 갱신
- `data/promotions/promotions_YYYYMMDD_HHMMSS.json` — 승급 평가
- `docs/integration_guides/*.md` — 승급 전략 통합 가이드

### 금요일 파이프라인 출력:
- `data/underperformers/underperformers_*.json` — 부진 식별 결과
- `data/weakness_reports/weakness_*.json` — 약점 분석
- `data/variants/{id}_v0.2_*.json` — 자동 생성된 v0.2 후보
- `data/ensembles/ensembles_*.json` — 앙상블 상세
- `data/leaderboard_ensembles.js` — 앙상블 리더보드 트랙

### 공통:
- `data/pipeline_runs.jsonl` — 실행 로그 누적

브라우저에서 `leaderboard.html` 새로고침 시 최신 결과 반영됨.

---

## 트러블슈팅

### KRX API rate limit
- `--workers 4`가 기본. rate limit 경고 나오면 `--workers 2`로 낮춤.

### 특정 전략 무거움 (opening/turtle/foreign_flow)
- 주간 파이프라인은 기본 1w만 실행 (15~30분).
- 1m 이상은 별도 실행 권장:
  ```bash
  python3 -m runner.matrix_runner --strategies opening_30min_volume_burst --periods 1m --save
  ```

### 실행 실패 복구
- `--skip-backtest`로 기존 결과만 사용해 승급/가이드 단계만 재실행 가능:
  ```bash
  python3 -m runner.weekly_pipeline --skip-backtest
  ```
