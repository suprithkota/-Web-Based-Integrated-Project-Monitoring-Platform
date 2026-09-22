import os
import uuid
import json
import hashlib
from datetime import datetime, date
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from database import db
from database.models import (
    Project, User, SiteInspectionRecord, MaterialQualityTest,
    ProjectDelayRecord, ProjectMaterial, PublicComplaint,
    DocumentEvidence, Contractor
)
from services.rbac_service import role_required, admin_required, officer_required, get_scoped_projects_query
from services.audit_service import log_security_event

engineering_bp = Blueprint('engineering', __name__)

ALLOWED_PHOTO_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}

def _calc_sha256(file_bytes):
    h = hashlib.sha256()
    h.update(file_bytes)
    return h.hexdigest()

# =========================================================================
# 1. ENGINEERING / TECHNICAL DASHBOARD (OFFICER & ADMIN)
# =========================================================================
@engineering_bp.route('/engineering-dashboard')
@role_required('admin', 'officer')
def dashboard():
    # Officers see assigned / scoped projects; Admins see all
    projects_query = get_scoped_projects_query(current_user)
    projects = projects_query.order_by(Project.project_name.asc()).all()
    project_ids = [p.id for p in projects]

    # Metrics
    total_projects = len(projects)
    active_sites = sum(1 for p in projects if p.project_status in ['Ongoing', 'Delayed'])
    delayed_sites = sum(1 for p in projects if p.project_status == 'Delayed' or (p.delay_days or 0) > 0)

    # Inspections
    inspections_query = SiteInspectionRecord.query
    if project_ids:
        inspections_query = inspections_query.filter(SiteInspectionRecord.project_id.in_(project_ids))
    recent_inspections = inspections_query.order_by(SiteInspectionRecord.inspection_date.desc(), SiteInspectionRecord.id.desc()).limit(10).all()
    
    pending_ee_reviews = inspections_query.filter(
        SiteInspectionRecord.verification_status.in_(['Pending Review', 'Pending EE Review'])
    ).count()

    # Material Tests
    tests_query = MaterialQualityTest.query
    if project_ids:
        tests_query = tests_query.filter(MaterialQualityTest.project_id.in_(project_ids))
    total_tests = tests_query.count()
    passed_tests = tests_query.filter_by(status='PASS').count()
    failed_tests = tests_query.filter_by(status='FAIL').count()
    recent_tests = tests_query.order_by(MaterialQualityTest.id.desc()).limit(8).all()

    # Delay records
    delays_query = ProjectDelayRecord.query
    if project_ids:
        delays_query = delays_query.filter(ProjectDelayRecord.project_id.in_(project_ids))
    recent_delays = delays_query.order_by(ProjectDelayRecord.recorded_at.desc()).limit(6).all()

    # Complaints needing field verification
    complaints_query = PublicComplaint.query
    if project_ids:
        complaints_query = complaints_query.filter(
            (PublicComplaint.project_id.in_(project_ids)) | 
            (PublicComplaint.status.in_(['Submitted', 'Received', 'Site Inspection Required', 'Under Review']))
        )
    field_complaints = complaints_query.filter(
        PublicComplaint.status.in_(['Submitted', 'Received', 'Site Inspection Required', 'Under Review', 'Investigation'])
    ).order_by(PublicComplaint.created_at.desc()).limit(8).all()

    return render_template(
        'engineering/engineering_dashboard.html',
        projects=projects,
        total_projects=total_projects,
        active_sites=active_sites,
        delayed_sites=delayed_sites,
        recent_inspections=recent_inspections,
        pending_ee_reviews=pending_ee_reviews,
        total_tests=total_tests,
        passed_tests=passed_tests,
        failed_tests=failed_tests,
        recent_tests=recent_tests,
        recent_delays=recent_delays,
        field_complaints=field_complaints
    )

