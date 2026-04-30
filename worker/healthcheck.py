"""Phase A 워커 — 인프라 검증용 헬스체크.

KIS API 미연동. 30분(기본)마다 Telegram에 alive 핑만 보낸다.
시작/종료 시에도 알림. systemd가 죽이면 SIGTERM 받고 graceful 종료.

Phase B에서 이 파일을 KIS 잔고 조회로 확장한다.
"""

from __future__ import annotations

import os
import signal
import socket
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore

# 프로젝트 루트를 import path에 추가 (telegram_notifier 재사용)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from telegram_notifier import TelegramNotifier  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
HEARTBEAT_INTERVAL_SEC = int(os.getenv("HEARTBEAT_INTERVAL_SEC", "1800"))
HOSTNAME = socket.gethostname()
PHASE = "A"

_running = True


def _stop(signum, frame):
    global _running
    _running = False


def _now() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")


def _uptime_str(start_ts: float) -> str:
    sec = int(time.time() - start_ts)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m}m {s}s"


def main() -> int:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    notifier = TelegramNotifier()
    start_ts = time.time()

    notifier.send_custom(
        title=f"워커 시작 (Phase {PHASE})",
        content=(
            f"호스트: <code>{HOSTNAME}</code>\n"
            f"시각: {_now()}\n"
            f"Heartbeat: {HEARTBEAT_INTERVAL_SEC}s 주기"
        ),
        emoji="🟢",
    )

    last_beat = time.time()
    try:
        while _running:
            now = time.time()
            if now - last_beat >= HEARTBEAT_INTERVAL_SEC:
                notifier.send_custom(
                    title="워커 alive",
                    content=(
                        f"호스트: <code>{HOSTNAME}</code>\n"
                        f"시각: {_now()}\n"
                        f"Phase: {PHASE}\n"
                        f"Uptime: {_uptime_str(start_ts)}"
                    ),
                    emoji="💓",
                )
                last_beat = now
            time.sleep(5)
    finally:
        notifier.send_custom(
            title="워커 종료",
            content=(
                f"호스트: <code>{HOSTNAME}</code>\n"
                f"시각: {_now()}\n"
                f"Uptime: {_uptime_str(start_ts)}"
            ),
            emoji="🔴",
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
