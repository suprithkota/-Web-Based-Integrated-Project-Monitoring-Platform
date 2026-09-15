import io
import csv
from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response
from flask_login import login_required, current_user
from database import db
from database.models import Project, Milestone, ProjectHistory, Alert, ProjectAssignment
from services.rbac_service import role_required, project_access_required, admin_required, officer_required, get_scoped_projects_query
from services.risk_service import update_project_risk, calculate_project_risk_dna
from services.alert_service import evaluate_and_generate_alerts
from services.recommendation_service import generate_project_recommendations
from services.audit_service import log_security_event
from services.data_minimization_service import serialize_project_for_user, get_visible_project_fields, filter_project_fields_by_role
from ml.predictor import predict_project_risk

projects_bp = Blueprint('projects', __name__)

def validate_project_inputs(form_data):
    errors = []
    try:
        phys = float(form_data.get('physical_progress') or 0.0)
        if not (0.0 <= phys <= 100.0):
            errors.append("Physical progress must be between 0.0% and 100.0%.")
    except (ValueError, TypeError):
        errors.append("Physical progress must be a valid number.")

    try:
        plan = float(form_data.get('planned_progress') or 0.0)
        if not (0.0 <= plan <= 100.0):
            errors.append("Planned progress must be between 0.0% and 100.0%.")
    except (ValueError, TypeError):
        errors.append("Planned progress must be a valid number.")

    try:
        cost = float(form_data.get('approved_cost') or 0.0)
        if cost < 0:
            errors.append("Approved cost cannot be negative.")
    except (ValueError, TypeError):
        errors.append("Approved cost must be a valid number.")

    try:
        exp = float(form_data.get('expenditure') or 0.0)
        if exp < 0:
            errors.append("Expenditure cannot be negative.")
    except (ValueError, TypeError):
        errors.append("Expenditure must be a valid number.")

    try:
        delay = int(form_data.get('delay_days') or 0)
        if delay < 0:
            errors.append("Delay days cannot be negative.")
    except (ValueError, TypeError):
        errors.append("Delay days must be a valid integer.")

    return errors

@projects_bp.route('/projects')
@login_required
def index():
    page = request.args.get('page', 1, type=int)
    per_page = 15
    
    # Scoped project query based on current user role & object assignments
    query = get_scoped_projects_query(current_user)
    
    # Search by name or code
    search = request.args.get('search', '').strip()
    if search:
        query = query.filter(
            (Project.project_name.ilike(f"%{search}%")) |
            (Project.project_code.ilike(f"%{search}%")) |
            (Project.location.ilike(f"%{search}%"))
        )
        
    # Filters
    ministry = request.args.get('ministry', '').strip()
    if ministry:
        query = query.filter(Project.ministry == ministry)
        
    sector = request.args.get('sector', '').strip()
    if sector:
        query = query.filter(Project.sector == sector)
        
    state = request.args.get('state', '').strip()
    if state:
        query = query.filter(Project.state == state)
        
    status = request.args.get('status', '').strip()
    if status:
        query = query.filter(Project.project_status == status)
        
    risk_level = request.args.get('risk_level', '').strip()
    if risk_level:
        query = query.filter(Project.risk_level == risk_level)
        
    # Sorting
    sort_by = request.args.get('sort_by', 'risk_score')
    sort_order = request.args.get('sort_order', 'desc')
    
    col = getattr(Project, sort_by, Project.risk_score)
    if sort_order == 'asc':
        query = query.order_by(col.asc())
    else:
        query = query.order_by(col.desc())
        
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Filter dropdown choices
    ministries = [m[0] for m in Project.query.with_entities(Project.ministry).distinct().order_by(Project.ministry).all()]
    sectors = [s[0] for s in Project.query.with_entities(Project.sector).distinct().order_by(Project.sector).all()]
    states = [st[0] for st in Project.query.with_entities(Project.state).distinct().order_by(Project.state).all()]
    
    return render_template(
        'projects.html',
        projects=pagination.items,
        pagination=pagination,
        ministries=ministries,
        sectors=sectors,
        states=states,
        search=search,
        active_filters={
            'ministry': ministry,
            'sector': sector,
            'state': state,
            'status': status,
            'risk_level': risk_level,
            'sort_by': sort_by,
            'sort_order': sort_order
        }
    )

