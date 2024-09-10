import re
from flask.helpers import flash
from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user

from app.models import Task, User, TaskAssignment
from app.forms import CreateTask

from datetime import datetime, timedelta

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

@main.app_template_filter("days_diff")
def date_diff(date1 : datetime, date2 : datetime) -> timedelta.days:
    if not date2:
        return 0
    diff = date2 - date1
    return diff.days

@main.app_template_filter("absolute")
def absolute(num):
    return abs(num)

@main.route("/dashboard/tasks")
@login_required
def tasks():
    tasks = Task.query.filter_by(assigned_to_user_id=current_user.id).all()
    todays_date = datetime.now().date()
    return render_template("tasks.html", user=current_user, tasks=tasks, today=todays_date, active_page="tasks")

@main.route("/dashboard/projects")
@login_required
def projects():
    return render_template("projects.html", user=current_user, active_page="projects")

@main.route("/profile")
@login_required
def profile():
    formatted_date_joined = format_date(current_user.date_joined)
    formatted_dob = format_date(current_user.dob)
    dates = {'joined': formatted_date_joined, 'birth': formatted_dob}
    return render_template("profile.html", user=current_user, user_profile_info=current_user, active_page=None, dates=dates)

@main.route("/profile/edit")
@login_required
def edit_profile():
    pass

@main.route("/user/<int:user_id>/profile")
@login_required
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

@main.route("/dashboard/tasks/new", methods=['GET','POST'])
@login_required
def create_task():
    from app import db

    form = CreateTask()
    if form.validate_on_submit():
        form_data = form.data
        form_data.pop("submit", None)
        form_data.pop("csrf_token", None)
        task = Task(**form_data)
        task.user = current_user
        assignment = TaskAssignment()
        assignment.title = "Self Assigned Task"
        assignment.task.append(task)
        assignment.user = current_user
        db.session.add_all([task, assignment])
        db.session.commit()
        flash("Task created successfully", "success")
        return redirect(url_for("main.task", task_id=task.id))
    return render_template("new_task.html", user=current_user, active_page="tasks", form=form)

@main.route("/dashboard/tasks/<int:task_id>")
@login_required
def task(task_id):
    task = Task.query.filter_by(id=task_id).first()
    if not task:
        return "Not Found", 404
    if task.assigned_to_user_id != current_user.id:
        flash("You don't have the permission to view this task")
        return redirect(url_for("main.dashboard"))
    return render_template("task.html", user=current_user, task=task, active_page="tasks")