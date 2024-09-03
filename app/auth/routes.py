from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, login_user, logout_user

from app import login_manager

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
        new_user = User(**data)
        db.session.add(new_user)
        db.session.commit()

        flash("Signed-Up Successfully, Please Login", "success")
        return redirect(url_for("auth.login"))

    return render_template('signup.html', form=form)

@auth.route("/login", methods=["GET", "POST"])
def login():
    from app.forms import LoginForm
    from app.models import User
    from app import bcrypt

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.uname_or_email.data).first() or User.query.filter_by(email=form.uname_or_email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            flash("Logged in successfully", "success")
            return redirect(url_for("main.dashboard"))
    return render_template('login.html', form=form)

@auth.route("/logout")
@login_required
def logout():
    flash("Logged out successfully", "success")
    logout_user()
    return redirect(url_for("auth.login"))