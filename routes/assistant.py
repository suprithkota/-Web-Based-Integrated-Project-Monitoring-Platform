import re
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from extensions import limiter
from services.assistant_service import assistant_service
from services.audit_service import log_security_event

assistant_bp = Blueprint('assistant', __name__)

PROBING_PATTERN = re.compile(
    r'\b(password|secret|hash|token|api[_\s-]?key|database|credential|\.env|master_key|private_key|system_prompt)\b',
    re.IGNORECASE
)

ADMIN_PROBING_PATTERN = re.compile(
    r'\b(admin(istrator)? (information|data|details|accounts?)|user accounts?|user passwords?|audit logs?|system settings?)\b',
    re.IGNORECASE
)

BULK_DUMP_PATTERN = re.compile(
    r'\b(everything in the database|dump (the )?database|give me all (the )?data|export all records|all tables)\b',
    re.IGNORECASE
)

@assistant_bp.route('/assistant')
@login_required
def index():
    sample_prompts = [
        "Which projects have the highest delay risk?",
        "Which ministry has the most critical projects?",
        "How many projects are currently critical?",
        "Which projects have cost escalation above 20%?",
        "Show projects with low physical progress but high expenditure.",
        "Which sector has the highest average risk?",
        "Why is PRJ-0003 high risk?"
    ]
    return render_template('assistant.html', sample_prompts=sample_prompts)

@assistant_bp.route('/api/assistant', methods=['POST'])
@login_required
@limiter.limit("20 per minute")
def api_chat():
    data = request.get_json(silent=True) or {}
    user_query = str(data.get('query', '')).strip()
    
    if not user_query:
        return jsonify({
            'status': 'error',
            'message': 'Please provide a valid question or search query.'
        }), 400

    if len(user_query) > 500:
        return jsonify({
            'status': 'error',
            'message': 'Query exceeds maximum permissible length of 500 characters.'
        }), 400

    # Guardrail 1: Prohibit bulk extraction of raw database records (Requirement 19)
    if BULK_DUMP_PATTERN.search(user_query):
        return jsonify({
            'status': 'success',
            'query': user_query,
            'response': "### Information Minimization Notice\n\nI can provide structured analytical summaries and project monitoring insights available to your account, but bulk extraction of raw database records is restricted by data minimization policies."
        })

    # Guardrail 2: Prohibit unauthorized administrative inquiries (Requirement 18)
    if ADMIN_PROBING_PATTERN.search(user_query):
        return jsonify({
            'status': 'success',
            'query': user_query,
            'response': "### Access Restricted\n\nUnder Role-Based Access Control and data minimization governance, user account management, administrative audit trails, and system security configurations are confidential and not accessible via the AI Assistant."
        })

    # Guardrail 3: Prevent credential/secret probing via Assistant
    if PROBING_PATTERN.search(user_query):
        log_security_event(
            'ASSISTANT_SECURITY_PROBE',
            user_id=current_user.id if current_user.is_authenticated else None,
            username=current_user.username if current_user.is_authenticated else 'unknown',
            resource_type='assistant',
            details=f"Sensitive term queried: {user_query[:80]}",
            status='WARNING'
        )
        return jsonify({
            'status': 'success',
            'query': user_query,
            'response': "### Security Policy Notice\n\nSystem configurations, user credentials, authentication tokens, cryptographic keys, and database credentials are confidential and protected by ProjectPulse AI security policies. This assistant only provides analytics for authorized infrastructure monitoring data."
        })
        
    authorized_ids = current_user.get_authorized_project_ids() if hasattr(current_user, 'get_authorized_project_ids') else None
    answer = assistant_service.process_query(user_query, authorized_project_ids=authorized_ids)
    
    return jsonify({
        'status': 'success',
        'query': user_query,
        'response': answer
    })

