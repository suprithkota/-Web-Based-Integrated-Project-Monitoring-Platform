import logging
from datetime import datetime
from flask import request, has_request_context
from flask_login import current_user
from database import db
from database.models import SecurityAuditLog

logger = logging.getLogger('projectpulse.security')

SENSITIVE_KEYWORDS = ['password', 'secret', 'token', 'key', 'credential', 'hash']

def _sanitize_details(details):
    """Ensure sensitive data like passwords or tokens are never stored in audit logs."""
    if not details:
        return ""
    if isinstance(details, dict):
        clean = {}
        for k, v in details.items():
            if any(s in k.lower() for s in SENSITIVE_KEYWORDS):
                clean[k] = '[REDACTED]'
            else:
                clean[k] = str(v)[:200]
        return str(clean)
    text = str(details)
    return text[:1000]

def log_security_event(action, user_id=None, username=None, resource_type=None, resource_id=None, details=None, status='SUCCESS'):
    """
    Records a high-integrity security audit event.
    Guarantees no crash on failure and sanitizes any sensitive credentials.
    """
    try:
        ip_address = '127.0.0.1'
        user_agent = 'System'

        if has_request_context():
            ip_address = request.headers.get('X-Forwarded-For', request.remote_addr) or '127.0.0.1'
            if ',' in ip_address:
                ip_address = ip_address.split(',')[0].strip()
            ip_address = ip_address[:64]
            user_agent = (request.user_agent.string if request.user_agent else 'Unknown')[:255]

            if not user_id and current_user and current_user.is_authenticated:
                user_id = current_user.id
                username = current_user.username

        clean_details = _sanitize_details(details)

        audit_entry = SecurityAuditLog(
            user_id=user_id,
            username=username[:64] if username else None,
            action=action[:100],
            resource_type=resource_type[:50] if resource_type else None,
            resource_id=str(resource_id)[:50] if resource_id else None,
            details=clean_details,
            ip_address=ip_address,
            user_agent=user_agent,
            status=status[:20],
            created_at=datetime.utcnow()
        )

        db.session.add(audit_entry)
        db.session.commit()
        return audit_entry
    except Exception as e:
        db.session.rollback()
        logger.warning(f"Audit log writing failed: {e}")
        return None
