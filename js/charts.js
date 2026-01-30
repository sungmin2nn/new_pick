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

        this.instances[canvasId] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: equityData.map(d => d.date),
                datasets: [{
                    label: '자본',
                    data: equityData.map(d => d.capital),
                    borderColor: '#0066cc',
                    backgroundColor: 'rgba(0, 102, 204, 0.1)',
                    tension: 0.2,
                    fill: true,
                    pointRadius: 3,
                    pointHoverRadius: 5
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
                                return '자본: ' + context.parsed.y.toLocaleString('ko-KR') + '원';
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
    }
};
