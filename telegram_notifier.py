"""
Telegram 알림 모듈
- 매매 신호, 익절/손절 알림 전송
- GitHub Actions에서 사용
"""

import os
import json
import requests
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List


class TelegramNotifier:
    """Telegram 봇을 통한 알림 전송"""

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token or os.environ.get('TELEGRAM_BOT_TOKEN')
        self.chat_id = chat_id or os.environ.get('TELEGRAM_CHAT_ID')
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    def is_configured(self) -> bool:
        """설정 여부 확인"""
        return bool(self.bot_token and self.chat_id)

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """메시지 전송"""
        if not self.is_configured():
            print("[Telegram] 설정되지 않음 - TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 필요")
            return False

        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True
            }
            response = requests.post(url, json=payload, timeout=10)

            if response.status_code == 200:
                print("[Telegram] 알림 전송 성공")
                return True
            else:
                print(f"[Telegram] 전송 실패: {response.text}")
                return False

        except Exception as e:
            print(f"[Telegram] 오류: {e}")
            return False

    # === 매매 알림 템플릿 ===

    def send_buy_signal(self, stock_name: str, stock_code: str,
                        price: int, score: int, reason: str) -> bool:
        """매수 신호 알림"""
        kst = timezone(timedelta(hours=9))
        now = datetime.now(kst).strftime("%Y-%m-%d %H:%M")

        message = f"""
<b>🟢 매수 신호</b>

<b>종목:</b> {stock_name} ({stock_code})
<b>현재가:</b> {price:,}원
<b>점수:</b> {score}점
<b>사유:</b> {reason}

<i>⏰ {now}</i>
"""
        return self.send_message(message.strip())

    def send_sell_signal(self, stock_name: str, stock_code: str,
                         price: int, signal_type: str, pnl_pct: float) -> bool:
        """매도 신호 알림 (익절/손절)"""
        kst = timezone(timedelta(hours=9))
        now = datetime.now(kst).strftime("%Y-%m-%d %H:%M")

        if signal_type == "profit":
            emoji = "🎯"
            title = "익절 신호"
            color_emoji = "🟢"
        else:
            emoji = "🛑"
            title = "손절 신호"
            color_emoji = "🔴"

        pnl_sign = "+" if pnl_pct >= 0 else ""

        message = f"""
<b>{emoji} {title}</b>

<b>종목:</b> {stock_name} ({stock_code})
<b>현재가:</b> {price:,}원
<b>수익률:</b> {color_emoji} {pnl_sign}{pnl_pct:.2f}%

<i>⏰ {now}</i>
"""
        return self.send_message(message.strip())

    def send_daily_summary(self, data: Dict[str, Any]) -> bool:
        """일일 요약 알림"""
        kst = timezone(timedelta(hours=9))
        now = datetime.now(kst).strftime("%Y-%m-%d")

        total = data.get('total_stocks', 0)
        profit_hit = data.get('profit_hit', 0)
        loss_hit = data.get('loss_hit', 0)
        waiting = data.get('waiting', 0)

        total_pnl = data.get('total_pnl_pct', 0)
        pnl_sign = "+" if total_pnl >= 0 else ""
        pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"

        message = f"""
<b>📊 일일 매매 현황</b>

<b>날짜:</b> {now}
<b>총 종목:</b> {total}개

<b>✅ 익절:</b> {profit_hit}개
<b>❌ 손절:</b> {loss_hit}개
<b>⏳ 대기:</b> {waiting}개

<b>총 수익률:</b> {pnl_emoji} {pnl_sign}{total_pnl:.2f}%
"""
        return self.send_message(message.strip())

    def send_stock_selection(self, stocks: List[Dict[str, Any]], strategy: str = "") -> bool:
        """종목 선정 알림"""
        kst = timezone(timedelta(hours=9))
        now = datetime.now(kst).strftime("%Y-%m-%d %H:%M")

        if not stocks:
            message = f"""
<b>📋 종목 선정 결과</b>

전략: {strategy or "기본"}
선정 종목: 없음

<i>⏰ {now}</i>
"""
        else:
            stock_lines = []
            for i, s in enumerate(stocks[:10], 1):  # 최대 10개
                name = s.get('name', s.get('stock_name', 'N/A'))
                code = s.get('code', s.get('stock_code', ''))
                score = s.get('score', s.get('total_score', 0))
                stock_lines.append(f"{i}. {name} ({code}) - {score}점")

            stocks_text = "\n".join(stock_lines)

            message = f"""
<b>📋 종목 선정 완료</b>

<b>전략:</b> {strategy or "기본"}
<b>선정:</b> {len(stocks)}개

{stocks_text}

<i>⏰ {now}</i>
"""
        return self.send_message(message.strip())

    def send_error_alert(self, error_type: str, message: str,
                         workflow: str = "") -> bool:
        """오류 알림"""
        kst = timezone(timedelta(hours=9))
        now = datetime.now(kst).strftime("%Y-%m-%d %H:%M")

        alert = f"""
<b>🚨 오류 발생</b>

<b>유형:</b> {error_type}
<b>워크플로우:</b> {workflow or "N/A"}
<b>내용:</b> {message[:500]}

<i>⏰ {now}</i>
"""
        return self.send_message(alert.strip())

    def send_custom(self, title: str, content: str, emoji: str = "📢") -> bool:
        """커스텀 알림"""
        kst = timezone(timedelta(hours=9))
        now = datetime.now(kst).strftime("%Y-%m-%d %H:%M")

        message = f"""
<b>{emoji} {title}</b>

{content}

<i>⏰ {now}</i>
"""
        return self.send_message(message.strip())


# === CLI 인터페이스 ===

def main():
    """커맨드라인에서 직접 실행"""
    import argparse

    parser = argparse.ArgumentParser(description='Telegram 알림 전송')
    parser.add_argument('--type', '-t', choices=['test', 'buy', 'sell', 'summary', 'selection', 'error', 'custom'],
                        default='test', help='알림 유형')
    parser.add_argument('--message', '-m', default='', help='메시지 내용')
    parser.add_argument('--title', default='알림', help='제목 (custom 타입)')
    parser.add_argument('--data', '-d', default='', help='JSON 데이터 파일 경로')

    args = parser.parse_args()

    notifier = TelegramNotifier()

    if not notifier.is_configured():
        print("❌ Telegram 설정 필요:")
        print("   export TELEGRAM_BOT_TOKEN='your-bot-token'")
        print("   export TELEGRAM_CHAT_ID='your-chat-id'")
        return

    if args.type == 'test':
        notifier.send_custom("테스트", "Telegram 알림이 정상 작동합니다! ✅", "🔔")

    elif args.type == 'custom':
        notifier.send_custom(args.title, args.message or "내용 없음")

    elif args.type == 'summary' and args.data:
        with open(args.data) as f:
            data = json.load(f)
        notifier.send_daily_summary(data)

    elif args.type == 'selection' and args.data:
        with open(args.data) as f:
            data = json.load(f)
        stocks = data.get('stocks', data.get('selected', []))
        notifier.send_stock_selection(stocks, data.get('strategy', ''))

    elif args.type == 'error':
        notifier.send_error_alert("수동 알림", args.message or "오류 내용 없음")

    else:
        print(f"알림 유형: {args.type}")
        print("--data 옵션으로 JSON 파일 경로 지정 필요 (summary, selection)")


if __name__ == "__main__":
    main()