# =========================================================================
# 2. SITE INSPECTION LOGGING (OFFICER & ADMIN)
# =========================================================================
@engineering_bp.route('/engineering/inspection/new', methods=['GET', 'POST'])
@role_required('admin', 'officer')
def new_inspection():
    preselected_project_id = request.args.get('project_id', type=int)
    projects_query = get_scoped_projects_query(current_user)
    available_projects = projects_query.order_by(Project.project_name.asc()).all()

    if request.method == 'POST':
        project_id = request.form.get('project_id', type=int)
        stage_inspected = request.form.get('stage_inspected', '').strip()
        work_completed_percentage = request.form.get('work_completed_percentage', 0.0, type=float)
        measurements_recorded = request.form.get('measurements_recorded', '').strip()
        gps_lat = request.form.get('gps_latitude', type=float)
        gps_lng = request.form.get('gps_longitude', type=float)
        inspection_date_str = request.form.get('inspection_date')
        
        # Officer details
        officer_name = current_user.full_name or current_user.username
        officer_desig = getattr(current_user, 'technical_designation', 'Junior Engineer') or 'Junior Engineer'

        if not project_id:
            flash("Please select a project for site inspection.", "danger")
            return redirect(url_for('engineering.new_inspection', project_id=preselected_project_id))

        project = db.session.get(Project, project_id)
        if not project:
            flash("Selected project not found.", "danger")
            return redirect(url_for('engineering.new_inspection'))

        insp_date = date.today()
        if inspection_date_str:
            try:
                insp_date = datetime.strptime(inspection_date_str, '%Y-%m-%d').date()
            except ValueError:
                insp_date = date.today()

        # Handle photo uploads
        uploaded_photos = []
        if 'inspection_photos' in request.files:
            files = request.files.getlist('inspection_photos')
            for f in files:
                if f and f.filename:
                    fname = secure_filename(f.filename)
                    ext = os.path.splitext(fname)[1].lower()
                    if ext in ALLOWED_PHOTO_EXTENSIONS:
                        fbytes = f.read()
                        fhash = _calc_sha256(fbytes)
                        upload_dir = os.path.join(current_app.root_path, 'data', 'inspection_photos')
                        os.makedirs(upload_dir, exist_ok=True)
                        saved_name = f"INSP_{uuid.uuid4().hex[:8]}_{fname}"
                        save_path = os.path.join(upload_dir, saved_name)
                        with open(save_path, 'wb') as dest:
                            dest.write(fbytes)
                        rel_path = f"/data/inspection_photos/{saved_name}"
                        uploaded_photos.append({
                            'url': rel_path,
                            'name': fname,
                            'hash': fhash
                        })

                        # Register in DocumentEvidence for chain of custody
                        doc = DocumentEvidence(
                            document_code=f"INSP-DOC-{uuid.uuid4().hex[:8].upper()}",
                            project_id=project.id,
                            contractor_id=project.contractor_id,
                            doc_type='Site Inspection Photo',
                            title=f"Site Inspection Photo - {project.project_code} - {stage_inspected}",
                            file_name=fname,
                            file_path=rel_path,
                            file_size_bytes=len(fbytes),
                            mime_type='image/jpeg',
                            source_agency='Site Field Engineering Team',
                            verification_status='Verified',
                            tamper_hash=fhash,
                            uploaded_by_user_id=current_user.id
                        )
                        db.session.add(doc)

        inspection = SiteInspectionRecord(
            project_id=project.id,
            officer_id=current_user.id,
            officer_name=officer_name,
            officer_designation=officer_desig,
            inspection_date=insp_date,
            stage_inspected=stage_inspected,
            work_completed_percentage=work_completed_percentage,
            measurements_recorded=measurements_recorded,
            gps_latitude=gps_lat,
            gps_longitude=gps_lng,
            photos_json=json.dumps(uploaded_photos),
            verification_status='Pending EE Review'
        )
        db.session.add(inspection)

        # Update Project physical progress if field-measured is higher
        if work_completed_percentage > (project.physical_progress or 0.0):
            project.physical_progress = work_completed_percentage
        if stage_inspected:
            project.current_construction_stage = stage_inspected
        project.latest_govt_inspection = f"{insp_date.strftime('%d-%b-%Y')}: {stage_inspected} inspected by {officer_name} ({officer_desig}). Field progress: {work_completed_percentage}%."
        project.sync_timestamp = datetime.utcnow()

        db.session.commit()

        log_security_event(
            'SITE_INSPECTION_RECORDED',
            user_id=current_user.id,
            username=current_user.username,
            resource_type='inspection',
            resource_id=str(inspection.id),
            details=f"Inspection recorded for {project.project_code} at stage {stage_inspected}",
            status='SUCCESS'
        )

        flash(f"Site inspection log #{inspection.id} recorded successfully with {len(uploaded_photos)} photo(s). Sent for EE technical certification.", "success")
        return redirect(url_for('engineering.inspection_detail', inspection_id=inspection.id))

    return render_template(
        'engineering/site_inspection_form.html',
        projects=available_projects,
        preselected_project_id=preselected_project_id
    )

# =========================================================================
# 3. INSPECTION DETAIL VIEW (OFFICER & ADMIN)
# =========================================================================
@engineering_bp.route('/engineering/inspection/<int:inspection_id>')
@role_required('admin', 'officer')
def inspection_detail(inspection_id):
    inspection = db.session.get(SiteInspectionRecord, inspection_id)
    if not inspection:
        flash("Site inspection record not found.", "warning")
        return redirect(url_for('engineering.dashboard'))

    project = inspection.project
    photos = []
    try:
        photos = json.loads(inspection.photos_json or '[]')
    except Exception:
        photos = []

    return render_template(
        'engineering/inspection_detail.html',
        inspection=inspection,
        project=project,
        photos=photos
    )

