from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from database.models import Project, User, SiteInspectionRecord, PublicComplaint, DepartmentHierarchy, DocumentEvidence
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

    # Role-specific operational telemetry and governance queues
    role_context = {}
    if current_user.role == 'officer':
        assigned_query = Project.query
        if authorized_ids is not None:
            assigned_query = assigned_query.filter(Project.id.in_(authorized_ids))
        assigned_projects = assigned_query.order_by(Project.risk_score.desc()).limit(6).all()
        
        insp_query = SiteInspectionRecord.query.filter(SiteInspectionRecord.verification_status.ilike('%Pending%'))
        if authorized_ids is not None:
            insp_query = insp_query.filter(SiteInspectionRecord.project_id.in_(authorized_ids))
        pending_inspections = insp_query.order_by(SiteInspectionRecord.inspection_date.desc()).limit(5).all()
        pending_inspections_count = insp_query.count()

        comp_query = PublicComplaint.query.filter(~PublicComplaint.status.in_(['Resolved', 'Closed']))
        if authorized_ids is not None:
            comp_query = comp_query.filter(PublicComplaint.project_id.in_(authorized_ids))
        assigned_complaints = comp_query.order_by(PublicComplaint.created_at.desc()).limit(5).all()
        assigned_complaints_count = comp_query.count()

        role_context = {
            'assigned_projects': assigned_projects,
            'assigned_projects_count': len(assigned_projects),
            'pending_inspections': pending_inspections,
            'pending_inspections_count': pending_inspections_count,
            'assigned_complaints': assigned_complaints,
            'assigned_complaints_count': assigned_complaints_count,
        }
    elif current_user.role == 'admin':
        pending_users = User.query.filter_by(status='pending_approval').order_by(User.created_at.desc()).limit(5).all()
        pending_users_count = User.query.filter_by(status='pending_approval').count()
        total_users_count = User.query.count()
        total_depts = DepartmentHierarchy.query.count()
        unresolved_complaints_count = PublicComplaint.query.filter(~PublicComplaint.status.in_(['Resolved', 'Closed'])).count()
        total_docs = DocumentEvidence.query.count()
        verified_docs = DocumentEvidence.query.filter_by(verification_status='Verified').count()
        sync_integrity_pct = round((verified_docs / total_docs * 100.0), 1) if total_docs > 0 else 100.0

        role_context = {
            'pending_users': pending_users,
            'pending_users_count': pending_users_count,
            'total_users_count': total_users_count,
            'total_departments_count': total_depts,
            'unresolved_complaints_count': unresolved_complaints_count,
            'sync_integrity_pct': sync_integrity_pct,
            'total_docs_count': total_docs,
        }
    else:  # viewer
        role_context = {
            'total_public_projects': Project.query.count(),
            'completed_public_projects': Project.query.filter_by(project_status='Completed').count(),
            'ongoing_public_projects': Project.query.filter_by(project_status='Ongoing').count(),
        }
    
    return render_template(
        'dashboard.html',
        kpis=kpis,
        alerts=alerts,
        recommendations=recommendations,
        ministries=ministries,
        sectors=sectors,
        states=states,
        active_filters=active_filters,
        role_context=role_context
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