@projects_bp.route('/projects/<int:project_id>')
@login_required
@project_access_required(write=False)
def detail(project_id):
    project = db.get_or_404(Project, project_id)
    
    # Fetch real-time predictions, explainability, and 8-dimension Project Risk DNA
    eval_result = predict_project_risk(project)
    recommendations = generate_project_recommendations(project.to_dict())
    risk_dna = calculate_project_risk_dna(project)
    
    # Fetch project alerts and recent history
    alerts = Alert.query.filter_by(project_id=project.id).order_by(Alert.created_at.desc()).limit(5).all()
    history = ProjectHistory.query.filter_by(project_id=project.id).order_by(ProjectHistory.reporting_date.asc()).all()
    
    return render_template(
        'project_detail.html',
        project=project,
        eval_result=eval_result,
        recommendations=recommendations,
        risk_dna=risk_dna,
        alerts=alerts,
        history=history
    )

@projects_bp.route('/projects/new', methods=['GET', 'POST'])
@role_required('admin', 'officer')
def create_project():
    if request.method == 'POST':
        errors = validate_project_inputs(request.form)
        if errors:
            for err in errors:
                flash(err, "danger")
            return render_template('project_form.html', project=None, title="Add New Infrastructure Project")

        try:
            p = Project(
                project_code=request.form['project_code'].strip().upper(),
                project_name=request.form['project_name'].strip(),
                ministry=request.form['ministry'].strip(),
                department=request.form.get('department', '').strip(),
                sector=request.form['sector'].strip(),
                state=request.form['state'].strip(),
                location=request.form.get('location', '').strip(),
                implementing_agency=request.form.get('implementing_agency', '').strip(),
                approved_cost=float(request.form.get('approved_cost') or 0.0),
                revised_cost=float(request.form.get('revised_cost') or request.form.get('approved_cost') or 0.0),
                expenditure=float(request.form.get('expenditure') or 0.0),
                physical_progress=float(request.form.get('physical_progress') or 0.0),
                planned_progress=float(request.form.get('planned_progress') or 0.0),
                delay_days=int(request.form.get('delay_days') or 0),
                milestones_total=int(request.form.get('milestones_total') or 4),
                milestones_completed=int(request.form.get('milestones_completed') or 0),
                milestones_delayed=int(request.form.get('milestones_delayed') or 0),
                contractor_status=request.form.get('contractor_status', 'On Track'),
                land_acquisition_status=request.form.get('land_acquisition_status', 'Completed'),
                environmental_clearance_status=request.form.get('environmental_clearance_status', 'Completed'),
                utility_shifting_status=request.form.get('utility_shifting_status', 'Completed'),
                project_status=request.form.get('project_status', 'Ongoing')
            )
            
            start_d = request.form.get('start_date')
            orig_d = request.form.get('original_completion_date')
            rev_d = request.form.get('revised_completion_date')
            if start_d:
                p.start_date = datetime.strptime(start_d, '%Y-%m-%d').date()
            if orig_d:
                p.original_completion_date = datetime.strptime(orig_d, '%Y-%m-%d').date()
            if rev_d:
                p.revised_completion_date = datetime.strptime(rev_d, '%Y-%m-%d').date()
                
            db.session.add(p)
            db.session.flush()

            # If created by an officer, automatically assign this project to the officer
            if current_user.role == 'officer':
                assignment = ProjectAssignment(
                    user_id=current_user.id,
                    project_id=p.id,
                    can_edit=True,
                    role_scope='Monitoring Officer'
                )
                db.session.add(assignment)
            
            # Evaluate ML risk and generate early warnings
            update_project_risk(p)
            evaluate_and_generate_alerts(p)
            db.session.commit()
            
            log_security_event('PROJECT_CREATE', resource_type='project', resource_id=str(p.id), details=f"Created project {p.project_code} ({p.project_name})")
            flash(f"Project '{p.project_name}' successfully added and evaluated.", "success")
            return redirect(url_for('projects.detail', project_id=p.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Error creating project: {str(e)}", "danger")

    return render_template('project_form.html', project=None, title="Add New Infrastructure Project")

@projects_bp.route('/projects/<int:project_id>/edit', methods=['GET', 'POST'])
@role_required('admin', 'officer')
@project_access_required(write=True)
def edit_project(project_id):
    project = db.get_or_404(Project, project_id)
    if request.method == 'POST':
        errors = validate_project_inputs(request.form)
        if errors:
            for err in errors:
                flash(err, "danger")
            return render_template('project_form.html', project=project, title=f"Edit Project: {project.project_code}")

        try:
            project.project_name = request.form['project_name'].strip()
            project.ministry = request.form['ministry'].strip()
            project.department = request.form.get('department', '').strip()
            project.sector = request.form['sector'].strip()
            project.state = request.form['state'].strip()
            project.location = request.form.get('location', '').strip()
            project.implementing_agency = request.form.get('implementing_agency', '').strip()
            project.approved_cost = float(request.form.get('approved_cost') or 0.0)
            project.revised_cost = float(request.form.get('revised_cost') or project.approved_cost)
            project.expenditure = float(request.form.get('expenditure') or 0.0)
            project.physical_progress = float(request.form.get('physical_progress') or 0.0)
            project.planned_progress = float(request.form.get('planned_progress') or 0.0)
            project.delay_days = int(request.form.get('delay_days') or 0)
            project.milestones_total = int(request.form.get('milestones_total') or 4)
            project.milestones_completed = int(request.form.get('milestones_completed') or 0)
            project.milestones_delayed = int(request.form.get('milestones_delayed') or 0)
            project.contractor_status = request.form.get('contractor_status', 'On Track')
            project.land_acquisition_status = request.form.get('land_acquisition_status', 'Completed')
            project.environmental_clearance_status = request.form.get('environmental_clearance_status', 'Completed')
            project.utility_shifting_status = request.form.get('utility_shifting_status', 'Completed')
            project.project_status = request.form.get('project_status', 'Ongoing')
            
            # Recompute Risk & Alerts
            update_project_risk(project)
            evaluate_and_generate_alerts(project)
            db.session.commit()
            
            log_security_event('PROJECT_UPDATE', resource_type='project', resource_id=str(project.id), details=f"Updated project {project.project_code} ({project.project_name})")
            flash(f"Project '{project.project_name}' updated successfully.", "success")
            return redirect(url_for('projects.detail', project_id=project.id))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating project: {str(e)}", "danger")

    return render_template('project_form.html', project=project, title=f"Edit Project: {project.project_code}")

@projects_bp.route('/projects/<int:project_id>/delete', methods=['POST'])
@admin_required
def delete_project(project_id):
    project = db.get_or_404(Project, project_id)
    name = project.project_name
    code = project.project_code
    db.session.delete(project)
    db.session.commit()
    log_security_event('PROJECT_DELETE', resource_type='project', resource_id=str(project_id), details=f"Deleted project {code} ({name})")
    flash(f"Project '{name}' and related analytics records removed.", "info")
    return redirect(url_for('projects.index'))

@projects_bp.route('/projects/<int:project_id>/quick-update', methods=['POST'])
@role_required('admin', 'officer')
@project_access_required(write=True)
def quick_update(project_id):
    project = db.get_or_404(Project, project_id)
    try:
        errors = validate_project_inputs(request.form)
        if errors:
            for err in errors:
                flash(err, "danger")
            return redirect(url_for('projects.detail', project_id=project.id))

        if 'physical_progress' in request.form:
            project.physical_progress = float(request.form['physical_progress'])
        if 'expenditure' in request.form:
            project.expenditure = float(request.form['expenditure'])
        if 'delay_days' in request.form:
            project.delay_days = int(request.form['delay_days'])
        if 'contractor_status' in request.form:
            project.contractor_status = request.form['contractor_status']
        if 'land_acquisition_status' in request.form:
            project.land_acquisition_status = request.form['land_acquisition_status']
            
        update_project_risk(project)
        evaluate_and_generate_alerts(project)
        db.session.commit()
        
        log_security_event('PROJECT_QUICK_UPDATE', resource_type='project', resource_id=str(project.id), details=f"Quick status update for {project.project_code}")
        flash("Project status and risk indicators successfully updated.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating project: {str(e)}", "danger")
        
    return redirect(url_for('projects.detail', project_id=project.id))

# ================= SAFE CSV EXPORT =================

def _sanitize_csv_cell(val):
    if val is None:
        return ''
    s = str(val)
    if s.startswith(('=', '+', '-', '@', '\t', '\r')):
        s = "'" + s
    return s

@projects_bp.route('/projects/export')
@role_required('admin', 'officer')
def export_projects():
    query = get_scoped_projects_query(current_user).order_by(Project.project_code.asc())
    projects = query.all()
    
    si = io.StringIO()
    cw = csv.writer(si)
    
    # Role-based column whitelisting for export (Least Privilege)
    if current_user.role == 'officer':
        headers = [
            'Project Code', 'Project Name', 'Ministry', 'Department', 'Sector', 'State', 'Location',
            'Approved Cost (Cr)', 'Revised Cost (Cr)', 'Expenditure (Cr)',
            'Physical Progress (%)', 'Planned Progress (%)', 'Delay Days', 'Progress Gap (%)',
            'Milestones Delayed', 'Contractor Status', 'Land Acq Status', 'Env Clearance Status',
            'Risk Level', 'Risk Score', 'Health Score', 'Status'
        ]
        cw.writerow(headers)
        for p in projects:
            cw.writerow([
                _sanitize_csv_cell(p.project_code),
                _sanitize_csv_cell(p.project_name),
                _sanitize_csv_cell(p.ministry),
                _sanitize_csv_cell(p.department),
                _sanitize_csv_cell(p.sector),
                _sanitize_csv_cell(p.state),
                _sanitize_csv_cell(p.location),
                _sanitize_csv_cell(p.approved_cost),
                _sanitize_csv_cell(p.revised_cost),
                _sanitize_csv_cell(p.expenditure),
                _sanitize_csv_cell(p.physical_progress),
                _sanitize_csv_cell(p.planned_progress),
                _sanitize_csv_cell(p.delay_days),
                _sanitize_csv_cell(p.progress_gap),
                _sanitize_csv_cell(p.milestones_delayed),
                _sanitize_csv_cell(p.contractor_status),
                _sanitize_csv_cell(p.land_acquisition_status),
                _sanitize_csv_cell(p.environmental_clearance_status),
                _sanitize_csv_cell(p.risk_level),
                _sanitize_csv_cell(p.risk_score),
                _sanitize_csv_cell(p.health_score),
                _sanitize_csv_cell(p.project_status)
            ])
    else:
        # Admin: Full operational & administrative export
        headers = [
            'Project Code', 'Project Name', 'Ministry', 'Department', 'Sector', 'State', 'Location',
            'Implementing Agency', 'Approved Cost (Cr)', 'Revised Cost (Cr)', 'Expenditure (Cr)',
            'Physical Progress (%)', 'Planned Progress (%)', 'Delay Days', 'Progress Gap (%)',
            'Milestones Total', 'Milestones Completed', 'Milestones Delayed',
            'Contractor Status', 'Land Acq Status', 'Env Clearance Status', 'Utility Shifting',
            'Risk Level', 'Risk Score', 'Health Score', 'Status'
        ]
        cw.writerow(headers)
        for p in projects:
            cw.writerow([
                _sanitize_csv_cell(p.project_code),
                _sanitize_csv_cell(p.project_name),
                _sanitize_csv_cell(p.ministry),
                _sanitize_csv_cell(p.department),
                _sanitize_csv_cell(p.sector),
                _sanitize_csv_cell(p.state),
                _sanitize_csv_cell(p.location),
                _sanitize_csv_cell(p.implementing_agency),
                _sanitize_csv_cell(p.approved_cost),
                _sanitize_csv_cell(p.revised_cost),
                _sanitize_csv_cell(p.expenditure),
                _sanitize_csv_cell(p.physical_progress),
                _sanitize_csv_cell(p.planned_progress),
                _sanitize_csv_cell(p.delay_days),
                _sanitize_csv_cell(p.progress_gap),
                _sanitize_csv_cell(p.milestones_total),
                _sanitize_csv_cell(p.milestones_completed),
                _sanitize_csv_cell(p.milestones_delayed),
                _sanitize_csv_cell(p.contractor_status),
                _sanitize_csv_cell(p.land_acquisition_status),
                _sanitize_csv_cell(p.environmental_clearance_status),
                _sanitize_csv_cell(p.utility_shifting_status),
                _sanitize_csv_cell(p.risk_level),
                _sanitize_csv_cell(p.risk_score),
                _sanitize_csv_cell(p.health_score),
                _sanitize_csv_cell(p.project_status)
            ])
        
    log_security_event('EXPORT_DATA', resource_type='project', details=f"Exported {len(projects)} projects as safe CSV for role {current_user.role}")
    
    output = si.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=projectpulse_projects_export.csv"}
    )

# ================= REST APIs =================

@projects_bp.route('/api/projects/search', methods=['GET'])
@login_required
def api_search_projects():
    q = request.args.get('q', '').strip()
    raw_limit = request.args.get('limit', 10, type=int)
    limit = min(max(1, raw_limit), 25)
    
    query = get_scoped_projects_query(current_user)
    if q:
        query = query.filter(
            (Project.project_name.ilike(f"%{q}%")) |
            (Project.project_code.ilike(f"%{q}%"))
        )
    projects = query.order_by(Project.project_name.asc()).limit(limit).all()
    
    # Requirement 11: Minimally serialized search autocomplete results
    results = [{
        'id': p.id,
        'project_code': p.project_code,
        'project_name': p.project_name,
        'state': p.state,
        'sector': p.sector,
        'risk_level': p.risk_level,
        'project_status': p.project_status
    } for p in projects]
    
    return jsonify({
        'status': 'success',
        'count': len(results),
        'results': results
    })

@projects_bp.route('/api/projects', methods=['GET'])
@login_required
def api_get_projects():
    page = request.args.get('page', 1, type=int)
    raw_limit = request.args.get('limit', 20, type=int)
    if raw_limit <= 0:
        raw_limit = 20
    limit = min(raw_limit, 100)

    query = get_scoped_projects_query(current_user).order_by(Project.id.asc())
    total = query.count()
    pagination = query.paginate(page=page, per_page=limit, error_out=False)

    # Apply role-based field minimization at summary level
    minimized_projects = [
        serialize_project_for_user(p, current_user, detail_level='summary')
        for p in pagination.items
    ]

    return jsonify({
        'status': 'success',
        'page': pagination.page,
        'limit': limit,
        'total': total,
        'pages': pagination.pages,
        'count': len(minimized_projects),
        'projects': minimized_projects
    })

@projects_bp.route('/api/projects/<int:project_id>', methods=['GET'])
@login_required
@project_access_required(write=False)
def api_get_project(project_id):
    p = db.get_or_404(Project, project_id)
    eval_result = predict_project_risk(p)
    recs = generate_project_recommendations(p.to_dict())
    risk_dna = calculate_project_risk_dna(p)
    
    # Serialize project according to role permissions (Default-Deny)
    data = serialize_project_for_user(p, current_user, detail_level='standard')
    
    # Role-based evaluation & recommendation minimization
    if current_user.role == 'viewer':
        data['risk_evaluation'] = {
            'overall_risk_score': eval_result.get('overall_risk_score'),
            'risk_level': eval_result.get('risk_level'),
            'health_score': eval_result.get('health_score'),
            'explanation': eval_result.get('explanation')
        }
        data['recommendations'] = [{
            'category': r.get('category'),
            'priority': r.get('priority'),
            'action': r.get('action'),
            'summary_statement': r.get('summary_statement')
        } for r in recs]
    else:
        data['risk_evaluation'] = eval_result
        data['recommendations'] = recs
        data['risk_dna'] = risk_dna
        
    return jsonify({'status': 'success', 'project': data})

@projects_bp.route('/api/projects', methods=['POST'])
@role_required('admin', 'officer')
def api_create_project():
    data = request.get_json(silent=True) or {}
    errors = validate_project_inputs(data)
    if errors:
        return jsonify({'status': 'error', 'message': '; '.join(errors)}), 400

    code = str(data.get('project_code', '')).strip().upper()
    name = str(data.get('project_name', '')).strip()
    if not code or not name:
        return jsonify({'status': 'error', 'message': 'project_code and project_name are required.'}), 400

    try:
        p = Project(
            project_code=code,
            project_name=name,
            ministry=data.get('ministry', 'Ministry of Road Transport and Highways'),
            department=data.get('department', ''),
            sector=data.get('sector', 'Road Transport'),
            state=data.get('state', 'National'),
            location=data.get('location', ''),
            implementing_agency=data.get('implementing_agency', ''),
            approved_cost=float(data.get('approved_cost') or 0.0),
            revised_cost=float(data.get('revised_cost') or data.get('approved_cost') or 0.0),
            expenditure=float(data.get('expenditure') or 0.0),
            physical_progress=float(data.get('physical_progress') or 0.0),
            planned_progress=float(data.get('planned_progress') or 0.0),
            delay_days=int(data.get('delay_days') or 0),
            milestones_total=int(data.get('milestones_total') or 4),
            milestones_completed=int(data.get('milestones_completed') or 0),
            milestones_delayed=int(data.get('milestones_delayed') or 0),
            contractor_status=data.get('contractor_status', 'On Track'),
            land_acquisition_status=data.get('land_acquisition_status', 'Completed'),
            environmental_clearance_status=data.get('environmental_clearance_status', 'Completed'),
            utility_shifting_status=data.get('utility_shifting_status', 'Completed'),
            project_status=data.get('project_status', 'Ongoing')
        )
        db.session.add(p)
        db.session.flush()

        if current_user.role == 'officer':
            db.session.add(ProjectAssignment(user_id=current_user.id, project_id=p.id, can_edit=True))

        update_project_risk(p)
        evaluate_and_generate_alerts(p)
        db.session.commit()

        log_security_event('PROJECT_CREATE_API', resource_type='project', resource_id=str(p.id), details=f"Created project {p.project_code}")
        return jsonify({'status': 'success', 'message': 'Project created successfully', 'project': serialize_project_for_user(p, current_user, detail_level='standard')}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@projects_bp.route('/api/projects/<int:project_id>', methods=['PUT'])
@role_required('admin', 'officer')
@project_access_required(write=True)
def api_update_project(project_id):
    p = db.get_or_404(Project, project_id)
    data = request.get_json(silent=True) or {}
    errors = validate_project_inputs(data)
    if errors:
        return jsonify({'status': 'error', 'message': '; '.join(errors)}), 400

    try:
        if 'project_name' in data:
            p.project_name = str(data['project_name']).strip()
        if 'approved_cost' in data:
            p.approved_cost = float(data['approved_cost'])
        if 'revised_cost' in data:
            p.revised_cost = float(data['revised_cost'])
        if 'expenditure' in data:
            p.expenditure = float(data['expenditure'])
        if 'physical_progress' in data:
            p.physical_progress = float(data['physical_progress'])
        if 'planned_progress' in data:
            p.planned_progress = float(data['planned_progress'])
        if 'delay_days' in data:
            p.delay_days = int(data['delay_days'])
        if 'contractor_status' in data:
            p.contractor_status = data['contractor_status']
        if 'land_acquisition_status' in data:
            p.land_acquisition_status = data['land_acquisition_status']
        if 'project_status' in data:
            p.project_status = data['project_status']

        update_project_risk(p)
        evaluate_and_generate_alerts(p)
        db.session.commit()

        log_security_event('PROJECT_UPDATE_API', resource_type='project', resource_id=str(p.id), details=f"Updated project {p.project_code}")
        return jsonify({'status': 'success', 'message': 'Project updated successfully', 'project': serialize_project_for_user(p, current_user, detail_level='standard')})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@projects_bp.route('/api/projects/<int:project_id>', methods=['DELETE'])
@admin_required
def api_delete_project(project_id):
    p = db.get_or_404(Project, project_id)
    code = p.project_code
    db.session.delete(p)
    db.session.commit()
    log_security_event('PROJECT_DELETE_API', resource_type='project', resource_id=str(project_id), details=f"Deleted project {code}")
    return jsonify({'status': 'success', 'message': f"Project {code} deleted successfully."})

@projects_bp.route('/api/risk/<int:project_id>', methods=['GET'])
@login_required
@project_access_required(write=False)
def api_get_risk(project_id):
    p = db.get_or_404(Project, project_id)
    eval_result = predict_project_risk(p)
    risk_dna = calculate_project_risk_dna(p)
    
    if current_user.role == 'viewer':
        return jsonify({
            'status': 'success',
            'project_id': p.id,
            'project_code': p.project_code,
            'evaluation': {
                'overall_risk_score': eval_result.get('overall_risk_score'),
                'risk_level': eval_result.get('risk_level'),
                'health_score': eval_result.get('health_score'),
                'explanation': eval_result.get('explanation')
            }
        })
    else:
        return jsonify({
            'status': 'success',
            'project_id': p.id,
            'project_code': p.project_code,
            'evaluation': eval_result,
            'risk_dna': risk_dna
        })

