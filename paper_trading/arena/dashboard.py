"""
Arena 대시보드 - HTML 생성
- 4팀 리더보드 + ELO
- 팀별 포트폴리오 / 일일 기록 / 학습 노트
- 헬스체크 & 에러 로그
- BNF 별도 섹션
"""

import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

KST = timezone(timedelta(hours=9))

ARENA_DIR = Path(__file__).parent.parent.parent / "data" / "arena"
DATA_DIR = Path(__file__).parent.parent.parent / "data"
BNF_DIR = DATA_DIR / "bnf"


def generate_arena_dashboard() -> str:
    """아레나 대시보드 HTML 생성"""
    from .team import Team, TEAM_CONFIGS
    from .leaderboard import Leaderboard
    from .healthcheck import HealthChecker

    # 데이터 수집
    teams = {}
    for tid in TEAM_CONFIGS:
        try:
            teams[tid] = Team(tid)
        except Exception:
            pass

    lb = Leaderboard()
    ranking = lb.get_ranking()
    history = lb.get_daily_history(30)

    hc = HealthChecker()
    hc_data = hc.format_dashboard_data()

    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Arena - 4팀 경쟁 트레이딩 대시보드</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #0f0f1a; color: #e0e0e0; }}
.container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}

/* Header */
.header {{ text-align: center; padding: 30px 0; border-bottom: 2px solid #333; margin-bottom: 30px; }}
.header h1 {{ font-size: 2.2em; color: #fff; }}
.header .subtitle {{ color: #888; margin-top: 8px; }}
.header .updated {{ color: #666; font-size: 0.85em; margin-top: 5px; }}

/* Tabs */
.tabs {{ display: flex; gap: 4px; margin-bottom: 20px; border-bottom: 2px solid #333; }}
.tab {{ padding: 12px 24px; cursor: pointer; border: none; background: transparent;
        color: #888; font-size: 1em; border-bottom: 3px solid transparent;
        transition: all 0.2s; }}
.tab:hover {{ color: #ccc; background: #1a1a2e; }}
.tab.active {{ color: #fff; border-bottom-color: #4a9eff; background: #1a1a2e; }}

/* Tab content */
.tab-content {{ display: none; }}
.tab-content.active {{ display: block; }}

/* Cards */
.card {{ background: #1a1a2e; border-radius: 12px; padding: 24px; margin-bottom: 20px;
         border: 1px solid #2a2a4a; }}
.card h2 {{ font-size: 1.3em; margin-bottom: 16px; color: #fff; }}
.card h3 {{ font-size: 1.1em; margin: 16px 0 10px; color: #ccc; }}

/* Leaderboard */
.leaderboard {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }}
.team-card {{ background: #12122a; border-radius: 12px; padding: 20px;
              border: 2px solid #2a2a4a; position: relative; transition: transform 0.2s; }}
.team-card:hover {{ transform: translateY(-2px); }}
.team-card.rank-1 {{ border-color: #ffd700; box-shadow: 0 0 20px rgba(255,215,0,0.15); }}
.team-card.rank-2 {{ border-color: #c0c0c0; }}
.team-card.rank-3 {{ border-color: #cd7f32; }}
.team-card .rank-badge {{ position: absolute; top: -12px; right: 16px; font-size: 1.5em; }}
.team-card .team-name {{ font-size: 1.2em; font-weight: bold; margin-bottom: 8px; }}
.team-card .team-strategy {{ color: #888; font-size: 0.85em; margin-bottom: 12px; }}
.team-card .stat {{ display: flex; justify-content: space-between; padding: 6px 0;
                    border-bottom: 1px solid #222; }}
.team-card .stat:last-child {{ border: none; }}
.team-card .stat .label {{ color: #888; }}
.team-card .stat .value {{ font-weight: bold; }}
.positive {{ color: #4caf50; }}
.negative {{ color: #f44336; }}
.neutral {{ color: #888; }}

/* Table */
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #2a2a4a; }}
th {{ color: #888; font-weight: 600; font-size: 0.85em; text-transform: uppercase; }}
td {{ font-size: 0.95em; }}
tr:hover {{ background: #1e1e3a; }}

/* Health */
.health-status {{ display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px;
                  border-radius: 20px; font-size: 0.85em; font-weight: bold; }}
.health-healthy {{ background: #1b3a1b; color: #4caf50; }}
.health-warning {{ background: #3a3a1b; color: #ff9800; }}
.health-unhealthy {{ background: #3a1b1b; color: #f44336; }}

.health-dot {{ width: 8px; height: 8px; border-radius: 50%; }}
.dot-green {{ background: #4caf50; }}
.dot-yellow {{ background: #ff9800; }}
.dot-red {{ background: #f44336; }}

/* Journal */
.journal {{ max-height: 400px; overflow-y: auto; padding: 16px; background: #12122a;
            border-radius: 8px; font-family: monospace; font-size: 0.9em;
            line-height: 1.6; white-space: pre-wrap; }}

/* Chart placeholder */
.chart-area {{ height: 200px; background: #12122a; border-radius: 8px; display: flex;
               align-items: center; justify-content: center; color: #555; }}

/* BNF */
.bnf-section {{ border-left: 4px solid #9c27b0; }}

/* Responsive */
@media (max-width: 768px) {{
    .leaderboard {{ grid-template-columns: 1fr; }}
    .tabs {{ flex-wrap: wrap; }}
    .tab {{ flex: 1; text-align: center; min-width: 80px; font-size: 0.85em; padding: 10px; }}
}}
</style>
</head>
<body>
<div class="container">

<div class="header">
    <h1>🏟️ Arena - 4팀 경쟁 트레이딩</h1>
    <div class="subtitle">전략별 독립 팀 경쟁 시스템</div>
    <div class="updated">마지막 업데이트: {now}</div>
</div>

<div class="tabs">
    <button class="tab active" onclick="showTab('leaderboard')">🏆 리더보드</button>
    <button class="tab" onclick="showTab('teams')">👥 팀별 상세</button>
    <button class="tab" onclick="showTab('history')">📈 히스토리</button>
    <button class="tab" onclick="showTab('health')">🏥 헬스체크</button>
    <button class="tab" onclick="showTab('bnf')">🎯 BNF</button>
</div>

<!-- 리더보드 탭 -->
<div id="leaderboard" class="tab-content active">
{_render_leaderboard(teams, ranking, history)}
</div>

<!-- 팀별 상세 탭 -->
<div id="teams" class="tab-content">
{_render_teams_detail(teams)}
</div>

<!-- 히스토리 탭 -->
<div id="history" class="tab-content">
{_render_history(history, teams)}
</div>

<!-- 헬스체크 탭 -->
<div id="health" class="tab-content">
{_render_healthcheck(hc_data)}
</div>

<!-- BNF 탭 -->
<div id="bnf" class="tab-content">
{_render_bnf()}
</div>

</div>

<script>
function showTab(tabId) {{
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
    document.getElementById(tabId).classList.add('active');
    event.target.classList.add('active');
}}
</script>

</body>
</html>"""

    # 저장
    output_path = DATA_DIR / "arena_dashboard.html"
    output_path.write_text(html, encoding='utf-8')
    print(f"[Dashboard] 저장: {output_path}")

    return str(output_path)


def _render_leaderboard(teams: dict, ranking: list, history: list) -> str:
    """리더보드 섹션 렌더링"""
    medals = ["🥇", "🥈", "🥉", "4️⃣"]

    cards = []
    for t in ranking:
        tid = t["team_id"]
        team = teams.get(tid)
        if not team:
            continue

        pf = team.portfolio
        rank = t.get("elo_rank", 0)
        rank_class = f"rank-{rank}" if rank <= 3 else ""
        medal = medals[min(rank - 1, 3)]

        win_rate = round(pf.total_wins / pf.total_trades * 100, 1) if pf.total_trades > 0 else 0
        cap_class = "positive" if pf.total_return_pct > 0 else "negative" if pf.total_return_pct < 0 else "neutral"

        cards.append(f"""
    <div class="team-card {rank_class}">
        <div class="rank-badge">{medal}</div>
        <div class="team-name">{team.emoji} {team.team_name}</div>
        <div class="team-strategy">{team.description}</div>
        <div class="stat"><span class="label">ELO</span><span class="value">{t['elo']}</span></div>
        <div class="stat"><span class="label">누적 수익률</span><span class="value {cap_class}">{pf.total_return_pct:+.2f}%</span></div>
        <div class="stat"><span class="label">현재 자금</span><span class="value">{pf.current_capital:,.0f}원</span></div>
        <div class="stat"><span class="label">승/패</span><span class="value">{pf.total_wins}/{pf.total_losses}</span></div>
        <div class="stat"><span class="label">승률</span><span class="value">{win_rate:.1f}%</span></div>
        <div class="stat"><span class="label">거래일</span><span class="value">{pf.trading_days}일</span></div>
        <div class="stat"><span class="label">최대 연승</span><span class="value">{pf.max_win_streak}</span></div>
        <div class="stat"><span class="label">MDD</span><span class="value negative">{pf.max_drawdown_pct:.1f}%</span></div>
    </div>""")

    return f"""
    <div class="card">
        <h2>🏆 ELO 랭킹</h2>
        <div class="leaderboard">
            {''.join(cards)}
        </div>
    </div>"""


def _render_teams_detail(teams: dict) -> str:
    """팀별 상세 섹션"""
    sections = []

    for tid, team in teams.items():
        records = team.get_daily_records(10)
        journal = team.get_journal()
        param_history = team.get_param_history()

        # 최근 매매 기록 테이블
        trade_rows = ""
        for rec in records[:7]:
            sim = rec.get("simulation", {})
            date = rec.get("date", "")
            ret = sim.get("total_return", 0)
            ret_class = "positive" if ret > 0 else "negative" if ret < 0 else "neutral"
            wr = sim.get("win_rate", 0)
            trades = sim.get("total_trades", 0)
            trade_rows += f"""
            <tr>
                <td>{date}</td>
                <td class="{ret_class}">{ret:+.2f}%</td>
                <td>{wr:.0f}%</td>
                <td>{trades}건</td>
            </tr>"""

        # 파라미터 변경 이력
        param_rows = ""
        for p in param_history[-5:]:
            param_rows += f"""
            <tr>
                <td>{p.get('date', '')}</td>
                <td>{p.get('parameter', '')}</td>
                <td>{p.get('old_value', '')} → {p.get('new_value', '')}</td>
                <td>{p.get('reason', '')}</td>
            </tr>"""

        sections.append(f"""
    <div class="card">
        <h2>{team.emoji} {team.team_name}</h2>
        <p style="color:#888; margin-bottom:16px;">{team.description}</p>

        <h3>📊 최근 매매 기록</h3>
        <table>
            <thead><tr><th>날짜</th><th>수익률</th><th>승률</th><th>거래</th></tr></thead>
            <tbody>{trade_rows if trade_rows else '<tr><td colspan="4" style="text-align:center;color:#555">기록 없음</td></tr>'}</tbody>
        </table>

        <h3>🔧 파라미터 변경 이력</h3>
        <table>
            <thead><tr><th>날짜</th><th>파라미터</th><th>변경</th><th>사유</th></tr></thead>
            <tbody>{param_rows if param_rows else '<tr><td colspan="4" style="text-align:center;color:#555">변경 이력 없음</td></tr>'}</tbody>
        </table>

        <h3>📝 학습 노트</h3>
        <div class="journal">{journal if journal else '학습 노트 없음'}</div>
    </div>""")

    return "".join(sections)


def _render_history(history: list, teams: dict) -> str:
    """히스토리 테이블"""
    rows = ""
    for entry in reversed(history[-30:]):
        date = entry.get("date", "")
        ranking = entry.get("ranking", [])
        cells = f"<td>{date}</td>"
        for r in ranking:
            tid = r["team_id"]
            team = teams.get(tid)
            emoji = team.emoji if team else ""
            ret = r.get("total_return", 0)
            ret_class = "positive" if ret > 0 else "negative" if ret < 0 else "neutral"
            cells += f'<td class="{ret_class}">{r["rank"]}위 {emoji} {ret:+.2f}%</td>'
        rows += f"<tr>{cells}</tr>"

    # 헤더
    team_headers = ""
    for entry in history[-1:] if history else []:
        for r in entry.get("ranking", []):
            tid = r["team_id"]
            team = teams.get(tid)
            name = team.team_name if team else tid
            team_headers += f"<th>{name}</th>"

    return f"""
    <div class="card">
        <h2>📈 일일 성과 히스토리</h2>
        <table>
            <thead><tr><th>날짜</th>{team_headers}</tr></thead>
            <tbody>{rows if rows else '<tr><td colspan="5" style="text-align:center;color:#555">히스토리 없음</td></tr>'}</tbody>
        </table>
    </div>"""


def _render_healthcheck(hc_data: dict) -> str:
    """헬스체크 섹션"""
    recent = hc_data.get("recent_status", [])
    total = hc_data.get("total_checks", 0)
    unhealthy = hc_data.get("unhealthy_count", 0)
    warnings = hc_data.get("warning_count", 0)

    # 요약 카드
    summary_html = f"""
    <div class="card">
        <h2>🏥 헬스체크 현황</h2>
        <div style="display:flex; gap:24px; margin-bottom:20px;">
            <div>
                <span style="color:#888;">총 체크</span>
                <div style="font-size:1.8em; font-weight:bold;">{total}</div>
            </div>
            <div>
                <span style="color:#888;">에러</span>
                <div style="font-size:1.8em; font-weight:bold; color:#f44336;">{unhealthy}</div>
            </div>
            <div>
                <span style="color:#888;">경고</span>
                <div style="font-size:1.8em; font-weight:bold; color:#ff9800;">{warnings}</div>
            </div>
        </div>
    """

    # 최근 상태 테이블
    rows = ""
    for entry in recent:
        date = entry.get("date", "")
        status = entry.get("status", "")
        issues = entry.get("issues", 0)
        details = "; ".join(entry.get("details", []))

        if status == "healthy":
            badge = '<span class="health-status health-healthy"><span class="health-dot dot-green"></span>정상</span>'
        elif status == "warning":
            badge = '<span class="health-status health-warning"><span class="health-dot dot-yellow"></span>경고</span>'
        else:
            badge = '<span class="health-status health-unhealthy"><span class="health-dot dot-red"></span>에러</span>'

        rows += f"""
        <tr>
            <td>{date}</td>
            <td>{badge}</td>
            <td>{issues}건</td>
            <td style="max-width:400px; overflow:hidden; text-overflow:ellipsis;">{details or '-'}</td>
        </tr>"""

    summary_html += f"""
        <h3>최근 헬스체크 로그</h3>
        <table>
            <thead><tr><th>날짜</th><th>상태</th><th>이슈</th><th>상세</th></tr></thead>
            <tbody>{rows if rows else '<tr><td colspan="4" style="text-align:center;color:#555">로그 없음</td></tr>'}</tbody>
        </table>
    </div>"""

    return summary_html


def _render_bnf() -> str:
    """BNF 섹션 (별도 장기투자)"""
    # BNF 포지션 로드
    positions_html = ""
    positions_path = BNF_DIR / "positions.json"

    if positions_path.exists():
        try:
            with open(positions_path, 'r', encoding='utf-8') as f:
                positions = json.load(f)

            if isinstance(positions, dict):
                pos_list = positions.get("positions", [])
            else:
                pos_list = positions

            rows = ""
            for p in pos_list:
                name = p.get("name", p.get("stock_name", ""))
                code = p.get("code", p.get("stock_code", ""))
                entry = p.get("entry_price", p.get("avg_price", 0))
                current = p.get("current_price", 0)
                pnl = p.get("pnl_pct", p.get("return_pct", 0))
                pnl_class = "positive" if pnl > 0 else "negative" if pnl < 0 else "neutral"
                status = p.get("status", "holding")

                rows += f"""
                <tr>
                    <td>{name} ({code})</td>
                    <td>{entry:,}</td>
                    <td>{current:,}</td>
                    <td class="{pnl_class}">{pnl:+.2f}%</td>
                    <td>{status}</td>
                </tr>"""

            positions_html = f"""
            <table>
                <thead><tr><th>종목</th><th>매입가</th><th>현재가</th><th>수익률</th><th>상태</th></tr></thead>
                <tbody>{rows if rows else '<tr><td colspan="5" style="text-align:center;color:#555">포지션 없음</td></tr>'}</tbody>
            </table>"""
        except Exception:
            positions_html = '<p style="color:#555">포지션 데이터 로드 실패</p>'
    else:
        positions_html = '<p style="color:#555">BNF 포지션 데이터 없음</p>'

    # BNF 매매 이력
    history_html = ""
    history_path = BNF_DIR / "trade_history.json"
    if history_path.exists():
        try:
            with open(history_path, 'r', encoding='utf-8') as f:
                trades = json.load(f)

            if isinstance(trades, dict):
                trade_list = trades.get("trades", [])
            else:
                trade_list = trades

            rows = ""
            for t in trade_list[-10:]:
                rows += f"""
                <tr>
                    <td>{t.get('date', '')}</td>
                    <td>{t.get('name', t.get('stock_name', ''))}</td>
                    <td>{t.get('action', t.get('type', ''))}</td>
                    <td>{t.get('price', 0):,}</td>
                    <td>{t.get('reason', '')}</td>
                </tr>"""

            history_html = f"""
            <h3>📋 최근 매매 이력</h3>
            <table>
                <thead><tr><th>날짜</th><th>종목</th><th>매매</th><th>가격</th><th>사유</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>"""
        except Exception:
            pass

    return f"""
    <div class="card bnf-section">
        <h2>🎯 BNF 낙폭과대 장기투자</h2>
        <p style="color:#888; margin-bottom:16px;">경쟁 시스템과 별도 운영 - 낙폭과대 대형주 중장기 보유 전략</p>

        <h3>📊 현재 포지션</h3>
        {positions_html}
        {history_html}
    </div>"""


if __name__ == "__main__":
    generate_arena_dashboard()
    print("Arena 대시보드 생성 완료")
