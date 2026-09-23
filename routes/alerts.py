from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from database import db
from database.models import Alert, Project
from routes.auth import officer_required
from services.alert_service import update_alert_status, generate_alerts_for_all
from services.data_minimization_service import serialize_alert_for_user

alerts_bp = Blueprint('alerts', __name__)

@alerts_bp.route('/alerts')
@login_required
def index():
    severity = request.args.get('severity', '')
    status = request.args.get('status', 'active')  # default to active (Open + Under Review)
    project_id = request.args.get('project_id', type=int)
    
    query = Alert.query.join(Project)
    
    # Scope for Monitoring Officers to their assigned projects
    if current_user.role == 'officer':
        assigned_ids = current_user.get_authorized_project_ids()
        if assigned_ids:
            query = query.filter(Alert.project_id.in_(assigned_ids))
        else:
            query = query.filter(Alert.project_id == -1)
    
    if severity:
        query = query.filter(Alert.severity == severity)
        
    if status == 'active':
        query = query.filter(Alert.status.in_(['Open', 'Under Review']))
    elif status:
        query = query.filter(Alert.status == status)
        
    if project_id:
        query = query.filter(Alert.project_id == project_id)
        
    alerts = query.order_by(Alert.created_at.desc()).all()
    
    # Counts for summary badges (scoped if officer)
    base_count_q = Alert.query.join(Project)
    if current_user.role == 'officer':
        assigned_ids = current_user.get_authorized_project_ids() or []
        base_count_q = base_count_q.filter(Alert.project_id.in_(assigned_ids)) if assigned_ids else base_count_q.filter(Alert.project_id == -1)

    total_active = base_count_q.filter(Alert.status.in_(['Open', 'Under Review'])).count()
    critical_count = base_count_q.filter(Alert.status.in_(['Open', 'Under Review']), Alert.severity == 'CRITICAL').count()
    high_count = base_count_q.filter(Alert.status.in_(['Open', 'Under Review']), Alert.severity == 'HIGH').count()
    medium_count = base_count_q.filter(Alert.status.in_(['Open', 'Under Review']), Alert.severity == 'MEDIUM').count()
    resolved_count = base_count_q.filter(Alert.status == 'Resolved').count()
    
    return render_template(
        'alerts.html',
        alerts=alerts,
        counts={
            'active': total_active,
            'critical': critical_count,
            'high': high_count,
            'medium': medium_count,
            'resolved': resolved_count
        },
        current_filter={'severity': severity, 'status': status, 'project_id': project_id}
    )

@alerts_bp.route('/risk-intelligence')
@alerts_bp.route('/risk-alerts', endpoint='risk_intelligence')
@login_required
def risk_intelligence():
    from database.models import ProjectDelayRecord
    from services.recommendation_service import generate_project_recommendations
    from services.rbac_service import get_scoped_projects_query
    
    # 1. Alerts & Counts
    base_query = Alert.query.join(Project)
    if current_user.role == 'officer':
        assigned_ids = current_user.get_authorized_project_ids() or []
        base_query = base_query.filter(Alert.project_id.in_(assigned_ids)) if assigned_ids else base_query.filter(Alert.project_id == -1)
    
    alerts = base_query.filter(Alert.status.in_(['Open', 'Under Review'])).order_by(Alert.created_at.desc()).all()
    
    total_active = len(alerts)
    critical_count = sum(1 for a in alerts if a.severity == 'CRITICAL')
    high_count = sum(1 for a in alerts if a.severity == 'HIGH')
    medium_count = sum(1 for a in alerts if a.severity == 'MEDIUM')
    resolved_count = Alert.query.filter_by(status='Resolved').count()
    
    # 2. Critical Risks
    p_query = get_scoped_projects_query(current_user)
    critical_projects = p_query.filter(Project.risk_level == 'CRITICAL').order_by(Project.risk_score.desc()).all()
    
    # 3. Delayed Projects
    delayed_projects = p_query.filter(Project.delay_days > 60).order_by(Project.delay_days.desc()).all()
    
    # 4. Cost Overruns
    cost_overrun_projects = p_query.filter(Project.revised_cost > Project.approved_cost).order_by((Project.revised_cost - Project.approved_cost).desc()).all()
    
    # 5. Schedule Risks
    schedule_risk_projects = p_query.filter(Project.milestones_delayed > 0).order_by(Project.milestones_delayed.desc()).all()
    
    # 6. Delay Causes
    delay_records = ProjectDelayRecord.query.order_by(ProjectDelayRecord.recorded_at.desc()).limit(30).all()
    delay_cat_stats = {}
    for d in delay_records:
        cat = d.delay_category or 'Other'
        if cat not in delay_cat_stats:
            delay_cat_stats[cat] = {'count': 0, 'total_days': 0}
        delay_cat_stats[cat]['count'] += 1
        delay_cat_stats[cat]['total_days'] += (d.affected_days or 0)
        
    # 7. AI Recommendations
    recommendations = []
    sample_projects = p_query.order_by(Project.risk_score.desc()).limit(5).all()
    for sp in sample_projects:
        recs = generate_project_recommendations(sp.to_dict())
        for r in recs[:2]:
            r['project_name'] = sp.project_name
            recommendations.append(r)
            
    # 8. All projects for Simulator
    all_projects = p_query.order_by(Project.project_name.asc()).all()
    selected_project = all_projects[0] if all_projects else None

    return render_template(
        'risk_intelligence.html',
        alerts=alerts,
        counts={
            'active': total_active,
            'critical': critical_count,
            'high': high_count,
            'medium': medium_count,
            'resolved': resolved_count
        },
        critical_projects=critical_projects,
        delayed_projects=delayed_projects,
        cost_overrun_projects=cost_overrun_projects,
        schedule_risk_projects=schedule_risk_projects,
        delay_records=delay_records,
        delay_category_stats=delay_cat_stats,
        recommendations=recommendations,
        all_projects=all_projects,
        selected_project=selected_project
    )

