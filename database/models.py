import json
import secrets
from datetime import datetime, date, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from database import db


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(32), default='viewer', nullable=False)  # admin, officer, viewer
    technical_designation = db.Column(db.String(50), default='Monitoring Officer')  # Chief Engineer, SE, EE, AEE, AE, JE, Monitoring Officer
    jurisdiction = db.Column(db.String(150), default='')
    full_name = db.Column(db.String(120), default='')
    organization = db.Column(db.String(150), default='')
    department = db.Column(db.String(120), default='Infrastructure Monitoring')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Verification and account lifecycle fields
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    status = db.Column(db.String(32), default='pending_verification', nullable=False)  # pending_verification, pending_approval, active, suspended
    verification_token = db.Column(db.String(128), unique=True, nullable=True, index=True)
    verification_token_expires_at = db.Column(db.DateTime, nullable=True)

    # Password reset fields
    reset_token = db.Column(db.String(128), unique=True, nullable=True, index=True)
    reset_token_expires_at = db.Column(db.DateTime, nullable=True)

    # SMS recovery & verification fields
    phone_number = db.Column(db.String(20), nullable=True, index=True)
    sms_code = db.Column(db.String(16), nullable=True)
    sms_code_expires_at = db.Column(db.DateTime, nullable=True)

    # Rate limiting & security
    last_resend_at = db.Column(db.DateTime, nullable=True)
    resend_count = db.Column(db.Integer, default=0)
    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_verification_token(self, expires_in_hours=24):
        token = secrets.token_urlsafe(32)
        self.verification_token = token
        self.verification_token_expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)
        return token

    def verify_email(self, token):
        if not self.verification_token or self.verification_token != token:
            return False, "Invalid or already used verification link."
        if self.verification_token_expires_at and datetime.utcnow() > self.verification_token_expires_at:
            return False, "This verification link has expired. Please request a new verification email."
        
        self.email_verified = True
        self.verification_token = None
        self.verification_token_expires_at = None
        
        # Officer accounts require administrator approval before activation
        if self.role == 'officer':
            self.status = 'pending_approval'
            return True, "Email verified successfully. Your account is pending administrator approval before you can sign in."
        else:
            self.status = 'active'
            return True, "Email verified successfully. You can now sign in to your account."

    def generate_reset_token(self, expires_in_hours=1):
        token = secrets.token_urlsafe(32)
        self.reset_token = token
        self.reset_token_expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)
        return token

    def reset_password(self, token, new_password):
        if not self.reset_token or self.reset_token != token:
            return False, "Invalid or already used password reset link."
        if self.reset_token_expires_at and datetime.utcnow() > self.reset_token_expires_at:
            return False, "This password reset link has expired. Please request a new password reset."
        
        self.set_password(new_password)
        self.reset_token = None
        self.reset_token_expires_at = None
        self.failed_login_attempts = 0
        self.locked_until = None
        return True, "Password has been updated successfully."

    def change_password(self, current_password, new_password):
        if not self.check_password(current_password):
            return False, "Current password is incorrect."
        self.set_password(new_password)
        self.failed_login_attempts = 0
        self.locked_until = None
        return True, "Password updated successfully."

    def generate_sms_code(self, expires_in_minutes=10):
        from services.sms_service import generate_sms_otp
        code = generate_sms_otp(6)
        self.sms_code = code
        self.sms_code_expires_at = datetime.utcnow() + timedelta(minutes=expires_in_minutes)
        return code

    def verify_sms_code(self, code):
        if not self.sms_code or not code:
            return False, "No SMS verification code was generated or provided."
        if self.sms_code.strip() != str(code).strip():
            return False, "Invalid SMS verification code. Please verify the 6-digit code and try again."
        if self.sms_code_expires_at and datetime.utcnow() > self.sms_code_expires_at:
            return False, "SMS verification code has expired (valid for 10 minutes). Please request a new code."
        return True, "SMS verification code is valid."

    def update_password_with_sms_code(self, code, new_password):
        valid, msg = self.verify_sms_code(code)
        if not valid:
            return False, msg
        self.set_password(new_password)
        self.sms_code = None
        self.sms_code_expires_at = None
        self.failed_login_attempts = 0
        self.locked_until = None
        return True, "Password updated successfully."

    @property
    def is_locked(self):
        if self.locked_until and datetime.utcnow() < self.locked_until:
            return True
        return False

    @property
    def is_active_account(self):
        return self.email_verified and self.status == 'active' and not self.is_locked

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_officer(self):
        return self.role in ['admin', 'officer']

    @property
    def can_edit(self):
        return self.role == 'admin'

    @property
    def can_triage_alerts(self):
        return self.role in ['admin', 'officer']

    def get_authorized_project_ids(self):
        """
        Returns a set of authorized project IDs for this user.
        - Admin: None (unrestricted, access to all projects)
        - Viewer: None (read-only access to all projects)
        - Officer: Set of project IDs assigned in ProjectAssignment
        """
        if self.is_admin or self.role == 'viewer':
            return None
        if self.role == 'officer':
            assigned = [a.project_id for a in ProjectAssignment.query.filter_by(user_id=self.id).all()]
            return set(assigned)
        return set()

    def can_access_project(self, project_id, write=False):
        """
        Fine-grained object-level authorization check.
        - Admin: Can read and write any project.
        - Viewer: Can read any project; can NEVER write (returns False).
        - Officer: Can read and write ONLY if explicitly assigned to this project.
        """
        if not self.is_authenticated:
            return False
        
        if hasattr(self, 'is_active_account') and not self.is_active_account:
            return False

        if write:
            if self.role == 'viewer':
                return False
            if self.is_admin:
                return True
            if self.role == 'officer':
                assignment = ProjectAssignment.query.filter_by(user_id=self.id, project_id=project_id).first()
                return assignment is not None and assignment.can_edit
            return False
        else:
            # Read check
            if self.is_admin or self.role == 'viewer':
                return True
            if self.role == 'officer':
                assignment = ProjectAssignment.query.filter_by(user_id=self.id, project_id=project_id).first()
                return assignment is not None
            return False

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'technical_designation': self.technical_designation,
            'jurisdiction': self.jurisdiction,
            'full_name': self.full_name,
            'organization': self.organization,
            'department': self.department,
            'email_verified': self.email_verified,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ProjectAssignment(db.Model):
    __tablename__ = 'project_assignments'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    can_edit = db.Column(db.Boolean, default=True, nullable=False)
    role_scope = db.Column(db.String(50), default='Monitoring Officer')
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('assignments', cascade='all, delete-orphan', lazy='dynamic'))
    project = db.relationship('Project', backref=db.backref('assigned_officers', cascade='all, delete-orphan', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('user_id', 'project_id', name='uq_user_project_assignment'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'project_id': self.project_id,
            'can_edit': self.can_edit,
            'role_scope': self.role_scope,
            'assigned_at': self.assigned_at.isoformat() if self.assigned_at else None
        }


class Contractor(db.Model):
    __tablename__ = 'contractors'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, index=True)
    contractor_code = db.Column(db.String(64), unique=True, nullable=False, index=True)
    registration_number = db.Column(db.String(100), unique=True, nullable=False, index=True)
    contractor_license_number = db.Column(db.String(100), default='', index=True)
    company_type = db.Column(db.String(100), default='Private Limited')  # Private Limited, Public Limited, Joint Venture, Sole Proprietorship, Partnership
    owner_representative = db.Column(db.String(200), default='')
    year_established = db.Column(db.Integer, default=2000)
    years_of_experience = db.Column(db.Integer, default=24)
    headquarters = db.Column(db.String(200), default='')
    contact_email = db.Column(db.String(120), default='')
    contact_phone = db.Column(db.String(50), default='')
    address = db.Column(db.Text, default='')
    website = db.Column(db.String(255), default='')
    govt_registration_details = db.Column(db.Text, default='')
    license_validity_date = db.Column(db.Date, nullable=True)
    registration_status = db.Column(db.String(50), default='Active')  # Active, Suspended, Expired, Renewal Pending
    contractor_class = db.Column(db.String(50), default='Class 1 / Class A')  # Super Class, Class 1 / Class A, Class 2
    areas_of_specialization = db.Column(db.Text, default='[]')  # JSON array
    sectors_served = db.Column(db.Text, default='[]')  # JSON array
    certifications = db.Column(db.Text, default='[]')  # JSON array
    
    # Official Source & Verification Metadata
    data_source = db.Column(db.String(200), default='Central / State Contractor Registry')
    source_timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    sync_timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    verification_status = db.Column(db.String(50), default='Verified')  # Verified, Source-confirmed, Officer verified, Pending verification, Conflicting data
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    branches = db.relationship('ContractorBranch', backref='contractor', cascade='all, delete-orphan', lazy=True)
    subcontractor_assignments = db.relationship('ProjectSubcontractor', backref='contractor', cascade='all, delete-orphan', lazy=True)
    materials = db.relationship('ProjectMaterial', backref='contractor', lazy=True)
    delay_records = db.relationship('ProjectDelayRecord', backref='contractor', lazy=True)
    post_construction_records = db.relationship('PostConstructionRecord', backref='contractor', lazy=True)
    complaints = db.relationship('PublicComplaint', backref='contractor', lazy=True)
    documents = db.relationship('DocumentEvidence', backref='contractor', lazy=True)

    def get_specializations(self):
        try:
            return json.loads(self.areas_of_specialization or '[]')
        except Exception:
            return [s.strip() for s in (self.areas_of_specialization or '').split(',') if s.strip()]

    def get_sectors(self):
        try:
            return json.loads(self.sectors_served or '[]')
        except Exception:
            return [s.strip() for s in (self.sectors_served or '').split(',') if s.strip()]

    def get_certifications(self):
        try:
            return json.loads(self.certifications or '[]')
        except Exception:
            return [s.strip() for s in (self.certifications or '').split(',') if s.strip()]

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'contractor_code': self.contractor_code,
            'registration_number': self.registration_number,
            'contractor_license_number': self.contractor_license_number,
            'company_type': self.company_type,
            'owner_representative': self.owner_representative,
            'year_established': self.year_established,
            'years_of_experience': self.years_of_experience,
            'headquarters': self.headquarters,
            'contact_email': self.contact_email,
            'contact_phone': self.contact_phone,
            'address': self.address,
            'website': self.website,
            'govt_registration_details': self.govt_registration_details,
            'license_validity_date': self.license_validity_date.isoformat() if self.license_validity_date else None,
            'registration_status': self.registration_status,
            'contractor_class': self.contractor_class,
            'areas_of_specialization': self.get_specializations(),
            'sectors_served': self.get_sectors(),
            'certifications': self.get_certifications(),
            'data_source': self.data_source,
            'source_timestamp': self.source_timestamp.isoformat() if self.source_timestamp else None,
            'sync_timestamp': self.sync_timestamp.isoformat() if self.sync_timestamp else None,
            'verification_status': self.verification_status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Project(db.Model):
    __tablename__ = 'projects'

    id = db.Column(db.Integer, primary_key=True)
    project_code = db.Column(db.String(64), unique=True, nullable=False, index=True)
    project_name = db.Column(db.String(255), nullable=False, index=True)
    ministry = db.Column(db.String(150), nullable=False, index=True)
    department = db.Column(db.String(150), default='')
    sector = db.Column(db.String(100), nullable=False, index=True)
    state = db.Column(db.String(100), nullable=False, index=True)
    location = db.Column(db.String(200), default='')
    implementing_agency = db.Column(db.String(150), default='')
    
    # Financial fields (in Crores INR)
    approved_cost = db.Column(db.Float, default=0.0)
    revised_cost = db.Column(db.Float, default=0.0)
    expenditure = db.Column(db.Float, default=0.0)
    financial_progress = db.Column(db.Float, default=0.0)  # percentage
    
    # Schedule fields
    start_date = db.Column(db.Date, nullable=True)
    original_completion_date = db.Column(db.Date, nullable=True)
    revised_completion_date = db.Column(db.Date, nullable=True)
    predicted_completion_date = db.Column(db.Date, nullable=True)
    delay_days = db.Column(db.Integer, default=0)
    
    # Physical and milestone metrics
    physical_progress = db.Column(db.Float, default=0.0)  # percentage
    planned_progress = db.Column(db.Float, default=0.0)   # percentage
    milestones_total = db.Column(db.Integer, default=0)
    milestones_completed = db.Column(db.Integer, default=0)
    milestones_delayed = db.Column(db.Integer, default=0)
    
    # Bottleneck status indicators
    contractor_status = db.Column(db.String(50), default='On Track')       # On Track, Minor Delay, Delayed, Critical
    land_acquisition_status = db.Column(db.String(50), default='Completed')# Completed, In Progress, Delayed, Pending
    environmental_clearance_status = db.Column(db.String(50), default='Completed') # Completed, In Progress, Delayed, Pending
    utility_shifting_status = db.Column(db.String(50), default='Completed')        # Completed, In Progress, Delayed, Pending
    
    # General status & metadata
    reporting_date = db.Column(db.Date, default=date.today)
    project_status = db.Column(db.String(50), default='Ongoing')           # Ongoing, Completed, Delayed, Stalled
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    
    # Contractor & Operational Intelligence linkage
    contractor_id = db.Column(db.Integer, db.ForeignKey('contractors.id', ondelete='SET NULL'), nullable=True, index=True)
    original_budget = db.Column(db.Float, default=0.0)
    final_cost = db.Column(db.Float, default=0.0)
    contract_value = db.Column(db.Float, default=0.0)
    planned_duration_months = db.Column(db.Integer, default=0)
    actual_duration_months = db.Column(db.Integer, default=0)
    completion_certificate_ref = db.Column(db.String(100), default='')
    completion_certificate_date = db.Column(db.Date, nullable=True)
    documented_delay_reason = db.Column(db.Text, default='')
    responsible_stakeholder = db.Column(db.String(200), default='')
    latest_govt_inspection = db.Column(db.Text, default='')
    latest_contractor_update = db.Column(db.Text, default='')
    corrective_action = db.Column(db.Text, default='')
    expected_restart_date = db.Column(db.Date, nullable=True)
    current_construction_stage = db.Column(db.String(100), default='')
    current_site_status = db.Column(db.String(255), default='')
    reported_issues = db.Column(db.Text, default='{}')
    
    # Source Verification & Telemetry (Requirement 10 & 16)
    data_source = db.Column(db.String(200), default='Official Department Project Record')
    source_timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    sync_timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    verification_status = db.Column(db.String(50), default='Verified')
    
    # AI/ML Risk Cache
    risk_score = db.Column(db.Float, default=0.0)
    delay_probability = db.Column(db.Float, default=0.0)
    cost_overrun_probability = db.Column(db.Float, default=0.0)
    risk_level = db.Column(db.String(20), default='LOW')  # LOW, MEDIUM, HIGH, CRITICAL
    health_score = db.Column(db.Float, default=100.0)
    
    # Relationships
    milestones = db.relationship('Milestone', backref='project', cascade='all, delete-orphan', lazy=True, order_by='Milestone.sequence_order')
    history = db.relationship('ProjectHistory', backref='project', cascade='all, delete-orphan', lazy=True, order_by='ProjectHistory.reporting_date')
    alerts = db.relationship('Alert', backref='project', cascade='all, delete-orphan', lazy=True, order_by='desc(Alert.created_at)')
    predictions = db.relationship('RiskPrediction', backref='project', cascade='all, delete-orphan', lazy=True, order_by='desc(RiskPrediction.prediction_date)')
    contractor = db.relationship('Contractor', backref=db.backref('projects', lazy='dynamic'))
    subcontractors = db.relationship('ProjectSubcontractor', backref='project', cascade='all, delete-orphan', lazy=True)
    materials = db.relationship('ProjectMaterial', backref='project', cascade='all, delete-orphan', lazy=True)
    delay_records = db.relationship('ProjectDelayRecord', backref='project', cascade='all, delete-orphan', lazy=True, order_by='desc(ProjectDelayRecord.recorded_at)')
    financial_records = db.relationship('ProjectFinancialRecord', backref='project', cascade='all, delete-orphan', lazy=True)
    lifecycle_events = db.relationship('ProjectLifecycleEvent', backref='project', cascade='all, delete-orphan', lazy=True, order_by='ProjectLifecycleEvent.sequence_order')
    post_construction = db.relationship('PostConstructionRecord', backref='project', cascade='all, delete-orphan', lazy=True)
    complaints = db.relationship('PublicComplaint', backref='project', cascade='all, delete-orphan', lazy=True, order_by='desc(PublicComplaint.created_at)')
    documents = db.relationship('DocumentEvidence', backref='project', cascade='all, delete-orphan', lazy=True, order_by='desc(DocumentEvidence.uploaded_at)')
    site_inspections = db.relationship('SiteInspectionRecord', backref='project', cascade='all, delete-orphan', lazy=True, order_by='desc(SiteInspectionRecord.inspection_date)')

    @property
    def progress_gap(self):
        return round(max(0.0, (self.planned_progress or 0.0) - (self.physical_progress or 0.0)), 1)

    @property
    def cost_escalation(self):
        if self.approved_cost and self.approved_cost > 0:
            return round(((self.revised_cost - self.approved_cost) / self.approved_cost) * 100.0, 1)
        return 0.0

    @property
    def budget_utilization(self):
        if self.approved_cost and self.approved_cost > 0:
            return round((self.expenditure / self.approved_cost) * 100.0, 1)
        return 0.0

    @property
    def cost_escalation_amount(self):
        return round(max(0.0, (self.revised_cost or 0.0) - (self.approved_cost or 0.0)), 2)

    @property
    def cost_variance(self):
        base = self.original_budget if (self.original_budget and self.original_budget > 0) else self.approved_cost
        curr = self.final_cost if (self.final_cost and self.final_cost > 0) else self.revised_cost
        return round(curr - base, 2)

    @property
    def cost_variance_pct(self):
        base = self.original_budget if (self.original_budget and self.original_budget > 0) else self.approved_cost
        if base and base > 0:
            curr = self.final_cost if (self.final_cost and self.final_cost > 0) else self.revised_cost
            return round(((curr - base) / base) * 100.0, 1)
        return 0.0

    @property
    def schedule_variance_days(self):
        return self.delay_days or 0

    @property
    def timeliness_status(self):
        if self.project_status == 'Completed':
            if (self.delay_days or 0) <= 0:
                return 'Completed on schedule'
            return 'Completed after planned schedule'
        if (self.delay_days or 0) > 0:
            return 'Delayed'
        return 'On schedule'

    @property
    def risk_badge_class(self):
        mapping = {
            'LOW': 'bg-success',
            'MEDIUM': 'bg-warning text-dark',
            'HIGH': 'bg-orange text-white',
            'CRITICAL': 'bg-danger'
        }
        return mapping.get(self.risk_level, 'bg-secondary')

    def to_dict(self):
        return {
            'id': self.id,
            'project_code': self.project_code,
            'project_name': self.project_name,
            'ministry': self.ministry,
            'department': self.department,
            'sector': self.sector,
            'state': self.state,
            'location': self.location,
            'implementing_agency': self.implementing_agency,
            'contractor_id': self.contractor_id,
            'contractor_name': self.contractor.name if self.contractor else None,
            'approved_cost': self.approved_cost,
            'revised_cost': self.revised_cost,
            'original_budget': self.original_budget,
            'final_cost': self.final_cost,
            'contract_value': self.contract_value,
            'cost_variance': self.cost_variance,
            'cost_variance_pct': self.cost_variance_pct,
            'expenditure': self.expenditure,
            'financial_progress': self.financial_progress,
            'cost_escalation': self.cost_escalation,
            'budget_utilization': self.budget_utilization,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'original_completion_date': self.original_completion_date.isoformat() if self.original_completion_date else None,
            'revised_completion_date': self.revised_completion_date.isoformat() if self.revised_completion_date else None,
            'predicted_completion_date': self.predicted_completion_date.isoformat() if self.predicted_completion_date else None,
            'delay_days': self.delay_days,
            'schedule_variance_days': self.schedule_variance_days,
            'timeliness_status': self.timeliness_status,
            'planned_duration_months': self.planned_duration_months,
            'actual_duration_months': self.actual_duration_months,
            'completion_certificate_ref': self.completion_certificate_ref,
            'completion_certificate_date': self.completion_certificate_date.isoformat() if self.completion_certificate_date else None,
            'documented_delay_reason': self.documented_delay_reason,
            'responsible_stakeholder': self.responsible_stakeholder,
            'latest_govt_inspection': self.latest_govt_inspection,
            'latest_contractor_update': self.latest_contractor_update,
            'corrective_action': self.corrective_action,
            'expected_restart_date': self.expected_restart_date.isoformat() if self.expected_restart_date else None,
            'current_construction_stage': self.current_construction_stage,
            'current_site_status': self.current_site_status,
            'physical_progress': self.physical_progress,
            'planned_progress': self.planned_progress,
            'progress_gap': self.progress_gap,
            'milestones_total': self.milestones_total,
            'milestones_completed': self.milestones_completed,
            'milestones_delayed': self.milestones_delayed,
            'contractor_status': self.contractor_status,
            'land_acquisition_status': self.land_acquisition_status,
            'environmental_clearance_status': self.environmental_clearance_status,
            'utility_shifting_status': self.utility_shifting_status,
            'reporting_date': self.reporting_date.isoformat() if self.reporting_date else None,
            'project_status': self.project_status,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'risk_score': round(self.risk_score, 1),
            'health_score': round(self.health_score, 1),
            'delay_probability': round(self.delay_probability, 1),
            'cost_overrun_probability': round(self.cost_overrun_probability, 1),
            'risk_level': self.risk_level,
            'data_source': self.data_source,
            'source_timestamp': self.source_timestamp.isoformat() if self.source_timestamp else None,
            'sync_timestamp': self.sync_timestamp.isoformat() if self.sync_timestamp else None,
            'verification_status': self.verification_status
        }


class Milestone(db.Model):
    __tablename__ = 'milestones'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    target_date = db.Column(db.Date, nullable=True)
    revised_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(50), default='Upcoming')  # Completed, In Progress, Delayed, Upcoming
    completion_percentage = db.Column(db.Float, default=0.0)
    dependencies = db.Column(db.String(255), default='')
    sequence_order = db.Column(db.Integer, default=1)

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'name': self.name,
            'target_date': self.target_date.isoformat() if self.target_date else None,
            'revised_date': self.revised_date.isoformat() if self.revised_date else None,
            'status': self.status,
            'completion_percentage': self.completion_percentage,
            'dependencies': self.dependencies,
            'sequence_order': self.sequence_order
        }


