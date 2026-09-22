import os
import hashlib
import uuid
from datetime import datetime, date
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from database import db
from database.models import (
    Contractor, ContractorBranch, MaterialSupplier, ProjectMaterial,
    MaterialQualityTest, ProjectDelayRecord, ProjectFinancialRecord,
    ProjectLifecycleEvent, PostConstructionRecord, ProjectSubcontractor,
    PublicComplaint, DocumentEvidence, Project, User
)
from services.contractor_service import ContractorService
from services.audit_service import log_security_event
from services.rbac_service import role_required, admin_required, officer_required

contractors_bp = Blueprint('contractors', __name__)

ALLOWED_DOC_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.xlsx', '.csv', '.doc', '.docx'}

def _calc_sha256(file_bytes):
    h = hashlib.sha256()
    h.update(file_bytes)
    return h.hexdigest()

# =========================================================================
# 1. CONTRACTOR INTELLIGENCE DASHBOARD (PUBLIC / ALL ROLES)
# =========================================================================
@contractors_bp.route('/contractor-intelligence')
def dashboard():
    stats = ContractorService.get_contractor_intelligence_dashboard_stats()
    top_contractors = ContractorService.get_all_contractors_summary()[:6]
    recent_delays = ProjectDelayRecord.query.order_by(ProjectDelayRecord.recorded_at.desc()).limit(5).all()
    recent_tests = MaterialQualityTest.query.order_by(MaterialQualityTest.id.desc()).limit(5).all()
    open_complaints = PublicComplaint.query.filter(~PublicComplaint.status.in_(['Resolved', 'Closed', 'Rejected with Reason'])).limit(5).all()

    return render_template(
        'contractors/dashboard.html',
        stats=stats,
        top_contractors=top_contractors,
        recent_delays=recent_delays,
        recent_tests=recent_tests,
        open_complaints=open_complaints
    )

# =========================================================================
# 2. CONTRACTOR MASTER DIRECTORY (PUBLIC / ALL ROLES)
# =========================================================================
@contractors_bp.route('/contractors')
def index():
    search = request.args.get('search', '').strip()
    company_type = request.args.get('company_type', '').strip()
    contractor_class = request.args.get('contractor_class', '').strip()
    status = request.args.get('status', '').strip()
    sector = request.args.get('sector', '').strip()

    filters = {
        'search': search,
        'company_type': company_type,
        'contractor_class': contractor_class,
        'status': status
    }

    contractors = ContractorService.get_all_contractors_summary(filters)
    
    # Optional sector filter post-filter if requested
    if sector:
        contractors = [c for c in contractors if sector.lower() in [s.lower() for s in c.get('sectors_served', [])]]

    company_types = db.session.query(Contractor.company_type).distinct().all()
    contractor_classes = db.session.query(Contractor.contractor_class).distinct().all()

    return render_template(
        'contractors/contractors_list.html',
        contractors=contractors,
        filters=filters,
        sector=sector,
        company_types=[ct[0] for ct in company_types if ct[0]],
        contractor_classes=[cc[0] for cc in contractor_classes if cc[0]]
    )

