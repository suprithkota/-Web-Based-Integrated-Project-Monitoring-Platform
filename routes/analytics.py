from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from services.analytics_service import get_chart_analytics, get_dashboard_kpis
from database.models import Project

analytics_bp = Blueprint('analytics', __name__)

@analytics_bp.route('/analytics')
@login_required
def index():
    authorized_ids = current_user.get_authorized_project_ids() if hasattr(current_user, 'get_authorized_project_ids') else None
    kpis = get_dashboard_kpis(project_ids=authorized_ids)
    charts = get_chart_analytics(project_ids=authorized_ids)
    return render_template('analytics.html', kpis=kpis, charts=charts)

@analytics_bp.route('/api/analytics')
@login_required
def api_analytics():
    authorized_ids = current_user.get_authorized_project_ids() if hasattr(current_user, 'get_authorized_project_ids') else None
    charts = get_chart_analytics(project_ids=authorized_ids)
    kpis = get_dashboard_kpis(project_ids=authorized_ids)
    return jsonify({
        'status': 'success',
        'kpis': kpis,
        'analytics': charts
    })