class ProjectHistory(db.Model):
    __tablename__ = 'project_history'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, index=True)
    reporting_date = db.Column(db.Date, nullable=False, index=True)
    physical_progress = db.Column(db.Float, default=0.0)
    planned_progress = db.Column(db.Float, default=0.0)
    expenditure = db.Column(db.Float, default=0.0)
    revised_cost = db.Column(db.Float, default=0.0)
    delay_days = db.Column(db.Integer, default=0)
    milestones_delayed = db.Column(db.Integer, default=0)
    risk_score = db.Column(db.Float, default=0.0)

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'reporting_date': self.reporting_date.isoformat() if self.reporting_date else None,
            'physical_progress': self.physical_progress,
            'planned_progress': self.planned_progress,
            'expenditure': self.expenditure,
            'revised_cost': self.revised_cost,
            'delay_days': self.delay_days,
            'milestones_delayed': self.milestones_delayed,
            'risk_score': round(self.risk_score, 1)
        }


class RiskPrediction(db.Model):
    __tablename__ = 'risk_predictions'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, index=True)
    prediction_date = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    delay_probability = db.Column(db.Float, default=0.0)
    cost_overrun_probability = db.Column(db.Float, default=0.0)
    overall_risk_score = db.Column(db.Float, default=0.0)
    risk_level = db.Column(db.String(20), default='LOW')
    
    # Decomposed Health Scores (0-100)
    schedule_health = db.Column(db.Float, default=100.0)
    financial_health = db.Column(db.Float, default=100.0)
    physical_health = db.Column(db.Float, default=100.0)
    milestone_health = db.Column(db.Float, default=100.0)
    risk_factors_health = db.Column(db.Float, default=100.0)
    
    explanation = db.Column(db.Text, default='')
    contributing_factors = db.Column(db.Text, default='{}')  # JSON encoded

    def get_factors(self):
        try:
            return json.loads(self.contributing_factors or '{}')
        except Exception:
            return {}

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'prediction_date': self.prediction_date.isoformat() if self.prediction_date else None,
            'delay_probability': round(self.delay_probability, 1),
            'cost_overrun_probability': round(self.cost_overrun_probability, 1),
            'overall_risk_score': round(self.overall_risk_score, 1),
            'risk_level': self.risk_level,
            'schedule_health': round(self.schedule_health, 1),
            'financial_health': round(self.financial_health, 1),
            'physical_health': round(self.physical_health, 1),
            'milestone_health': round(self.milestone_health, 1),
            'risk_factors_health': round(self.risk_factors_health, 1),
            'explanation': self.explanation,
            'contributing_factors': self.get_factors()
        }


