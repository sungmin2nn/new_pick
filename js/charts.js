// Chart Rendering Module - Chart.js 래퍼

const Charts = {
    instances: {},

    /**
     * 차트 인스턴스 파괴 (재렌더링 전)
     */
    destroyChart(chartId) {
        if (this.instances[chartId]) {
            this.instances[chartId].destroy();
            delete this.instances[chartId];
        }
    },

    /**
     * 자본 증가 곡선 차트 (라인 차트)
     */
    renderEquityCurve(canvasId, equityData) {
        this.destroyChart(canvasId);

        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.error(`[Charts] Canvas not found: ${canvasId}`);
            return;
        }

        const ctx = canvas.getContext('2d');

        const grad = ctx.createLinearGradient(0, 0, 0, canvas.clientHeight || 200);
        grad.addColorStop(0, 'rgba(0,255,135,0.15)');
        grad.addColorStop(1, 'transparent');

        this.instances[canvasId] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: equityData.map(d => d.date),
                datasets: [{
                    label: '자본',
                    data: equityData.map(d => d.capital),
                    borderColor: '#00ff87',
                    backgroundColor: grad,
                    tension: 0.4,
                    fill: true,
                    borderWidth: 2.5,
                    pointRadius: 4,
                    pointBackgroundColor: '#0a0a0a',
                    pointBorderColor: '#00ff87',
                    pointBorderWidth: 2,
                    pointHoverRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: {
                    duration: 800
                },
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        padding: 12,
                        titleFont: {
                            size: 14
                        },
                        bodyFont: {
                            size: 13
                        },
                        callbacks: {
                            label: function(context) {
                                return '자본: ' + context.parsed.y.toLocaleString('ko-KR') + '원';
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            color: 'rgba(255,255,255,0.06)'
                        },
                        ticks: { color: '#9CA3AF' }
                    },
                    y: {
                        beginAtZero: false,
                        grid: {
                            color: 'rgba(255,255,255,0.06)'
                        },
                        ticks: {
                            color: '#9CA3AF',
                            callback: function(value) {
                                return value.toLocaleString('ko-KR') + '원';
                            }
                        }
                    }
                }
            }
        });
    },

    /**
     * 결과 분포 차트 (도넛 차트) - 5단계
     */
    renderResultDistribution(canvasId, profitCount, lossCount, noneProfitCount, noneLossCount, noneNeutralCount) {
        this.destroyChart(canvasId);

        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.error(`[Charts] Canvas not found: ${canvasId}`);
            return;
        }

        const ctx = canvas.getContext('2d');
        const total = profitCount + lossCount + noneProfitCount + noneLossCount + noneNeutralCount;

        this.instances[canvasId] = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['익절', '손절', '미달(수익)', '미달(손실)', '미달(유지)'],
                datasets: [{
                    data: [profitCount, lossCount, noneProfitCount, noneLossCount, noneNeutralCount],
                    backgroundColor: [
                        '#f56565',  // 익절 - 빨강
                        '#4299e1',  // 손절 - 파랑
                        '#ffa07a',  // 미달(수익) - 연한 빨강
                        '#87ceeb',  // 미달(손실) - 연한 파랑
                        '#d3d3d3'   // 미달(유지) - 회색
                    ],
                    borderWidth: 2,
                    borderColor: '#ffffff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            padding: 10,
                            font: {
                                size: 11
                            }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const label = context.label || '';
                                const value = context.parsed || 0;
                                const percent = total > 0 ? ((value / total) * 100).toFixed(1) : 0;
                                return `${label}: ${value}건 (${percent}%)`;
                            }
                        }
                    }
                }
            }
        });
    },

    /**
     * 요일별 패턴 차트 (바 차트)
     */
    renderDayOfWeekChart(canvasId, dayData) {
        this.destroyChart(canvasId);

        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.error(`[Charts] Canvas not found: ${canvasId}`);
            return;
        }

        const ctx = canvas.getContext('2d');

        this.instances[canvasId] = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: dayData.map(d => d.day),
                datasets: [
                    {
                        label: '익절',
                        data: dayData.map(d => d.profitCount),
                        backgroundColor: '#f56565'
                    },
                    {
                        label: '손절',
                        data: dayData.map(d => d.lossCount),
                        backgroundColor: '#4299e1'
                    },
                    {
                        label: '미달',
                        data: dayData.map(d => d.noneCount),
                        backgroundColor: '#a0aec0'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'top'
                    }
                },
                scales: {
                    x: {
                        stacked: true
                    },
                    y: {
                        stacked: true,
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1
                        }
                    }
                }
            }
        });
    },

    /**
     * 시간대별 패턴 차트 (꺾은선 그래프)
     */
    renderTimeOfDayChart(canvasId, timeData) {
        this.destroyChart(canvasId);

        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.error(`[Charts] Canvas not found: ${canvasId}`);
            return;
        }

        const ctx = canvas.getContext('2d');

        this.instances[canvasId] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: timeData.map(d => d.timeSlot),
                datasets: [
                    {
                        label: '익절',
                        data: timeData.map(d => d.profitHits),
                        borderColor: '#f56565',
                        backgroundColor: 'rgba(245, 101, 101, 0.1)',
                        tension: 0.3,
                        fill: false,
                        pointRadius: 4,
                        pointHoverRadius: 6
                    },
                    {
                        label: '손절',
                        data: timeData.map(d => d.lossHits),
                        borderColor: '#4299e1',
                        backgroundColor: 'rgba(66, 153, 225, 0.1)',
                        tension: 0.3,
                        fill: false,
                        pointRadius: 4,
                        pointHoverRadius: 6
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'top'
                    }
                },
                scales: {
                    x: {
                        ticks: {
                            maxRotation: 45,
                            minRotation: 45,
                            font: {
                                size: 10
                            }
                        }
                    },
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1
                        }
                    }
                }
            }
        });
    },

    /**
     * 수익률 분포 차트 (히스토그램)
     */
    renderReturnDistribution(canvasId, distributionData) {
        this.destroyChart(canvasId);

        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.error(`[Charts] Canvas not found: ${canvasId}`);
            return;
        }

        const ctx = canvas.getContext('2d');

        // 색상 결정: 음수는 파랑, 양수는 빨강, 0 근처는 회색
        const colors = distributionData.map(d => {
            if (d.bucket.includes('-10') || d.bucket.includes('-5') || d.bucket.includes('-3')) {
                return '#4299e1';  // 파랑
            } else if (d.bucket.includes('10') || d.bucket.includes('5') || d.bucket.includes('3')) {
                return '#f56565';  // 빨강
            } else {
                return '#a0aec0';  // 회색
            }
        });

        this.instances[canvasId] = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: distributionData.map(d => d.bucket),
                datasets: [{
                    label: '거래 수',
                    data: distributionData.map(d => d.count),
                    backgroundColor: colors,
                    borderWidth: 1,
                    borderColor: '#ffffff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return '거래 수: ' + context.parsed.y + '건';
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: {
                            maxRotation: 45,
                            minRotation: 45,
                            font: {
                                size: 10
                            }
                        }
                    },
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1
                        }
                    }
                }
            }
        });
    },

    /**
     * 드로우다운 차트 (Area 차트)
     * @param {string} canvasId - 캔버스 ID
     * @param {Array} drawdownData - [{date: '2024-01-01', drawdown: -5.2}, ...]
     */
    renderDrawdownChart(canvasId, drawdownData) {
        this.destroyChart(canvasId);

        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.error(`[Charts] Canvas not found: ${canvasId}`);
            return;
        }

        const ctx = canvas.getContext('2d');

        // 최대 드로우다운 포인트 찾기
        const maxDrawdownPoint = drawdownData.reduce((min, current) => {
            return (current.drawdown < min.drawdown) ? current : min;
        }, drawdownData[0]);

        // 최대 드로우다운 포인트에 마커 표시를 위한 포인트 반지름 설정
        const pointRadii = drawdownData.map(d =>
            (d.date === maxDrawdownPoint.date && d.drawdown === maxDrawdownPoint.drawdown) ? 6 : 0
        );

        this.instances[canvasId] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: drawdownData.map(d => d.date),
                datasets: [{
                    label: '드로우다운',
                    data: drawdownData.map(d => d.drawdown),
                    borderColor: '#EF4444',
                    backgroundColor: 'rgba(239, 68, 68, 0.2)',
                    tension: 0.4,
                    fill: true,
                    pointRadius: pointRadii,
                    pointBackgroundColor: '#DC2626',
                    pointBorderColor: '#ffffff',
                    pointBorderWidth: 2,
                    pointHoverRadius: 8
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: {
                    duration: 800
                },
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        padding: 12,
                        titleFont: {
                            size: 14
                        },
                        bodyFont: {
                            size: 13
                        },
                        callbacks: {
                            label: function(context) {
                                return '드로우다운: ' + context.parsed.y.toFixed(2) + '%';
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            display: false
                        }
                    },
                    y: {
                        beginAtZero: false,
                        max: 0,
                        min: -30,
                        ticks: {
                            callback: function(value) {
                                return value.toFixed(0) + '%';
                            }
                        }
                    }
                }
            }
        });
    },

    /**
     * 월별 히트맵 차트 (바 차트로 구현)
     * @param {string} canvasId - 캔버스 ID
     * @param {Array} monthlyData - [{yearMonth: '2026-01', returnPercent: 3.5}, ...]
     */
    renderMonthlyHeatmap(canvasId, monthlyData) {
        this.destroyChart(canvasId);

        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.error(`[Charts] Canvas not found: ${canvasId}`);
            return;
        }

        const ctx = canvas.getContext('2d');

        // 색상 함수: 수익률에 따라 색상 결정
        const getColor = (value) => {
            if (value < -5) return '#3B82F6';      // 진한 파랑
            if (value < -2) return '#60A5FA';      // 파랑
            if (value < -0.5) return '#93C5FD';    // 연한 파랑
            if (value < 0.5) return '#D1D5DB';     // 회색
            if (value < 2) return '#FCA5A5';       // 연한 빨강
            if (value < 5) return '#F87171';       // 빨강
            return '#EF4444';                      // 진한 빨강
        };

        const colors = monthlyData.map(d => getColor(d.returnPercent));

        this.instances[canvasId] = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: monthlyData.map(d => d.yearMonth),
                datasets: [{
                    label: '월별 수익률',
                    data: monthlyData.map(d => d.returnPercent),
                    backgroundColor: colors,
                    borderWidth: 1,
                    borderColor: '#ffffff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        padding: 12,
                        callbacks: {
                            label: function(context) {
                                const data = monthlyData[context.dataIndex];
                                return [
                                    '수익률: ' + data.returnPercent.toFixed(2) + '%',
                                    '거래 수: ' + data.tradesCount + '건'
                                ];
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            display: false
                        }
                    },
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {
                                return value.toFixed(1) + '%';
                            }
                        }
                    }
                }
            }
        });
    },

    /**
     * 벤치마크 비교 차트 (누적 수익률)
     * @param {string} canvasId - 캔버스 ID
     * @param {Array} strategyData - [{date: '2024-01-01', cumulativeReturn: 5.2}, ...]
     * @param {Array} benchmarkData - [{date: '2024-01-01', cumulativeReturn: 2.1}, ...]
     */
    renderBenchmarkComparison(canvasId, strategyData, benchmarkData) {
        this.destroyChart(canvasId);

        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.error(`[Charts] Canvas not found: ${canvasId}`);
            return;
        }

        const ctx = canvas.getContext('2d');

        this.instances[canvasId] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: strategyData.map(d => d.date),
                datasets: [
                    {
                        label: '전략',
                        data: strategyData.map(d => d.cumulativeReturn),
                        borderColor: '#00C6BE',
                        backgroundColor: 'rgba(0, 198, 190, 0.1)',
                        tension: 0.4,
                        fill: false,
                        pointRadius: 0,
                        pointHoverRadius: 6,
                        borderWidth: 2
                    },
                    {
                        label: 'KOSPI',
                        data: benchmarkData.map(d => d.cumulativeReturn),
                        borderColor: '#9CA3AF',
                        backgroundColor: 'rgba(156, 163, 175, 0.1)',
                        tension: 0.4,
                        fill: false,
                        pointRadius: 0,
                        pointHoverRadius: 6,
                        borderWidth: 2,
                        borderDash: [5, 5]
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: {
                    duration: 800
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: {
                            padding: 15,
                            font: {
                                size: 12
                            },
                            usePointStyle: true
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        padding: 12,
                        titleFont: {
                            size: 14
                        },
                        bodyFont: {
                            size: 13
                        },
                        callbacks: {
                            label: function(context) {
                                return context.dataset.label + ': ' + context.parsed.y.toFixed(2) + '%';
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            display: false
                        }
                    },
                    y: {
                        beginAtZero: false,
                        ticks: {
                            callback: function(value) {
                                return value.toFixed(1) + '%';
                            }
                        }
                    }
                }
            }
        });
    },

    /**
     * 수익률 분포 히스토그램 (세밀한 구간)
     * @param {string} canvasId - 캔버스 ID
     * @param {Array} distributionData - [{bucket: '-10~-8', count: 5, percentage: 15.2}, ...]
     */
    renderReturnHistogram(canvasId, distributionData) {
        this.destroyChart(canvasId);

        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.error(`[Charts] Canvas not found: ${canvasId}`);
            return;
        }

        const ctx = canvas.getContext('2d');

        // 색상 결정: 음수는 파랑, 양수는 빨강, 0 근처는 회색
        const colors = distributionData.map(d => {
            if (d.bucket.includes('-20') || d.bucket.includes('-15') || d.bucket.includes('-10')) {
                return '#3B82F6';  // 진한 파랑
            } else if (d.bucket.includes('-5') || d.bucket.includes('-3')) {
                return '#60A5FA';  // 파랑
            } else if (d.bucket.includes('0%')) {
                return '#D1D5DB';  // 회색
            } else if (d.bucket.includes('3%') || d.bucket.includes('5%')) {
                return '#F87171';  // 빨강
            } else if (d.bucket.includes('10') || d.bucket.includes('15') || d.bucket.includes('20')) {
                return '#EF4444';  // 진한 빨강
            } else {
                return '#A0AEC0';  // 기본 회색
            }
        });

        this.instances[canvasId] = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: distributionData.map(d => d.bucket),
                datasets: [{
                    label: '빈도수',
                    data: distributionData.map(d => d.count),
                    backgroundColor: colors,
                    borderWidth: 1,
                    borderColor: '#ffffff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        padding: 12,
                        callbacks: {
                            label: function(context) {
                                const data = distributionData[context.dataIndex];
                                return [
                                    '빈도수: ' + data.count + '건',
                                    '비율: ' + data.percentage.toFixed(1) + '%'
                                ];
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        title: {
                            display: true,
                            text: '수익률 구간'
                        },
                        ticks: {
                            maxRotation: 45,
                            minRotation: 45,
                            font: {
                                size: 10
                            }
                        }
                    },
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: '빈도수'
                        },
                        ticks: {
                            stepSize: 1
                        }
                    }
                }
            }
        });
    }
};
