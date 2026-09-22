import os
import uuid
import json
from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from database import db
from database.models import (
    DataSourceConfig, DataSyncLog, DataVersionHistory,
    DataConflictRecord, Project, Contractor
)
from services.sync_service import SyncService
from services.rbac_service import role_required, admin_required, officer_required
from services.audit_service import log_security_event

data_sync_bp = Blueprint('data_sync', __name__)

# =========================================================================
# 1. OFFICIAL DATA SOURCES MANAGEMENT (ADMIN & OFFICER VIEW)
# =========================================================================
@data_sync_bp.route('/admin/data-sources')
@admin_required
def data_sources():
    sources = DataSourceConfig.query.order_by(DataSourceConfig.source_priority.asc(), DataSourceConfig.id.asc()).all()
    recent_logs = DataSyncLog.query.order_by(DataSyncLog.request_time.desc()).limit(10).all()
    unresolved_conflicts = DataConflictRecord.query.filter_by(status='Unresolved').count()

    # Aggregate telemetry
    total_sources = len(sources)
    connected_sources = sum(1 for s in sources if s.connection_status == 'Connected')
    total_imported = sum((s.records_imported or 0) for s in sources)
    total_updated = sum((s.records_updated or 0) for s in sources)

    return render_template(
        'sync/data_sources.html',
        sources=sources,
        recent_logs=recent_logs,
        unresolved_conflicts=unresolved_conflicts,
        total_sources=total_sources,
        connected_sources=connected_sources,
        total_imported=total_imported,
        total_updated=total_updated
    )

@data_sync_bp.route('/admin/data-sources/new', methods=['GET', 'POST'])
@admin_required
def new_data_source():
    if request.method == 'POST':
        name = request.form.get('source_name', '').strip()
        dept = request.form.get('department', '').strip()
        stype = request.form.get('source_type', 'API').strip()
        url = request.form.get('endpoint_url', '').strip()
        auth_method = request.form.get('auth_method', 'None').strip()
        secret = request.form.get('auth_secret', '').strip()
        sync_method = request.form.get('sync_method', 'Polling').strip()
        frequency = request.form.get('sync_frequency', '1 hour').strip()
        priority = request.form.get('source_priority', 1, type=int)

        if not name:
            flash("Data source name is required.", "danger")
            return redirect(url_for('data_sync.new_data_source'))

        existing = DataSourceConfig.query.filter_by(source_name=name).first()
        if existing:
            flash(f"Data source '{name}' already exists.", "warning")
            return redirect(url_for('data_sync.new_data_source'))

        now = datetime.utcnow()
        source = DataSourceConfig(
            source_name=name,
            department=dept,
            source_type=stype,
            endpoint_url=url,
            auth_method=auth_method,
            encrypted_auth_secret=secret,
            sync_method=sync_method,
            sync_frequency=frequency,
            source_priority=priority,
            connection_status='Connected',
            next_scheduled_sync=SyncService._calculate_next_sync(frequency, now),
            is_active=True
        )
        db.session.add(source)
        db.session.commit()

        log_security_event(
            'DATA_SOURCE_CREATED',
            user_id=current_user.id,
            username=current_user.username,
            resource_type='data_source',
            resource_id=str(source.id),
            details=f"Created official source config '{name}'",
            status='SUCCESS'
        )

        flash(f"Official Data Source '{name}' registered successfully.", "success")
        return redirect(url_for('data_sync.data_sources'))

    return render_template('sync/data_source_form.html', source=None)

