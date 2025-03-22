import re
from flask.helpers import flash
from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from flask import request, jsonify

from app.models import Task, User, TaskAssignment, Todo, TaskProgress
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

# Custom template filters
@main.app_template_filter('deadline_category')
def deadline_category_filter(days):
    if days is None:
        return 'secondary'
    if days <= 3:
        return 'danger'
    elif days <= 6:
        return 'warning'
    return 'safe'

@main.app_template_filter('deadline_display')
def deadline_display_filter(days):
    if days is None:
        return 'No deadline'
    if days == 0:
        return 'Today!'
    elif days < 0:
        return f'{-days}d overdue'
    return f'{days}d left'


@main.route("/")
def home():
    return render_template("index.html")

@main.route("/dashboard")
@login_required
def dashboard():
    stats = {
        "total_tasks": 15,
        "pending_tasks": 10,
        "completed_tasks": 5,
        "active_projects": 3,
        "deadlines_today": 2
    }
    return render_template("dashboard.html", user=current_user, active_page="home", stats=stats)

@main.route('/dashboard/tasks')
@login_required
def tasks():
    # Fetch tasks assigned to the current user
    tasks = Task.query.filter_by(assigned_to_user_id=current_user.id).all()
    today = datetime.today().date()

    # Calculate deadline_from_now for each task
    for task in tasks:
        if task.deadline:
            deadline_from_now = (task.deadline - today).days
        else:
            deadline_from_now = None
        task.deadline_from_now = deadline_from_now

    return render_template("tasks.html", user=current_user, tasks=tasks, active_page="tasks", today=today)

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

@main.route("/dashboard/tasks/<int:task_id>/add_todo", methods=["POST"])
@login_required
def add_todo(task_id):
    from app import db

    data = request.get_json()
    content = data.get("content")
    if not content:
        return jsonify({"error": "Todo content is required"}), 400

    todo = Todo(content=content, task_id=task_id)
    db.session.add(todo)
    db.session.commit()
    return jsonify({"id": todo.id, "content": todo.content, "is_completed": todo.is_completed})

@main.route("/dashboard/tasks/<int:task_id>/update_todo/<int:todo_id>", methods=["PUT"])
@login_required
def update_todo(task_id, todo_id):
    from app import db

    data = request.get_json()
    todo = Todo.query.get_or_404(todo_id)
    if "content" in data:
        todo.content = data["content"]
    if "is_completed" in data:
        todo.is_completed = data["is_completed"]
    db.session.commit()
    return jsonify({"message": "Todo updated"})

@main.route("/dashboard/tasks/<int:task_id>/delete_todo/<int:todo_id>", methods=["DELETE"])
@login_required
def delete_todo(task_id, todo_id):
    from app import db

    todo = Todo.query.get_or_404(todo_id)
    if todo.is_completed:
        progress = TaskProgress(task_id=task_id, progress=-1, notes="undone_on_delete")
        db.session.add(progress)
    db.session.delete(todo)
    db.session.commit()
    return jsonify({"message": "Todo deleted"})

@main.route("/dashboard/tasks/<int:task_id>/save_progress", methods=["POST"])
@login_required
def save_progress(task_id):
    from app import db

    data = request.get_json()
    progress = data.get("progress")
    if not progress:
        return jsonify({"error": "Progress is required"}), 400

    task_progress = TaskProgress(task_id=task_id, progress=progress)
    db.session.add(task_progress)
    db.session.commit()
    return jsonify({"message": "Progress saved"})