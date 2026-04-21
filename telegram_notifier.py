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

    LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "telegram")

    # msg_type별 표시 정보
    TYPE_LABELS = {
        "arena_report": {"emoji": "📊", "label": "Arena 일일 결과"},
        "healthcheck": {"emoji": "🏥", "label": "헬스체크"},
        "stock_selection": {"emoji": "📋", "label": "종목 선정"},
        "buy_signal": {"emoji": "🟢", "label": "매수 신호"},
        "sell_profit": {"emoji": "🎯", "label": "익절 신호"},
        "sell_loss": {"emoji": "🛑", "label": "손절 신호"},
        "sell_batch": {"emoji": "📈", "label": "장중 매매 신호"},
        "daily_summary": {"emoji": "📊", "label": "일일 현황"},
        "error_alert": {"emoji": "🚨", "label": "오류 알림"},
        "custom": {"emoji": "📢", "label": "커스텀 알림"},
    }

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token or os.environ.get('TELEGRAM_BOT_TOKEN')
        self.chat_id = chat_id or os.environ.get('TELEGRAM_CHAT_ID')
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    def is_configured(self) -> bool:
        """설정 여부 확인"""
        return bool(self.bot_token and self.chat_id)

    def _log_send(self, success: bool, msg_type: str, preview: str,
                  full_message: str = "", error: str = ""):
        """발송 이력을 일별 jsonl 파일에 기록 (logs/telegram/YYYY-MM-DD.jsonl)"""
        try:
            kst = timezone(timedelta(hours=9))
            now = datetime.now(kst)
            date_str = now.strftime("%Y-%m-%d")
            type_info = self.TYPE_LABELS.get(msg_type, {"emoji": "📨", "label": msg_type})

            entry = {
                "timestamp": now.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
                "time": now.strftime("%H:%M:%S"),
                "success": success,
                "type": msg_type,
                "emoji": type_info["emoji"],
                "label": type_info["label"],
                "preview": preview[:100],
                "message": full_message[:2000] if full_message else preview[:200],
            }
            if error:
                entry["error"] = str(error)[:300]

            os.makedirs(self.LOG_DIR, exist_ok=True)
            log_path = os.path.join(self.LOG_DIR, f"{date_str}.jsonl")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass  # 로깅 실패가 발송을 막으면 안 됨

    def send_message(self, text: str, parse_mode: str = "HTML",
                     msg_type: str = "custom") -> bool:
        """메시지 전송"""
        if not self.is_configured():
            print("[Telegram] 설정되지 않음 - TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 필요")
            self._log_send(False, msg_type, text[:100], text, "not_configured")
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
                self._log_send(True, msg_type, text[:100], text)
                return True
            else:
                print(f"[Telegram] 전송 실패: {response.text}")
                self._log_send(False, msg_type, text[:100], text, response.text[:300])
                return False

        except Exception as e:
            print(f"[Telegram] 오류: {e}")
            self._log_send(False, msg_type, text[:100], text, str(e))
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
        return self.send_message(message.strip(), msg_type="buy_signal")

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
        return self.send_message(message.strip(), msg_type=f"sell_{signal_type}")

    def send_sell_signals_batch(self, signals: List[Dict]) -> bool:
        """익절/손절 신호를 한 건으로 취합 발송 + 중복 방지"""
        if not signals:
            return False

        # 중복 방지: 오늘 이미 발송한 종목 제외
        sent_codes = self._get_today_sent_codes()
        new_signals = [s for s in signals if s.get('code', '') not in sent_codes]

        if not new_signals:
            print(f"모든 {len(signals)}건 이미 발송됨 - 생략")
            return False

        kst = timezone(timedelta(hours=9))
        now = datetime.now(kst).strftime("%Y-%m-%d %H:%M")

        profits = [s for s in new_signals if s['signal_type'] == 'profit']
        losses = [s for s in new_signals if s['signal_type'] == 'loss']

        lines = [f"<b>📈 장중 매매 신호</b> ({len(new_signals)}건)", ""]

        if profits:
            lines.append(f"<b>🎯 익절 ({len(profits)}건)</b>")
            for s in profits:
                pnl_sign = "+" if s['pnl_pct'] >= 0 else ""
                lines.append(
                    f"  • {s['name']}({s['code']}) "
                    f"{s['price']:,}원 🟢{pnl_sign}{s['pnl_pct']:.2f}%"
                )
            lines.append("")

        if losses:
            lines.append(f"<b>🛑 손절 ({len(losses)}건)</b>")
            for s in losses:
                pnl_sign = "+" if s['pnl_pct'] >= 0 else ""
                lines.append(
                    f"  • {s['name']}({s['code']}) "
                    f"{s['price']:,}원 🔴{pnl_sign}{s['pnl_pct']:.2f}%"
                )
            lines.append("")

        lines.append(f"<i>⏰ {now}</i>")

        msg_type = "sell_batch"
        message = "\n".join(lines)
        return self.send_message(message, msg_type=msg_type)

    def _get_today_sent_codes(self) -> set:
        """오늘 이미 익절/손절 발송한 종목코드 set 반환"""
        kst = timezone(timedelta(hours=9))
        today = datetime.now(kst).strftime("%Y-%m-%d")
        log_file = os.path.join(self.LOG_DIR, f"{today}.jsonl")

        sent = set()
        if not os.path.exists(log_file):
            return sent

        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    if entry.get('type') in ('sell_profit', 'sell_loss', 'sell_batch') and entry.get('success'):
                        # 메시지에서 종목코드 추출 (괄호 안 6자리 숫자)
                        import re
                        codes = re.findall(r'\((\d{6})\)', entry.get('message', ''))
                        sent.update(codes)
        except Exception:
            pass
        return sent

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
        return self.send_message(message.strip(), msg_type="daily_summary")

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
                change = s.get('change_pct', 0)
                strategy = s.get('strategy', '')
                chg_sign = "+" if change >= 0 else ""
                chg_emoji = "🔴" if change > 0 else "🔵" if change < 0 else "⚪"
                strat_tag = f" [{strategy}]" if strategy else ""
                stock_lines.append(f"{i}. {name} ({code}) {chg_emoji}{chg_sign}{change:.2f}% · {score}점{strat_tag}")

            stocks_text = "\n".join(stock_lines)

            message = f"""
<b>📋 종목 선정 완료</b>

<b>전략:</b> {strategy or "기본"}
<b>선정:</b> {len(stocks)}개

{stocks_text}

<i>⏰ {now}</i>
"""
        return self.send_message(message.strip(), msg_type="stock_selection")

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
        return self.send_message(alert.strip(), msg_type="error_alert")

    def send_custom(self, title: str, content: str, emoji: str = "📢") -> bool:
        """커스텀 알림"""
        kst = timezone(timedelta(hours=9))
        now = datetime.now(kst).strftime("%Y-%m-%d %H:%M")

        message = f"""
<b>{emoji} {title}</b>

{content}

<i>⏰ {now}</i>
"""
        return self.send_message(message.strip(), msg_type="custom")


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