class Alert(db.Model):
    __tablename__ = 'alerts'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, index=True)
    severity = db.Column(db.String(20), default='INFO', index=True)  # INFO, MEDIUM, HIGH, CRITICAL
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    trigger = db.Column(db.String(255), default='')
    probability = db.Column(db.Float, default=0.0)
    contributing_factors = db.Column(db.Text, default='')
    recommendation = db.Column(db.Text, default='')
    status = db.Column(db.String(30), default='Open', index=True)  # Open, Under Review, Resolved
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolved_by = db.Column(db.String(100), default='')
    notes = db.Column(db.Text, default='')

    @property
    def badge_class(self):
        mapping = {
            'INFO': 'bg-info text-white',
            'MEDIUM': 'bg-warning text-dark',
            'HIGH': 'bg-orange text-white',
            'CRITICAL': 'bg-danger text-white'
        }
        return mapping.get(self.severity, 'bg-secondary')

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'project_name': self.project.project_name if self.project else 'N/A',
            'project_code': self.project.project_code if self.project else 'N/A',
            'severity': self.severity,
            'title': self.title,
            'description': self.description,
            'trigger': self.trigger,
            'probability': self.probability,
            'contributing_factors': self.contributing_factors,
            'recommendation': self.recommendation,
            'status': self.status,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else None,
            'resolved_at': self.resolved_at.strftime('%Y-%m-%d %H:%M') if self.resolved_at else None,
            'resolved_by': self.resolved_by,
            'notes': self.notes
        }


