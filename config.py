import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

class Config:
    APP_NAME = 'Web-Based Integrated Project-Monitoring Platform'
    SECRET_KEY = os.environ.get('SECRET_KEY', 'projectpulse-ai-gov-intel-key-2026')
    
    # SQLite default, PostgreSQL ready (with Netlify serverless /tmp support)
    db_url = os.environ.get('DATABASE_URL') or os.environ.get('DATABASE_URI')
    if not db_url:
        if os.environ.get('AWS_LAMBDA_FUNCTION_NAME') or os.environ.get('NETLIFY'):
            import shutil
            import tempfile
            tmp_db = Path(tempfile.gettempdir()) / 'project_monitoring.db'
            seed_db = BASE_DIR / 'instance' / 'project_monitoring.db'
            if seed_db.exists() and not tmp_db.exists():
                try:
                    shutil.copy2(seed_db, tmp_db)
                except Exception:
                    pass
            db_file = tmp_db.resolve().as_posix()
            db_url = f"sqlite:///{db_file}"
        else:
            instance_path = BASE_DIR / 'instance'
            instance_path.mkdir(exist_ok=True)
            db_file = (instance_path / 'project_monitoring.db').resolve().as_posix()
            db_url = f"sqlite:///{db_file}"
    
    SQLALCHEMY_DATABASE_URI = db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Upload limits
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload
    UPLOAD_FOLDER = BASE_DIR / 'data' / 'uploads'
    
    # Demo and disclaimer flags
    DEMO_MODE = True
    DISCLAIMER = (
        "Predictions shown by this prototype are analytical estimates for "
        "decision support and are not official government forecasts."
    )
    DATASET_LABEL = "Representative Demo Dataset — Not official government data."
    
    # Optional LLM API Config
    AI_API_KEY = os.environ.get('AI_API_KEY', None)
    AI_API_ENDPOINT = os.environ.get('AI_API_ENDPOINT', None)
    AI_MODEL_NAME = os.environ.get('AI_MODEL_NAME', 'gemini-1.5-flash')

    # Email Service Configuration (Environment Driven)
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'localhost')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@projectpulse.gov.in')
    APP_BASE_URL = os.environ.get('APP_BASE_URL', 'http://127.0.0.1:5000')

    # Security & Cookie Configuration
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() in ['true', '1']
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() in ['true', '1']

    # CSRF & Rate Limiting Configuration
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None
    RATELIMIT_ENABLED = True
    RATELIMIT_DEFAULT = "200 per day; 60 per minute"
    RATELIMIT_STORAGE_URI = "memory://"
    RATELIMIT_STRATEGY = "fixed-window"
    RATELIMIT_HEADERS_ENABLED = True


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    SECRET_KEY = 'test-secret-key-for-unit-tests'

