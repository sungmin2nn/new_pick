# deploy/ — 워커 인프라

24h 트레이딩 워커를 Oracle Cloud Free Tier (또는 임의의 Ubuntu 22.04 서버)에 배포하기 위한 스크립트/설정.

상세 셋업 절차는 `obsidian/ai-lab-showcase/oracle-phase-a-runbook.md` 참조.

## 구성

```
deploy/
├── install.sh                       # 1회성 부트스트랩 (root)
├── secrets.env.example              # /etc/news-trading-bot/secrets.env 템플릿
├── systemd/
│   └── ntb-worker.service           # 메인 워커 서비스 unit
└── README.md                        # 이 파일
```

## 빠른 배포 (요약)

```bash
# 인스턴스에서:
sudo apt-get update && sudo apt-get install -y git
git clone https://<PAT>@github.com/sungmin2nn/new_pick.git /tmp/ntb
cd /tmp/ntb
sudo REPO_URL='https://<PAT>@github.com/sungmin2nn/new_pick.git' bash deploy/install.sh

sudo nano /etc/news-trading-bot/secrets.env  # TELEGRAM_* 입력
sudo systemctl start ntb-worker
sudo journalctl -u ntb-worker -f
```

## Phase 별 추가 예정

| Phase | 추가 파일 |
|---|---|
| A (현재) | `install.sh`, `ntb-worker.service`, `healthcheck.py` |
| B | `ntb-token.service` + `ntb-token.timer`, `worker/token_refresher.py` |
| D | `worker/trader.py`, `broker/kis/order.py` |
| E | GitHub Actions 측 `live_results.json` reader step |

## 코드 갱신

```bash
sudo -u ntb bash -c "cd /opt/news-trading-bot && git pull"
sudo systemctl restart ntb-worker
```

## 시크릿 변경

```bash
sudo nano /etc/news-trading-bot/secrets.env
sudo systemctl restart ntb-worker
```

## 운영 관련

- 로그: `sudo journalctl -u ntb-worker -f`
- 상태: `sudo systemctl status ntb-worker`
- 정지: `sudo systemctl stop ntb-worker`
- 재시작: `sudo systemctl restart ntb-worker`
- 수동 킬 스위치 (Phase D 이후): `sudo -u ntb touch /opt/news-trading-bot/data/HALT.flag`
