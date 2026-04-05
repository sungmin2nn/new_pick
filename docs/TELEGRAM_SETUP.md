# Telegram 알림 설정 가이드

## 1. Telegram 봇 생성

### Step 1: BotFather에서 봇 생성

1. Telegram에서 **@BotFather** 검색
2. `/newbot` 명령어 입력
3. 봇 이름 입력 (예: `My Trading Bot`)
4. 봇 유저네임 입력 (예: `my_trading_bot`) - 반드시 `_bot`으로 끝나야 함
5. **API 토큰** 복사 (예: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

```
BotFather: Done! Congratulations on your new bot.
You will find it at t.me/my_trading_bot.
Use this token to access the HTTP API:
123456789:ABCdefGHIjklMNOpqrsTUVwxyz
```

### Step 2: Chat ID 확인

**방법 A: 개인 채팅**
1. 생성한 봇에게 아무 메시지 전송
2. 브라우저에서 접속:
   ```
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
   ```
3. `"chat":{"id":123456789}` 에서 Chat ID 확인

**방법 B: 그룹 채팅**
1. 봇을 그룹에 추가
2. 그룹에 메시지 전송
3. 위와 같이 getUpdates 확인 (그룹 ID는 음수: `-123456789`)

---

## 2. GitHub Secrets 설정

### Repository Secrets 추가

1. GitHub 저장소 → **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret** 클릭
3. 아래 두 개 추가:

| Name | Value |
|------|-------|
| `TELEGRAM_BOT_TOKEN` | `123456789:ABCdefGHIjklMNOpqrsTUVwxyz` |
| `TELEGRAM_CHAT_ID` | `123456789` (또는 그룹 `-123456789`) |

---

## 3. 알림 종류

### 자동 알림 (워크플로우)

| 워크플로우 | 알림 내용 | 트리거 |
|-----------|----------|--------|
| `paper-trading-select.yml` | 종목 선정 완료 | 매일 08:00 |
| `paper-trading-check.yml` | 익절/손절 발생 | 장중 3회 |

### 수동 알림 (CLI)

```bash
# 테스트 알림
python telegram_notifier.py --type test

# 커스텀 메시지
python telegram_notifier.py --type custom --title "제목" --message "내용"

# 일일 요약 (JSON 파일)
python telegram_notifier.py --type summary --data data/paper_trading/status_20260403.json

# 종목 선정 결과
python telegram_notifier.py --type selection --data data/paper_trading/candidates_20260403_all.json
```

---

## 4. 알림 예시

### 매수 신호
```
🟢 매수 신호

종목: 삼성전자 (005930)
현재가: 75,000원
점수: 85점
사유: 외국인 순매수 급증

⏰ 2026-04-03 09:15
```

### 익절 신호
```
🎯 익절 신호

종목: SK하이닉스 (000660)
현재가: 145,000원
수익률: 🟢 +5.23%

⏰ 2026-04-03 14:30
```

### 손절 신호
```
🛑 손절 신호

종목: LG화학 (051910)
현재가: 380,000원
수익률: 🔴 -3.15%

⏰ 2026-04-03 11:45
```

### 종목 선정 완료
```
📋 종목 선정 완료

전략: 다중전략 (4개)
선정: 10개

1. 삼성전자 (005930) - 92점
2. SK하이닉스 (000660) - 88점
3. 현대차 (005380) - 85점
...

⏰ 2026-04-03 08:00
```

---

## 5. 문제 해결

### 알림이 오지 않을 때

1. **Secrets 확인**: GitHub Actions 로그에서 `Telegram 미설정` 메시지 확인
2. **토큰 확인**: BotFather에서 토큰 재발급 (`/token`)
3. **Chat ID 확인**: getUpdates API로 재확인
4. **봇 차단 확인**: 봇을 차단하지 않았는지 확인

### 그룹에서 알림 받기

1. 봇을 그룹에 추가
2. 그룹 설정 → 봇을 관리자로 지정 (선택사항)
3. Chat ID를 그룹 ID로 변경 (음수)

### 로컬 테스트

```bash
export TELEGRAM_BOT_TOKEN='your-token'
export TELEGRAM_CHAT_ID='your-chat-id'
python telegram_notifier.py --type test
```

---

## 6. 추가 설정 (선택)

### 알림 필터링

`telegram_notifier.py`에서 조건 수정:

```python
# 5% 이상 익절만 알림
if pnl_pct >= 5.0:
    notifier.send_sell_signal(...)

# 특정 종목만 알림
if stock_code in ['005930', '000660']:
    notifier.send_buy_signal(...)
```

### 알림 시간 제한

워크플로우에서 장중 시간만 알림:
```yaml
- name: Send Alert
  if: ${{ steps.time_check.outputs.IS_MARKET_HOURS == 'true' }}
```