# =========================================================================
# 3. MASTER 10-TAB CONTRACTOR PROFILE (PUBLIC / ALL ROLES)
# =========================================================================
@contractors_bp.route('/contractors/<int:contractor_id>')
def detail(contractor_id):
    contractor = db.session.get(Contractor, contractor_id)
    if not contractor:
        flash("Contractor profile not found.", "warning")
        return redirect(url_for('contractors.index'))

    metrics = ContractorService.calculate_contractor_metrics(contractor)
    ai_summary = ContractorService.generate_contractor_ai_summary(contractor)
    
    projects = contractor.projects.all() if hasattr(contractor.projects, 'all') else Project.query.filter_by(contractor_id=contractor.id).all()
    completed_projects = [p for p in projects if p.project_status == 'Completed']
    ongoing_projects = [p for p in projects if p.project_status == 'Ongoing']
    delayed_projects = [p for p in projects if p.project_status == 'Delayed' or (p.delay_days or 0) > 0]
    pending_projects = [p for p in projects if p.project_status in ['Not started', 'Suspended', 'Stalled', 'Awaiting approval', 'Awaiting funding', 'Under legal dispute']]

    project_ids = [p.id for p in projects]
    materials = ProjectMaterial.query.filter(ProjectMaterial.project_id.in_(project_ids)).all() if project_ids else []
    material_ids = [m.id for m in materials]
    quality_tests = MaterialQualityTest.query.filter(MaterialQualityTest.material_id.in_(material_ids)).order_by(MaterialQualityTest.id.desc()).all() if material_ids else []
    delay_records = ProjectDelayRecord.query.filter(ProjectDelayRecord.project_id.in_(project_ids)).order_by(ProjectDelayRecord.start_date.desc()).all() if project_ids else []
    post_construction = PostConstructionRecord.query.filter(PostConstructionRecord.project_id.in_(project_ids)).all() if project_ids else []
    complaints = PublicComplaint.query.filter(
        (PublicComplaint.contractor_id == contractor.id) | 
        (PublicComplaint.project_id.in_(project_ids) if project_ids else False)
    ).order_by(PublicComplaint.created_at.desc()).all()
    documents = DocumentEvidence.query.filter(
        (DocumentEvidence.contractor_id == contractor.id) | 
        (DocumentEvidence.project_id.in_(project_ids) if project_ids else False)
    ).order_by(DocumentEvidence.uploaded_at.desc()).all()

    # Active tab from query param
    active_tab = request.args.get('tab', 'overview')

    return render_template(
        'contractors/contractor_detail.html',
        contractor=contractor,
        metrics=metrics,
        ai_summary=ai_summary,
        completed_projects=completed_projects,
        ongoing_projects=ongoing_projects,
        delayed_projects=delayed_projects,
        pending_projects=pending_projects,
        materials=materials,
        quality_tests=quality_tests,
        delay_records=delay_records,
        post_construction=post_construction,
        complaints=complaints,
        documents=documents,
        active_tab=active_tab
    )

# =========================================================================
# 4. BRANCH DETAIL VIEW (PUBLIC / ALL ROLES)
# =========================================================================
@contractors_bp.route('/contractors/branches/<int:branch_id>')
def branch_detail(branch_id):
    branch = db.session.get(ContractorBranch, branch_id)
    if not branch:
        flash("Contractor branch not found.", "warning")
        return redirect(url_for('contractors.index'))

    contractor = branch.contractor
    # Find projects in the same state or location
    branch_projects = Project.query.filter(
        Project.contractor_id == contractor.id,
        (Project.state.ilike(f"%{branch.location}%")) | (Project.location.ilike(f"%{branch.location}%"))
    ).all()

    return render_template(
        'contractors/branch_detail.html',
        branch=branch,
        contractor=contractor,
        branch_projects=branch_projects
    )

# =========================================================================
# 5. SUPPLIERS & MATERIAL INTELLIGENCE (PUBLIC / ALL ROLES)
# =========================================================================
@contractors_bp.route('/contractors/suppliers')
def suppliers_list():
    suppliers = MaterialSupplier.query.order_by(MaterialSupplier.name.asc()).all()
    return render_template('contractors/suppliers_list.html', suppliers=suppliers)

@contractors_bp.route('/contractors/suppliers/<int:supplier_id>')
def supplier_detail(supplier_id):
    supplier = db.session.get(MaterialSupplier, supplier_id)
    if not supplier:
        flash("Supplier record not found.", "warning")
        return redirect(url_for('contractors.suppliers_list'))

    materials = supplier.materials_supplied
    return render_template('contractors/supplier_detail.html', supplier=supplier, materials=materials)

@contractors_bp.route('/contractors/materials')
def materials_explorer():
    category = request.args.get('category', '').strip()
    status = request.args.get('status', '').strip()
    search = request.args.get('search', '').strip()

    query = ProjectMaterial.query
    if category:
        query = query.filter(ProjectMaterial.material_category == category)
    if status:
        query = query.filter(ProjectMaterial.approval_status == status)
    if search:
        query = query.filter(
            (ProjectMaterial.material_name.ilike(f"%{search}%")) |
            (ProjectMaterial.brand_manufacturer.ilike(f"%{search}%")) |
            (ProjectMaterial.batch_number.ilike(f"%{search}%"))
        )

    materials = query.order_by(ProjectMaterial.id.desc()).limit(100).all()
    categories = db.session.query(ProjectMaterial.material_category).distinct().all()

    # Recent laboratory tests
    recent_tests = MaterialQualityTest.query.order_by(MaterialQualityTest.id.desc()).limit(20).all()

    return render_template(
        'contractors/materials_explorer.html',
        materials=materials,
        recent_tests=recent_tests,
        categories=[c[0] for c in categories if c[0]],
        selected_category=category,
        selected_status=status,
        search=search
    )