class SecurityAuditLog(db.Model):
    __tablename__ = 'security_audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    username = db.Column(db.String(64), nullable=True, index=True)
    action = db.Column(db.String(100), nullable=False, index=True)
    resource_type = db.Column(db.String(50), nullable=True)
    resource_id = db.Column(db.String(50), nullable=True)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), default='SUCCESS', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship('User', backref=db.backref('audit_logs', lazy='dynamic'))

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.username or (self.user.username if self.user else 'Anonymous'),
            'action': self.action,
            'resource_type': self.resource_type,
            'resource_id': self.resource_id,
            'details': self.details,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'status': self.status,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }


class ContractorBranch(db.Model):
    __tablename__ = 'contractor_branches'

    id = db.Column(db.Integer, primary_key=True)
    contractor_id = db.Column(db.Integer, db.ForeignKey('contractors.id', ondelete='CASCADE'), nullable=False, index=True)
    branch_name = db.Column(db.String(200), nullable=False)
    location = db.Column(db.String(200), nullable=False)
    branch_manager = db.Column(db.String(150), default='')
    contact_email = db.Column(db.String(120), default='')
    contact_phone = db.Column(db.String(50), default='')
    address = db.Column(db.Text, default='')
    registration_info = db.Column(db.String(200), default='')
    workforce_count = db.Column(db.Integer, default=0)
    equipment_summary = db.Column(db.Text, default='')
    departments_served = db.Column(db.Text, default='[]')
    local_suppliers = db.Column(db.Text, default='[]')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'contractor_id': self.contractor_id,
            'branch_name': self.branch_name,
            'location': self.location,
            'branch_manager': self.branch_manager,
            'contact_email': self.contact_email,
            'contact_phone': self.contact_phone,
            'address': self.address,
            'registration_info': self.registration_info,
            'workforce_count': self.workforce_count,
            'equipment_summary': self.equipment_summary,
            'departments_served': json.loads(self.departments_served or '[]') if self.departments_served.startswith('[') else [self.departments_served],
            'local_suppliers': json.loads(self.local_suppliers or '[]') if self.local_suppliers.startswith('[') else [self.local_suppliers],
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class MaterialSupplier(db.Model):
    __tablename__ = 'material_suppliers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False, index=True)
    registration_number = db.Column(db.String(100), default='', index=True)
    category = db.Column(db.String(100), default='')
    contact_person = db.Column(db.String(150), default='')
    phone = db.Column(db.String(50), default='')
    email = db.Column(db.String(120), default='')
    address = db.Column(db.Text, default='')
    city = db.Column(db.String(100), default='')
    state = db.Column(db.String(100), default='')
    certifications = db.Column(db.Text, default='')
    delivery_delay_records = db.Column(db.Integer, default=0)
    data_source = db.Column(db.String(200), default='Official Supplier Register')
    verification_status = db.Column(db.String(50), default='Verified')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    materials_supplied = db.relationship('ProjectMaterial', backref='supplier', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'registration_number': self.registration_number,
            'category': self.category,
            'contact_person': self.contact_person,
            'phone': self.phone,
            'email': self.email,
            'address': self.address,
            'city': self.city,
            'state': self.state,
            'certifications': self.certifications,
            'delivery_delay_records': self.delivery_delay_records,
            'data_source': self.data_source,
            'verification_status': self.verification_status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ProjectMaterial(db.Model):
    __tablename__ = 'project_materials'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    contractor_id = db.Column(db.Integer, db.ForeignKey('contractors.id', ondelete='SET NULL'), nullable=True, index=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('material_suppliers.id', ondelete='SET NULL'), nullable=True, index=True)
    material_name = db.Column(db.String(200), nullable=False)
    material_category = db.Column(db.String(100), nullable=False, index=True)
    brand_manufacturer = db.Column(db.String(150), default='')
    batch_number = db.Column(db.String(100), default='', index=True)
    quantity = db.Column(db.Float, default=0.0)
    unit = db.Column(db.String(50), default='MT')
    delivery_date = db.Column(db.Date, nullable=True)
    source_location = db.Column(db.String(200), default='')
    purchase_order_ref = db.Column(db.String(100), default='')
    invoice_ref = db.Column(db.String(100), default='')
    required_specification = db.Column(db.Text, default='')
    actual_specification = db.Column(db.Text, default='')
    approval_status = db.Column(db.String(50), default='Approved')  # Approved, Pending Test, Rejected, Conditional Approval
    quality_certification_status = db.Column(db.String(100), default='Pending Test')  # BIS Certified, Pending Test, Failed Lab Test, Quality Approved
    quality_certificate_ref = db.Column(db.String(150), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    quality_tests = db.relationship('MaterialQualityTest', backref='material', cascade='all, delete-orphan', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'project_code': self.project.project_code if self.project else None,
            'contractor_id': self.contractor_id,
            'contractor_name': self.contractor.name if self.contractor else None,
            'supplier_id': self.supplier_id,
            'supplier_name': self.supplier.name if self.supplier else None,
            'material_name': self.material_name,
            'material_category': self.material_category,
            'brand_manufacturer': self.brand_manufacturer,
            'batch_number': self.batch_number,
            'quantity': self.quantity,
            'unit': self.unit,
            'delivery_date': self.delivery_date.isoformat() if self.delivery_date else None,
            'source_location': self.source_location,
            'purchase_order_ref': self.purchase_order_ref,
            'invoice_ref': self.invoice_ref,
            'required_specification': self.required_specification,
            'actual_specification': self.actual_specification,
            'approval_status': self.approval_status,
            'quality_certification_status': self.quality_certification_status,
            'quality_certificate_ref': self.quality_certificate_ref,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class MaterialQualityTest(db.Model):
    __tablename__ = 'material_quality_tests'

    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey('project_materials.id', ondelete='CASCADE'), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    test_name = db.Column(db.String(200), nullable=False)
    required_standard = db.Column(db.String(150), default='')  # BIS standard e.g. IS 516, IS 1786
    manufacturer_spec = db.Column(db.Text, default='')
    dept_specification = db.Column(db.Text, default='')
    test_standard = db.Column(db.String(150), default='')
    test_date = db.Column(db.Date, nullable=True)
    testing_laboratory = db.Column(db.String(200), default='NABL Accredited Lab')
    test_result_value = db.Column(db.String(200), default='')
    status = db.Column(db.String(30), default='PASS', index=True)  # PASS, FAIL, CONDITIONAL
    inspector_name = db.Column(db.String(150), default='')
    inspector_designation = db.Column(db.String(150), default='Quality Assurance Engineer')
    quality_certificate_ref = db.Column(db.String(150), default='')
    sample_info = db.Column(db.Text, default='')
    rejection_information = db.Column(db.Text, default='')
    replacement_information = db.Column(db.Text, default='')
    verified_at = db.Column(db.DateTime, nullable=True)
    verified_by = db.Column(db.String(100), default='')

    def to_dict(self):
        return {
            'id': self.id,
            'material_id': self.material_id,
            'material_name': self.material.material_name if self.material else None,
            'project_id': self.project_id,
            'test_name': self.test_name,
            'required_standard': self.required_standard,
            'manufacturer_spec': self.manufacturer_spec,
            'dept_specification': self.dept_specification,
            'test_standard': self.test_standard,
            'test_date': self.test_date.isoformat() if self.test_date else None,
            'testing_laboratory': self.testing_laboratory,
            'test_result_value': self.test_result_value,
            'status': self.status,
            'inspector_name': self.inspector_name,
            'inspector_designation': self.inspector_designation,
            'quality_certificate_ref': self.quality_certificate_ref,
            'sample_info': self.sample_info,
            'rejection_information': self.rejection_information,
            'replacement_information': self.replacement_information,
            'verified_at': self.verified_at.isoformat() if self.verified_at else None,
            'verified_by': self.verified_by
        }


class ProjectDelayRecord(db.Model):
    __tablename__ = 'project_delay_records'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    contractor_id = db.Column(db.Integer, db.ForeignKey('contractors.id', ondelete='SET NULL'), nullable=True, index=True)
    delay_category = db.Column(db.String(50), nullable=False, index=True)  # Administrative, Financial, Land / Legal, Technical, Contractor / Execution, Material, Environmental, Other
    delay_description = db.Column(db.Text, nullable=False)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    affected_days = db.Column(db.Integer, default=0)
    evidence_document_ref = db.Column(db.String(200), default='')
    official_source = db.Column(db.String(200), default='')
    responsible_authority = db.Column(db.String(200), default='')
    officer_remarks = db.Column(db.Text, default='')
    corrective_action = db.Column(db.Text, default='')
    verification_status = db.Column(db.String(50), default='Verified')
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'project_code': self.project.project_code if self.project else None,
            'contractor_id': self.contractor_id,
            'contractor_name': self.contractor.name if self.contractor else None,
            'delay_category': self.delay_category,
            'delay_description': self.delay_description,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'affected_days': self.affected_days,
            'evidence_document_ref': self.evidence_document_ref,
            'official_source': self.official_source,
            'responsible_authority': self.responsible_authority,
            'officer_remarks': self.officer_remarks,
            'corrective_action': self.corrective_action,
            'verification_status': self.verification_status,
            'recorded_at': self.recorded_at.isoformat() if self.recorded_at else None
        }


class ProjectFinancialRecord(db.Model):
    __tablename__ = 'project_financial_records'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    record_type = db.Column(db.String(100), nullable=False)  # Administrative Sanction, Technical Sanction, Contract Value, Variation Order, Milestone Payment, Revised Estimate, Escalation Sanction
    title = db.Column(db.String(255), nullable=False)
    reference_no = db.Column(db.String(100), default='')
    approved_amount = db.Column(db.Float, default=0.0)  # Crores INR
    actual_expenditure = db.Column(db.Float, default=0.0)
    sanction_date = db.Column(db.Date, nullable=True)
    sanctioning_authority = db.Column(db.String(150), default='')
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'record_type': self.record_type,
            'title': self.title,
            'reference_no': self.reference_no,
            'approved_amount': self.approved_amount,
            'actual_expenditure': self.actual_expenditure,
            'sanction_date': self.sanction_date.isoformat() if self.sanction_date else None,
            'sanctioning_authority': self.sanctioning_authority,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ProjectLifecycleEvent(db.Model):
    __tablename__ = 'project_lifecycle_events'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    stage_name = db.Column(db.String(150), nullable=False)
    planned_date = db.Column(db.Date, nullable=True)
    actual_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(50), default='Completed')  # Completed On Schedule, Completed Delayed, In Progress, Pending
    delay_days = db.Column(db.Integer, default=0)
    remarks = db.Column(db.Text, default='')
    sequence_order = db.Column(db.Integer, default=1)

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'stage_name': self.stage_name,
            'planned_date': self.planned_date.isoformat() if self.planned_date else None,
            'actual_date': self.actual_date.isoformat() if self.actual_date else None,
            'status': self.status,
            'delay_days': self.delay_days,
            'remarks': self.remarks,
            'sequence_order': self.sequence_order
        }


