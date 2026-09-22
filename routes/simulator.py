from flask import Blueprint, render_template, request, jsonify, abort
from flask_login import login_required, current_user
from extensions import limiter
from database import db
from database.models import Project
from services.rbac_service import get_scoped_projects_query
from ml.predictor import predict_project_risk

simulator_bp = Blueprint('simulator', __name__)

@simulator_bp.route('/simulator')
@login_required
def index():
    projects = get_scoped_projects_query(current_user).order_by(Project.project_name).all()
    selected_id = request.args.get('project_id', type=int)
    
    selected_project = None
    if selected_id:
        if current_user.can_access_project(selected_id, write=False):
            selected_project = db.session.get(Project, selected_id)
        else:
            abort(403)
            
    if not selected_project and projects:
        selected_project = projects[0]
        
    return render_template(
        'simulator.html',
        projects=projects,
        selected_project=selected_project
    )

@simulator_bp.route('/api/simulate', methods=['POST'])
@login_required
@limiter.limit("30 per minute")
def api_simulate():
    """
    Accepts baseline project parameters and scenario modifications,
    runs the risk prediction engine, and returns side-by-side comparative metrics.
    """
    data = request.get_json(silent=True) or request.form.to_dict()
    
    project_id = data.get('project_id')
    base_project = None
    if project_id:
        try:
            pid = int(project_id)
            if not current_user.can_access_project(pid, write=False):
                return jsonify({'status': 'error', 'message': 'Forbidden: You do not have permission to simulate on this project.'}), 403
            base_project = db.session.get(Project, pid)
        except (ValueError, TypeError):
            return jsonify({'status': 'error', 'message': 'Invalid project_id parameter.'}), 400
    
    # Baseline data
    if base_project:
        base_data = base_project.to_dict()
        current_eval = predict_project_risk(base_project)
    else:
        try:
            base_data = {
                'physical_progress': max(0.0, min(100.0, float(data.get('base_physical_progress', 50.0)))),
                'planned_progress': max(0.0, min(100.0, float(data.get('base_planned_progress', 65.0)))),
                'approved_cost': max(0.0, float(data.get('base_approved_cost', 1000.0))),
                'revised_cost': max(0.0, float(data.get('base_revised_cost', 1100.0))),
                'expenditure': max(0.0, float(data.get('base_expenditure', 550.0))),
                'delay_days': max(0, min(3650, int(data.get('base_delay_days', 60)))),
                'milestones_total': max(1, int(data.get('base_milestones_total', 4))),
                'milestones_delayed': max(0, int(data.get('base_milestones_delayed', 1))),
                'contractor_status': str(data.get('base_contractor_status', 'On Track'))[:50],
                'land_acquisition_status': str(data.get('base_land_acquisition_status', 'In Progress'))[:50],
                'environmental_clearance_status': str(data.get('base_environmental_clearance_status', 'Completed'))[:50],
                'utility_shifting_status': str(data.get('base_utility_shifting_status', 'Completed'))[:50]
            }
        except (ValueError, TypeError):
            return jsonify({'status': 'error', 'message': 'Invalid baseline input parameters.'}), 400
        current_eval = predict_project_risk(base_data)

    # Construct simulated scenario parameters
    sim_data = dict(base_data)
    try:
        if 'physical_progress' in data and data['physical_progress'] != '':
            sim_data['physical_progress'] = max(0.0, min(100.0, float(data['physical_progress'])))
        if 'planned_progress' in data and data['planned_progress'] != '':
            sim_data['planned_progress'] = max(0.0, min(100.0, float(data['planned_progress'])))
        if 'revised_cost' in data and data['revised_cost'] != '':
            sim_data['revised_cost'] = max(0.0, float(data['revised_cost']))
        if 'expenditure' in data and data['expenditure'] != '':
            sim_data['expenditure'] = max(0.0, float(data['expenditure']))
        if 'delay_days' in data and data['delay_days'] != '':
            sim_data['delay_days'] = max(0, min(3650, int(data['delay_days'])))
        if 'milestones_delayed' in data and data['milestones_delayed'] != '':
            sim_data['milestones_delayed'] = max(0, int(data['milestones_delayed']))
        if 'contractor_status' in data and data['contractor_status']:
            sim_data['contractor_status'] = str(data['contractor_status'])[:50]
        if 'land_acquisition_status' in data and data['land_acquisition_status']:
            sim_data['land_acquisition_status'] = str(data['land_acquisition_status'])[:50]
        if 'environmental_clearance_status' in data and data['environmental_clearance_status']:
            sim_data['environmental_clearance_status'] = str(data['environmental_clearance_status'])[:50]
        if 'utility_shifting_status' in data and data['utility_shifting_status']:
            sim_data['utility_shifting_status'] = str(data['utility_shifting_status'])[:50]
    except (ValueError, TypeError):
        return jsonify({'status': 'error', 'message': 'Invalid scenario input values.'}), 400

    simulated_eval = predict_project_risk(sim_data)
    
    # Calculate deltas
    risk_delta = round(simulated_eval['overall_risk_score'] - current_eval['overall_risk_score'], 1)
    delay_delta = round(simulated_eval['delay_probability'] - current_eval['delay_probability'], 1)
    cost_delta = round(simulated_eval['cost_overrun_probability'] - current_eval['cost_overrun_probability'], 1)
    health_delta = round(simulated_eval['health_score'] - current_eval['health_score'], 1)

    return jsonify({
        'status': 'success',
        'disclaimer': 'Scenario Simulation — Not an official forecast',
        'current': {
            'risk_score': current_eval['overall_risk_score'],
            'delay_prob': current_eval['delay_probability'],
            'cost_prob': current_eval['cost_overrun_probability'],
            'health_score': current_eval['health_score'],
            'risk_level': current_eval['risk_level'],
            'explanation': current_eval['explanation'],
            'model_predictions': current_eval.get('model_predictions', {}),
            'anomaly': current_eval.get('anomaly', {}),
            'cluster': current_eval.get('cluster', {}),
            'shap_explanation': current_eval.get('shap_explanation', {})
        },
        'simulated': {
            'risk_score': simulated_eval['overall_risk_score'],
            'delay_prob': simulated_eval['delay_probability'],
            'cost_prob': simulated_eval['cost_overrun_probability'],
            'health_score': simulated_eval['health_score'],
            'risk_level': simulated_eval['risk_level'],
            'explanation': simulated_eval['explanation'],
            'factors': simulated_eval['contributing_factors'] if current_user.role != 'viewer' else {},
            'model_predictions': simulated_eval.get('model_predictions', {}),
            'anomaly': simulated_eval.get('anomaly', {}),
            'cluster': simulated_eval.get('cluster', {}),
            'shap_explanation': simulated_eval.get('shap_explanation', {})
        },
        'deltas': {
            'risk_delta': risk_delta,
            'delay_delta': delay_delta,
            'cost_delta': cost_delta,
            'health_delta': health_delta,
            'direction': 'DETERIORATING' if risk_delta > 0 else ('IMPROVING' if risk_delta < 0 else 'STABLE')
        }
    })