# =========================================================================
# 6. DELAY ANALYSIS EXPLORER (PUBLIC / ALL ROLES)
# =========================================================================
@contractors_bp.route('/contractors/delays')
def delays_explorer():
    category = request.args.get('category', '').strip()
    query = ProjectDelayRecord.query
    if category:
        query = query.filter(ProjectDelayRecord.delay_category == category)

    delays = query.order_by(ProjectDelayRecord.recorded_at.desc()).all()
    categories = [
        'Administrative', 'Financial', 'Land / Legal', 'Technical',
        'Contractor / Execution', 'Material', 'Environmental', 'Other'
    ]

    return render_template(
        'contractors/delays_explorer.html',
        delays=delays,
        categories=categories,
        selected_category=category
    )

# =========================================================================
# 7. POST-CONSTRUCTION MONITORING (PUBLIC / ALL ROLES)
# =========================================================================
@contractors_bp.route('/contractors/post-construction')
def post_construction():
    records = PostConstructionRecord.query.order_by(PostConstructionRecord.inspection_date.desc()).all()
    return render_template('contractors/post_construction.html', records=records)

# =========================================================================
# 8. CITIZEN COMPLAINTS & GRIEVANCE SYSTEM (PUBLIC & OFFICER)
# =========================================================================
@contractors_bp.route('/contractors/complaints')
def complaints_list():
    status = request.args.get('status', '').strip()
    query = PublicComplaint.query
    if status:
        query = query.filter(PublicComplaint.status == status)

    complaints = query.order_by(PublicComplaint.created_at.desc()).all()
    return render_template('contractors/complaints_list.html', complaints=complaints, selected_status=status)

@contractors_bp.route('/contractors/complaints/new', methods=['GET', 'POST'])
@contractors_bp.route('/contractors/complaints/new', methods=['GET', 'POST'], endpoint='new_complaint')
def complaint_new():
    if request.method == 'POST':
        project_id = request.form.get('project_id', type=int)
        location = request.form.get('location', '').strip()
        category = request.form.get('category', '').strip()
        description = request.form.get('description', '').strip()
        name = request.form.get('complainant_name', '').strip() or 'Citizen'
        contact = request.form.get('complainant_contact', '').strip()
        lat = request.form.get('gps_lat', type=float)
        lng = request.form.get('gps_lng', type=float)

        if not location or not category or not description:
            flash("Location, category, and description are required to submit a grievance.", "danger")
            return redirect(url_for('contractors.complaint_new'))

        # Handle optional evidence photo upload
        file_path = ''
        if 'evidence_file' in request.files:
            file = request.files['evidence_file']
            if file and file.filename:
                fname = secure_filename(file.filename)
                ext = os.path.splitext(fname)[1].lower()
                if ext in ALLOWED_DOC_EXTENSIONS:
                    upload_dir = os.path.join(current_app.root_path, 'data', 'complaints')
                    os.makedirs(upload_dir, exist_ok=True)
                    stored_name = f"GRIEVANCE_{uuid.uuid4().hex[:8]}{ext}"
                    dest = os.path.join(upload_dir, stored_name)
                    file.save(dest)
                    file_path = f"/data/complaints/{stored_name}"

        # Assign contractor from project if available
        contractor_id = None
        dept = 'Infrastructure Grievance Cell'
        if project_id:
            p = db.session.get(Project, project_id)
            if p:
                contractor_id = p.contractor_id
                dept = p.department or p.ministry

        code = f"CMP-{datetime.utcnow().year}-{uuid.uuid4().hex[:6].upper()}"
        complaint = PublicComplaint(
            complaint_code=code,
            project_id=project_id if project_id else None,
            contractor_id=contractor_id,
            location=location,
            gps_lat=lat,
            gps_lng=lng,
            category=category,
            description=description,
            complainant_name=name,
            complainant_contact=contact,
            evidence_file_path=file_path,
            status='Submitted',
            routed_department=dept
        )
        db.session.add(complaint)
        db.session.commit()

        flash(f"Your public grievance has been registered successfully with Reference Code: {code}. It has been routed to {dept} for site inspection review.", "success")
        return redirect(url_for('contractors.complaint_detail', complaint_id=complaint.id))

    projects = Project.query.order_by(Project.project_name.asc()).all()
    return render_template('contractors/complaint_new.html', projects=projects)