class PostConstructionRecord(db.Model):
    __tablename__ = 'post_construction_records'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    contractor_id = db.Column(db.Integer, db.ForeignKey('contractors.id', ondelete='SET NULL'), nullable=True, index=True)
    inspection_date = db.Column(db.Date, nullable=True)
    inspector_name = db.Column(db.String(150), default='')
    warranty_dlp_expiry = db.Column(db.Date, nullable=True)
    quality_status = db.Column(db.String(50), default='No significant defects reported')
    structural_condition = db.Column(db.String(100), default='Good')
    road_condition = db.Column(db.String(100), default='Satisfactory')
    building_condition = db.Column(db.String(100), default='Good')
    cracks_observed = db.Column(db.Text, default='None')
    water_leakage_status = db.Column(db.Text, default='None')
    corrosion_settlement_status = db.Column(db.Text, default='None')
    drainage_status = db.Column(db.Text, default='Operational')
    verified_findings = db.Column(db.Text, default='')
    repair_history = db.Column(db.Text, default='')
    defect_reports = db.Column(db.Text, default='')
    maintenance_requirements = db.Column(db.Text, default='')

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'contractor_id': self.contractor_id,
            'inspection_date': self.inspection_date.isoformat() if self.inspection_date else None,
            'inspector_name': self.inspector_name,
            'warranty_dlp_expiry': self.warranty_dlp_expiry.isoformat() if self.warranty_dlp_expiry else None,
            'quality_status': self.quality_status,
            'structural_condition': self.structural_condition,
            'road_condition': self.road_condition,
            'building_condition': self.building_condition,
            'cracks_observed': self.cracks_observed,
            'water_leakage_status': self.water_leakage_status,
            'corrosion_settlement_status': self.corrosion_settlement_status,
            'drainage_status': self.drainage_status,
            'verified_findings': self.verified_findings,
            'repair_history': self.repair_history,
            'defect_reports': self.defect_reports,
            'maintenance_requirements': self.maintenance_requirements
        }


