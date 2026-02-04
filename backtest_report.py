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
                            entry = {
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
                            }

                            # 멀티 시나리오 데이터 (있으면)
                            ms = stock_data.get('multi_scenario')
                            if ms and ms.get('scenarios'):
                                entry['multi_scenario'] = ms['scenarios']

                            # 단타 전략 데이터 (있으면)
                            scalp = stock_data.get('scalp_strategy')
                            if scalp:
                                entry['scalp_strategy'] = scalp

                            # 스윙 전략 데이터 (있으면)
                            swing = stock_data.get('swing_strategy')
                            if swing:
                                entry['swing_strategy'] = swing

                            all_data.append(entry)
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

    def calculate_equity_curve(self, data, initial_capital=10000000):
        """
        자본 증가 곡선 계산
        각 종목에 균등 투자했다고 가정 (일별 총 자본을 5등분)

        Args:
            data: 전체 백테스트 데이터
            initial_capital: 초기 자본금 (기본 1000만원)

        Returns:
            list: 일별 자본 변동 내역
        """
        by_date = defaultdict(list)
        for d in data:
            by_date[d['date']].append(d)

        equity_curve = []
        current_capital = initial_capital

        for date in sorted(by_date.keys()):
            stocks = by_date[date]
            num_stocks = len(stocks)

            if num_stocks == 0:
                continue

            # 각 종목에 균등 투자
            invest_per_stock = current_capital / num_stocks

            daily_profit_loss = 0
            daily_details = []

            for stock in stocks:
                # 종목별 수익/손실 계산
                return_pct = stock['closing_percent'] / 100
                stock_profit = invest_per_stock * return_pct
                daily_profit_loss += stock_profit

                daily_details.append({
                    'name': stock['name'],
                    'invest_amount': invest_per_stock,
                    'return_pct': stock['closing_percent'],
                    'profit_loss': stock_profit,
                    'first_hit': stock['first_hit']
                })

            # 일별 수익률 계산
            daily_return_pct = (daily_profit_loss / current_capital) * 100

            # 자본 업데이트
            previous_capital = current_capital
            current_capital += daily_profit_loss

            equity_curve.append({
                'date': date,
                'capital': current_capital,
                'previous_capital': previous_capital,
                'daily_profit_loss': daily_profit_loss,
                'daily_return_pct': daily_return_pct,
                'cumulative_return_pct': ((current_capital - initial_capital) / initial_capital) * 100,
                'num_stocks': num_stocks,
                'details': daily_details
            })

        return equity_curve, initial_capital

    def calculate_multi_scenario_stats(self, data):
        """멀티 시나리오 통계 계산"""
        scenario_stats = {}

        for d in data:
            ms = d.get('multi_scenario')
            if not ms:
                continue

            for name, sc in ms.items():
                if name not in scenario_stats:
                    scenario_stats[name] = {
                        'label': sc.get('label', name),
                        'profit': 0, 'loss': 0, 'none': 0, 'total': 0,
                        'rr': sc.get('rr', '-'),
                    }
                scenario_stats[name]['total'] += 1
                result = sc.get('result', 'none')
                if result == 'profit':
                    scenario_stats[name]['profit'] += 1
                elif result == 'loss':
                    scenario_stats[name]['loss'] += 1
                else:
                    scenario_stats[name]['none'] += 1

        return scenario_stats

    def calculate_scalp_stats(self, data):
        """단타 전략 통계 계산"""
        total = 0
        entered = 0
        profit = 0
        loss = 0
        timeout = 0

        for d in data:
            scalp = d.get('scalp_strategy')
            if not scalp:
                continue

            total += 1
            if scalp.get('should_enter', False):
                entered += 1

            exit_result = scalp.get('exit_result')
            if exit_result == 'profit':
                profit += 1
            elif exit_result == 'loss':
                loss += 1
            elif exit_result == 'timeout':
                timeout += 1

        if total == 0:
            return None

        return {
            'total': total,
            'entered': entered,
            'profit': profit,
            'loss': loss,
            'timeout': timeout,
        }

    def calculate_swing_stats(self, data):
        """스윙 전략 통계 계산"""
        total = 0
        signals = defaultdict(int)

        for d in data:
            swing = d.get('swing_strategy')
            if not swing:
                continue

            total += 1
            signal = swing.get('signal', 'unknown')
            signals[signal] += 1

        if total == 0:
            return None

        return {
            'total': total,
            'strong_buy': signals.get('strong_buy', 0),
            'hold': signals.get('hold', 0),
            'watch': signals.get('watch', 0),
            'warning': signals.get('warning', 0),
            'sell': signals.get('sell', 0),
        }

    def generate_html_report(self, all_data):
        """HTML 리포트 생성"""
        overall_stats = self.calculate_statistics(all_data)
        score_analysis = self.analyze_by_score_range(all_data)
        date_analysis = self.analyze_by_date(all_data)
        equity_curve, initial_capital = self.calculate_equity_curve(all_data)

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
        .chart-container {{
            position: relative;
            height: 400px;
            margin: 20px 0;
        }}
        .equity-table {{
            margin-top: 20px;
        }}
        .equity-table th {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}
        .profit {{ color: #e74c3c; font-weight: 600; }}
        .loss {{ color: #3498db; font-weight: 600; }}
        .summary-box {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
        }}
        .summary-box h3 {{
            margin-bottom: 15px;
            font-size: 18px;
        }}
        .summary-row {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255,255,255,0.2);
        }}
        .summary-row:last-child {{
            border-bottom: none;
        }}
        .summary-value {{
            font-weight: bold;
            font-size: 18px;
        }}
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
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

        # 자본 증가 곡선 섹션
        if equity_curve:
            final_capital = equity_curve[-1]['capital'] if equity_curve else initial_capital
            total_profit_loss = final_capital - initial_capital
            total_return_pct = ((final_capital - initial_capital) / initial_capital) * 100

            # 그래프용 데이터 생성
            dates_js = [eq['date'] for eq in equity_curve]
            capitals_js = [round(eq['capital'], 0) for eq in equity_curve]
            daily_returns_js = [round(eq['daily_return_pct'], 2) for eq in equity_curve]

            html += f"""
        <div class="section">
            <h2>💰 자본 증가 곡선</h2>

            <div class="summary-box">
                <h3>투자 성과 요약</h3>
                <div class="summary-row">
                    <span>초기 자본금</span>
                    <span class="summary-value">{initial_capital:,.0f}원</span>
                </div>
                <div class="summary-row">
                    <span>최종 자본금</span>
                    <span class="summary-value">{final_capital:,.0f}원</span>
                </div>
                <div class="summary-row">
                    <span>총 손익</span>
                    <span class="summary-value" style="color: {'#90EE90' if total_profit_loss >= 0 else '#FFB6C1'}">
                        {'+' if total_profit_loss >= 0 else ''}{total_profit_loss:,.0f}원
                    </span>
                </div>
                <div class="summary-row">
                    <span>총 수익률</span>
                    <span class="summary-value" style="color: {'#90EE90' if total_return_pct >= 0 else '#FFB6C1'}">
                        {'+' if total_return_pct >= 0 else ''}{total_return_pct:.2f}%
                    </span>
                </div>
            </div>

            <div class="chart-container">
                <canvas id="equityChart"></canvas>
            </div>

            <div class="chart-container">
                <canvas id="dailyReturnChart"></canvas>
            </div>

            <h3 style="margin-top: 30px; margin-bottom: 15px;">📋 일별 상세 내역</h3>
            <table class="equity-table">
                <thead>
                    <tr>
                        <th>날짜</th>
                        <th>종목 수</th>
                        <th>전일 자본</th>
                        <th>당일 자본</th>
                        <th>일 손익</th>
                        <th>일 수익률</th>
                        <th>누적 수익률</th>
                    </tr>
                </thead>
                <tbody>
"""
            for eq in equity_curve:
                date_formatted = eq['date']
                if len(date_formatted) == 8:
                    date_formatted = f"{{date_formatted[:4]}}-{{date_formatted[4:6]}}-{{date_formatted[6:]}}"

                profit_class = 'profit' if eq['daily_profit_loss'] >= 0 else 'loss'
                cumulative_class = 'profit' if eq['cumulative_return_pct'] >= 0 else 'loss'

                html += f"""
                    <tr>
                        <td><strong>{eq['date']}</strong></td>
                        <td>{eq['num_stocks']}개</td>
                        <td>{eq['previous_capital']:,.0f}원</td>
                        <td>{eq['capital']:,.0f}원</td>
                        <td class="{profit_class}">{'+' if eq['daily_profit_loss'] >= 0 else ''}{eq['daily_profit_loss']:,.0f}원</td>
                        <td class="{profit_class}">{'+' if eq['daily_return_pct'] >= 0 else ''}{eq['daily_return_pct']:.2f}%</td>
                        <td class="{cumulative_class}">{'+' if eq['cumulative_return_pct'] >= 0 else ''}{eq['cumulative_return_pct']:.2f}%</td>
                    </tr>
"""

            html += f"""
                </tbody>
            </table>
        </div>

        <script>
            // 자본 증가 곡선 차트
            const equityCtx = document.getElementById('equityChart').getContext('2d');
            new Chart(equityCtx, {{
                type: 'line',
                data: {{
                    labels: {dates_js},
                    datasets: [{{
                        label: '자본금 (원)',
                        data: {capitals_js},
                        borderColor: '#667eea',
                        backgroundColor: 'rgba(102, 126, 234, 0.1)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 6,
                        pointHoverRadius: 8,
                        pointBackgroundColor: '#667eea',
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        title: {{
                            display: true,
                            text: '자본 증가 곡선 (초기 자본: {initial_capital:,}원)',
                            font: {{ size: 16 }}
                        }},
                        legend: {{ display: false }},
                        tooltip: {{
                            callbacks: {{
                                label: function(context) {{
                                    return '자본금: ' + context.raw.toLocaleString() + '원';
                                }}
                            }}
                        }}
                    }},
                    scales: {{
                        y: {{
                            beginAtZero: false,
                            ticks: {{
                                callback: function(value) {{
                                    return value.toLocaleString() + '원';
                                }}
                            }}
                        }}
                    }}
                }}
            }});

            // 일별 수익률 차트
            const dailyCtx = document.getElementById('dailyReturnChart').getContext('2d');
            const dailyReturns = {daily_returns_js};
            const barColors = dailyReturns.map(v => v >= 0 ? 'rgba(231, 76, 60, 0.8)' : 'rgba(52, 152, 219, 0.8)');

            new Chart(dailyCtx, {{
                type: 'bar',
                data: {{
                    labels: {dates_js},
                    datasets: [{{
                        label: '일 수익률 (%)',
                        data: dailyReturns,
                        backgroundColor: barColors,
                        borderColor: barColors.map(c => c.replace('0.8', '1')),
                        borderWidth: 1
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        title: {{
                            display: true,
                            text: '일별 수익률',
                            font: {{ size: 16 }}
                        }},
                        legend: {{ display: false }},
                        tooltip: {{
                            callbacks: {{
                                label: function(context) {{
                                    return '수익률: ' + (context.raw >= 0 ? '+' : '') + context.raw + '%';
                                }}
                            }}
                        }}
                    }},
                    scales: {{
                        y: {{
                            ticks: {{
                                callback: function(value) {{
                                    return (value >= 0 ? '+' : '') + value + '%';
                                }}
                            }}
                        }}
                    }}
                }}
            }});
        </script>
"""

        # 멀티 시나리오 비교 분석
        scenario_stats = self.calculate_multi_scenario_stats(all_data)
        if scenario_stats:
            html += """
        <div class="section">
            <h2>🎯 4가지 시나리오 비교 분석</h2>
            <table>
                <thead>
                    <tr>
                        <th>시나리오</th>
                        <th>종목 수</th>
                        <th>승률</th>
                        <th>익절</th>
                        <th>손절</th>
                        <th>미도달</th>
                        <th>R:R</th>
                    </tr>
                </thead>
                <tbody>
"""
            for name in sorted(scenario_stats.keys()):
                st = scenario_stats[name]
                win_rate = (st['profit'] / st['total'] * 100) if st['total'] > 0 else 0
                html += f"""
                    <tr>
                        <td><strong>{st['label']}</strong></td>
                        <td>{st['total']}개</td>
                        <td class="{'positive' if win_rate > 50 else ''}">{win_rate:.1f}%</td>
                        <td>{st['profit']}</td>
                        <td>{st['loss']}</td>
                        <td>{st['none']}</td>
                        <td>{st.get('rr', '-')}</td>
                    </tr>
"""
            html += """
                </tbody>
            </table>
        </div>
"""

        # 단타/스윙 전략 비교
        scalp_stats = self.calculate_scalp_stats(all_data)
        swing_stats = self.calculate_swing_stats(all_data)
        if scalp_stats or swing_stats:
            html += """
        <div class="section">
            <h2>⚡ 전략별 성과 비교</h2>
            <table>
                <thead>
                    <tr>
                        <th>전략</th>
                        <th>분석 종목</th>
                        <th>진입 신호</th>
                        <th>익절</th>
                        <th>손절</th>
                        <th>타임아웃</th>
                        <th>승률</th>
                    </tr>
                </thead>
                <tbody>
"""
            if scalp_stats:
                scalp_total = scalp_stats.get('total', 0)
                scalp_entered = scalp_stats.get('entered', 0)
                scalp_profit = scalp_stats.get('profit', 0)
                scalp_loss = scalp_stats.get('loss', 0)
                scalp_timeout = scalp_stats.get('timeout', 0)
                scalp_winrate = (scalp_profit / scalp_entered * 100) if scalp_entered > 0 else 0
                html += f"""
                    <tr>
                        <td><strong>단타 (09:00~09:10)</strong></td>
                        <td>{scalp_total}개</td>
                        <td>{scalp_entered}개</td>
                        <td>{scalp_profit}</td>
                        <td>{scalp_loss}</td>
                        <td>{scalp_timeout}</td>
                        <td class="{'positive' if scalp_winrate > 50 else ''}">{scalp_winrate:.1f}%</td>
                    </tr>
"""
            if swing_stats:
                swing_total = swing_stats.get('total', 0)
                html += f"""
                    <tr>
                        <td><strong>스윙 (종가 기준)</strong></td>
                        <td>{swing_total}개</td>
                        <td>-</td>
                        <td>{swing_stats.get('strong_buy', 0)}</td>
                        <td>{swing_stats.get('sell', 0)}</td>
                        <td>-</td>
                        <td>-</td>
                    </tr>
"""
            html += """
                </tbody>
            </table>
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
