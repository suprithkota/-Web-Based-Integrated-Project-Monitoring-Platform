import os
from flask import Flask, render_template, request, jsonify, abort, flash, redirect, url_for
from flask_login import LoginManager
from flask_wtf.csrf import CSRFError
from config import Config
from database import db
from database.models import User, Alert
from extensions import csrf, limiter

login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = "Please sign in with your credentials to access the intelligence platform."
login_manager.login_message_category = "info"

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@login_manager.unauthorized_handler
def unauthorized():
    if request.path.startswith('/api/') or request.is_json:
        return jsonify({'status': 'error', 'message': 'Authentication required. Please sign in.', 'code': 401}), 401
    flash("Please sign in with your credentials to access the intelligence platform.", "info")
    return redirect(url_for('auth.login', next=request.url))

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    if app.config.get('TESTING') and not getattr(config_class, 'ENABLE_TEST_RATELIMIT', False):
        app.config['RATELIMIT_ENABLED'] = False
    limiter.init_app(app)

    # Register Blueprints
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.projects import projects_bp
    from routes.alerts import alerts_bp
    from routes.analytics import analytics_bp
    from routes.simulator import simulator_bp
    from routes.assistant import assistant_bp
    from routes.map_view import map_bp
    from routes.data_import import data_import_bp
    from routes.ml_analytics import ml_analytics_bp
    from routes.contractors import contractors_bp
    from routes.engineering import engineering_bp
    from routes.data_sync import data_sync_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(alerts_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(simulator_bp)
    app.register_blueprint(assistant_bp)
    app.register_blueprint(map_bp)
    app.register_blueprint(data_import_bp)
    app.register_blueprint(ml_analytics_bp)
    app.register_blueprint(contractors_bp)
    app.register_blueprint(engineering_bp)
    app.register_blueprint(data_sync_bp)

    # Start background synchronization daemon (disabled in testing mode or serverless)
    if not app.config.get('TESTING') and not os.environ.get('AWS_LAMBDA_FUNCTION_NAME') and not os.environ.get('NETLIFY'):
        try:
            from services.sync_service import SyncService
            SyncService.start_background_scheduler(app)
        except Exception:
            pass

    # Request Lifecycle Hooks for Security
    @app.before_request
    def block_sensitive_files():
        path = request.path.lower()
        blocked_patterns = ['.db', '.sqlite', '.sqlite3', '.env', '.bak', '.git', '.key', '.log']
        for pat in blocked_patterns:
            if pat in path:
                abort(404)

    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://unpkg.com https://fonts.googleapis.com; "
            "font-src 'self' https://cdnjs.cloudflare.com https://fonts.gstatic.com data:; "
            "img-src 'self' data: https://*.tile.openstreetmap.org https://unpkg.com; "
            "connect-src 'self'; "
            "frame-ancestors 'self';"
        )
        response.headers['Content-Security-Policy'] = csp
        return response

    # Context Processors & Filters
    @app.context_processor
    def inject_global_vars():
        alert_count = 0
        conflict_count = 0
        try:
            alert_count = Alert.query.filter(Alert.status.in_(['Open', 'Under Review'])).count()
        except Exception:
            alert_count = 0

        try:
            from database.models import DataConflictRecord
            conflict_count = DataConflictRecord.query.filter_by(status='Unresolved').count()
        except Exception:
            conflict_count = 0
            
        from services.rbac_service import has_permission
        return {
            'APP_NAME': app.config.get('APP_NAME', 'Web-Based Integrated Project-Monitoring Platform'),
            'DEMO_MODE': app.config.get('DEMO_MODE', True),
            'DISCLAIMER': app.config.get('DISCLAIMER', ''),
            'DATASET_LABEL': app.config.get('DATASET_LABEL', ''),
            'OPEN_ALERTS_COUNT': alert_count,
            'UNRESOLVED_CONFLICTS_COUNT': conflict_count,
            'has_permission': has_permission
        }

    @app.route('/data/inspection_photos/<filename>')
    def serve_inspection_photo(filename):
        from flask import send_from_directory
        return send_from_directory(os.path.join(app.root_path, 'data', 'inspection_photos'), filename)

    @app.route('/data/documents/<filename>')
    def serve_document(filename):
        from flask import send_from_directory
        return send_from_directory(os.path.join(app.root_path, 'data', 'documents'), filename)

    @app.template_filter('inr')
    def format_inr(val):
        if val is None:
            return '₹0.00 Cr'
        try:
            f = float(val)
            return f"₹{f:,.2f} Cr"
        except (ValueError, TypeError):
            return str(val)

    @app.template_filter('pct')
    def format_pct(val):
        if val is None:
            return '0.0%'
        try:
            f = float(val)
            return f"{f:.1f}%"
        except (ValueError, TypeError):
            return str(val)

    # Error Handlers
    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        if request.path.startswith('/api/') or request.is_json:
            return jsonify({'status': 'error', 'message': f'CSRF token missing or invalid: {error.description}'}), 400
        return render_template('400.html', error_title="CSRF Security Validation Failed", error_message="Your security session token has expired or is invalid. Please refresh the page and try again."), 400

    @app.errorhandler(400)
    def bad_request_error(error):
        if request.path.startswith('/api/') or request.is_json:
            return jsonify({'status': 'error', 'message': 'Bad request. Parameters could not be validated.'}), 400
        return render_template('400.html', error_title="Invalid Request", error_message="The request could not be processed due to invalid parameters."), 400

    @app.errorhandler(403)
    def forbidden_error(error):
        if request.path.startswith('/api/') or request.is_json:
            return jsonify({'status': 'error', 'message': 'Forbidden. You do not have permission to access this resource.'}), 403
        return render_template('403.html'), 403

    @app.errorhandler(404)
    def not_found_error(error):
        if request.path.startswith('/api/') or request.is_json:
            return jsonify({'status': 'error', 'message': 'Resource not found.'}), 404
        return render_template('404.html'), 404

    @app.errorhandler(429)
    def ratelimit_handler(error):
        if request.path.startswith('/api/') or request.is_json:
            return jsonify({'status': 'error', 'message': f'Rate limit exceeded. {error.description}'}), 429
        return render_template('429.html', error_message=f"Rate limit exceeded: {error.description}. Please wait before making more requests."), 429

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        if request.path.startswith('/api/') or request.is_json:
            return jsonify({'status': 'error', 'message': 'An internal server error occurred.'}), 500
        return render_template('500.html'), 500

    return app

app = create_app()

if __name__ == '__main__':
    from run import main
    main()

