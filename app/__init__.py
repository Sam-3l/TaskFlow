from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
from flask_login.login_manager import LoginManager
import os
from config import DevelopmentConfig, DeploymentConfig

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
    login_manager.init_app(app)

    with app.app_context():
        from . import models
        from .auth.routes import auth
        from .main.routes import main

    app.register_blueprint(main)
    app.register_blueprint(auth, url_prefix="/auth")

    return app
