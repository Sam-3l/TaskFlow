from flask import current_app, redirect, url_for, session
from authlib.integrations.flask_client import OAuth
from app.models import User, db
from app import bcrypt
import secrets
import string

oauth = OAuth()

def init_oauth(app):
    oauth.init_app(app)
    
    # Google OAuth
    oauth.register(
        name='google',
        client_id=app.config['GOOGLE_CLIENT_ID'],
        client_secret=app.config['GOOGLE_CLIENT_SECRET'],
        access_token_url='https://accounts.google.com/o/oauth2/token',
        access_token_params=None,
        authorize_url='https://accounts.google.com/o/oauth2/auth',
        authorize_params=None,
        api_base_url='https://www.googleapis.com/oauth2/v1/',
        client_kwargs={
            'scope': 'openid email profile',
            'token_endpoint_auth_method': 'client_secret_post'
        },
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration'
    )
    
    # GitHub OAuth
    oauth.register(
        name='github',
        client_id=app.config['GITHUB_CLIENT_ID'],
        client_secret=app.config['GITHUB_CLIENT_SECRET'],
        access_token_url='https://github.com/login/oauth/access_token',
        access_token_params=None,
        authorize_url='https://github.com/login/oauth/authorize',
        authorize_params=None,
        api_base_url='https://api.github.com/',
        client_kwargs={'scope': 'user:email'},
    )

def generate_random_password(length=12):
    """Generate a random password for OAuth users"""
    chars = string.ascii_letters + string.digits + string.punctuation
    return ''.join(secrets.choice(chars) for _ in range(length))

def handle_oauth_callback(provider):
    try:
        token = oauth.create_client(provider).authorize_access_token()
        if not token:
            return None, "Failed to fetch access token."
            
        if provider == 'google':
            user_info = oauth.google.parse_id_token(
                token,
                claims_options={
                    'iss': {'essential': True, 'values': ['https://accounts.google.com']},
                    'aud': {'essential': True, 'value': current_app.config['GOOGLE_CLIENT_ID']}
                }
            )
            email = user_info.get('email')
            first_name = user_info.get('given_name', '')
            last_name = user_info.get('family_name', '')
            username = email.split('@')[0]
            picture = user_info.get('picture')
            
        elif provider == 'github':
            user_info = oauth.github.get('user').json()
            emails = oauth.github.get('user/emails').json()
            
            # Find primary email
            email = next((e['email'] for e in emails if e['primary']), None)
            if not email:
                return None, "No primary email found for GitHub account."
                
            name_parts = user_info.get('name', '').split(' ')
            first_name = name_parts[0] if name_parts else ''
            last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
            username = user_info.get('login')
            picture = user_info.get('avatar_url')
            
        else:
            return None, "Invalid OAuth provider."
            
        # Check if user already exists
        user = User.query.filter_by(email=email).first()
        
        if not user:
            # Create new user
            random_password = generate_random_password()
            
            user = User(
                fname=first_name,
                lname=last_name,
                username=username or email.split('@')[0],
                email=email,
                password=bcrypt.generate_password_hash(random_password).decode('utf-8'),
                email_verified=True,
                profile_img=picture or f"default_custom.jpg",
                gender='custom'
            )
            
            db.session.add(user)
            db.session.commit()
            
        return user, None
        
    except Exception as e:
        current_app.logger.error(f"OAuth {provider} error: {str(e)}")
        return None, str(e)