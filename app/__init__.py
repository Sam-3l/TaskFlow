import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
from flask_login.login_manager import LoginManager
from config import DevelopmentConfig, DeploymentConfig
from flask_mail import Mail
from app.utils.oauth import init_oauth
from werkzeug.middleware.proxy_fix import ProxyFix

mail = Mail()
db = SQLAlchemy()
migrate = Migrate()
bcrypt = Bcrypt()
csrf = CSRFProtect()
login_manager = LoginManager()

class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        def custom_start_response(status, headers, exc_info=None):
            # Add security headers
            headers.extend([
                ('X-Content-Type-Options', 'nosniff'),
                ('X-Frame-Options', 'SAMEORIGIN'),
                ('X-XSS-Protection', '1; mode=block'),
                ('Referrer-Policy', 'strict-origin-when-cross-origin'),
                ('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline' https://apis.google.com https://www.google.com https://www.gstatic.com; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://*.googleusercontent.com https://avatars.githubusercontent.com; connect-src 'self' https://accounts.google.com https://github.com; frame-src 'self' https://accounts.google.com")
            ])
            return start_response(status, headers, exc_info)
        
        return self.app(environ, custom_start_response)

def create_app():
    app = Flask(__name__)
    
    # Determine which config to use based on DEBUG setting
    if os.environ.get('DEBUG', 'True').lower() == 'true':
        app.config.from_object(DevelopmentConfig)
    else:
        app.config.from_object(DeploymentConfig)

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
    init_oauth(app)

    # Add middleware
    app.wsgi_app = SecurityHeadersMiddleware(app)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    with app.app_context():
        from . import models
        from .auth.routes import auth
        from .main.routes import main

    app.register_blueprint(main)
    app.register_blueprint(auth, url_prefix="/auth")

    return app