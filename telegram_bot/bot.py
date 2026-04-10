"""
Telegram Bot Server (Railway 배포용)
실시간 명령어 응답 + 알림 전송
"""

import os
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# 로깅 설정
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 환경 변수
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'username/news-trading-bot')  # 변경 필요
GITHUB_BRANCH = os.environ.get('GITHUB_BRANCH', 'main')

# KST 시간대
KST = timezone(timedelta(hours=9))


def get_today() -> str:
    """오늘 날짜 (YYYYMMDD)"""
    return datetime.now(KST).strftime('%Y%m%d')


def fetch_github_json(path: str) -> Optional[dict]:
    """GitHub raw 파일에서 JSON 로드"""
    url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{path}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            logger.warning(f"GitHub fetch failed: {url} -> {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"GitHub fetch error: {e}")
        return None


# === 명령어 핸들러 ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """시작 명령어"""
    welcome = """
🤖 <b>Trading Bot 활성화!</b>

사용 가능한 명령어:

📊 <b>조회</b>
/status (/s) - 현재 포트폴리오 상태
/today (/t) - 오늘 선정 종목
/pnl (/p) - 수익률 현황

📈 <b>분석</b>
/top (/tp) - 상위 종목 (점수순)
/signals (/sg) - 최근 매매 신호
/strategies (/st) - 전략 4종 설명

⚙️ <b>기타</b>
/help (/h) - 도움말
/ping (/pi) - 봇 상태 확인

아무 텍스트나 입력하면 자연어로 질문할 수 있어요!
"""
    await update.message.reply_text(welcome.strip(), parse_mode='HTML')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """도움말"""
    help_text = """
📖 <b>명령어 도움말</b>

<b>/status</b>
현재 보유 중인 종목과 손익 상태

<b>/today</b>
오늘 아침에 선정된 종목 리스트

<b>/pnl</b>
전체 수익률 및 통계

<b>/top</b>
점수 상위 종목 (매수 후보)

<b>/signals</b>
최근 익절/손절 신호

<b>/strategies</b>
다중 전략 4종(대형주역추세/모멘텀/테마/DART공시) 설명

<b>/ping</b>
봇 응답 확인

⚡ <b>단축키</b>
/s=status, /t=today, /p=pnl, /tp=top
/sg=signals, /st=strategies, /h=help, /pi=ping

💡 자연어 질문도 가능해요:
"삼성전자 어때?" "오늘 뭐 살까?"
"""
    await update.message.reply_text(help_text.strip(), parse_mode='HTML')


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """봇 상태 확인"""
    now = datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')
    await update.message.reply_text(f"🏓 Pong!\n⏰ {now} KST")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """현재 포트폴리오 상태"""
    today = get_today()
    data = fetch_github_json(f"data/paper_trading/status_{today}.json")

    if not data:
        await update.message.reply_text("📊 오늘 상태 데이터가 없습니다.")
        return

    total = data.get('total_stocks', 0)
    profit_hit = data.get('profit_hit', 0)
    loss_hit = data.get('loss_hit', 0)
    waiting = data.get('waiting', 0)

    # 종목별 상태
    stocks_text = ""
    for s in data.get('stocks', [])[:10]:
        if s['status'] == 'profit_hit':
            icon = '✅'
        elif s['status'] == 'loss_hit':
            icon = '❌'
        else:
            icon = '⏳'

        pnl = s.get('pnl_pct', 0)
        pnl_str = f"+{pnl:.1f}%" if pnl >= 0 else f"{pnl:.1f}%"
        stocks_text += f"{icon} {s['name']}: {pnl_str}\n"

    message = f"""
📊 <b>포트폴리오 현황</b>

총 종목: {total}개
✅ 익절: {profit_hit}개
❌ 손절: {loss_hit}개
⏳ 대기: {waiting}개

<b>종목별 상태:</b>
{stocks_text}
⏰ {data.get('checked_at', 'N/A')}
"""
    await update.message.reply_text(message.strip(), parse_mode='HTML')


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """오늘 선정 종목"""
    today_str = get_today()
    data = fetch_github_json(f"data/paper_trading/candidates_{today_str}_all.json")

    if not data:
        await update.message.reply_text("📋 오늘 선정된 종목이 없습니다.")
        return

    strategies = data.get('strategies', {})

    message = f"📋 <b>오늘의 선정 종목</b> ({today_str})\n\n"

    for sid, result in strategies.items():
        name = result.get('strategy_name', sid)
        candidates = result.get('candidates', [])

        if candidates:
            message += f"<b>▸ {name}</b>\n"
            for c in candidates[:5]:
                score = c.get('score', 0)
                change = c.get('change_pct', 0)
                change_str = f"+{change:.1f}%" if change >= 0 else f"{change:.1f}%"
                message += f"  • {c['name']} ({score}점, {change_str})\n"
            message += "\n"

    await update.message.reply_text(message.strip(), parse_mode='HTML')


async def pnl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """수익률 현황"""
    today = get_today()
    data = fetch_github_json(f"data/paper_trading/status_{today}.json")

    if not data:
        await update.message.reply_text("📈 수익률 데이터가 없습니다.")
        return

    total_pnl = data.get('total_pnl_pct', 0)
    pnl_sign = "+" if total_pnl >= 0 else ""
    pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"

    win_count = data.get('profit_hit', 0)
    loss_count = data.get('loss_hit', 0)
    total_trades = win_count + loss_count
    win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0

    message = f"""
📈 <b>수익률 현황</b>

<b>오늘 총 수익률:</b> {pnl_emoji} {pnl_sign}{total_pnl:.2f}%

<b>매매 통계:</b>
• 총 청산: {total_trades}건
• 익절: {win_count}건
• 손절: {loss_count}건
• 승률: {win_rate:.1f}%

⏰ 기준: {data.get('checked_at', 'N/A')}
"""
    await update.message.reply_text(message.strip(), parse_mode='HTML')


async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """상위 종목"""
    today = get_today()
    data = fetch_github_json(f"data/paper_trading/candidates_{today}_all.json")

    if not data:
        await update.message.reply_text("🏆 종목 데이터가 없습니다.")
        return

    # 전체 종목 수집
    all_stocks = []
    for sid, result in data.get('strategies', {}).items():
        for c in result.get('candidates', []):
            c['strategy'] = result.get('strategy_name', sid)
            all_stocks.append(c)

    # 점수순 정렬
    all_stocks.sort(key=lambda x: x.get('score', 0), reverse=True)
    top_10 = all_stocks[:10]

    message = "🏆 <b>점수 상위 종목</b>\n\n"
    for i, s in enumerate(top_10, 1):
        score = s.get('score', 0)
        change = s.get('change_pct', 0)
        change_str = f"+{change:.1f}%" if change >= 0 else f"{change:.1f}%"
        message += f"{i}. <b>{s['name']}</b> - {score}점 ({change_str})\n"
        message += f"   └ {s.get('strategy', 'N/A')}\n"

    await update.message.reply_text(message.strip(), parse_mode='HTML')


async def signals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """최근 매매 신호"""
    today = get_today()
    data = fetch_github_json(f"data/paper_trading/status_{today}.json")

    if not data:
        await update.message.reply_text("🔔 신호 데이터가 없습니다.")
        return

    message = "🔔 <b>최근 매매 신호</b>\n\n"

    has_signals = False
    for s in data.get('stocks', []):
        if s['status'] in ['profit_hit', 'loss_hit']:
            has_signals = True
            if s['status'] == 'profit_hit':
                icon = '🎯 익절'
            else:
                icon = '🛑 손절'

            pnl = s.get('pnl_pct', 0)
            pnl_str = f"+{pnl:.1f}%" if pnl >= 0 else f"{pnl:.1f}%"
            message += f"{icon}: <b>{s['name']}</b> ({pnl_str})\n"

    if not has_signals:
        message += "오늘 발생한 신호가 없습니다."

    await update.message.reply_text(message.strip(), parse_mode='HTML')


async def strategies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """전략 설명"""
    message = """
📚 <b>다중 전략 시스템 (4개)</b>

━━━━━━━━━━━━━━━━━━━━

1️⃣ <b>대형주 역추세</b>
시총 상위 대형주 중 전일 하락 종목에서 반등 기회 포착

• 조건: 시총 1조↑, 전일 -1.5%↓, 거래대금 50억↑
• 배점: 시총 30 + 하락폭 25 + 거래대금 20 + 가격대 15 + 변동성 10
• 원리: 대형주는 급락 후 기관/외국인 저가매수로 반등 확률 높음

━━━━━━━━━━━━━━━━━━━━

2️⃣ <b>모멘텀 추세</b>
전일 급등 종목 중 거래대금 상위 - 추세 추종

• 조건: 전일 +3%~+15%, 거래대금 30억↑
• 배점: 상승률 35 + 거래대금 30 + 거래량급증 20 + 가격대 15
• 원리: 강한 상승 추세에 편승, 거래량 수반 시 추가 상승 기대

━━━━━━━━━━━━━━━━━━━━

3️⃣ <b>테마/정책</b>
네이버 금융 상승 테마 기반 종목 선정

• 조건: 당일 상승 테마 감지 → 테마 내 종목 자동 선정
• 배점: 테마관련도 40 + 등락률 25 + 거래대금 20 + 테마강도 15
• 원리: 방산·반도체·바이오 등 시장 테마 흐름에 올라탐

━━━━━━━━━━━━━━━━━━━━

4️⃣ <b>DART 공시</b>
전일 18:00~당일 08:30 긍정 공시 종목 - 시초가 매매

• 조건: 시총 1000억~10조, 거래대금 10억↑
• 배점: 공시점수 40 + 등락률 25 + 거래대금 20 + 시총 15
• 원리: 실적·계약·투자 등 긍정 공시 발표 후 시초가 갭업 노림

━━━━━━━━━━━━━━━━━━━━

💡 4개 전략이 매일 아침 동시 실행되어 종합 점수순으로 종목 선정
"""
    await update.message.reply_text(message.strip(), parse_mode='HTML')


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """일반 텍스트 메시지 처리"""
    text = update.message.text.lower()

    # 간단한 키워드 매칭
    if '상태' in text or 'status' in text:
        await status(update, context)
    elif '오늘' in text or '종목' in text:
        await today(update, context)
    elif '수익' in text or 'pnl' in text:
        await pnl(update, context)
    elif '상위' in text or 'top' in text or '추천' in text:
        await top(update, context)
    elif '신호' in text or '매매' in text:
        await signals(update, context)
    elif '전략' in text or 'strategy' in text:
        await strategies(update, context)
    else:
        await update.message.reply_text(
            "🤔 무슨 말씀이신지 잘 모르겠어요.\n"
            "/help 로 명령어를 확인해보세요!"
        )


async def post_init(application: Application):
    """봇 시작 시 명령어 메뉴 설정"""
    commands = [
        BotCommand("status", "포트폴리오 현황"),
        BotCommand("today", "오늘 선정 종목"),
        BotCommand("pnl", "수익률 현황"),
        BotCommand("top", "점수 상위 종목"),
        BotCommand("signals", "최근 매매 신호"),
        BotCommand("strategies", "전략 4종 설명"),
        BotCommand("help", "도움말"),
        BotCommand("ping", "봇 상태 확인"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands registered")


def main():
    """봇 실행"""
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return

    # 애플리케이션 생성
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # 핸들러 등록 (정식명 + 단축 alias)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler(["help", "h"], help_command))
    application.add_handler(CommandHandler(["ping", "pi"], ping))
    application.add_handler(CommandHandler(["status", "s"], status))
    application.add_handler(CommandHandler(["today", "t"], today))
    application.add_handler(CommandHandler(["pnl", "p"], pnl))
    application.add_handler(CommandHandler(["top", "tp"], top))
    application.add_handler(CommandHandler(["signals", "sg"], signals))
    application.add_handler(CommandHandler(["strategies", "st"], strategies))

    # 일반 메시지 핸들러
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # 봇 실행 (Polling 모드)
    logger.info("Bot starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
