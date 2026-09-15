"""
ProjectPulse AI — Role-Based Data Visibility & Information Minimization Service
Implements Least Privilege, Need-to-Know, and Default-Deny policies.
Ensures unauthorized or sensitive fields never leave the backend.
"""
import re
import html
from typing import Dict, List, Any, Optional, Set

# Data Classifications
DATA_CLASSIFICATIONS = {
    'PUBLIC': 'General non-sensitive directory and overview data',
    'PROJECT': 'Standard project monitoring and tracking metrics',
    'RESTRICTED': 'Operational telemetry, bottleneck indicators, risk model diagnostics',
    'CONFIDENTIAL': 'Administrative management, user identity governance, security logs',
    'SECRET': 'Cryptographic credentials, password hashes, verification/reset tokens (NEVER EXPOSED)'
}

# Strict Field Whitelists (Default-Deny: Any field not listed is automatically excluded)
FIELD_PERMISSIONS: Dict[str, Dict[str, List[str]]] = {
    'viewer': {
        'summary': [
            'id', 'project_code', 'project_name', 'ministry', 'sector', 'state',
            'physical_progress', 'risk_level', 'risk_score', 'project_status'
        ],
        'standard': [
            'id', 'project_code', 'project_name', 'ministry', 'sector', 'state',
            'location', 'approved_cost', 'revised_cost', 'expenditure',
            'physical_progress', 'planned_progress', 'milestones_total',
            'milestones_completed', 'cost_escalation', 'budget_utilization',
            'project_status', 'risk_level', 'risk_score', 'health_score',
            'reporting_date'
        ]
    },
    'officer': {
        'summary': [
            'id', 'project_code', 'project_name', 'ministry', 'department', 'sector',
            'state', 'location', 'physical_progress', 'planned_progress',
            'approved_cost', 'revised_cost', 'expenditure', 'delay_days',
            'risk_level', 'risk_score', 'health_score', 'project_status'
        ],
        'standard': [
            'id', 'project_code', 'project_name', 'ministry', 'department', 'sector',
            'state', 'location', 'implementing_agency', 'approved_cost', 'revised_cost',
            'expenditure', 'financial_progress', 'cost_escalation', 'budget_utilization',
            'start_date', 'original_completion_date', 'revised_completion_date',
            'predicted_completion_date', 'delay_days', 'physical_progress',
            'planned_progress', 'progress_gap', 'milestones_total',
            'milestones_completed', 'milestones_delayed', 'contractor_status',
            'land_acquisition_status', 'environmental_clearance_status',
            'utility_shifting_status', 'reporting_date', 'project_status',
            'latitude', 'longitude', 'risk_score', 'health_score',
            'delay_probability', 'cost_overrun_probability', 'risk_level'
        ]
    },
    'admin': {
        'summary': [
            'id', 'project_code', 'project_name', 'ministry', 'department', 'sector',
            'state', 'location', 'physical_progress', 'planned_progress',
            'approved_cost', 'revised_cost', 'expenditure', 'delay_days',
            'risk_level', 'risk_score', 'health_score', 'project_status'
        ],
        'standard': [
            'id', 'project_code', 'project_name', 'ministry', 'department', 'sector',
            'state', 'location', 'implementing_agency', 'approved_cost', 'revised_cost',
            'expenditure', 'financial_progress', 'cost_escalation', 'budget_utilization',
            'start_date', 'original_completion_date', 'revised_completion_date',
            'predicted_completion_date', 'delay_days', 'physical_progress',
            'planned_progress', 'progress_gap', 'milestones_total',
            'milestones_completed', 'milestones_delayed', 'contractor_status',
            'land_acquisition_status', 'environmental_clearance_status',
            'utility_shifting_status', 'reporting_date', 'project_status',
            'latitude', 'longitude', 'risk_score', 'health_score',
            'delay_probability', 'cost_overrun_probability', 'risk_level'
        ]
    }
}

# Absolute blacklist of fields that must NEVER be returned under ANY circumstances
ABSOLUTE_SECRET_FIELDS = {
    'password_hash',
    'verification_token',
    'verification_token_expires_at',
    'reset_token',
    'reset_token_expires_at',
    'failed_login_attempts',
    'locked_until',
    'last_resend_at',
    'resend_count',
    'smtp_password',
    'secret_key',
    'api_key'
}

def get_user_role(user: Any) -> str:
    """Safely extracts role from user object or string with viewer fallback."""
    if not user:
        return 'viewer'
    if isinstance(user, str):
        role = user.lower()
    elif hasattr(user, 'role'):
        role = str(user.role).lower()
    else:
        role = 'viewer'
    if role not in FIELD_PERMISSIONS:
        return 'viewer'
    return role

def get_visible_project_fields(role: str, detail_level: str = 'standard') -> List[str]:
    """Returns the whitelisted project fields for a given role and detail level."""
    role_key = role.lower() if role else 'viewer'
    if role_key not in FIELD_PERMISSIONS:
        role_key = 'viewer'
    level_key = detail_level if detail_level in ['summary', 'standard'] else 'standard'
    return list(FIELD_PERMISSIONS[role_key][level_key])

