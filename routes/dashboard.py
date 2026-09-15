from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from database.models import Project
from services.analytics_service import get_dashboard_kpis, get_chart_analytics, get_dashboard_alerts, get_dashboard_recommendations

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')
def root():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    return redirect(url_for('auth.login'))

@dashboard_bp.route('/dashboard')
@login_required
def index():
    # Collect unique filter options from DB
    ministries = [m[0] for m in Project.query.with_entities(Project.ministry).distinct().order_by(Project.ministry).all()]
    sectors = [s[0] for s in Project.query.with_entities(Project.sector).distinct().order_by(Project.sector).all()]
    states = [st[0] for st in Project.query.with_entities(Project.state).distinct().order_by(Project.state).all()]
    
    # Active filters from URL query parameters
    active_filters = {
        'ministry': request.args.get('ministry', ''),
        'sector': request.args.get('sector', ''),
        'state': request.args.get('state', ''),
        'status': request.args.get('status', ''),
        'risk_level': request.args.get('risk_level', '')
    }
    
    # Filter out empty values
    clean_filters = {k: v for k, v in active_filters.items() if v}
    authorized_ids = current_user.get_authorized_project_ids() if hasattr(current_user, 'get_authorized_project_ids') else None

    kpis = get_dashboard_kpis(clean_filters, project_ids=authorized_ids)
    alerts = get_dashboard_alerts(limit=6, project_ids=authorized_ids)
    recommendations = get_dashboard_recommendations(limit=5, project_ids=authorized_ids)
    
    return render_template(
        'dashboard.html',
        kpis=kpis,
        alerts=alerts,
        recommendations=recommendations,
        ministries=ministries,
        sectors=sectors,
        states=states,
        active_filters=active_filters
    )

@dashboard_bp.route('/api/dashboard')
@login_required
def api_dashboard():
    active_filters = {
        'ministry': request.args.get('ministry', ''),
        'sector': request.args.get('sector', ''),
        'state': request.args.get('state', ''),
        'status': request.args.get('status', ''),
        'risk_level': request.args.get('risk_level', '')
    }
    clean_filters = {k: v for k, v in active_filters.items() if v}
    authorized_ids = current_user.get_authorized_project_ids() if hasattr(current_user, 'get_authorized_project_ids') else None
    
    kpis = get_dashboard_kpis(clean_filters, project_ids=authorized_ids)
    chart_data = get_chart_analytics(project_ids=authorized_ids)
    
    return jsonify({
        'status': 'success',
        'kpis': kpis,
        'charts': chart_data
    })

@dashboard_bp.route('/about')
def about():
    return render_template('about.html')