# =========================================================================
# 4. INSPECTION CERTIFICATION / REVIEW (EE / SE / ADMIN)
# =========================================================================
@engineering_bp.route('/engineering/inspection/<int:inspection_id>/verify', methods=['POST'])
@role_required('admin', 'officer')
def verify_inspection(inspection_id):
    inspection = db.session.get(SiteInspectionRecord, inspection_id)
    if not inspection:
        flash("Site inspection record not found.", "warning")
        return redirect(url_for('engineering.dashboard'))

    action = request.form.get('action', 'verify').strip()
    remarks = request.form.get('review_remarks', '').strip()

    reviewer_title = current_user.full_name or current_user.username
    desig = getattr(current_user, 'technical_designation', 'Executive Engineer') or 'Executive Engineer'

    if action == 'verify':
        inspection.verification_status = f"Certified by {desig}"
        inspection.reviewed_by = f"{reviewer_title} ({desig})"
        inspection.reviewed_at = datetime.utcnow()
        inspection.review_remarks = remarks or "Measurements verified against DPR specifications. Certified satisfactory."
        flash("Inspection certified and verified successfully.", "success")
    elif action == 'reject':
        inspection.verification_status = "Rejected"
        inspection.reviewed_by = f"{reviewer_title} ({desig})"
        inspection.reviewed_at = datetime.utcnow()
        inspection.review_remarks = remarks or "Site measurements deviate from standards. Re-inspection required."
        flash("Inspection record rejected. Rectification requested.", "warning")
    else:
        inspection.verification_status = "Clarification Requested"
        inspection.reviewed_by = f"{reviewer_title} ({desig})"
        inspection.reviewed_at = datetime.utcnow()
        inspection.review_remarks = remarks
        flash("Clarification request recorded.", "info")

    db.session.commit()
    return redirect(url_for('engineering.inspection_detail', inspection_id=inspection.id))

# =========================================================================
# 5. FIELD MATERIAL QUALITY LAB TEST (OFFICER & ADMIN)
# =========================================================================
@engineering_bp.route('/engineering/quality-tests/new', methods=['GET', 'POST'])
@role_required('admin', 'officer')
def new_quality_test():
    projects_query = get_scoped_projects_query(current_user)
    available_projects = projects_query.order_by(Project.project_name.asc()).all()
    all_materials = ProjectMaterial.query.order_by(ProjectMaterial.id.desc()).limit(100).all()

    if request.method == 'POST':
        project_id = request.form.get('project_id', type=int)
        material_id = request.form.get('material_id', type=int)
        test_name = request.form.get('test_name', '').strip()
        standard = request.form.get('required_standard', 'IS 516 / IS 1786').strip()
        result_val = request.form.get('test_result_value', '').strip()
        status = request.form.get('status', 'PASS').strip().upper()
        lab = request.form.get('testing_laboratory', 'Government NABL Testing Facility').strip()
        sample_id = request.form.get('sample_id', '').strip()
        cert_ref = request.form.get('quality_certificate_ref', '').strip()
        rejection_info = request.form.get('rejection_information', '').strip()
        replacement_info = request.form.get('replacement_information', '').strip()

        if not material_id or not test_name or not result_val:
            flash("Material batch, test name, and measured result value are mandatory.", "danger")
            return redirect(url_for('engineering.new_quality_test'))

        test = MaterialQualityTest(
            material_id=material_id,
            project_id=project_id,
            test_name=test_name,
            required_standard=standard,
            test_result_value=result_val,
            status=status,
            testing_laboratory=lab,
            inspector_name=current_user.full_name or current_user.username,
            inspector_designation=getattr(current_user, 'technical_designation', 'Assistant Engineer') or 'Assistant Engineer',
            quality_certificate_ref=cert_ref or f"CERT-{uuid.uuid4().hex[:8].upper()}",
            rejection_information=rejection_info,
            replacement_information=replacement_info,
            verified_at=datetime.utcnow(),
            verified_by=current_user.username
        )
        db.session.add(test)

        # Update ProjectMaterial approval status if FAIL
        mat = db.session.get(ProjectMaterial, material_id)
        if mat:
            if status == 'FAIL':
                mat.approval_status = 'Rejected'
                mat.quality_certification_status = 'Failed Lab Test'
            elif status == 'PASS':
                mat.approval_status = 'Approved'
                mat.quality_certification_status = 'BIS Certified'

        db.session.commit()
        flash(f"Material Quality Laboratory Test for '{test_name}' [{status}] logged successfully.", "success")
        return redirect(url_for('contractors.materials_explorer'))

    return render_template(
        'engineering/quality_test_form.html',
        projects=available_projects,
        materials=all_materials
    )

