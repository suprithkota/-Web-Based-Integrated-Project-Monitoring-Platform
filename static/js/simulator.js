document.addEventListener('DOMContentLoaded', function() {
    const projectSelect = document.getElementById('projectSelect');
    const progRange = document.getElementById('progRange');
    const delayRange = document.getElementById('delayRange');
    const milestoneRange = document.getElementById('milestoneRange');
    const costRange = document.getElementById('costRange');
    const runBtn = document.getElementById('runSimulationBtn');

    // Display labels
    const progVal = document.getElementById('progVal');
    const delayVal = document.getElementById('delayVal');
    const milestoneVal = document.getElementById('milestoneVal');
    const costVal = document.getElementById('costVal');

    if (progRange && progVal) {
        progRange.addEventListener('input', () => progVal.innerText = progRange.value + '%');
    }
    if (delayRange && delayVal) {
        delayRange.addEventListener('input', () => delayVal.innerText = delayRange.value + ' days');
    }
    if (milestoneRange && milestoneVal) {
        milestoneRange.addEventListener('input', () => milestoneVal.innerText = milestoneRange.value + ' delayed');
    }
    if (costRange && costVal) {
        costRange.addEventListener('input', () => costVal.innerText = '₹' + costRange.value + ' Cr');
    }

    if (projectSelect) {
        projectSelect.addEventListener('change', function() {
            window.location.href = '/simulator?project_id=' + this.value;
        });
    }

    if (runBtn) {
        runBtn.addEventListener('click', triggerSimulation);
        // Run initial simulation on load
        triggerSimulation();
    }
});

function triggerSimulation() {
    const projectId = document.getElementById('projectSelect')?.value;
    const prog = document.getElementById('progRange')?.value;
    const delay = document.getElementById('delayRange')?.value;
    const milestones = document.getElementById('milestoneRange')?.value;
    const cost = document.getElementById('costRange')?.value;
    const contractor = document.getElementById('contractorSelect')?.value;
    const land = document.getElementById('landSelect')?.value;
    const env = document.getElementById('envSelect')?.value;
    const util = document.getElementById('utilSelect')?.value;

    const payload = {
        project_id: projectId,
        physical_progress: prog,
        delay_days: delay,
        milestones_delayed: milestones,
        revised_cost: cost,
        contractor_status: contractor,
        land_acquisition_status: land,
        environmental_clearance_status: env,
        utility_shifting_status: util
    };

    fetch('/api/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            updateSimulationUI(data);
        }
    })
    .catch(err => console.error('Simulation error:', err));
}

function updateSimulationUI(data) {
    // Current State
    document.getElementById('currentRiskScore').innerText = data.current.risk_score + '/100';
    document.getElementById('currentDelayProb').innerText = data.current.delay_prob + '%';
    document.getElementById('currentCostProb').innerText = data.current.cost_prob + '%';
    document.getElementById('currentHealthScore').innerText = data.current.health_score + '/100';
    const currBadge = document.getElementById('currentRiskLevel');
    currBadge.innerText = data.current.risk_level;
    currBadge.className = 'badge ' + getRiskBadgeClass(data.current.risk_level);

    // Simulated State
    document.getElementById('simulatedRiskScore').innerText = data.simulated.risk_score + '/100';
    document.getElementById('simulatedDelayProb').innerText = data.simulated.delay_prob + '%';
    document.getElementById('simulatedCostProb').innerText = data.simulated.cost_prob + '%';
    document.getElementById('simulatedHealthScore').innerText = data.simulated.health_score + '/100';
    const simBadge = document.getElementById('simulatedRiskLevel');
    simBadge.innerText = data.simulated.risk_level;
    simBadge.className = 'badge ' + getRiskBadgeClass(data.simulated.risk_level);

    // Deltas
    const dirBadge = document.getElementById('directionBadge');
    if (data.deltas.direction === 'DETERIORATING') {
        dirBadge.className = 'badge bg-danger';
        dirBadge.innerText = 'DETERIORATING (+Risk)';
    } else if (data.deltas.direction === 'IMPROVING') {
        dirBadge.className = 'badge bg-success';
        dirBadge.innerText = 'IMPROVING (-Risk)';
    } else {
        dirBadge.className = 'badge bg-secondary';
        dirBadge.innerText = 'STABLE (No Change)';
    }

    const dRisk = document.getElementById('deltaRisk');
    dRisk.innerText = (data.deltas.risk_delta > 0 ? '+' : '') + data.deltas.risk_delta;
    dRisk.className = 'fw-bold fs-6 ' + (data.deltas.risk_delta > 0 ? 'text-danger' : 'text-success');

    const dDelay = document.getElementById('deltaDelay');
    dDelay.innerText = (data.deltas.delay_delta > 0 ? '+' : '') + data.deltas.delay_delta + '%';
    dDelay.className = 'fw-bold fs-6 ' + (data.deltas.delay_delta > 0 ? 'text-danger' : 'text-success');

    const dCost = document.getElementById('deltaCost');
    dCost.innerText = (data.deltas.cost_delta > 0 ? '+' : '') + data.deltas.cost_delta + '%';
    dCost.className = 'fw-bold fs-6 ' + (data.deltas.cost_delta > 0 ? 'text-danger' : 'text-success');

    const dHealth = document.getElementById('deltaHealth');
    dHealth.innerText = (data.deltas.health_delta > 0 ? '+' : '') + data.deltas.health_delta;
    dHealth.className = 'fw-bold fs-6 ' + (data.deltas.health_delta >= 0 ? 'text-success' : 'text-danger');

    // Multi-Model Consensus (Simulated)
    const simRegs = (data.simulated && data.simulated.model_predictions && data.simulated.model_predictions.regressors) || {};
    const simRf = document.getElementById('simRfScore');
    const simXgb = document.getElementById('simXgbScore');
    const simLgb = document.getElementById('simLgbScore');
    if (simRf) simRf.innerText = (simRegs.random_forest != null ? simRegs.random_forest + '/100' : (data.simulated.risk_score + '/100'));
    if (simXgb) simXgb.innerText = (simRegs.xgboost != null ? simRegs.xgboost + '/100' : 'N/A');
    if (simLgb) simLgb.innerText = (simRegs.lightgbm != null ? simRegs.lightgbm + '/100' : 'N/A');

    // Narrative
    document.getElementById('simulatedExplanation').innerText = data.simulated.explanation;
}

function getRiskBadgeClass(level) {
    if (level === 'CRITICAL') return 'bg-danger';
    if (level === 'HIGH') return 'bg-orange text-white';
    if (level === 'MEDIUM') return 'bg-warning text-dark';
    return 'bg-success';
}