class ProjectSubcontractor(db.Model):
    __tablename__ = 'project_subcontractors'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    contractor_id = db.Column(db.Integer, db.ForeignKey('contractors.id', ondelete='CASCADE'), nullable=False, index=True)
    subcontractor_name = db.Column(db.String(255), nullable=False)
    registration_number = db.Column(db.String(100), default='')
    scope_of_work = db.Column(db.String(255), default='')
    contract_value = db.Column(db.Float, default=0.0)
    performance_status = db.Column(db.String(50), default='Satisfactory')

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'contractor_id': self.contractor_id,
            'subcontractor_name': self.subcontractor_name,
            'registration_number': self.registration_number,
            'scope_of_work': self.scope_of_work,
            'contract_value': self.contract_value,
            'performance_status': self.performance_status
        }


class DepartmentHierarchy(db.Model):
    __tablename__ = 'department_hierarchies'

    id = db.Column(db.Integer, primary_key=True)
    department_name = db.Column(db.String(150), nullable=False, index=True)
    region_circle = db.Column(db.String(150), default='')
    district = db.Column(db.String(100), default='')
    division = db.Column(db.String(150), default='')
    chief_engineer = db.Column(db.String(150), default='')
    superintending_engineer = db.Column(db.String(150), default='')
    executive_engineer = db.Column(db.String(150), default='')
    assistant_exec_engineer = db.Column(db.String(150), default='')
    assistant_engineer = db.Column(db.String(150), default='')
    junior_engineer = db.Column(db.String(150), default='')
    official_routing_email = db.Column(db.String(120), default='')

    def to_dict(self):
        return {
            'id': self.id,
            'department_name': self.department_name,
            'region_circle': self.region_circle,
            'district': self.district,
            'division': self.division,
            'chief_engineer': self.chief_engineer,
            'superintending_engineer': self.superintending_engineer,
            'executive_engineer': self.executive_engineer,
            'assistant_exec_engineer': self.assistant_exec_engineer,
            'assistant_engineer': self.assistant_engineer,
            'junior_engineer': self.junior_engineer,
            'official_routing_email': self.official_routing_email
        }


