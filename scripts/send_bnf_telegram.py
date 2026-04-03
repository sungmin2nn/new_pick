#!/usr/bin/env python3
"""BNF Telegram 알림 전송 스크립트"""
import json
import os
import sys
from datetime import datetime
import pytz

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from telegram_notifier import TelegramNotifier


def send_selection_alert():
    """BNF 종목 선정 알림"""
    kst = pytz.timezone('Asia/Seoul')
    today = datetime.now(kst).strftime('%Y%m%d')

    notifier = TelegramNotifier()
    if not notifier.is_configured():
        print('Telegram 미설정')
        return

    try:
        filepath = f'data/bnf/candidates_{today}.json'
        if not os.path.exists(filepath):
            filepath = 'data/bnf/candidates.json'

        with open(filepath) as f:
            data = json.load(f)

        candidates = data.get('candidates', [])
        if candidates:
            lines = [f"{c['rank']}. {c['name']} -{c['max_drop']:.1f}%" for c in candidates[:5]]
            msg = f"선정: {len(candidates)}개\n" + '\n'.join(lines)
            notifier.send_custom('BNF 낙폭과대', msg, '🔥')
        else:
            notifier.send_custom('BNF 낙폭과대', '조건 충족 종목 없음', '📭')

        print('BNF 선정 알림 완료')
    except Exception as e:
        print(f'오류: {e}')


def send_simulation_alert():
    """BNF 시뮬레이션 알림"""
    kst = pytz.timezone('Asia/Seoul')
    now = datetime.now(kst)

    notifier = TelegramNotifier()
    if not notifier.is_configured():
        print('Telegram 미설정')
        return

    try:
        if os.path.exists('data/bnf/positions.json'):
            with open('data/bnf/positions.json') as f:
                pos_data = json.load(f)

            positions = [p for p in pos_data.get('positions', []) if p.get('state') != 'CLOSED']

            if now.hour >= 15 and positions:
                msg = f"보유: {len(positions)}개"
                notifier.send_custom('BNF 포지션', msg, '📊')

            print('BNF 매매 알림 완료')
    except Exception as e:
        print(f'오류: {e}')


if __name__ == '__main__':
    if len(sys.argv) > 1:
        action = sys.argv[1]
        if action == 'selection':
            send_selection_alert()
        elif action == 'simulation':
            send_simulation_alert()
        else:
            print(f'Unknown action: {action}')
            print('Usage: python send_bnf_telegram.py [selection|simulation]')
    else:
        print('Usage: python send_bnf_telegram.py [selection|simulation]')
