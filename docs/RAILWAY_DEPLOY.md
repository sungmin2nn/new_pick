# Railway 배포 가이드

## 1. Railway 가입 (2분)

1. https://railway.app 접속
2. **GitHub 계정으로 로그인** (권장)
3. 이메일 인증 완료

> 💡 GitHub 로그인하면 레포 연동이 쉬움

---

## 2. 새 프로젝트 생성 (3분)

### Step 1: 프로젝트 시작
1. Dashboard에서 **New Project** 클릭
2. **Deploy from GitHub repo** 선택
3. `news-trading-bot` 레포 선택

### Step 2: 서비스 설정
1. **Configure** 클릭
2. **Root Directory** 설정: `telegram_bot`
3. **Deploy** 클릭

---

## 3. 환경 변수 설정 (1분)

프로젝트 → **Variables** 탭:

| Variable | Value |
|----------|-------|
| `TELEGRAM_BOT_TOKEN` | `123456789:ABC...` (봇 토큰) |
| `TELEGRAM_CHAT_ID` | `123456789` (채팅 ID) |
| `GITHUB_REPO` | `yourname/news-trading-bot` |
| `GITHUB_BRANCH` | `main` |

**Add** 버튼으로 각각 추가

---

## 4. 배포 확인

### 로그 확인
프로젝트 → **Deployments** → 최신 배포 클릭 → **View Logs**

성공 시:
```
Bot starting...
Bot commands registered
```

### 봇 테스트
Telegram에서 봇에게:
```
/start
/ping
/status
```

---

## 5. 사용 가능한 명령어

| 명령어 | 설명 |
|--------|------|
| `/start` | 시작 + 명령어 안내 |
| `/status` | 현재 포트폴리오 상태 |
| `/today` | 오늘 선정 종목 |
| `/pnl` | 수익률 현황 |
| `/top` | 점수 상위 종목 |
| `/signals` | 최근 매매 신호 |
| `/ping` | 봇 상태 확인 |
| `/help` | 도움말 |

자연어도 가능:
- "오늘 종목 뭐야?"
- "수익률 어때?"
- "상위 종목 보여줘"

---

## 6. 비용

### 무료 플랜
- 월 **$5 크레딧** 제공
- 이 봇은 약 **$2~3/월** 사용
- **충분히 무료로 운영 가능**

### 사용량 확인
Dashboard → **Usage** 탭

---

## 7. 문제 해결

### 봇이 응답 안 할 때

1. **로그 확인**: Deployments → View Logs
2. **환경 변수 확인**: Variables 탭에서 토큰/ID 확인
3. **재배포**: Deployments → Redeploy

### 데이터가 안 나올 때

1. `GITHUB_REPO` 형식 확인: `username/repo-name`
2. 레포가 **Public**인지 확인 (Private이면 토큰 필요)
3. 파일 경로 확인: `data/paper_trading/` 폴더 존재 여부

### Private 레포 사용 시

환경 변수 추가:
```
GITHUB_TOKEN = ghp_xxxxxxxxxxxx
```

`bot.py`에서 헤더 추가 필요 (요청 시 안내)

---

## 8. 자동 배포 설정

GitHub에 push하면 자동 배포:

1. 프로젝트 Settings → **Triggers**
2. **Enable GitHub trigger** 확인
3. Branch: `main`

이제 코드 수정 → push → 자동 재배포!

---

## 빠른 시작 요약

```bash
# 1. Railway 가입 (GitHub 로그인)
https://railway.app

# 2. New Project → Deploy from GitHub → news-trading-bot 선택

# 3. Configure → Root Directory: telegram_bot

# 4. Variables 추가:
#    TELEGRAM_BOT_TOKEN = your-token
#    TELEGRAM_CHAT_ID = your-chat-id
#    GITHUB_REPO = yourname/news-trading-bot

# 5. Deploy!

# 6. Telegram에서 /start 테스트
```

총 소요 시간: **약 5~10분**