# =========================================================================
# 6. DELAY LOGGING ENTRY (OFFICER & ADMIN)
# =========================================================================
@engineering_bp.route('/engineering/delays/new', methods=['GET', 'POST'])
@role_required('admin', 'officer')
def new_delay_record():
    projects_query = get_scoped_projects_query(current_user)
    available_projects = projects_query.order_by(Project.project_name.asc()).all()

    if request.method == 'POST':
        project_id = request.form.get('project_id', type=int)
        contractor_id = request.form.get('contractor_id', type=int)
        category = request.form.get('delay_category', 'Technical').strip()
        description = request.form.get('delay_description', '').strip()
        affected_days = request.form.get('affected_days', 0, type=int)
        official_source = request.form.get('official_source', 'Site Field Inspection Log').strip()
        authority = request.form.get('responsible_authority', '').strip()
        corrective = request.form.get('corrective_action', '').strip()

        if not project_id or not description:
            flash("Project and detailed delay explanation are required.", "danger")
            return redirect(url_for('engineering.new_delay_record'))

        delay = ProjectDelayRecord(
            project_id=project_id,
            contractor_id=contractor_id,
            delay_category=category,
            delay_description=description,
            affected_days=affected_days,
            official_source=official_source,
            responsible_authority=authority,
            corrective_action=corrective,
            officer_remarks=f"Verified by {current_user.full_name or current_user.username}",
            verification_status='Officer verified'
        )
        db.session.add(delay)

        proj = db.session.get(Project, project_id)
        if proj and affected_days > (proj.delay_days or 0):
            proj.delay_days = affected_days
            proj.documented_delay_reason = description
            if authority:
                proj.responsible_stakeholder = authority
            if corrective:
                proj.corrective_action = corrective

        db.session.commit()
        flash("Official project delay cause and mitigation documented successfully.", "success")
        return redirect(url_for('contractors.delays_explorer'))

    return render_template(
        'engineering/delay_form.html',
        projects=available_projects
    )

# =========================================================================
# 7. FIELD COMPLAINT TRIAGE & ACTION (OFFICER & ADMIN)
# =========================================================================
@engineering_bp.route('/engineering/complaints/<int:complaint_id>/triage', methods=['POST'])
@role_required('admin', 'officer')
def triage_complaint(complaint_id):
    complaint = db.session.get(PublicComplaint, complaint_id)
    if not complaint:
        flash("Complaint record not found.", "warning")
        return redirect(url_for('engineering.dashboard'))

    status = request.form.get('status', 'Under Review').strip()
    official_response = request.form.get('official_response', '').strip()
    inspection_ref = request.form.get('inspection_finding_ref', '').strip()
    routed_dept = request.form.get('routed_department', '').strip()

    complaint.status = status
    if official_response:
        complaint.official_response = official_response
    if inspection_ref:
        complaint.inspection_finding_ref = inspection_ref
    if routed_dept:
        complaint.routed_department = routed_dept
    complaint.assigned_officer = current_user.full_name or current_user.username

    if status in ['Resolved', 'Closed']:
        complaint.resolved_at = datetime.utcnow()

    db.session.commit()
    flash(f"Citizen complaint {complaint.complaint_code} updated to status '{status}'.", "success")
    return redirect(url_for('contractors.complaint_detail', complaint_id=complaint.id))

# =========================================================================
# 8. REST APIS FOR ENGINEERING MODULE
# =========================================================================
@engineering_bp.route('/api/engineering/dashboard-stats')
@role_required('admin', 'officer')
def api_dashboard_stats():
    projects_query = get_scoped_projects_query(current_user)
    projects = projects_query.all()
    project_ids = [p.id for p in projects]

    inspections_count = SiteInspectionRecord.query.filter(SiteInspectionRecord.project_id.in_(project_ids)).count() if project_ids else 0
    tests_count = MaterialQualityTest.query.filter(MaterialQualityTest.project_id.in_(project_ids)).count() if project_ids else 0
    pending_ee = SiteInspectionRecord.query.filter(
        SiteInspectionRecord.project_id.in_(project_ids),
        SiteInspectionRecord.verification_status.in_(['Pending Review', 'Pending EE Review'])
    ).count() if project_ids else 0

    return jsonify({
        'status': 'success',
        'data': {
            'total_scoped_projects': len(projects),
            'total_inspections': inspections_count,
            'total_quality_tests': tests_count,
            'pending_ee_reviews': pending_ee
        }
    })

@engineering_bp.route('/api/engineering/inspections')
@role_required('admin', 'officer')
def api_inspections():
    project_id = request.args.get('project_id', type=int)
    query = SiteInspectionRecord.query
    if project_id:
        query = query.filter_by(project_id=project_id)
    records = query.order_by(SiteInspectionRecord.inspection_date.desc()).limit(50).all()
    return jsonify({
        'status': 'success',
        'count': len(records),
        'inspections': [r.to_dict() for r in records]
    })
