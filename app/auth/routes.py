from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, login_user, logout_user, current_user

from app import login_manager, db
from app.utils.email import send_verification_email, send_password_reset_email
from app.models import User

auth = Blueprint("auth", __name__)

@login_manager.user_loader
def user_loader(user_id):
    from app.models import User
    return User.query.get(int(user_id))

login_manager.login_view = "auth.login"

@auth.route("/signup", methods=["GET", "POST"])
def signup():
    from app.forms import SignupForm
    from app.models import User
    from app import db, bcrypt

    form = SignupForm()
    if form.validate_on_submit():
        data = form.data
        data.pop("c_pass", None)
        data.pop("check", None)
        data.pop("submit", None)
        data.pop("csrf_token", None)
        data["password"] = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        
        # data storage
        data.setdefault("gender", None)
        data.setdefault("address", None)
        data.setdefault("dob", None)
        data.setdefault("phone", None)
        data.setdefault("city", None)
        data.setdefault("state", None)
        data.setdefault("zip", None)
        
        new_user = User(**data)
        db.session.add(new_user)
        db.session.commit()

        # Send verification email
        send_verification_email(new_user)
        
        flash("A verification email has been sent to your email address. Please verify your email to login.", "info")
        return redirect(url_for("auth.login"))

    return render_template('signup.html', form=form)

@auth.route("/login", methods=["GET", "POST"])
def login():
    from app.forms import LoginForm
    from app.models import User
    from app import bcrypt

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.uname_or_email.data).first() or \
               User.query.filter_by(email=form.uname_or_email.data).first()
        
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            if not user.email_verified:
                flash(f"Please verify {user.email} to login. <a href='{url_for('auth.resend_verification', email=user.email)}'>Resend link</a>", "warning")
                return redirect(url_for("auth.login"))
            
            login_user(user, remember=form.remember.data)
            flash("Logged in successfully", "success")
            
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for("main.dashboard"))
        else:
            flash("Invalid credentials. Please try again.", "danger")

    return render_template('login.html', form=form)

@auth.route("/verify-email/<token>")
def verify_email(token):
    from app.models import User
    
    user = User.query.filter_by(email_verification_token=token).first()
    
    if not user or not user.verify_token(token, 'email'):
        flash("The verification link is invalid or has expired.", "danger")
        return redirect(url_for("auth.login"))
    
    user.email_verified = True
    user.email_verification_token = None
    user.email_verification_sent_at = None
    db.session.commit()
    
    flash("Your email has been verified successfully! You can now log in.", "success")
    return redirect(url_for("auth.login"))

@auth.route("/resend-verification", methods=["GET", "POST"])
def resend_verification():
    if request.method == "POST":
        email = request.form.get("email")
        user = User.query.filter_by(email=email).first()
        
        if user:
            if user.email_verified:
                flash("Email is already verified. Please log in.", "info")
                return redirect(url_for("auth.login"))
            
            send_verification_email(user)
            flash("A new verification email has been sent. Please check your inbox.", "info")
            return redirect(url_for("auth.login"))
        else:
            flash("No account found with that email address.", "danger")
    
    return render_template("resend_verification.html")

@auth.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    from app.forms import ForgotPasswordForm
    from app.models import User
    
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            send_password_reset_email(user)
            flash("Password reset instructions have been sent to your email.", "info")
            return redirect(url_for("auth.login"))
        else:
            flash("No account found with that email address.", "danger")
    
    return render_template("forgot_password.html", form=form)

@auth.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    from app import bcrypt

    from app.models import User
    from app.forms import ResetPasswordForm
    
    user = User.query.filter_by(password_reset_token=token).first()
    
    if not user or not user.verify_token(token, 'password'):
        flash("The password reset link is invalid or has expired.", "danger")
        return redirect(url_for("auth.forgot_password"))
    
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user.password_reset_token = None
        user.password_reset_sent_at = None
        db.session.commit()
        
        flash("Your password has been updated successfully! You can now log in.", "success")
        return redirect(url_for("auth.login"))
    
    return render_template("reset_password.html", form=form, token=token)

@auth.route("/logout")
@login_required
def logout():
    flash("Logged out successfully", "success")
    logout_user()
    return redirect(url_for("auth.login"))