"""
백테스팅 리포트 생성
data/intraday/*.json 파일들을 분석하여 종합 리포트 생성
"""

import json
import os
from datetime import datetime
from collections import defaultdict
import glob

class BacktestReporter:
    def __init__(self):
        self.intraday_dir = 'data/intraday'
        self.report_output = 'data/backtest_report.html'

    def load_all_intraday_data(self):
        """모든 장중 데이터 로드"""
        all_data = []

        pattern = os.path.join(self.intraday_dir, 'intraday_*.json')
        files = sorted(glob.glob(pattern))

        print(f"📁 {len(files)}개 백테스트 파일 발견")

        for filepath in files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    date = data.get('date', '')
                    stocks = data.get('stocks', {})

                    for code, stock_data in stocks.items():
                        pl = stock_data.get('profit_loss_analysis')
                        if pl:
                            all_data.append({
                                'date': date,
                                'code': code,
                                'name': stock_data.get('name', ''),
                                'score': stock_data.get('selection_score', 0),
                                'reason': stock_data.get('selection_reason', ''),
                                'opening_price': pl.get('opening_price', 0),
                                'closing_price': pl.get('closing_price', 0),
                                'closing_percent': pl.get('closing_percent', 0),
                                'first_hit': pl.get('first_hit', 'none'),
                                'first_hit_time': pl.get('first_hit_time', ''),
                                'max_profit_percent': pl.get('max_profit_percent', 0),
                                'max_loss_percent': pl.get('max_loss_percent', 0),
                                'profit_target_percent': pl.get('profit_target_percent', 3.0),
                                'loss_target_percent': pl.get('loss_target_percent', -2.0),
                            })
            except Exception as e:
                print(f"⚠️  파일 로드 실패 ({filepath}): {e}")

        print(f"✓ 총 {len(all_data)}개 종목 데이터 로드 완료")
        return all_data

    def calculate_statistics(self, data):
        """전체 통계 계산"""
        if not data:
            return None

        total = len(data)
        profit_count = sum(1 for d in data if d['first_hit'] == 'profit')
        loss_count = sum(1 for d in data if d['first_hit'] == 'loss')
        none_count = sum(1 for d in data if d['first_hit'] == 'none')

        win_rate = (profit_count / total * 100) if total > 0 else 0

        # 평균 수익률 (종가 기준)
        avg_return = sum(d['closing_percent'] for d in data) / total if total > 0 else 0

        # 익절 도달한 종목만
        profit_returns = [d['closing_percent'] for d in data if d['first_hit'] == 'profit']
        avg_profit_return = sum(profit_returns) / len(profit_returns) if profit_returns else 0

        # 손절 도달한 종목만
        loss_returns = [d['closing_percent'] for d in data if d['first_hit'] == 'loss']
        avg_loss_return = sum(loss_returns) / len(loss_returns) if loss_returns else 0

        # 최대 수익/손실
        max_profit = max(d['closing_percent'] for d in data) if data else 0
        max_loss = min(d['closing_percent'] for d in data) if data else 0

        return {
            'total': total,
            'profit_count': profit_count,
            'loss_count': loss_count,
            'none_count': none_count,
            'win_rate': win_rate,
            'avg_return': avg_return,
            'avg_profit_return': avg_profit_return,
            'avg_loss_return': avg_loss_return,
            'max_profit': max_profit,
            'max_loss': max_loss,
        }

    def analyze_by_score_range(self, data):
        """점수대별 성과 분석"""
        score_ranges = [
            (70, 145, '70점 이상 (고득점)'),
            (50, 70, '50-70점 (중득점)'),
            (30, 50, '30-50점 (저득점)'),
            (0, 30, '30점 미만 (극저점)'),
        ]

        results = []

        for min_score, max_score, label in score_ranges:
            filtered = [d for d in data if min_score <= d['score'] < max_score]
            stats = self.calculate_statistics(filtered)

            if stats and stats['total'] > 0:
                results.append({
                    'label': label,
                    'range': f"{min_score}-{max_score}점",
                    'stats': stats,
                })

        return results

    def analyze_by_date(self, data):
        """날짜별 성과 분석"""
        by_date = defaultdict(list)

        for d in data:
            by_date[d['date']].append(d)

        results = []
        for date in sorted(by_date.keys(), reverse=True):
            stats = self.calculate_statistics(by_date[date])
            if stats:
                results.append({
                    'date': date,
                    'stats': stats,
                    'stocks': by_date[date]
                })

        return results

    def generate_html_report(self, all_data):
        """HTML 리포트 생성"""
        overall_stats = self.calculate_statistics(all_data)
        score_analysis = self.analyze_by_score_range(all_data)
        date_analysis = self.analyze_by_date(all_data)

        html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>백테스팅 리포트</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            color: #333;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        .header {{
            background: white;
            padding: 30px;
            border-radius: 15px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .header h1 {{
            font-size: 28px;
            color: #667eea;
            margin-bottom: 10px;
        }}
        .header .meta {{
            color: #666;
            font-size: 14px;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .stat-card .label {{
            font-size: 12px;
            color: #666;
            margin-bottom: 5px;
        }}
        .stat-card .value {{
            font-size: 24px;
            font-weight: bold;
            color: #333;
        }}
        .stat-card.positive .value {{ color: #e74c3c; }}
        .stat-card.negative .value {{ color: #3498db; }}
        .section {{
            background: white;
            padding: 25px;
            border-radius: 15px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .section h2 {{
            font-size: 20px;
            margin-bottom: 20px;
            color: #667eea;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }}
        th {{
            background: #f8f9fa;
            font-weight: 600;
            color: #666;
            font-size: 13px;
        }}
        td {{
            font-size: 14px;
        }}
        .positive {{ color: #e74c3c; font-weight: 600; }}
        .negative {{ color: #3498db; font-weight: 600; }}
        .badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }}
        .badge.profit {{ background: #fee; color: #e74c3c; }}
        .badge.loss {{ background: #eef; color: #3498db; }}
        .badge.none {{ background: #f0f0f0; color: #999; }}
        .progress-bar {{
            height: 8px;
            background: #eee;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 8px;
        }}
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #667eea, #764ba2);
            transition: width 0.3s;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 백테스팅 리포트</h1>
            <div class="meta">
                생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} |
                분석 기간: {len(date_analysis)}일 |
                총 종목: {overall_stats['total'] if overall_stats else 0}개
            </div>
        </div>
"""

        # 전체 통계
        if overall_stats:
            html += f"""
        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">총 종목</div>
                <div class="value">{overall_stats['total']}개</div>
            </div>
            <div class="stat-card positive">
                <div class="label">승률</div>
                <div class="value">{overall_stats['win_rate']:.1f}%</div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {overall_stats['win_rate']:.1f}%"></div>
                </div>
            </div>
            <div class="stat-card">
                <div class="label">평균 수익률</div>
                <div class="value {'positive' if overall_stats['avg_return'] > 0 else 'negative'}">
                    {overall_stats['avg_return']:+.2f}%
                </div>
            </div>
            <div class="stat-card positive">
                <div class="label">익절 성공</div>
                <div class="value">{overall_stats['profit_count']}건</div>
            </div>
            <div class="stat-card negative">
                <div class="label">손절 발생</div>
                <div class="value">{overall_stats['loss_count']}건</div>
            </div>
            <div class="stat-card">
                <div class="label">미도달</div>
                <div class="value">{overall_stats['none_count']}건</div>
            </div>
            <div class="stat-card positive">
                <div class="label">최대 수익</div>
                <div class="value">+{overall_stats['max_profit']:.2f}%</div>
            </div>
            <div class="stat-card negative">
                <div class="label">최대 손실</div>
                <div class="value">{overall_stats['max_loss']:.2f}%</div>
            </div>
        </div>
"""

        # 점수대별 분석
        if score_analysis:
            html += """
        <div class="section">
            <h2>점수대별 성과 분석</h2>
            <table>
                <thead>
                    <tr>
                        <th>점수 범위</th>
                        <th>종목 수</th>
                        <th>승률</th>
                        <th>평균 수익률</th>
                        <th>익절</th>
                        <th>손절</th>
                        <th>미도달</th>
                    </tr>
                </thead>
                <tbody>
"""
            for analysis in score_analysis:
                stats = analysis['stats']
                html += f"""
                    <tr>
                        <td><strong>{analysis['label']}</strong></td>
                        <td>{stats['total']}개</td>
                        <td class="{'positive' if stats['win_rate'] > 50 else ''}">{stats['win_rate']:.1f}%</td>
                        <td class="{'positive' if stats['avg_return'] > 0 else 'negative'}">{stats['avg_return']:+.2f}%</td>
                        <td>{stats['profit_count']}</td>
                        <td>{stats['loss_count']}</td>
                        <td>{stats['none_count']}</td>
                    </tr>
"""
            html += """
                </tbody>
            </table>
        </div>
"""

        # 날짜별 상세
        if date_analysis:
            html += """
        <div class="section">
            <h2>날짜별 상세 내역</h2>
"""
            for day in date_analysis:
                date_str = day['date']
                stats = day['stats']
                stocks = day['stocks']

                # 날짜 포맷 (YYYYMMDD -> YYYY-MM-DD)
                if len(date_str) == 8:
                    formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
                else:
                    formatted_date = date_str

                html += f"""
            <h3 style="margin-top: 25px; margin-bottom: 15px; color: #333;">{formatted_date}</h3>
            <div class="stats-grid" style="margin-bottom: 15px;">
                <div class="stat-card">
                    <div class="label">종목 수</div>
                    <div class="value">{stats['total']}개</div>
                </div>
                <div class="stat-card">
                    <div class="label">승률</div>
                    <div class="value {'positive' if stats['win_rate'] > 50 else ''}">{stats['win_rate']:.1f}%</div>
                </div>
                <div class="stat-card">
                    <div class="label">평균 수익률</div>
                    <div class="value {'positive' if stats['avg_return'] > 0 else 'negative'}">{stats['avg_return']:+.2f}%</div>
                </div>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>종목명</th>
                        <th>점수</th>
                        <th>결과</th>
                        <th>시초가</th>
                        <th>종가</th>
                        <th>수익률</th>
                        <th>도달시간</th>
                    </tr>
                </thead>
                <tbody>
"""
                for stock in sorted(stocks, key=lambda x: x['score'], reverse=True):
                    result_badge = ''
                    if stock['first_hit'] == 'profit':
                        result_badge = '<span class="badge profit">익절</span>'
                    elif stock['first_hit'] == 'loss':
                        result_badge = '<span class="badge loss">손절</span>'
                    else:
                        result_badge = '<span class="badge none">미도달</span>'

                    html += f"""
                    <tr>
                        <td><strong>{stock['name']}</strong></td>
                        <td>{stock['score']:.0f}점</td>
                        <td>{result_badge}</td>
                        <td>{stock['opening_price']:,}원</td>
                        <td>{stock['closing_price']:,}원</td>
                        <td class="{'positive' if stock['closing_percent'] > 0 else 'negative'}">
                            {stock['closing_percent']:+.2f}%
                        </td>
                        <td style="font-size: 12px; color: #999;">{stock['first_hit_time'] or '-'}</td>
                    </tr>
"""
                html += """
                </tbody>
            </table>
"""
            html += """
        </div>
"""

        html += """
    </div>
</body>
</html>
"""

        return html

    def generate_report(self):
        """리포트 생성 메인 함수"""
        print("\n" + "="*60)
        print("📊 백테스팅 리포트 생성")
        print("="*60)

        # 데이터 로드
        all_data = self.load_all_intraday_data()

        if not all_data:
            print("⚠️  분석할 데이터가 없습니다.")
            return None

        # HTML 리포트 생성
        print("\n📝 HTML 리포트 생성 중...")
        html = self.generate_html_report(all_data)

        # 파일 저장
        os.makedirs(os.path.dirname(self.report_output), exist_ok=True)
        with open(self.report_output, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"✅ 리포트 생성 완료: {self.report_output}")

        # 요약 출력
        overall_stats = self.calculate_statistics(all_data)
        if overall_stats:
            print("\n" + "="*60)
            print("📈 백테스팅 요약")
            print("="*60)
            print(f"  총 종목: {overall_stats['total']}개")
            print(f"  승률: {overall_stats['win_rate']:.1f}%")
            print(f"  평균 수익률: {overall_stats['avg_return']:+.2f}%")
            print(f"  익절 성공: {overall_stats['profit_count']}건 ({overall_stats['profit_count']/overall_stats['total']*100:.1f}%)")
            print(f"  손절 발생: {overall_stats['loss_count']}건 ({overall_stats['loss_count']/overall_stats['total']*100:.1f}%)")
            print(f"  미도달: {overall_stats['none_count']}건 ({overall_stats['none_count']/overall_stats['total']*100:.1f}%)")
            print("="*60)

        return self.report_output


if __name__ == '__main__':
    reporter = BacktestReporter()
    reporter.generate_report()