def filter_project_fields_by_role(data: Dict[str, Any], role: str, detail_level: str = 'standard') -> Dict[str, Any]:
    """
    Applies strict default-deny filtering to a project dictionary based on role.
    Only fields explicitly present in the whitelist are retained.
    """
    allowed_fields = set(get_visible_project_fields(role, detail_level))
    filtered = {}
    for field in allowed_fields:
        if field in data:
            filtered[field] = data[field]
    return filtered

def serialize_project_for_user(project: Any, user: Any, detail_level: str = 'standard') -> Dict[str, Any]:
    """
    Serializes a Project model instance strictly filtered for the requesting user's role.
    Guarantees no internal or unauthorized fields leave the backend.
    """
    if project is None:
        return {}
        
    role = get_user_role(user)
    raw_dict = project.to_dict() if hasattr(project, 'to_dict') else dict(project)
    
    # Strip any accidental secrets
    for secret in ABSOLUTE_SECRET_FIELDS:
        raw_dict.pop(secret, None)
        
    return filter_project_fields_by_role(raw_dict, role, detail_level)

def serialize_user_for_user(target_user: Any, requesting_user: Any) -> Optional[Dict[str, Any]]:
    """
    Serializes a User instance.
    - Non-admins can only view their own account profile.
    - Admins can view other users.
    - In ALL cases, password hashes, reset tokens, verification tokens, and lock timestamps are NEVER sent.
    """
    if target_user is None:
        return None
        
    req_role = get_user_role(requesting_user)
    req_id = getattr(requesting_user, 'id', None)
    target_id = getattr(target_user, 'id', None)
    
    # Access check: user viewing self OR administrator viewing any user
    if req_role != 'admin' and req_id != target_id:
        return None

    # Safe whitelist of allowed user profile fields
    return {
        'id': target_user.id,
        'username': target_user.username,
        'email': target_user.email,
        'role': target_user.role,
        'full_name': target_user.full_name or '',
        'organization': target_user.organization or '',
        'department': target_user.department or '',
        'email_verified': bool(target_user.email_verified),
        'status': target_user.status,
        'created_at': target_user.created_at.isoformat() if target_user.created_at else None
    }

def serialize_alert_for_user(alert: Any, user: Any) -> Dict[str, Any]:
    """
    Serializes an Alert model instance according to user role.
    - Viewers receive public alert telemetry (title, description, status, severity, project code/name).
    - Viewers NEVER receive internal resolution notes, officer private notes, or internal triggers.
    - Officers and Admins receive full triage metadata.
    """
    if alert is None:
        return {}
        
    role = get_user_role(user)
    base = {
        'id': alert.id,
        'project_id': alert.project_id,
        'project_name': alert.project.project_name if alert.project else 'N/A',
        'project_code': alert.project.project_code if alert.project else 'N/A',
        'severity': alert.severity,
        'title': alert.title,
        'description': alert.description,
        'probability': alert.probability,
        'status': alert.status,
        'created_at': alert.created_at.strftime('%Y-%m-%d %H:%M') if alert.created_at else None
    }
    
    # Officer and Admin receive internal notes, resolution attribution, and trigger context
    if role in ['officer', 'admin']:
        base['trigger'] = alert.trigger or ''
        base['contributing_factors'] = alert.contributing_factors or ''
        base['recommendation'] = alert.recommendation or ''
        base['resolved_at'] = alert.resolved_at.strftime('%Y-%m-%d %H:%M') if alert.resolved_at else None
        base['resolved_by'] = alert.resolved_by or ''
        base['notes'] = alert.notes or ''
        
    return base

def serialize_audit_log_for_user(log: Any, user: Any) -> Optional[Dict[str, Any]]:
    """
    Serializes a SecurityAuditLog entry.
    - Strictly restricted to Administrators. Non-admins receive None.
    - Sanitizes details to ensure no tokens or secrets leak.
    """
    if log is None:
        return None
        
    role = get_user_role(user)
    if role != 'admin':
        return None
        
    clean_details = str(log.details or '')
    for keyword in ['password', 'secret', 'token', 'key', 'hash']:
        clean_details = re.sub(rf'({keyword}[^,\s:]*[:=]\s*)[^\s,]+', r'\1[REDACTED]', clean_details, flags=re.IGNORECASE)
        
    return {
        'id': log.id,
        'user_id': log.user_id,
        'username': log.username or (log.user.username if log.user else 'Anonymous'),
        'action': log.action,
        'resource_type': log.resource_type,
        'resource_id': log.resource_id,
        'details': clean_details,
        'ip_address': log.ip_address,
        'user_agent': log.user_agent,
        'status': log.status,
        'created_at': log.created_at.strftime('%Y-%m-%d %H:%M:%S') if log.created_at else None
    }

def sanitize_html_output(text: str) -> str:
    """Escapes executable HTML/script content to prevent XSS."""
    if not text:
        return ""
    clean = html.escape(str(text))
    return clean
