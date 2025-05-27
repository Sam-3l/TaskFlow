from flask import current_app, render_template
from flask_mail import Message
from app import mail
from threading import Thread

def send_async_email(app, msg):
    with app.app_context():
        mail.send(msg)

def send_email(subject, recipients, template, **kwargs):
    msg = Message(
        subject,
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[recipients] if isinstance(recipients, str) else recipients
    )
    msg.html = render_template(template, **kwargs)
    
    # Send email asynchronously
    Thread(target=send_async_email, args=(current_app._get_current_object(), msg)).start()

def send_verification_email(user):
    token = user.generate_verification_token()
    send_email(
        "Verify Your TaskFlow Account",
        user.email,
        "emails/verify_email.html",
        user=user,
        token=token
    )

def send_password_reset_email(user):
    token = user.generate_password_reset_token()
    send_email(
        "Reset Your TaskFlow Password",
        user.email,
        "emails/reset_password.html",
        user=user,
        token=token
    )