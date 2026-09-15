document.addEventListener('DOMContentLoaded', function() {
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
                    backgroundColor: ['#10b981', '#f59e0b', '#f97316', '#ef4444'],
                    borderWidth: 2,
                    borderColor: '#ffffff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'bottom', labels: { boxWidth: 12, padding: 12 } }
                },
                cutout: '68%'
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
                    backgroundColor: '#1d3557',
                    borderRadius: 4
                }, {
                    label: 'Avg Risk Index',
                    data: charts.ministries.avg_risks,
                    backgroundColor: '#f97316',
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                scales: {
                    x: { beginAtZero: true, grid: { color: '#f1f5f9' } },
                    y: { grid: { display: false } }
                },
                plugins: {
                    legend: { position: 'top' }
                }
            }
        });
    }

    // 3. Sector Distribution (Bar)
    const ctxSec = document.getElementById('sectorChart');
    if (ctxSec && charts.sectors) {
        new Chart(ctxSec, {
            type: 'bar',
            data: {
                labels: charts.sectors.labels,
                datasets: [{
                    label: 'Projects Count',
                    data: charts.sectors.counts,
                    backgroundColor: '#3b82f6',
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: { beginAtZero: true, grid: { color: '#f1f5f9' } },
                    x: { grid: { display: false } }
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
                        if (!p) return '#3b82f6';
                        if (p.risk_level === 'CRITICAL') return '#ef4444';
                        if (p.risk_level === 'HIGH') return '#f97316';
                        if (p.risk_level === 'MEDIUM') return '#f59e0b';
                        return '#10b981';
                    },
                    pointRadius: 6,
                    pointHoverRadius: 8
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        title: { display: true, text: 'Actual Physical Progress (%)' },
                        min: 0,
                        max: 100,
                        grid: { color: '#f1f5f9' }
                    },
                    y: {
                        title: { display: true, text: 'Expenditure Utilization (%)' },
                        min: 0,
                        max: 120,
                        grid: { color: '#f1f5f9' }
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
                    <div class="fw-semibold text-dark text-truncate" style="max-width: 200px;">${p.name}</div>
                    <div class="small text-muted font-monospace">${p.code}</div>
                </td>
                <td>
                    <span class="badge bg-danger bg-opacity-10 text-danger fw-bold fs-7">
                        ${p.delay_prob}%
                    </span>
                </td>
                <td class="text-muted small">${p.delay_days} days</td>
                <td>
                    <a href="/projects/${p.id}" class="btn btn-sm btn-outline-primary py-0 px-2">
                        Inspect
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
                    <div class="fw-semibold text-dark text-truncate" style="max-width: 200px;">${p.name}</div>
                    <div class="small text-muted font-monospace">${p.code}</div>
                </td>
                <td>
                    <span class="badge bg-warning bg-opacity-25 text-dark fw-bold fs-7">
                        ${p.cost_prob}%
                    </span>
                </td>
                <td class="text-danger small fw-semibold">+${p.cost_escalation}%</td>
                <td>
                    <a href="/projects/${p.id}" class="btn btn-sm btn-outline-primary py-0 px-2">
                        Inspect
                    </a>
                </td>
            </tr>
        `).join('');
    }
}
