from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
from flask_login.login_manager import LoginManager

db = SQLAlchemy()
migrate = Migrate()
bcrypt = Bcrypt()
csrf = CSRFProtect()
login_manager = LoginManager()

def create_app() -> Flask:
    app = Flask(__name__)

    app.config.from_object('config.DevelopmentConfig')
    
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
