import numpy as np

STATUS_ENCODINGS = {
    'contractor': {
        'On Track': 0.0,
        'Minor Delay': 0.35,
        'Delayed': 0.75,
        'Critical': 1.0
    },
    'land_acquisition': {
        'Completed': 0.0,
        'In Progress': 0.30,
        'Delayed': 0.80,
        'Pending': 1.0
    },
    'environmental_clearance': {
        'Completed': 0.0,
        'In Progress': 0.25,
        'Delayed': 0.75,
        'Pending': 1.0
    },
    'utility_shifting': {
        'Completed': 0.0,
        'In Progress': 0.25,
        'Delayed': 0.70,
        'Pending': 0.90
    }
}

FEATURE_NAMES = [
    'progress_gap',                  # Planned - Actual (percentage points)
    'delay_days_norm',               # Delay days / 365.0
    'cost_escalation_pct',           # (Revised - Approved) / Approved * 100
    'milestone_delay_ratio',         # Delayed / Total milestones
    'expenditure_vs_progress_ratio', # Budget utilization % - Physical progress %
    'contractor_risk_val',           # Encoded contractor risk
    'land_risk_val',                 # Encoded land acquisition risk
    'env_risk_val',                  # Encoded environmental clearance risk
    'utility_risk_val',              # Encoded utility shifting risk
    'physical_progress_norm',        # Physical progress / 100
    'financial_progress_norm'        # Financial progress / 100
]

def extract_features_from_dict(p_data):
    """
    Extracts numerical features from a project dictionary or model representation.
    """
    physical_prog = float(p_data.get('physical_progress') or 0.0)
    planned_prog = float(p_data.get('planned_progress') or 0.0)
    progress_gap = max(0.0, planned_prog - physical_prog)
    
    approved_cost = float(p_data.get('approved_cost') or 1.0)
    revised_cost = float(p_data.get('revised_cost') or approved_cost)
    expenditure = float(p_data.get('expenditure') or 0.0)
    
    cost_escalation = ((revised_cost - approved_cost) / approved_cost * 100.0) if approved_cost > 0 else 0.0
    cost_escalation = max(0.0, cost_escalation)
    
    budget_utilization = (expenditure / approved_cost * 100.0) if approved_cost > 0 else 0.0
    expenditure_vs_progress = max(0.0, budget_utilization - physical_prog)
    
    delay_days = float(p_data.get('delay_days') or 0.0)
    delay_days_norm = min(3.0, delay_days / 365.0)  # capped at 3 years
    
    milestones_total = max(1, int(p_data.get('milestones_total') or 4))
    milestones_delayed = int(p_data.get('milestones_delayed') or 0)
    milestone_delay_ratio = min(1.0, milestones_delayed / float(milestones_total))
    
    contractor_str = str(p_data.get('contractor_status') or 'On Track').strip()
    land_str = str(p_data.get('land_acquisition_status') or 'Completed').strip()
    env_str = str(p_data.get('environmental_clearance_status') or 'Completed').strip()
    utility_str = str(p_data.get('utility_shifting_status') or 'Completed').strip()
    
    contractor_val = STATUS_ENCODINGS['contractor'].get(contractor_str, 0.3)
    land_val = STATUS_ENCODINGS['land_acquisition'].get(land_str, 0.2)
    env_val = STATUS_ENCODINGS['environmental_clearance'].get(env_str, 0.2)
    utility_val = STATUS_ENCODINGS['utility_shifting'].get(utility_str, 0.2)
    
    feature_vector = np.array([
        progress_gap,
        delay_days_norm,
        cost_escalation,
        milestone_delay_ratio,
        expenditure_vs_progress,
        contractor_val,
        land_val,
        env_val,
        utility_val,
        physical_prog / 100.0,
        (float(p_data.get('financial_progress') or budget_utilization)) / 100.0
    ], dtype=np.float32)
    
    return feature_vector, {
        'progress_gap': progress_gap,
        'cost_escalation': cost_escalation,
        'delay_days': delay_days,
        'milestone_delay_ratio': milestone_delay_ratio,
        'expenditure_vs_progress': expenditure_vs_progress,
        'contractor_risk': contractor_val,
        'land_risk': land_val,
        'env_risk': env_val,
        'utility_risk': utility_val
    }