@contractors_bp.route('/contractors/complaints/<int:complaint_id>')
def complaint_detail(complaint_id):
    complaint = db.session.get(PublicComplaint, complaint_id)
    if not complaint:
        flash("Grievance record not found.", "warning")
        return redirect(url_for('contractors.complaints_list'))

    return render_template('contractors/complaint_detail.html', complaint=complaint)

# =========================================================================
# 9. OFFICER & ADMIN MANAGEMENT ACTIONS
# =========================================================================
@contractors_bp.route('/contractors/new', methods=['GET', 'POST'], endpoint='new_contractor')
@contractors_bp.route('/contractors/new', methods=['GET', 'POST'], endpoint='create_contractor')
@officer_required
def create_contractor():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        reg_no = request.form.get('registration_number', '').strip()
        lic_no = request.form.get('contractor_license_number', '').strip()
        company_type = request.form.get('company_type', 'Private Limited').strip()
        owner = request.form.get('owner_representative', '').strip()
        year_est = request.form.get('year_established', 2000, type=int)
        exp = request.form.get('years_of_experience', 24, type=int)
        hq = request.form.get('headquarters', '').strip()
        email = request.form.get('contact_email', '').strip()
        phone = request.form.get('contact_phone', '').strip()
        address = request.form.get('address', '').strip()
        website = request.form.get('website', '').strip()
        govt_reg = request.form.get('govt_registration_details', '').strip()
        c_class = request.form.get('contractor_class', 'Class 1 / Class A').strip()

        if not name or not reg_no:
            flash("Company Name and Registration Number are required.", "danger")
            return redirect(url_for('contractors.create_contractor'))

        # Check duplicate registration number
        existing = Contractor.query.filter_by(registration_number=reg_no).first()
        if existing:
            flash(f"A contractor with registration number '{reg_no}' already exists.", "warning")
            return redirect(url_for('contractors.create_contractor'))

        code = f"CON-{Contractor.query.count() + 101:04d}"
        contractor = Contractor(
            name=name,
            contractor_code=code,
            registration_number=reg_no,
            contractor_license_number=lic_no,
            company_type=company_type,
            owner_representative=owner,
            year_established=year_est,
            years_of_experience=exp,
            headquarters=hq,
            contact_email=email,
            contact_phone=phone,
            address=address,
            website=website,
            govt_registration_details=govt_reg,
            contractor_class=c_class,
            data_source='Authorized Officer Entry',
            verification_status='Officer verified'
        )
        db.session.add(contractor)
        db.session.commit()

        log_security_event(
            user=current_user,
            action='CREATE_CONTRACTOR',
            resource_type='contractor',
            resource_id=str(contractor.id),
            details=f"Created contractor profile {name} ({code})",
            status='SUCCESS'
        )

        flash(f"Contractor '{name}' registered successfully.", "success")
        return redirect(url_for('contractors.detail', contractor_id=contractor.id))

    return render_template('contractors/contractor_form.html', contractor=None)

@contractors_bp.route('/contractors/<int:contractor_id>/edit', methods=['GET', 'POST'])
@officer_required
def edit_contractor(contractor_id):
    contractor = db.session.get(Contractor, contractor_id)
    if not contractor:
        flash("Contractor not found.", "warning")
        return redirect(url_for('contractors.index'))

    if request.method == 'POST':
        contractor.name = request.form.get('name', contractor.name).strip()
        contractor.contractor_license_number = request.form.get('contractor_license_number', contractor.contractor_license_number).strip()
        contractor.company_type = request.form.get('company_type', contractor.company_type).strip()
        contractor.owner_representative = request.form.get('owner_representative', contractor.owner_representative).strip()
        contractor.headquarters = request.form.get('headquarters', contractor.headquarters).strip()
        contractor.contact_email = request.form.get('contact_email', contractor.contact_email).strip()
        contractor.contact_phone = request.form.get('contact_phone', contractor.contact_phone).strip()
        contractor.contractor_class = request.form.get('contractor_class', contractor.contractor_class).strip()
        contractor.registration_status = request.form.get('registration_status', contractor.registration_status).strip()
        
        db.session.commit()
        log_security_event(
            user=current_user,
            action='UPDATE_CONTRACTOR',
            resource_type='contractor',
            resource_id=str(contractor.id),
            details=f"Updated contractor profile {contractor.name}",
            status='SUCCESS'
        )
        flash("Contractor information updated successfully.", "success")
        return redirect(url_for('contractors.detail', contractor_id=contractor.id))

    return render_template('contractors/contractor_form.html', contractor=contractor)

