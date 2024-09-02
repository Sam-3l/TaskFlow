from app.models import User
from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user

from datetime import datetime

def format_date(date_obj : datetime):
    day = date_obj.day
    month_year = date_obj.strftime("%B %Y")
    day_with_suffix = add_ordinal_suffix(day)
    
    # Combine the day with suffix and formatted month and year
    formatted_date = f"{day_with_suffix} {month_year}"
    return formatted_date

def add_ordinal_suffix(day):
    if 4 <= day <= 20 or 24 <= day <= 30:
        suffix = "th"
    else:
        suffix = ["st", "nd", "rd"][day % 10 - 1]
    return f"{day}{suffix}"

main = Blueprint("main", __name__)

@main.route("/")
def home():
    return render_template("index.html")

@main.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", user=current_user, active_page="home")

@login_required
@main.route("/dashboard/tasks")
def tasks():
    return render_template("tasks.html", user=current_user, active_page="tasks")

@login_required
@main.route("/dashboard/projects")
def projects():
    return render_template("projects.html", user=current_user, active_page="projects")

@login_required
@main.route("/profile")
def profile():
    formatted_date_joined = format_date(current_user.date_joined)
    formatted_dob = format_date(current_user.dob)
    dates = {'joined': formatted_date_joined, 'birth': formatted_dob}
    return render_template("profile.html", user=current_user, user_profile_info=current_user, active_page=None, dates=dates)

@login_required
@main.route("/profile/edit")
def edit_profile():
    pass

@login_required
@main.route("/user/<int:user_id>/profile")
def user(user_id):
    if current_user.id == user_id:
        return redirect(url_for("main.profile"))
    user = User.query.filter_by(id=user_id).first()
    if not user:
        return "Not found. Check your url", 404
    formatted_date_joined = format_date(user.date_joined)
    formatted_dob = format_date(user.dob)
    dates = {'joined': formatted_date_joined, 'birth': formatted_dob}
    return render_template("profile.html", user=current_user, user_profile_info=user, active_page=None, dates=dates)