@data_sync_bp.route('/admin/data-sources/<int:source_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_data_source(source_id):
    source = db.session.get(DataSourceConfig, source_id)
    if not source:
        flash("Data source not found.", "warning")
        return redirect(url_for('data_sync.data_sources'))

    if request.method == 'POST':
        source.source_name = request.form.get('source_name', source.source_name).strip()
        source.department = request.form.get('department', source.department).strip()
        source.source_type = request.form.get('source_type', source.source_type).strip()
        source.endpoint_url = request.form.get('endpoint_url', '').strip()
        source.auth_method = request.form.get('auth_method', 'None').strip()
        secret = request.form.get('auth_secret', '').strip()
        if secret:
            source.encrypted_auth_secret = secret
        source.sync_method = request.form.get('sync_method', source.sync_method).strip()
        source.sync_frequency = request.form.get('sync_frequency', source.sync_frequency).strip()
        source.source_priority = request.form.get('source_priority', source.source_priority, type=int)
        source.is_active = (request.form.get('is_active') == 'on')

        db.session.commit()
        flash(f"Data source '{source.source_name}' updated successfully.", "success")
        return redirect(url_for('data_sync.data_sources'))

    return render_template('sync/data_source_form.html', source=source)

@data_sync_bp.route('/admin/data-sources/<int:source_id>/sync-now', methods=['POST'])
@role_required('admin', 'officer')
def sync_now(source_id):
    source = db.session.get(DataSourceConfig, source_id)
    if not source:
        flash("Data source not found.", "warning")
        return redirect(url_for('data_sync.data_sources'))

    result = SyncService.sync_source(source.id)
    if result['status'] == 'SUCCESS':
        flash(
            f"Synchronization completed for '{source.source_name}'. "
            f"Received: {result['records_received']}, Inserted: {result['records_inserted']}, "
            f"Updated: {result['records_updated']}, Conflicts: {result['conflicts_count']}.",
            "success"
        )
    else:
        flash(f"Synchronization issue with '{source.source_name}': {result.get('error', 'Unknown error')}", "danger")

    return redirect(request.referrer or url_for('data_sync.data_sources'))

@data_sync_bp.route('/admin/data-sources/<int:source_id>/test-connection', methods=['POST'])
@admin_required
def test_connection(source_id):
    source = db.session.get(DataSourceConfig, source_id)
    if not source:
        return jsonify({'status': 'error', 'message': 'Data source not found'}), 404

    try:
        data = SyncService._fetch_source_data(source)
        source.connection_status = 'Connected'
        source.last_error_message = ''
        db.session.commit()
        return jsonify({
            'status': 'success',
            'message': f"Connection verified. Source returned {len(data)} live records.",
            'records_preview_count': len(data)
        })
    except Exception as e:
        source.connection_status = 'Temporarily Unavailable'
        source.last_error_message = str(e)
        db.session.commit()
        return jsonify({
            'status': 'error',
            'message': f"Connection test failed: {str(e)}"
        }), 500

# =========================================================================
# 2. CONFLICT RESOLUTION CENTER (ADMIN & OFFICER)
# =========================================================================
@data_sync_bp.route('/admin/data-conflicts')
@role_required('admin', 'officer')
def data_conflicts():
    status_filter = request.args.get('status', 'Unresolved').strip()
    query = DataConflictRecord.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    conflicts = query.order_by(DataConflictRecord.created_at.desc()).all()

    return render_template(
        'sync/data_conflicts.html',
        conflicts=conflicts,
        selected_status=status_filter
    )

@data_sync_bp.route('/admin/data-conflicts/<int:conflict_id>/resolve', methods=['POST'])
@role_required('admin', 'officer')
def resolve_conflict(conflict_id):
    conflict = db.session.get(DataConflictRecord, conflict_id)
    if not conflict:
        flash("Conflict record not found.", "warning")
        return redirect(url_for('data_sync.data_conflicts'))

    choice = request.form.get('resolution_choice', '').strip()  # 'source_a', 'source_b', 'custom'
    custom_val = request.form.get('custom_value', '').strip()
    notes = request.form.get('resolution_notes', '').strip()

    if choice == 'source_a':
        resolved_val = conflict.source_a_value
        source_adopted = conflict.source_a_name
    elif choice == 'source_b':
        resolved_val = conflict.source_b_value
        source_adopted = conflict.source_b_name
    elif choice == 'custom':
        resolved_val = custom_val
        source_adopted = f"Officer Determined ({current_user.username})"
    else:
        flash("Please select a valid resolution choice.", "danger")
        return redirect(url_for('data_sync.data_conflicts'))

    now = datetime.utcnow()

    # Update target entity
    if conflict.entity_type == 'Project':
        project = db.session.get(Project, conflict.entity_id)
        if project and hasattr(project, conflict.field_name):
            old_val = getattr(project, conflict.field_name)
            # Type cast appropriately
            target_type = type(old_val) if old_val is not None else str
            try:
                if target_type == float:
                    casted_val = float(resolved_val)
                elif target_type == int:
                    casted_val = int(resolved_val)
                else:
                    casted_val = str(resolved_val)
                setattr(project, conflict.field_name, casted_val)
            except Exception:
                setattr(project, conflict.field_name, resolved_val)

            # Record version history
            v = DataVersionHistory(
                entity_type='Project',
                entity_id=project.id,
                field_name=conflict.field_name,
                previous_value=str(old_val),
                new_value=str(resolved_val),
                source_name=source_adopted,
                source_timestamp=now,
                sync_timestamp=now,
                verification_status='Verified',
                changed_by=f"Officer {current_user.full_name or current_user.username}",
                reason=f"Resolved data conflict between {conflict.source_a_name} and {conflict.source_b_name}. Notes: {notes}"
            )
            db.session.add(v)

            # Check if any more unresolved conflicts exist for this project
            remaining = DataConflictRecord.query.filter(
                DataConflictRecord.entity_type == 'Project',
                DataConflictRecord.entity_id == project.id,
                DataConflictRecord.id != conflict.id,
                DataConflictRecord.status == 'Unresolved'
            ).count()
            if remaining == 0:
                project.verification_status = 'Verified'

    conflict.status = 'Resolved'
    conflict.resolved_value = str(resolved_val)
    conflict.resolved_by = current_user.full_name or current_user.username
    conflict.resolved_at = now
    conflict.notes = notes
    db.session.commit()

    log_security_event(
        'DATA_CONFLICT_RESOLVED',
        user_id=current_user.id,
        username=current_user.username,
        resource_type='conflict',
        resource_id=str(conflict.id),
        details=f"Conflict resolved on {conflict.entity_type} #{conflict.entity_id} ({conflict.field_name}) -> {resolved_val}",
        status='SUCCESS'
    )

    flash(f"Conflict on {conflict.field_name} resolved successfully with value: '{resolved_val}'.", "success")
    return redirect(url_for('data_sync.data_conflicts'))

# =========================================================================
# 3. AUDIT & SYNC LOGS HISTORY (ADMIN & OFFICER)
# =========================================================================
@data_sync_bp.route('/admin/sync-logs')
@role_required('admin', 'officer')
def sync_logs():
    page = request.args.get('page', 1, type=int)
    source_id = request.args.get('source_id', type=int)
    status_filter = request.args.get('status', '').strip()

    query = DataSyncLog.query
    if source_id:
        query = query.filter_by(source_id=source_id)
    if status_filter:
        query = query.filter_by(status=status_filter)

    logs = query.order_by(DataSyncLog.request_time.desc()).paginate(page=page, per_page=25, error_out=False)
    sources = DataSourceConfig.query.all()

    return render_template(
        'sync/sync_logs.html',
        logs=logs,
        sources=sources,
        selected_source_id=source_id,
        selected_status=status_filter
    )

# =========================================================================
# 4. OFFICER VERIFIED MANUAL ENTRY (OFFICER & ADMIN)
# =========================================================================
@data_sync_bp.route('/officer/data-entry', methods=['GET', 'POST'])
@role_required('admin', 'officer')
def officer_data_entry():
    projects = Project.query.order_by(Project.project_name.asc()).all()

    if request.method == 'POST':
        project_id = request.form.get('project_id', type=int)
        field_to_update = request.form.get('field_to_update', '').strip()
        new_val = request.form.get('new_value', '').strip()
        ref_order = request.form.get('official_order_reference', '').strip()
        reason = request.form.get('reason_for_update', '').strip()

        if not project_id or not field_to_update or not new_val or not ref_order:
            flash("All fields including Official Order Reference are required for audit trail.", "danger")
            return redirect(url_for('data_sync.officer_data_entry'))

        project = db.session.get(Project, project_id)
        if not project or not hasattr(project, field_to_update):
            flash("Invalid project or target field.", "danger")
            return redirect(url_for('data_sync.officer_data_entry'))

        old_val = getattr(project, field_to_update)
        try:
            target_type = type(old_val) if old_val is not None else str
            if target_type == float:
                casted_val = float(new_val)
            elif target_type == int:
                casted_val = int(new_val)
            else:
                casted_val = str(new_val)
            setattr(project, field_to_update, casted_val)
        except Exception:
            setattr(project, field_to_update, new_val)

        now = datetime.utcnow()
        v = DataVersionHistory(
            entity_type='Project',
            entity_id=project.id,
            field_name=field_to_update,
            previous_value=str(old_val),
            new_value=str(new_val),
            source_name=f"Verified Officer Manual Entry ({ref_order})",
            source_timestamp=now,
            sync_timestamp=now,
            verification_status='Officer verified',
            changed_by=f"{current_user.full_name or current_user.username} ({getattr(current_user, 'technical_designation', 'Engineer')})",
            reason=f"Official Order Ref: {ref_order}. Justification: {reason}"
        )
        db.session.add(v)
        project.sync_timestamp = now
        db.session.commit()

        flash(f"Manual update recorded and versioned for {project.project_code} ({field_to_update}).", "success")
        return redirect(url_for('data_sync.officer_data_entry'))

    return render_template('sync/officer_entry.html', projects=projects)

# =========================================================================
# 5. REAL-TIME WEBHOOK RECEIVER (EXTERNAL SOURCES)
# =========================================================================
@data_sync_bp.route('/api/webhooks/source/<int:source_id>', methods=['POST'])
def receive_webhook(source_id):
    source = db.session.get(DataSourceConfig, source_id)
    if not source or not source.is_active:
        return jsonify({'status': 'error', 'message': 'Invalid or inactive data source webhook endpoint'}), 404

    # Optional bearer token check if configured
    if source.encrypted_auth_secret:
        auth_header = request.headers.get('Authorization', '')
        expected = f"Bearer {source.encrypted_auth_secret}"
        if auth_header != expected:
            return jsonify({'status': 'error', 'message': 'Unauthorized webhook call'}), 401

    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({'status': 'error', 'message': 'Invalid JSON payload'}), 400

    items = payload if isinstance(payload, list) else payload.get('projects', [payload])

    inserted = 0
    updated = 0
    conflicts = 0

    for item in items:
        norm = SyncService.normalize_incoming_project(item, source.source_name)
        outcome, _ = SyncService.process_normalized_project(norm, source)
        if outcome == 'inserted':
            inserted += 1
        elif outcome == 'updated':
            updated += 1
        elif outcome == 'conflict':
            conflicts += 1

    source.last_successful_sync = datetime.utcnow()
    source.records_imported += inserted
    source.records_updated += updated
    db.session.commit()

    return jsonify({
        'status': 'success',
        'message': f"Webhook processed successfully: {len(items)} items received.",
        'inserted': inserted,
        'updated': updated,
        'conflicts': conflicts
    })

# =========================================================================
# 6. REST APIS FOR SYNC TELEMETRY
# =========================================================================
@data_sync_bp.route('/api/sync/sources')
@role_required('admin', 'officer')
def api_sources():
    sources = DataSourceConfig.query.all()
    return jsonify({
        'status': 'success',
        'sources': [s.to_dict() for s in sources]
    })

@data_sync_bp.route('/api/sync/logs')
@role_required('admin', 'officer')
def api_sync_logs():
    logs = DataSyncLog.query.order_by(DataSyncLog.request_time.desc()).limit(20).all()
    return jsonify({
        'status': 'success',
        'logs': [l.to_dict() for l in logs]
    })

@data_sync_bp.route('/api/sync/conflicts')
@role_required('admin', 'officer')
def api_conflicts():
    conflicts = DataConflictRecord.query.filter_by(status='Unresolved').all()
    return jsonify({
        'status': 'success',
        'conflicts': [c.to_dict() for c in conflicts]
    })
