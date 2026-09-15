import json
from datetime import datetime
from database import db
from database.models import Project, RiskPrediction
from ml.predictor import predict_project_risk

def update_project_risk(project, persist_prediction=True):
    """
    Computes risk prediction and updates project cached risk metrics in DB.
    """
    eval_result = predict_project_risk(project)
    
    project.risk_score = eval_result['overall_risk_score']
    project.delay_probability = eval_result['delay_probability']
    project.cost_overrun_probability = eval_result['cost_overrun_probability']
    project.risk_level = eval_result['risk_level']
    project.health_score = eval_result['health_score']
    
    if persist_prediction:
        pred_record = RiskPrediction(
            project_id=project.id,
            prediction_date=datetime.utcnow(),
            delay_probability=eval_result['delay_probability'],
            cost_overrun_probability=eval_result['cost_overrun_probability'],
            overall_risk_score=eval_result['overall_risk_score'],
            risk_level=eval_result['risk_level'],
            schedule_health=eval_result['health_breakdown']['schedule_health'],
            financial_health=eval_result['health_breakdown']['financial_health'],
            physical_health=eval_result['health_breakdown']['physical_health'],
            milestone_health=eval_result['health_breakdown']['milestone_health'],
            risk_factors_health=eval_result['health_breakdown']['risk_factors_health'],
            explanation=eval_result['explanation'],
            contributing_factors=json.dumps(eval_result['contributing_factors'])
        )
        db.session.add(pred_record)
        
    return eval_result

def batch_recompute_all_projects():
    """
    Recomputes and syncs risks for all projects in the database.
    """
    projects = Project.query.all()
    count = 0
    for p in projects:
        update_project_risk(p, persist_prediction=False)
        count += 1
    db.session.commit()
    return count

def calculate_project_risk_dna(project):
    """
    Computes a deterministic, grounded 8-dimension Project Risk DNA profile (0-100 scale for each):
    1. Schedule Risk: Derived from cumulative delay days and completion timeline
    2. Cost Risk: Derived from cost escalation %
    3. Progress Risk: Derived from physical progress lag against planned schedule
    4. Milestones Risk: Derived from proportion of delayed milestones
    5. Land Risk: Derived from statutory land acquisition status
    6. Environment Risk: Derived from statutory environmental clearance status
    7. Contractor Risk: Derived from contractor execution performance status
    8. Financial Risk: Derived from expenditure vs physical delivery divergence
    """
    delay_days = max(0, int(project.delay_days or 0))
    if delay_days == 0:
        sched_score = 12.0
    else:
        sched_score = min(98.0, round(15.0 + (delay_days / 180.0) * 83.0, 1))

    cost_esc = max(0.0, float(project.cost_escalation or 0.0))
    if cost_esc == 0:
        cost_score = 10.0
    else:
        cost_score = min(98.0, round(15.0 + (cost_esc / 30.0) * 83.0, 1))

    gap = max(0.0, float(project.progress_gap or 0.0))
    if gap == 0:
        prog_score = 10.0
    else:
        prog_score = min(98.0, round(15.0 + (gap / 25.0) * 83.0, 1))

    m_total = max(1, int(project.milestones_total or 1))
    m_delayed = max(0, int(project.milestones_delayed or 0))
    if m_delayed == 0:
        mile_score = 10.0
    else:
        mile_ratio = m_delayed / float(m_total)
        mile_score = min(98.0, round(20.0 + (mile_ratio * 78.0), 1))

    land_status = str(project.land_acquisition_status or 'Completed').strip()
    land_mapping = {'Completed': 10.0, 'In Progress': 35.0, 'Delayed': 80.0, 'Pending': 95.0}
    land_score = land_mapping.get(land_status, 30.0)

    env_status = str(project.environmental_clearance_status or 'Completed').strip()
    env_mapping = {'Completed': 10.0, 'In Progress': 35.0, 'Delayed': 80.0, 'Pending': 95.0}
    env_score = env_mapping.get(env_status, 30.0)

    cont_status = str(project.contractor_status or 'On Track').strip()
    cont_mapping = {'On Track': 12.0, 'Minor Delay': 45.0, 'Delayed': 78.0, 'Critical': 96.0}
    cont_score = cont_mapping.get(cont_status, 25.0)

    fin_prog = float(project.financial_progress or 0.0)
    if fin_prog == 0 and project.approved_cost and project.approved_cost > 0:
        fin_prog = (float(project.expenditure or 0.0) / float(project.approved_cost)) * 100.0
    phys_prog = float(project.physical_progress or 0.0)
    divergence = max(0.0, fin_prog - phys_prog)
    if divergence <= 5:
        fin_score = 12.0
    else:
        fin_score = min(98.0, round(15.0 + (divergence / 30.0) * 83.0, 1))

    def get_tier(val):
        if val >= 70:
            return 'CRITICAL', 'danger'
        elif val >= 45:
            return 'HIGH', 'warning'
        elif val >= 25:
            return 'MEDIUM', 'info'
        return 'LOW', 'success'

    dimensions = [
        {'key': 'schedule', 'name': 'Schedule', 'score': sched_score, 'tier': get_tier(sched_score)[0], 'color': get_tier(sched_score)[1], 'detail': f"{delay_days} days delay", 'is_observed': True},
        {'key': 'cost', 'name': 'Cost', 'score': cost_score, 'tier': get_tier(cost_score)[0], 'color': get_tier(cost_score)[1], 'detail': f"+{cost_esc}% escalation", 'is_observed': True},
        {'key': 'progress', 'name': 'Progress', 'score': prog_score, 'tier': get_tier(prog_score)[0], 'color': get_tier(prog_score)[1], 'detail': f"{gap}% progress lag", 'is_observed': True},
        {'key': 'milestones', 'name': 'Milestones', 'score': mile_score, 'tier': get_tier(mile_score)[0], 'color': get_tier(mile_score)[1], 'detail': f"{m_delayed}/{m_total} slipped", 'is_observed': True},
        {'key': 'land', 'name': 'Land', 'score': land_score, 'tier': get_tier(land_score)[0], 'color': get_tier(land_score)[1], 'detail': land_status, 'is_observed': True},
        {'key': 'environment', 'name': 'Environment', 'score': env_score, 'tier': get_tier(env_score)[0], 'color': get_tier(env_score)[1], 'detail': env_status, 'is_observed': True},
        {'key': 'contractor', 'name': 'Contractor', 'score': cont_score, 'tier': get_tier(cont_score)[0], 'color': get_tier(cont_score)[1], 'detail': cont_status, 'is_observed': True},
        {'key': 'financial', 'name': 'Financial', 'score': fin_score, 'tier': get_tier(fin_score)[0], 'color': get_tier(fin_score)[1], 'detail': f"{round(fin_prog, 1)}% spent vs {round(phys_prog, 1)}% physical", 'is_observed': True},
    ]

    avg_score = round(sum(d['score'] for d in dimensions) / len(dimensions), 1)
    highest = max(dimensions, key=lambda d: d['score'])

    return {
        'dimensions': dimensions,
        'average_dna_score': avg_score,
        'highest_risk': highest,
        'chart_labels': [d['name'] for d in dimensions],
        'chart_scores': [d['score'] for d in dimensions]
    }
