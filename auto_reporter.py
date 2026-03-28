"""
자동 리포트 생성기
- 일간/주간/월간 리포트 자동 생성
- HTML 및 Markdown 형식 지원
- 지식 베이스 자동 업데이트
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from project_logger import ProjectLogger, ContextLoader, LOGS_DIR, DOCS_DIR, DATA_DIR


class AutoReporter:
    """자동 리포트 생성기"""

    def __init__(self):
        self.logger = ProjectLogger()
        self.context_loader = ContextLoader()
        self.reports_dir = DATA_DIR / "reports"
        self.reports_dir.mkdir(exist_ok=True)

    def generate_daily_report(self, date: str = None) -> str:
        """일간 리포트 생성"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        trades = self.logger.get_trades(start_date=date, end_date=date)

        if not trades:
            return f"[{date}] 매매 기록 없음"

        trade = trades[0]
        summary = trade.get("summary", {})

        report = f"""
# 일간 리포트 - {date}

## 요약
- **총 거래**: {summary.get('total_trades', 0)}건
- **승리**: {summary.get('wins', 0)}건 / **패배**: {summary.get('losses', 0)}건
- **승률**: {summary.get('win_rate', 0):.1f}%
- **총 수익률**: {summary.get('total_return', 0):+.2f}%
- **평균 수익률**: {summary.get('avg_return', 0):+.2f}%

## 시장 상황
"""
        market = trade.get("market_condition", {})
        if market:
            report += f"- 코스피: {market.get('kospi_change', 'N/A')}%\n"
            report += f"- 코스닥: {market.get('kosdaq_change', 'N/A')}%\n"

        report += "\n## 매매 상세\n"
        report += "| 종목 | 매수가 | 매도가 | 수익률 | 청산유형 |\n"
        report += "|------|--------|--------|--------|----------|\n"

        for r in trade.get("results", []):
            report += f"| {r.get('name', 'N/A')} | {r.get('entry_price', 0):,}원 | "
            report += f"{r.get('exit_price', 0):,}원 | {r.get('return_pct', 0):+.2f}% | "
            report += f"{r.get('exit_type', 'N/A')} |\n"

        # 저장
        report_file = self.reports_dir / f"daily_{date}.md"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)

        print(f"[REPORT] 일간 리포트 생성: {report_file}")
        return report

    def generate_weekly_report(self, end_date: str = None) -> str:
        """주간 리포트 생성"""
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")

        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        start_dt = end_dt - timedelta(days=6)
        start_date = start_dt.strftime("%Y-%m-%d")

        trades = self.logger.get_trades(start_date=start_date, end_date=end_date)

        # 주간 통계 계산
        total_trades = 0
        total_wins = 0
        total_returns = []

        for trade in trades:
            summary = trade.get("summary", {})
            total_trades += summary.get("total_trades", 0)
            total_wins += summary.get("wins", 0)
            if summary.get("total_return"):
                total_returns.append(summary.get("total_return", 0))

        win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
        avg_daily_return = sum(total_returns) / len(total_returns) if total_returns else 0
        total_return = sum(total_returns)

        report = f"""
# 주간 리포트

**기간**: {start_date} ~ {end_date}

## 주간 요약

| 지표 | 값 |
|------|-----|
| 거래일 | {len(trades)}일 |
| 총 거래 | {total_trades}건 |
| 승률 | {win_rate:.1f}% |
| 주간 수익률 | {total_return:+.2f}% |
| 일평균 수익률 | {avg_daily_return:+.2f}% |

## 일별 성과

| 날짜 | 거래수 | 승률 | 수익률 |
|------|--------|------|--------|
"""
        for trade in sorted(trades, key=lambda x: x.get("date", "")):
            s = trade.get("summary", {})
            report += f"| {trade.get('date')} | {s.get('total_trades', 0)} | "
            report += f"{s.get('win_rate', 0):.1f}% | {s.get('total_return', 0):+.2f}% |\n"

        # 의사결정 및 변경사항
        decisions = self.logger.get_decisions(limit=10)
        week_decisions = [d for d in decisions
                        if start_date <= d.get("date", "") <= end_date]

        if week_decisions:
            report += "\n## 금주 의사결정\n"
            for d in week_decisions:
                report += f"- **{d.get('title')}**: {d.get('description')[:50]}...\n"

        # 저장
        week_num = end_dt.isocalendar()[1]
        report_file = self.reports_dir / f"weekly_{end_dt.year}_W{week_num:02d}.md"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)

        print(f"[REPORT] 주간 리포트 생성: {report_file}")
        return report

    def generate_monthly_report(self, year: int = None, month: int = None) -> str:
        """월간 리포트 생성"""
        if year is None:
            year = datetime.now().year
        if month is None:
            month = datetime.now().month

        start_date = f"{year}-{month:02d}-01"
        if month == 12:
            end_date = f"{year + 1}-01-01"
        else:
            end_date = f"{year}-{month + 1:02d}-01"

        end_dt = datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=1)
        end_date = end_dt.strftime("%Y-%m-%d")

        trades = self.logger.get_trades(start_date=start_date, end_date=end_date)

        # 월간 통계
        total_trades = 0
        total_wins = 0
        daily_returns = []

        for trade in trades:
            summary = trade.get("summary", {})
            total_trades += summary.get("total_trades", 0)
            total_wins += summary.get("wins", 0)
            daily_returns.append(summary.get("total_return", 0))

        win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
        total_return = sum(daily_returns)
        avg_return = sum(daily_returns) / len(daily_returns) if daily_returns else 0

        # 복리 수익률 계산
        capital = 1000000
        for r in daily_returns:
            capital *= (1 + r / 100)
        compound_return = (capital - 1000000) / 1000000 * 100

        report = f"""
# 월간 리포트 - {year}년 {month}월

## 월간 요약

| 지표 | 값 |
|------|-----|
| 거래일 | {len(trades)}일 |
| 총 거래 | {total_trades}건 |
| 승률 | {win_rate:.1f}% |
| 단순 수익률 | {total_return:+.2f}% |
| 복리 수익률 | {compound_return:+.2f}% |
| 일평균 수익률 | {avg_return:+.2f}% |

## 100만원 기준 결과
- **시작 금액**: 1,000,000원
- **최종 금액**: {capital:,.0f}원
- **손익**: {capital - 1000000:+,.0f}원

## 주차별 성과

"""
        # 주차별 집계
        weeks = {}
        for trade in trades:
            trade_date = datetime.strptime(trade.get("date", ""), "%Y-%m-%d")
            week_num = trade_date.isocalendar()[1]
            week_key = f"W{week_num}"

            if week_key not in weeks:
                weeks[week_key] = {"trades": 0, "wins": 0, "returns": []}

            s = trade.get("summary", {})
            weeks[week_key]["trades"] += s.get("total_trades", 0)
            weeks[week_key]["wins"] += s.get("wins", 0)
            weeks[week_key]["returns"].append(s.get("total_return", 0))

        report += "| 주차 | 거래수 | 승률 | 수익률 |\n"
        report += "|------|--------|------|--------|\n"

        for week_key in sorted(weeks.keys()):
            w = weeks[week_key]
            w_win_rate = (w["wins"] / w["trades"] * 100) if w["trades"] > 0 else 0
            w_return = sum(w["returns"])
            report += f"| {week_key} | {w['trades']} | {w_win_rate:.1f}% | {w_return:+.2f}% |\n"

        # 월간 의사결정
        decisions = self.logger.get_decisions()
        month_decisions = [d for d in decisions
                         if d.get("date", "").startswith(f"{year}-{month:02d}")]

        if month_decisions:
            report += "\n## 월간 의사결정\n"
            for d in month_decisions:
                report += f"\n### {d.get('date')} - {d.get('title')}\n"
                report += f"- **내용**: {d.get('description')}\n"
                report += f"- **사유**: {d.get('reason')}\n"

        # 전략 변경
        strategy_changes = self.logger.get_strategy_history()
        month_changes = [c for c in strategy_changes
                        if c.get("date", "").startswith(f"{year}-{month:02d}")]

        if month_changes:
            report += "\n## 전략 변경\n"
            for c in month_changes:
                report += f"- **{c.get('strategy_name')}** ({c.get('change_type')}): {c.get('reason')}\n"

        # 저장
        report_file = self.reports_dir / f"monthly_{year}_{month:02d}.md"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)

        print(f"[REPORT] 월간 리포트 생성: {report_file}")
        return report

    def update_knowledge_base(self):
        """지식 베이스 자동 업데이트"""
        kb_file = DOCS_DIR / "PROJECT_KNOWLEDGE_BASE.md"

        # 기존 내용 로드
        if kb_file.exists():
            with open(kb_file, 'r', encoding='utf-8') as f:
                content = f.read()
        else:
            content = "# 프로젝트 지식 베이스\n\n"

        # 업데이트 섹션 추가
        update_section = f"""

---

## 자동 업데이트 섹션

**최종 업데이트**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

### 최근 의사결정 (최근 5건)

"""
        for d in self.logger.get_decisions(limit=5):
            update_section += f"- **{d.get('date')}** - {d.get('title')}: {d.get('reason')[:50]}...\n"

        update_section += "\n### 활성 규칙\n\n"
        for r in self.logger.get_rules(status="active"):
            update_section += f"- **{r.get('rule_name')}**: {r.get('description')}\n"

        update_section += "\n### 제약조건\n\n"
        for c in self.logger.get_constraints():
            update_section += f"- {c.get('constraint_name')}: {c.get('value')} ({c.get('reason')})\n"

        # 최근 매매 성과
        trades = self.logger.get_trades()[:30]  # 최근 30일
        if trades:
            total_returns = [t.get("summary", {}).get("total_return", 0) for t in trades]
            update_section += f"""
### 최근 30일 매매 성과

- 거래일: {len(trades)}일
- 총 수익률: {sum(total_returns):+.2f}%
- 일평균: {sum(total_returns)/len(total_returns):+.2f}%
"""

        # 기존 자동 업데이트 섹션 제거 후 새로 추가
        if "## 자동 업데이트 섹션" in content:
            content = content.split("## 자동 업데이트 섹션")[0].rstrip()
            content += "\n" + update_section
        else:
            content += update_section

        # 저장
        with open(kb_file, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"[REPORT] 지식 베이스 업데이트: {kb_file}")

    def generate_html_dashboard(self) -> str:
        """HTML 대시보드 리포트 생성"""
        ctx = self.context_loader.load_context()
        trades = self.logger.get_trades()[:30]

        # 통계 계산
        total_trades = sum(t.get("summary", {}).get("total_trades", 0) for t in trades)
        total_wins = sum(t.get("summary", {}).get("wins", 0) for t in trades)
        win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
        total_returns = [t.get("summary", {}).get("total_return", 0) for t in trades]
        total_return = sum(total_returns)

        html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>프로젝트 대시보드</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, sans-serif;
            background: #1a1a2e;
            color: #e4e4e4;
            padding: 20px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #00d9ff; margin-bottom: 20px; }}
        h2 {{ color: #00ff88; margin: 20px 0 15px; }}
        .stat-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .stat-card {{
            background: #16213e;
            border-radius: 15px;
            padding: 25px;
            text-align: center;
        }}
        .stat-value {{
            font-size: 2em;
            font-weight: bold;
            color: #00d9ff;
        }}
        .stat-value.positive {{ color: #00ff88; }}
        .stat-value.negative {{ color: #ff6b6b; }}
        .stat-label {{ color: #8892b0; margin-top: 10px; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #2a2a4a;
        }}
        th {{ background: #0f3460; color: #00d9ff; }}
        .section {{
            background: #16213e;
            border-radius: 10px;
            padding: 20px;
            margin: 20px 0;
        }}
        .timestamp {{ color: #8892b0; font-size: 0.9em; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>프로젝트 대시보드</h1>
        <p class="timestamp">최종 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

        <div class="stat-grid">
            <div class="stat-card">
                <div class="stat-value">{len(trades)}</div>
                <div class="stat-label">최근 거래일</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{total_trades}</div>
                <div class="stat-label">총 거래 수</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{win_rate:.1f}%</div>
                <div class="stat-label">승률</div>
            </div>
            <div class="stat-card">
                <div class="stat-value {'positive' if total_return > 0 else 'negative'}">{total_return:+.2f}%</div>
                <div class="stat-label">총 수익률</div>
            </div>
        </div>

        <div class="section">
            <h2>활성 규칙</h2>
            <table>
                <tr><th>규칙명</th><th>유형</th><th>설명</th></tr>
"""
        for r in ctx.get("active_rules", [])[:10]:
            html += f"<tr><td>{r.get('rule_name')}</td><td>{r.get('rule_type')}</td><td>{r.get('description')}</td></tr>\n"

        html += """
            </table>
        </div>

        <div class="section">
            <h2>제약조건</h2>
            <table>
                <tr><th>항목</th><th>값</th><th>사유</th></tr>
"""
        for c in ctx.get("constraints", []):
            html += f"<tr><td>{c.get('constraint_name')}</td><td>{c.get('value')}</td><td>{c.get('reason')}</td></tr>\n"

        html += """
            </table>
        </div>

        <div class="section">
            <h2>최근 의사결정</h2>
            <table>
                <tr><th>날짜</th><th>제목</th><th>사유</th></tr>
"""
        for d in ctx.get("recent_decisions", [])[:5]:
            html += f"<tr><td>{d.get('date')}</td><td>{d.get('title')}</td><td>{d.get('reason')[:50]}...</td></tr>\n"

        html += """
            </table>
        </div>

        <div class="section">
            <h2>최근 매매 기록</h2>
            <table>
                <tr><th>날짜</th><th>거래수</th><th>승률</th><th>수익률</th></tr>
"""
        for t in trades[:10]:
            s = t.get("summary", {})
            ret = s.get("total_return", 0)
            ret_class = "positive" if ret > 0 else "negative" if ret < 0 else ""
            html += f"<tr><td>{t.get('date')}</td><td>{s.get('total_trades', 0)}</td>"
            html += f"<td>{s.get('win_rate', 0):.1f}%</td>"
            html += f"<td class='{ret_class}'>{ret:+.2f}%</td></tr>\n"

        html += """
            </table>
        </div>
    </div>
</body>
</html>
"""
        # 저장
        dashboard_file = DATA_DIR / "dashboard_report.html"
        with open(dashboard_file, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"[REPORT] HTML 대시보드 생성: {dashboard_file}")
        return html


    def aggregate_paper_trading_results(self) -> dict:
        """페이퍼 트레이딩 결과 통합"""
        paper_dir = DATA_DIR / "paper_trading"
        if not paper_dir.exists():
            return {"daily_results": []}

        daily_results = []

        # 모든 결과 파일 읽기
        for result_file in sorted(paper_dir.glob("result_*.json")):
            try:
                with open(result_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                simulation = data.get("simulation", {})
                if simulation:
                    daily_results.append(simulation)
            except Exception as e:
                print(f"[WARN] 파일 읽기 실패: {result_file} - {e}")

        # 통합 결과 저장
        results = {"daily_results": daily_results}
        output_file = paper_dir / "results.json"

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"[REPORT] 페이퍼 트레이딩 결과 통합: {output_file}")
        return results


def main():
    """CLI 메인 함수"""
    import sys

    reporter = AutoReporter()

    if len(sys.argv) < 2:
        print("사용법: python auto_reporter.py [명령]")
        print("  daily   [날짜]    - 일간 리포트 생성")
        print("  weekly  [종료일]  - 주간 리포트 생성")
        print("  monthly [년] [월] - 월간 리포트 생성")
        print("  update            - 지식 베이스 업데이트")
        print("  dashboard         - HTML 대시보드 생성")
        print("  all               - 모든 리포트 생성")
        return

    command = sys.argv[1]

    if command == "daily":
        date = sys.argv[2] if len(sys.argv) > 2 else None
        reporter.generate_daily_report(date)

    elif command == "weekly":
        end_date = sys.argv[2] if len(sys.argv) > 2 else None
        reporter.generate_weekly_report(end_date)

    elif command == "monthly":
        year = int(sys.argv[2]) if len(sys.argv) > 2 else None
        month = int(sys.argv[3]) if len(sys.argv) > 3 else None
        reporter.generate_monthly_report(year, month)

    elif command == "update":
        reporter.update_knowledge_base()

    elif command == "dashboard":
        reporter.generate_html_dashboard()

    elif command == "aggregate":
        reporter.aggregate_paper_trading_results()

    elif command == "all":
        reporter.generate_daily_report()
        reporter.generate_weekly_report()
        reporter.generate_monthly_report()
        reporter.update_knowledge_base()
        reporter.generate_html_dashboard()
        reporter.aggregate_paper_trading_results()
        print("\n[완료] 모든 리포트가 생성되었습니다.")


if __name__ == "__main__":
    main()
