from ml.risk_model import risk_engine

def predict_project_risk(project):
    """
    Computes real-time risk predictions, probabilities, health scores,
    explainability factors, and cautious root cause analysis for a Project instance or dict.
    """
    if hasattr(project, 'to_dict'):
        data = project.to_dict()
    elif isinstance(project, dict):
        data = project
    else:
        data = {
            'physical_progress': getattr(project, 'physical_progress', 0.0),
            'planned_progress': getattr(project, 'planned_progress', 0.0),
            'approved_cost': getattr(project, 'approved_cost', 0.0),
            'revised_cost': getattr(project, 'revised_cost', 0.0),
            'expenditure': getattr(project, 'expenditure', 0.0),
            'delay_days': getattr(project, 'delay_days', 0),
            'milestones_total': getattr(project, 'milestones_total', 4),
            'milestones_delayed': getattr(project, 'milestones_delayed', 0),
            'contractor_status': getattr(project, 'contractor_status', 'On Track'),
            'land_acquisition_status': getattr(project, 'land_acquisition_status', 'Completed'),
            'environmental_clearance_status': getattr(project, 'environmental_clearance_status', 'Completed'),
            'utility_shifting_status': getattr(project, 'utility_shifting_status', 'Completed')
        }

    return risk_engine.evaluate_project(data)
