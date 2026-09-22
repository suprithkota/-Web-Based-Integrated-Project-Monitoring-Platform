// ProjectPulse AI — Command Center Chart.js & Analytics Engine

document.addEventListener('DOMContentLoaded', function() {
    // Configure global Chart.js defaults
    if (typeof Chart !== 'undefined') {
        Chart.defaults.font.family = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
        Chart.defaults.font.size = 12;
        Chart.defaults.color = '#64748b';
        Chart.defaults.plugins.tooltip.backgroundColor = '#0f172a';
        Chart.defaults.plugins.tooltip.titleColor = '#ffffff';
        Chart.defaults.plugins.tooltip.bodyColor = '#f8fafc';
        Chart.defaults.plugins.tooltip.padding = 10;
        Chart.defaults.plugins.tooltip.cornerRadius = 6;
        Chart.defaults.plugins.tooltip.boxPadding = 4;
    }

    fetch('/api/dashboard' + window.location.search)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                renderCharts(data.charts);
                populateWatchlists(data.charts);
            }
        })
        .catch(err => console.error('Error loading dashboard analytics:', err));
});

function renderCharts(charts) {
    // 1. Risk Distribution Doughnut
    const ctxRisk = document.getElementById('riskDistChart');
    if (ctxRisk) {
        new Chart(ctxRisk, {
            type: 'doughnut',
            data: {
                labels: ['Low Risk', 'Medium Risk', 'High Risk', 'Critical Risk'],
                datasets: [{
                    data: [
                        charts.risk_distribution.LOW,
                        charts.risk_distribution.MEDIUM,
                        charts.risk_distribution.HIGH,
                        charts.risk_distribution.CRITICAL
                    ],
                    backgroundColor: ['#16a34a', '#d97706', '#ea580c', '#dc2626'],
                    borderWidth: 2,
                    borderColor: '#ffffff',
                    hoverOffset: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            boxWidth: 10,
                            boxHeight: 10,
                            padding: 14,
                            usePointStyle: true,
                            font: { size: 11, weight: 600 }
                        }
                    }
                },
                cutout: '72%'
            }
        });
    }

    // 2. Ministry Chart (Horizontal Bar)
    const ctxMin = document.getElementById('ministryChart');
    if (ctxMin && charts.ministries) {
        new Chart(ctxMin, {
            type: 'bar',
            data: {
                labels: charts.ministries.labels,
                datasets: [{
                    label: 'Active Projects',
                    data: charts.ministries.counts,
                    backgroundColor: '#2563eb',
                    borderRadius: 4,
                    barThickness: 16
                }, {
                    label: 'Avg Risk Index',
                    data: charts.ministries.avg_risks,
                    backgroundColor: '#ea580c',
                    borderRadius: 4,
                    barThickness: 16
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                scales: {
                    x: {
                        beginAtZero: true,
                        grid: { color: '#f1f5f9' },
                        ticks: { font: { size: 11 } }
                    },
                    y: {
                        grid: { display: false },
                        ticks: { font: { size: 11, weight: 500 }, color: '#0f172a' }
                    }
                },
                plugins: {
                    legend: {
                        position: 'top',
                        align: 'end',
                        labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true, padding: 12 }
                    }
                }
            }
        });
    }

    // 3. Sector Distribution (Vertical Bar)
    const ctxSec = document.getElementById('sectorChart');
    if (ctxSec && charts.sectors) {
        new Chart(ctxSec, {
            type: 'bar',
            data: {
                labels: charts.sectors.labels,
                datasets: [{
                    label: 'Projects Count',
                    data: charts.sectors.counts,
                    backgroundColor: '#0284c7',
                    borderRadius: 4,
                    maxBarThickness: 36
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { color: '#f1f5f9' },
                        ticks: { font: { size: 11 } }
                    },
                    x: {
                        grid: { display: false },
                        ticks: { font: { size: 11 } }
                    }
                },
                plugins: { legend: { display: false } }
            }
        });
    }

    // 4. Scatter Plot: Physical Progress vs Expenditure
    const ctxScatter = document.getElementById('scatterChart');
    if (ctxScatter && charts.scatter_points) {
        new Chart(ctxScatter, {
            type: 'scatter',
            data: {
                datasets: [{
                    label: 'Project Outliers',
                    data: charts.scatter_points.map(p => ({ x: p.x, y: p.y })),
                    backgroundColor: function(context) {
                        const idx = context.dataIndex;
                        const p = charts.scatter_points[idx];
                        if (!p) return '#2563eb';
                        if (p.risk_level === 'CRITICAL') return '#dc2626';
                        if (p.risk_level === 'HIGH') return '#ea580c';
                        if (p.risk_level === 'MEDIUM') return '#d97706';
                        return '#16a34a';
                    },
                    borderColor: '#ffffff',
                    borderWidth: 1,
                    pointRadius: 6,
                    pointHoverRadius: 8
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        title: { display: true, text: 'Actual Physical Progress (%)', font: { weight: 600 } },
                        min: 0,
                        max: 100,
                        grid: { color: '#f1f5f9' },
                        ticks: { font: { size: 11 } }
                    },
                    y: {
                        title: { display: true, text: 'Expenditure Utilization (%)', font: { weight: 600 } },
                        min: 0,
                        max: 120,
                        grid: { color: '#f1f5f9' },
                        ticks: { font: { size: 11 } }
                    }
                },
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const p = charts.scatter_points[context.dataIndex];
                                return `${p.name}: Progress ${p.x}%, Spend ${p.y}% (${p.risk_level} Risk)`;
                            }
                        }
                    }
                }
            }
        });
    }
}

function populateWatchlists(charts) {
    const delayTbody = document.getElementById('topDelayTableBody');
    if (delayTbody && charts.top_delay_risk) {
        delayTbody.innerHTML = charts.top_delay_risk.slice(0, 5).map(p => `
            <tr>
                <td>
                    <div class="fw-semibold text-dark text-truncate" style="max-width: 220px;">${p.name}</div>
                    <div class="small text-muted font-monospace">${p.code}</div>
                </td>
                <td>
                    <span class="badge-risk badge-risk-critical font-monospace">
                        ${p.delay_prob}%
                    </span>
                </td>
                <td class="text-secondary small font-monospace">${p.delay_days} days</td>
                <td>
                    <a href="/projects/${p.id}" class="btn btn-sm btn-outline-primary py-0 px-2 fw-semibold" style="font-size: 0.76rem;">
                        Inspect <i class="fa-solid fa-arrow-right ms-1"></i>
                    </a>
                </td>
            </tr>
        `).join('');
    }

    const costTbody = document.getElementById('topCostTableBody');
    if (costTbody && charts.top_cost_risk) {
        costTbody.innerHTML = charts.top_cost_risk.slice(0, 5).map(p => `
            <tr>
                <td>
                    <div class="fw-semibold text-dark text-truncate" style="max-width: 220px;">${p.name}</div>
                    <div class="small text-muted font-monospace">${p.code}</div>
                </td>
                <td>
                    <span class="badge-risk badge-risk-high font-monospace">
                        ${p.cost_prob}%
                    </span>
                </td>
                <td class="text-danger small font-monospace fw-semibold">+${p.cost_escalation}%</td>
                <td>
                    <a href="/projects/${p.id}" class="btn btn-sm btn-outline-primary py-0 px-2 fw-semibold" style="font-size: 0.76rem;">
                        Inspect <i class="fa-solid fa-arrow-right ms-1"></i>
                    </a>
                </td>
            </tr>
        `).join('');
    }
}

