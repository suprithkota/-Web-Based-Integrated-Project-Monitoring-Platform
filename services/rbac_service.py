from functools import wraps
from flask import request, jsonify, render_template, redirect, url_for, flash, abort
from flask_login import current_user
from database.models import Project, ProjectAssignment
from services.audit_service import log_security_event

ROLE_ALIASES = {
    'admin': 'admin',
    'administrator': 'admin',
    'officer': 'officer',
    'monitoring officer': 'officer',
    'monitoring_officer': 'officer',
    'viewer': 'viewer',
    'observer': 'viewer'
}

def normalize_role(role_name):
    if not role_name:
        return ''
    clean = str(role_name).strip().lower()
    return ROLE_ALIASES.get(clean, clean)

# Central RBAC Permissions Matrix
PERMISSIONS = {
    # Viewer, Officer, Admin permissions
    'VIEW_PROJECTS': {'viewer', 'officer', 'admin'},
    'VIEW_ANALYTICS': {'viewer', 'officer', 'admin'},
    'VIEW_MAP': {'viewer', 'officer', 'admin'},
    'VIEW_ALERTS': {'viewer', 'officer', 'admin'},
    'ASK_AI': {'viewer', 'officer', 'admin'},
    'REPORT_ISSUE': {'viewer', 'officer', 'admin'},
    'TRACK_COMPLAINT': {'viewer', 'officer', 'admin'},
    
    # Officer & Admin permissions
    'VIEW_VERIFICATION': {'officer', 'admin'},
    'LOG_INSPECTION': {'officer', 'admin'},
    'RECORD_LAB_TEST': {'officer', 'admin'},
    'VIEW_CONTRACTORS': {'officer', 'admin'},
    'TRIAGE_COMPLAINT': {'officer', 'admin'},
    'EDIT_ASSIGNED_PROJECT': {'officer', 'admin'},
    'CREATE_PROJECT': {'officer', 'admin'},
    'SIMULATE_SCENARIO': {'officer', 'admin'},
    'VIEW_OFFICER_WORKSPACE': {'officer', 'admin'},
    'VIEW_RISK_INTELLIGENCE': {'officer', 'admin'},
    'RESOLVE_CONFLICTS': {'officer', 'admin'},
    
    # Admin only permissions
    'MANAGE_USERS': {'admin'},
    'MANAGE_ORGANIZATIONS': {'admin'},
    'MANAGE_SYSTEM_SETTINGS': {'admin'},
    'VIEW_AUDIT_LOGS': {'admin'},
    'DELETE_PROJECT': {'admin'},
    'CONFIGURE_DATA_SOURCES': {'admin'},
    'INGEST_DATA': {'admin'},
}

def has_permission(permission, user=None):
    """
    Checks if a user has a specific fine-grained permission.
    Defaults to current_user if user is not supplied.
    """
    if user is None:
        user = current_user
    if not getattr(user, 'is_authenticated', False):
        return False
    user_role = normalize_role(getattr(user, 'role', ''))
    allowed = PERMISSIONS.get(permission, set())
    return user_role in allowed

def permission_required(permission):
    """
    Decorator enforcing that the current user possesses the required permission.
    """
    allowed_roles = PERMISSIONS.get(permission, set())
    return role_required(*allowed_roles)

