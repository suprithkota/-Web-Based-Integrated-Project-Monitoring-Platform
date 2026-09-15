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