class SiteInspectionRecord(db.Model):
    __tablename__ = 'site_inspection_records'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    officer_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    officer_name = db.Column(db.String(120), default='')
    officer_designation = db.Column(db.String(50), default='Junior Engineer')
    inspection_date = db.Column(db.Date, nullable=False, default=date.today)
    stage_inspected = db.Column(db.String(150), default='')
    work_completed_percentage = db.Column(db.Float, default=0.0)
    measurements_recorded = db.Column(db.Text, default='')
    gps_latitude = db.Column(db.Float, nullable=True)
    gps_longitude = db.Column(db.Float, nullable=True)
    photos_json = db.Column(db.Text, default='[]')
    verification_status = db.Column(db.String(50), default='Pending EE Review')  # Pending Review, Certified by EE, Rejected
    reviewed_by = db.Column(db.String(120), default='')
    reviewed_at = db.Column(db.DateTime, nullable=True)
    review_remarks = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'project_code': self.project.project_code if self.project else None,
            'officer_id': self.officer_id,
            'officer_name': self.officer_name,
            'officer_designation': self.officer_designation,
            'inspection_date': self.inspection_date.isoformat() if self.inspection_date else None,
            'stage_inspected': self.stage_inspected,
            'work_completed_percentage': self.work_completed_percentage,
            'measurements_recorded': self.measurements_recorded,
            'gps_latitude': self.gps_latitude,
            'gps_longitude': self.gps_longitude,
            'photos_json': self.photos_json,
            'verification_status': self.verification_status,
            'reviewed_by': self.reviewed_by,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
            'review_remarks': self.review_remarks,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class PublicComplaint(db.Model):
    __tablename__ = 'public_complaints'

    id = db.Column(db.Integer, primary_key=True)
    complaint_code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='SET NULL'), nullable=True, index=True)
    contractor_id = db.Column(db.Integer, db.ForeignKey('contractors.id', ondelete='SET NULL'), nullable=True, index=True)
    location = db.Column(db.String(255), nullable=False)
    gps_lat = db.Column(db.Float, nullable=True)
    gps_lng = db.Column(db.Float, nullable=True)
    category = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    complainant_name = db.Column(db.String(120), default='Citizen')
    complainant_contact = db.Column(db.String(100), default='')
    evidence_file_path = db.Column(db.String(255), default='')
    status = db.Column(db.String(50), default='Submitted', index=True)  # Submitted, Received, Under Review, Site Inspection Required, Investigation, Action Required, Resolved, Rejected with Reason, Closed
    routed_department = db.Column(db.String(150), default='')
    assigned_officer = db.Column(db.String(150), default='')
    official_response = db.Column(db.Text, default='')
    inspection_finding_ref = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'complaint_code': self.complaint_code,
            'project_id': self.project_id,
            'project_name': self.project.project_name if self.project else 'General Public Infrastructure',
            'project_code': self.project.project_code if self.project else None,
            'contractor_id': self.contractor_id,
            'contractor_name': self.contractor.name if self.contractor else None,
            'location': self.location,
            'gps_lat': self.gps_lat,
            'gps_lng': self.gps_lng,
            'category': self.category,
            'description': self.description,
            'complainant_name': self.complainant_name,
            'complainant_contact': self.complainant_contact,
            'evidence_file_path': self.evidence_file_path,
            'status': self.status,
            'routed_department': self.routed_department,
            'assigned_officer': self.assigned_officer,
            'official_response': self.official_response,
            'inspection_finding_ref': self.inspection_finding_ref,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else None,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M') if self.updated_at else None,
            'resolved_at': self.resolved_at.strftime('%Y-%m-%d %H:%M') if self.resolved_at else None
        }


class DocumentEvidence(db.Model):
    __tablename__ = 'document_evidence'

    id = db.Column(db.Integer, primary_key=True)
    document_code = db.Column(db.String(64), unique=True, nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='SET NULL'), nullable=True, index=True)
    contractor_id = db.Column(db.Integer, db.ForeignKey('contractors.id', ondelete='SET NULL'), nullable=True, index=True)
    material_id = db.Column(db.Integer, db.ForeignKey('project_materials.id', ondelete='SET NULL'), nullable=True)
    doc_type = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size_bytes = db.Column(db.Integer, default=0)
    mime_type = db.Column(db.String(100), default='application/pdf')
    source_agency = db.Column(db.String(200), default='')
    document_version = db.Column(db.String(20), default='v1.0')
    verification_status = db.Column(db.String(50), default='Verified')
    tamper_hash = db.Column(db.String(64), default='')
    uploaded_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'document_code': self.document_code,
            'project_id': self.project_id,
            'contractor_id': self.contractor_id,
            'doc_type': self.doc_type,
            'title': self.title,
            'file_name': self.file_name,
            'file_path': self.file_path,
            'file_size_bytes': self.file_size_bytes,
            'mime_type': self.mime_type,
            'source_agency': self.source_agency,
            'document_version': self.document_version,
            'verification_status': self.verification_status,
            'tamper_hash': self.tamper_hash,
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None
        }