def role_required(*allowed_roles):
    """
    Enforces that the current authenticated user has one of the specified roles.
    Returns HTTP 401 if unauthenticated, and HTTP 403 if unauthorized.
    Supports both JSON API endpoints and HTML browser routes.
    """
    normalized_allowed = {normalize_role(r) for r in allowed_roles}

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 1. Authentication Check
            if not current_user.is_authenticated:
                if request.path.startswith('/api/') or request.is_json:
                    return jsonify({
                        'status': 'error',
                        'message': 'Authentication required. Please sign in.',
                        'code': 401
                    }), 401
                flash("Please sign in to access this resource.", "warning")
                return redirect(url_for('auth.login', next=request.url))

            # 2. Account Status Check
            if hasattr(current_user, 'is_active_account') and not current_user.is_active_account:
                if request.path.startswith('/api/') or request.is_json:
                    return jsonify({
                        'status': 'error',
                        'message': 'Account is inactive, pending verification, or locked.',
                        'code': 403
                    }), 403
                return render_template('403.html', message="Your account is not active or is pending approval."), 403

            # 3. Role Authorization Check
            user_role = normalize_role(getattr(current_user, 'role', ''))
            if user_role not in normalized_allowed:
                log_security_event(
                    'UNAUTHORIZED_ROLE_ACCESS',
                    user_id=current_user.id,
                    username=current_user.username,
                    resource_type='route',
                    resource_id=request.path,
                    details=f"User with role '{current_user.role}' attempted to access endpoint restricted to {list(allowed_roles)}",
                    status='WARNING'
                )
                if request.path.startswith('/api/') or request.is_json:
                    return jsonify({
                        'status': 'error',
                        'message': 'Forbidden: Insufficient role permissions.',
                        'code': 403
                    }), 403
                return render_template('403.html', message="Access Denied: Your account role does not have permission to access this resource."), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator

def project_access_required(write=False):
    """
    Enforces fine-grained object-level authorization on project resources.
    - Admin: Universal read and write access.
    - Viewer: Read-only access to all projects; write is strictly prohibited (HTTP 403).
    - Officer: Access is granted ONLY for projects explicitly assigned to this officer.
               Unassigned projects return HTTP 403.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 1. Authentication Check
            if not current_user.is_authenticated:
                if request.path.startswith('/api/') or request.is_json:
                    return jsonify({'status': 'error', 'message': 'Authentication required.', 'code': 401}), 401
                return redirect(url_for('auth.login', next=request.url))

            # 2. Extract Project ID from kwargs, query params, form, or JSON body
            project_id = kwargs.get('project_id') or kwargs.get('id') or kwargs.get('pk')
            if project_id is None:
                project_id = request.args.get('project_id')
            if project_id is None and request.is_json:
                data = request.get_json(silent=True) or {}
                project_id = data.get('project_id') or data.get('id')
            if project_id is None and request.form:
                project_id = request.form.get('project_id')

            if project_id is not None:
                try:
                    pid = int(project_id)
                except (ValueError, TypeError):
                    if request.path.startswith('/api/') or request.is_json:
                        return jsonify({'status': 'error', 'message': 'Invalid project ID.', 'code': 400}), 400
                    return render_template('404.html'), 404

                # Check object-level authorization via User model helper
                if not current_user.can_access_project(pid, write=write):
                    action_type = "modify" if write else "view"
                    log_security_event(
                        'OBJECT_ACCESS_DENIED',
                        user_id=current_user.id,
                        username=current_user.username,
                        resource_type='project',
                        resource_id=str(pid),
                        details=f"User '{current_user.username}' ({current_user.role}) denied {action_type} access to Project #{pid}",
                        status='WARNING'
                    )
                    if request.path.startswith('/api/') or request.is_json:
                        return jsonify({
                            'status': 'error',
                            'message': f"Forbidden: You do not have object-level permission to {action_type} Project #{pid}.",
                            'code': 403
                        }), 403
                    return render_template('403.html', message=f"Access Denied: You are not authorized to {action_type} Project #{pid}."), 403

            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Common aliases for clean route annotation
admin_required = role_required('admin')
officer_required = role_required('admin', 'officer')
viewer_allowed = role_required('admin', 'officer', 'viewer')

def get_scoped_projects_query(user):
    """
    Returns an SQLAlchemy query for projects scoped to the user's role:
    - Admin: All projects.
    - Viewer: All projects (read-only).
    - Officer: Only explicitly assigned projects.
    """
    if not user.is_authenticated:
        return Project.query.filter(Project.id == -1)

    if user.is_admin or user.role == 'viewer':
        return Project.query

    if user.role == 'officer':
        assigned_ids = user.get_authorized_project_ids()
        if assigned_ids:
            return Project.query.filter(Project.id.in_(assigned_ids))
        else:
            return Project.query.filter(Project.id == -1)

    return Project.query.filter(Project.id == -1)
