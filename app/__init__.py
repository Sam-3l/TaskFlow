import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
from flask_login.login_manager import LoginManager
from config import DevelopmentConfig, DeploymentConfig
from flask_mail import Mail
from werkzeug.middleware.proxy_fix import ProxyFix

mail = Mail()
db = SQLAlchemy()
migrate = Migrate()
bcrypt = Bcrypt()
csrf = CSRFProtect()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    
    # Determine which config to use based on DEBUG setting
    if os.environ.get('DEBUG', 'True').lower() == 'true':
        app.config.from_object(DevelopmentConfig)
    else:
        app.config.from_object(DeploymentConfig)

    if not app.config['USE_S3']:
        # Ensure upload directories exist
        upload_dirs = [
            os.path.join(app.config['UPLOAD_FOLDER'], 'profile_img'),
            os.path.join(app.config['UPLOAD_FOLDER'], 'project_covers')
        ]
        
        # Create the base upload directory if it doesn't exist
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Create subdirectories
    for directory in upload_dirs:
        os.makedirs(directory, exist_ok=True)

    csrf.init_app(app)
    db.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)
    mail.init_app(app)
    login_manager.init_app(app)
    
    # Security headers via after_request
    @app.after_request
    def add_security_headers(response):
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
            "https://cdn.jsdelivr.net https://cdnjs.cloudflare.com "
            "https://code.jquery.com https://apis.google.com "
            "https://www.google.com https://www.gstatic.com; "
            "style-src 'self' 'unsafe-inline' "
            "https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "img-src 'self' data: blob: "
            "https://*.googleusercontent.com https://avatars.githubusercontent.com; "
            "font-src 'self' "
            "https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "connect-src 'self' "
            "https://accounts.google.com https://github.com; "
            "frame-src 'self' https://accounts.google.com; "
            "worker-src 'self' blob:; "
            "child-src 'self' blob:; "
            "media-src 'self' blob:"
        )
        
        response.headers['Content-Security-Policy'] = csp
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response
    
    # wsgi middleware for reverse proxy support
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    with app.app_context():
        from . import models
        from .auth.routes import auth
        from .main.routes import main

    app.register_blueprint(main)
    app.register_blueprint(auth, url_prefix="/auth")

    # Import OAuth after app creation to break circular dependency
    from app.utils.oauth import init_oauth
    init_oauth(app)

    @app.context_processor
    def override_url_for():
        from flask import url_for, current_app
        def s3_url_for(endpoint, **values):
            if endpoint == 'static' and current_app.config['USE_S3']:
                return current_app.config['STATIC_URL'] + values['filename']
            return url_for(endpoint, **values)
        return dict(url_for=s3_url_for)

    return app