class DataSourceConfig(db.Model):
    __tablename__ = 'data_source_configs'

    id = db.Column(db.Integer, primary_key=True)
    source_name = db.Column(db.String(200), unique=True, nullable=False)
    department = db.Column(db.String(150), default='')
    source_type = db.Column(db.String(50), default='API')  # API, Data Feed, File, Webhook
    endpoint_url = db.Column(db.String(500), default='')
    auth_method = db.Column(db.String(50), default='None')  # None, API Key, Bearer Token, OAuth2
    encrypted_auth_secret = db.Column(db.String(255), default='')
    sync_method = db.Column(db.String(50), default='Polling')  # Webhook, Polling, Daily, File Check
    sync_frequency = db.Column(db.String(50), default='1 hour')  # 5m, 15m, 30m, 1 hour, Daily
    source_priority = db.Column(db.Integer, default=1)  # 1 = highest
    connection_status = db.Column(db.String(50), default='Connected')  # Connected, Temporarily Unavailable, Disabled, Error
    last_successful_sync = db.Column(db.DateTime, nullable=True)
    next_scheduled_sync = db.Column(db.DateTime, nullable=True)
    records_imported = db.Column(db.Integer, default=0)
    records_updated = db.Column(db.Integer, default=0)
    records_rejected = db.Column(db.Integer, default=0)
    last_error_message = db.Column(db.Text, default='')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sync_logs = db.relationship('DataSyncLog', backref='data_source_rel', cascade='all, delete-orphan', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'source_name': self.source_name,
            'department': self.department,
            'source_type': self.source_type,
            'endpoint_url': self.endpoint_url,
            'auth_method': self.auth_method,
            'sync_method': self.sync_method,
            'sync_frequency': self.sync_frequency,
            'source_priority': self.source_priority,
            'connection_status': self.connection_status,
            'last_successful_sync': self.last_successful_sync.strftime('%Y-%m-%d %H:%M') if self.last_successful_sync else 'Never',
            'next_scheduled_sync': self.next_scheduled_sync.strftime('%Y-%m-%d %H:%M') if self.next_scheduled_sync else 'Not Scheduled',
            'records_imported': self.records_imported,
            'records_updated': self.records_updated,
            'records_rejected': self.records_rejected,
            'last_error_message': self.last_error_message,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class DataSyncLog(db.Model):
    __tablename__ = 'data_sync_logs'

    id = db.Column(db.Integer, primary_key=True)
    sync_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    source_id = db.Column(db.Integer, db.ForeignKey('data_source_configs.id', ondelete='SET NULL'), nullable=True)
    source_name = db.Column(db.String(200), default='')
    trigger_type = db.Column(db.String(50), default='Scheduled')  # Scheduled, Webhook, Manual, File Ingestion
    request_time = db.Column(db.DateTime, default=datetime.utcnow)
    response_time_ms = db.Column(db.Integer, default=0)
    records_received = db.Column(db.Integer, default=0)
    records_inserted = db.Column(db.Integer, default=0)
    records_updated = db.Column(db.Integer, default=0)
    records_rejected = db.Column(db.Integer, default=0)
    validation_failures = db.Column(db.Integer, default=0)
    error_details = db.Column(db.Text, default='')
    status = db.Column(db.String(20), default='SUCCESS')  # SUCCESS, PARTIAL, FAILED
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'sync_id': self.sync_id,
            'source_id': self.source_id,
            'source_name': self.source_name,
            'trigger_type': self.trigger_type,
            'request_time': self.request_time.strftime('%Y-%m-%d %H:%M:%S') if self.request_time else None,
            'response_time_ms': self.response_time_ms,
            'records_received': self.records_received,
            'records_inserted': self.records_inserted,
            'records_updated': self.records_updated,
            'records_rejected': self.records_rejected,
            'validation_failures': self.validation_failures,
            'error_details': self.error_details,
            'status': self.status,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }


class DataVersionHistory(db.Model):
    __tablename__ = 'data_version_history'

    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(50), nullable=False, index=True)  # Project, Contractor, Material, Budget
    entity_id = db.Column(db.Integer, nullable=False, index=True)
    field_name = db.Column(db.String(100), nullable=False)
    previous_value = db.Column(db.Text, default='')
    new_value = db.Column(db.Text, default='')
    source_name = db.Column(db.String(200), default='')
    source_timestamp = db.Column(db.DateTime, nullable=True)
    sync_timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    verification_status = db.Column(db.String(50), default='Verified')
    changed_by = db.Column(db.String(100), default='Sync Engine')
    reason = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'field_name': self.field_name,
            'previous_value': self.previous_value,
            'new_value': self.new_value,
            'source_name': self.source_name,
            'source_timestamp': self.source_timestamp.strftime('%Y-%m-%d %H:%M') if self.source_timestamp else None,
            'sync_timestamp': self.sync_timestamp.strftime('%Y-%m-%d %H:%M') if self.sync_timestamp else None,
            'verification_status': self.verification_status,
            'changed_by': self.changed_by,
            'reason': self.reason,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }


class DataConflictRecord(db.Model):
    __tablename__ = 'data_conflict_records'

    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(50), nullable=False, index=True)
    entity_id = db.Column(db.Integer, nullable=False, index=True)
    field_name = db.Column(db.String(100), nullable=False)
    source_a_name = db.Column(db.String(200), nullable=False)
    source_a_value = db.Column(db.Text, nullable=False)
    source_a_timestamp = db.Column(db.DateTime, nullable=True)
    source_b_name = db.Column(db.String(200), nullable=False)
    source_b_value = db.Column(db.Text, nullable=False)
    source_b_timestamp = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(50), default='Unresolved', index=True)  # Unresolved, Resolved
    resolved_value = db.Column(db.Text, default='')
    resolved_by = db.Column(db.String(100), default='')
    resolved_at = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'field_name': self.field_name,
            'source_a_name': self.source_a_name,
            'source_a_value': self.source_a_value,
            'source_a_timestamp': self.source_a_timestamp.strftime('%Y-%m-%d %H:%M') if self.source_a_timestamp else None,
            'source_b_name': self.source_b_name,
            'source_b_value': self.source_b_value,
            'source_b_timestamp': self.source_b_timestamp.strftime('%Y-%m-%d %H:%M') if self.source_b_timestamp else None,
            'status': self.status,
            'resolved_value': self.resolved_value,
            'resolved_by': self.resolved_by,
            'resolved_at': self.resolved_at.strftime('%Y-%m-%d %H:%M') if self.resolved_at else None,
            'notes': self.notes,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else None
        }

