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
            'approved_cost': self.approved_cost,
            'revised_cost': self.revised_cost,
            'expenditure': self.expenditure,
            'financial_progress': self.financial_progress,
            'cost_escalation': self.cost_escalation,
            'budget_utilization': self.budget_utilization,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'original_completion_date': self.original_completion_date.isoformat() if self.original_completion_date else None,
            'revised_completion_date': self.revised_completion_date.isoformat() if self.revised_completion_date else None,
            'predicted_completion_date': self.predicted_completion_date.isoformat() if self.predicted_completion_date else None,
            'delay_days': self.delay_days,
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
            'risk_level': self.risk_level
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

