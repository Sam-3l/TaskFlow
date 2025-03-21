import os
from datetime import timedelta
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or 'default_secret_key'
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or 'sqlite:///site.db'
    SQLALCHEMY_TRACK_MODIFIACTIONS = False
    WTF_CSRF_ENABLED = True
    REMEMBER_COOKIE_DURATION = timedelta(days=4)

class DevelopmentConfig(Config):
    DEBUG = os.getenv('DEBUG', default=False)
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///test.db'

class DeploymentConfig(Config):
    pass