@alerts_bp.route('/alerts/<int:alert_id>/status', methods=['POST'])
@officer_required
def change_status(alert_id):
    alert_obj = db.session.get(Alert, alert_id)
    if not alert_obj:
        flash("Alert not found.", "danger")
        return redirect(request.referrer or url_for('alerts.index'))

    # Check object permission for Officer
    if current_user.role == 'officer' and not current_user.can_access_project(alert_obj.project_id, write=True):
        flash("Access Denied: You are not authorized to modify alerts for this project.", "danger")
        return redirect(request.referrer or url_for('alerts.index'))

    new_status = request.form.get('status', 'Under Review')
    notes = request.form.get('notes', '')
    
    user_name = current_user.full_name or current_user.username
    alert = update_alert_status(alert_id, new_status, user_name, notes)
    
    if alert:
        flash(f"Alert #{alert.id} status updated to '{new_status}'.", "success")
    else:
        flash("Alert not found.", "danger")
        
    return redirect(request.referrer or url_for('alerts.index'))

@alerts_bp.route('/alerts/refresh', methods=['POST'])
@officer_required
def refresh_alerts():
    new_count = generate_alerts_for_all()
    flash(f"Early Warning System scan completed. {new_count} alerts generated/updated.", "info")
    return redirect(url_for('alerts.index'))

# ================= REST APIs =================

@alerts_bp.route('/api/alerts', methods=['GET'])
@login_required
def api_get_alerts():
    status = request.args.get('status')
    query = Alert.query.join(Project)
    
    if current_user.role == 'officer':
        assigned_ids = current_user.get_authorized_project_ids()
        if assigned_ids:
            query = query.filter(Alert.project_id.in_(assigned_ids))
        else:
            query = query.filter(Alert.project_id == -1)

    if status:
        query = query.filter(Alert.status == status)
    alerts = query.order_by(Alert.created_at.desc()).all()
    return jsonify({
        'status': 'success',
        'count': len(alerts),
        'alerts': [serialize_alert_for_user(a, current_user) for a in alerts]
    })

@alerts_bp.route('/api/alerts/<int:alert_id>/resolve', methods=['POST'])
@officer_required
def api_resolve_alert(alert_id):
    alert_obj = db.session.get(Alert, alert_id)
    if not alert_obj:
        return jsonify({'status': 'error', 'message': 'Alert not found'}), 404

    # Object-level check for officer
    if current_user.role == 'officer' and not current_user.can_access_project(alert_obj.project_id, write=True):
        return jsonify({'status': 'error', 'message': 'Forbidden: You do not have permission to resolve alerts for this project.'}), 403

    data = request.get_json(silent=True) or {}
    notes = data.get('notes', 'Resolved via API')
    user_name = current_user.full_name or current_user.username
    
    alert = update_alert_status(alert_id, 'Resolved', user_name, notes)
    return jsonify({
        'status': 'success',
        'message': f'Alert #{alert_id} marked as Resolved',
        'alert': serialize_alert_for_user(alert, current_user)
    })