@contractors_bp.route('/contractors/materials/test/new', methods=['POST'])
@officer_required
def add_material_test():
    material_id = request.form.get('material_id', type=int)
    project_id = request.form.get('project_id', type=int)
    test_name = request.form.get('test_name', '').strip()
    standard = request.form.get('required_standard', '').strip()
    result_val = request.form.get('test_result_value', '').strip()
    status = request.form.get('status', 'PASS').strip()
    lab = request.form.get('testing_laboratory', 'NABL Accredited Lab').strip()
    cert_ref = request.form.get('quality_certificate_ref', '').strip()
    rejection = request.form.get('rejection_information', '').strip()
    replacement = request.form.get('replacement_information', '').strip()

    if not material_id or not test_name or not result_val:
        flash("Material, test name, and test result value are required.", "danger")
        return redirect(url_for('contractors.materials_explorer'))

    test = MaterialQualityTest(
        material_id=material_id,
        project_id=project_id,
        test_name=test_name,
        required_standard=standard,
        test_result_value=result_val,
        status=status,
        testing_laboratory=lab,
        inspector_name=current_user.full_name or current_user.username,
        inspector_designation=getattr(current_user, 'technical_designation', 'Quality Assurance Engineer'),
        quality_certificate_ref=cert_ref,
        rejection_information=rejection,
        replacement_information=replacement,
        verified_at=datetime.utcnow(),
        verified_by=current_user.username
    )
    db.session.add(test)
    db.session.commit()

    flash(f"Laboratory test '{test_name}' ({status}) logged and verified.", "success")
    return redirect(url_for('contractors.materials_explorer'))

@contractors_bp.route('/contractors/delays/new', methods=['POST'])
@officer_required
def add_delay_record():
    project_id = request.form.get('project_id', type=int)
    contractor_id = request.form.get('contractor_id', type=int)
    category = request.form.get('delay_category', 'Technical').strip()
    desc = request.form.get('delay_description', '').strip()
    days = request.form.get('affected_days', 0, type=int)
    source = request.form.get('official_source', '').strip()
    auth = request.form.get('responsible_authority', '').strip()
    corrective = request.form.get('corrective_action', '').strip()

    if not project_id or not desc:
        flash("Project and delay description are required.", "danger")
        return redirect(url_for('contractors.delays_explorer'))

    delay = ProjectDelayRecord(
        project_id=project_id,
        contractor_id=contractor_id,
        delay_category=category,
        delay_description=desc,
        affected_days=days,
        official_source=source,
        responsible_authority=auth,
        corrective_action=corrective,
        officer_remarks=f"Logged by {current_user.username}",
        verification_status='Officer verified'
    )
    db.session.add(delay)
    
    # Update project delay days if applicable
    p = db.session.get(Project, project_id)
    if p and days > (p.delay_days or 0):
        p.delay_days = days
        p.documented_delay_reason = desc
        if auth:
            p.responsible_stakeholder = auth

    db.session.commit()
    flash("Official project delay record and root cause documented.", "success")
    return redirect(url_for('contractors.delays_explorer'))

@contractors_bp.route('/contractors/documents/upload', methods=['POST'])
@officer_required
def upload_document():
    if 'document_file' not in request.files:
        flash("No file selected for upload.", "danger")
        return redirect(request.referrer or url_for('contractors.dashboard'))

    file = request.files['document_file']
    if not file or not file.filename:
        flash("Please choose a valid document.", "danger")
        return redirect(request.referrer or url_for('contractors.dashboard'))

    fname = secure_filename(file.filename)
    ext = os.path.splitext(fname)[1].lower()
    if ext not in ALLOWED_DOC_EXTENSIONS:
        flash(f"Invalid file extension. Allowed: {', '.join(ALLOWED_DOC_EXTENSIONS)}", "danger")
        return redirect(request.referrer or url_for('contractors.dashboard'))

    file_bytes = file.read()
    digest = _calc_sha256(file_bytes)

    upload_dir = os.path.join(current_app.root_path, 'data', 'documents')
    os.makedirs(upload_dir, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex[:12]}_{fname}"
    dest = os.path.join(upload_dir, stored_name)
    with open(dest, 'wb') as f:
        f.write(file_bytes)

    project_id = request.form.get('project_id', type=int)
    contractor_id = request.form.get('contractor_id', type=int)
    doc_type = request.form.get('doc_type', 'Inspection Report').strip()
    title = request.form.get('title', fname).strip()

    doc_code = f"DOC-{datetime.utcnow().year}-{uuid.uuid4().hex[:6].upper()}"
    doc = DocumentEvidence(
        document_code=doc_code,
        project_id=project_id,
        contractor_id=contractor_id,
        doc_type=doc_type,
        title=title,
        file_name=fname,
        file_path=f"/data/documents/{stored_name}",
        file_size_bytes=len(file_bytes),
        mime_type=file.content_type or 'application/pdf',
        source_agency=getattr(current_user, 'organization', '') or 'Infrastructure Authority',
        verification_status='Verified',
        tamper_hash=digest,
        uploaded_by_user_id=current_user.id
    )
    db.session.add(doc)
    db.session.commit()

    flash(f"Official evidence document '{title}' verified and archived with SHA-256 hash: {digest[:12]}...", "success")
    return redirect(request.referrer or url_for('contractors.dashboard'))

