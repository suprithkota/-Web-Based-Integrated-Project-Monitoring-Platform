"""
Dedicated REST API Blueprint for Advanced Machine Learning Services:
- /api/ml/models (Listing & Diagnostic Status)
- /api/ml/comparison (Benchmarking Metrics)
- /api/ml/explanation/<project_id> (TreeSHAP Feature Attribution)
- /api/ml/anomaly/<project_id> (Isolation Forest Anomaly Detection)
- /api/ml/cluster/<project_id> (K-Means Risk Archetype Grouping)
"""

from flask import Blueprint, jsonify, abort
from flask_login import login_required, current_user
from database import db
from database.models import Project
from services.rbac_service import project_access_required
from ml.model_registry import model_registry
from ml.model_comparison import get_model_comparison_report
from ml.preprocessing import extract_features_from_dict
from ml.explainability.shap_explainer import compute_shap_explanation

ml_analytics_bp = Blueprint('ml_analytics', __name__)

@ml_analytics_bp.route('/api/ml/models', methods=['GET'])
@login_required
def api_list_models():
    """Returns metadata, diagnostic health, and operational readiness for all 7 models."""
    status_list = model_registry.get_model_status()
    return jsonify({
        'status': 'success',
        'count': len(status_list),
        'primary_model': 'Random Forest (Ensemble Regressor)',
        'models': status_list
    })

@ml_analytics_bp.route('/api/ml/comparison', methods=['GET'])
@login_required
def api_model_comparison():
    """Returns comparative regression and classification metrics across all models."""
    report = get_model_comparison_report()
    return jsonify({
        'status': 'success',
        'comparison': report
    })

@ml_analytics_bp.route('/api/ml/explanation/<int:project_id>', methods=['GET'])
@login_required
@project_access_required(write=False)
def api_project_explanation(project_id):
    """Computes and returns TreeSHAP feature attributions for a project."""
    project = db.get_or_404(Project, project_id)
    p_dict = project.to_dict()
    feature_vec, _ = extract_features_from_dict(p_dict)
    
    rf_model = model_registry.models.get('random_forest')
    shap_data = compute_shap_explanation(
        rf_model,
        feature_vec,
        model_id='rf',
        model_name='Random Forest'
    )
    
    return jsonify({
        'status': 'success',
        'project_id': project.id,
        'project_code': project.project_code,
        'project_name': project.project_name,
        'shap_explanation': shap_data
    })

@ml_analytics_bp.route('/api/ml/anomaly/<int:project_id>', methods=['GET'])
@login_required
@project_access_required(write=False)
def api_project_anomaly(project_id):
    """Computes Isolation Forest anomaly detection for a project."""
    project = db.get_or_404(Project, project_id)
    p_dict = project.to_dict()
    feature_vec, _ = extract_features_from_dict(p_dict)
    
    anomaly_result = model_registry.detect_anomaly(feature_vec)
    return jsonify({
        'status': 'success',
        'project_id': project.id,
        'project_code': project.project_code,
        'project_name': project.project_name,
        'anomaly': anomaly_result
    })

@ml_analytics_bp.route('/api/ml/cluster/<int:project_id>', methods=['GET'])
@login_required
@project_access_required(write=False)
def api_project_cluster(project_id):
    """Computes K-Means clustering assignment for a project."""
    project = db.get_or_404(Project, project_id)
    p_dict = project.to_dict()
    feature_vec, _ = extract_features_from_dict(p_dict)
    
    cluster_result = model_registry.assign_cluster(feature_vec)
    return jsonify({
        'status': 'success',
        'project_id': project.id,
        'project_code': project.project_code,
        'project_name': project.project_name,
        'cluster': cluster_result
    })
