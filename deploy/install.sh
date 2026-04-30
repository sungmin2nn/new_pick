#!/usr/bin/env bash
# Oracle Cloud Free Tier (Ubuntu 22.04, x86) — Phase A bootstrap
#
# 사용법:
#   sudo REPO_URL="https://<PAT>@github.com/sungmin2nn/new_pick.git" bash deploy/install.sh
#
# 결과:
#   - ntb 시스템 유저
#   - /opt/news-trading-bot 에 repo
#   - /etc/news-trading-bot/secrets.env 템플릿
#   - systemd: ntb-worker.service (enabled, NOT started)
#
# Phase A 까지만. Phase B에서 토큰 갱신 timer 추가.

set -euo pipefail

REPO_URL="${REPO_URL:-}"
INSTALL_DIR="/opt/news-trading-bot"
SECRETS_DIR="/etc/news-trading-bot"
SVC_USER="ntb"
PY_BIN="python3.11"

if [[ -z "$REPO_URL" ]]; then
    echo "✗ REPO_URL 환경변수가 필요합니다."
    echo "  예: sudo REPO_URL='https://<PAT>@github.com/sungmin2nn/new_pick.git' bash deploy/install.sh"
    exit 1
fi

if [[ "$EUID" -ne 0 ]]; then
    echo "✗ root 권한 필요 (sudo)"
    exit 1
fi

echo "▶ 1/7  시스템 유저 ($SVC_USER) 확인"
if ! id "$SVC_USER" &>/dev/null; then
    useradd -m -s /bin/bash "$SVC_USER"
    echo "  ✓ 유저 생성"
else
    echo "  ✓ 이미 존재"
fi

echo "▶ 2/7  패키지 설치"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    "$PY_BIN" "${PY_BIN}-venv" "${PY_BIN}-dev" \
    python3-pip git chrony tzdata curl ca-certificates build-essential

echo "▶ 3/7  타임존 + NTP"
timedatectl set-timezone Asia/Seoul
systemctl enable --now chrony >/dev/null 2>&1 || true
chronyc -a makestep >/dev/null 2>&1 || true

echo "▶ 4/7  repo clone → $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
chown "$SVC_USER:$SVC_USER" "$INSTALL_DIR"
if [[ ! -d "$INSTALL_DIR/.git" ]]; then
    sudo -u "$SVC_USER" git clone --quiet "$REPO_URL" "$INSTALL_DIR"
    echo "  ✓ clone 완료"
else
    echo "  ✓ 이미 clone됨, pull"
    sudo -u "$SVC_USER" bash -c "cd $INSTALL_DIR && git pull --quiet"
fi

echo "▶ 5/7  venv + 의존성 (Phase A: requests, python-dotenv 만)"
sudo -u "$SVC_USER" bash <<EOF
set -e
cd "$INSTALL_DIR"
if [[ ! -d .venv ]]; then
    "$PY_BIN" -m venv .venv
fi
.venv/bin/pip install -q -U pip wheel
.venv/bin/pip install -q "requests>=2.31.0" "python-dotenv>=1.0.0"
EOF

# 데이터/로그 디렉터리 (워커가 쓸 수 있도록)
sudo -u "$SVC_USER" mkdir -p "$INSTALL_DIR/data" "$INSTALL_DIR/logs"

echo "▶ 6/7  시크릿 디렉터리"
mkdir -p "$SECRETS_DIR"
chmod 750 "$SECRETS_DIR"
chown "root:$SVC_USER" "$SECRETS_DIR"
if [[ ! -f "$SECRETS_DIR/secrets.env" ]]; then
    cp "$INSTALL_DIR/deploy/secrets.env.example" "$SECRETS_DIR/secrets.env"
    chmod 640 "$SECRETS_DIR/secrets.env"
    chown "root:$SVC_USER" "$SECRETS_DIR/secrets.env"
    echo "  ✓ 템플릿 배포: $SECRETS_DIR/secrets.env"
else
    echo "  ✓ 기존 secrets.env 유지 (덮어쓰지 않음)"
fi

echo "▶ 7/7  systemd unit 등록"
cp "$INSTALL_DIR/deploy/systemd/ntb-worker.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable ntb-worker.service >/dev/null

echo ""
echo "════════════════════════════════════════════════════════════"
echo "✔ install.sh 완료"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "다음 단계:"
echo "  1) sudo nano $SECRETS_DIR/secrets.env"
echo "     → TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 입력"
echo ""
echo "  2) sudo systemctl start ntb-worker"
echo ""
echo "  3) sudo journalctl -u ntb-worker -f"
echo "     → Telegram에 '🟢 워커 시작' 메시지 확인"
echo ""