@contractors_bp.route('/contractors/complaints/<int:complaint_id>/triage', methods=['POST'])
@officer_required
def triage_complaint(complaint_id):
    complaint = db.session.get(PublicComplaint, complaint_id)
    if not complaint:
        flash("Grievance record not found.", "warning")
        return redirect(url_for('contractors.complaints_list'))

    new_status = request.form.get('status', complaint.status).strip()
    official_resp = request.form.get('official_response', '').strip()
    inspection_ref = request.form.get('inspection_finding_ref', '').strip()

    complaint.status = new_status
    complaint.assigned_officer = current_user.full_name or current_user.username
    if official_resp:
        complaint.official_response = official_resp
    if inspection_ref:
        complaint.inspection_finding_ref = inspection_ref
    if new_status in ['Resolved', 'Closed']:
        complaint.resolved_at = datetime.utcnow()

    db.session.commit()
    log_security_event(
        user=current_user,
        action='TRIAGE_COMPLAINT',
        resource_type='complaint',
        resource_id=str(complaint.id),
        details=f"Updated status of {complaint.complaint_code} to {new_status}",
        status='SUCCESS'
    )
    flash(f"Complaint {complaint.complaint_code} status updated to '{new_status}'.", "success")
    return redirect(url_for('contractors.complaint_detail', complaint_id=complaint.id))

# =========================================================================
# 10. REST API ENDPOINTS
# =========================================================================
@contractors_bp.route('/api/contractors')
def api_contractors():
    contractors = ContractorService.get_all_contractors_summary()
    return jsonify({'status': 'success', 'data': contractors, 'count': len(contractors)})

@contractors_bp.route('/api/contractors/<int:contractor_id>')
def api_contractor_detail(contractor_id):
    c = db.session.get(Contractor, contractor_id)
    if not c:
        return jsonify({'status': 'error', 'message': 'Contractor not found'}), 404
    data = c.to_dict()
    data['metrics'] = ContractorService.calculate_contractor_metrics(c)
    return jsonify({'status': 'success', 'data': data, 'contractor': data})

@contractors_bp.route('/api/contractors/<int:contractor_id>/metrics')
def api_contractor_metrics(contractor_id):
    c = db.session.get(Contractor, contractor_id)
    if not c:
        return jsonify({'status': 'error', 'message': 'Contractor not found'}), 404
    return jsonify({'status': 'success', 'data': ContractorService.calculate_contractor_metrics(c)})

@contractors_bp.route('/api/materials')
def api_materials():
    materials = ProjectMaterial.query.limit(100).all()
    return jsonify({'status': 'success', 'data': [m.to_dict() for m in materials]})

@contractors_bp.route('/api/delays')
def api_delays():
    delays = ProjectDelayRecord.query.order_by(ProjectDelayRecord.recorded_at.desc()).limit(100).all()
    return jsonify({'status': 'success', 'data': [d.to_dict() for d in delays]})

@contractors_bp.route('/api/complaints')
def api_complaints():
    complaints = PublicComplaint.query.order_by(PublicComplaint.created_at.desc()).limit(100).all()
    return jsonify({'status': 'success', 'data': [c.to_dict() for c in complaints]})

@contractors_bp.route('/api/contractor-intelligence/dashboard-stats')
def api_dashboard_stats():
    return jsonify({'status': 'success', 'data': ContractorService.get_contractor_intelligence_dashboard_stats()})
