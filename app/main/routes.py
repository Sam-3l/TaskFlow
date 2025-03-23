import re
from flask.helpers import flash
from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from flask import request, jsonify
from flask_wtf.csrf import validate_csrf
from wtforms import ValidationError


from app.models import Task, User, TaskAssignment, Todo, TaskProgress
from app.forms import CreateTask

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

@main.app_template_filter('calculate_progress')
def calculate_progress(task):
    if not task.todos:
        return 0
    completed = sum(1 for todo in task.todos if todo.is_completed)
    return int((completed / len(task.todos)) * 100)

@main.app_template_filter('datetime_format')
def datetime_format(value, format="%b %d, %Y"):
    if value is None:
        return ""
    return value.strftime(format)

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

# Todo API
@main.route("/tasks/<int:task_id>/todos", methods=["POST"])
@login_required
def create_todo(task_id):
    from app import db

    try:
        # Validate CSRF token
        validate_csrf(request.headers.get('X-CSRFToken'))
    except ValidationError:
        return jsonify({"error": "Invalid CSRF token"}), 400

    data = request.get_json()
    todo = Todo(content=data['content'], task_id=task_id)
    db.session.add(todo)
    db.session.commit()
    return jsonify({
        'id': todo.id,
        'content': todo.content,
        'is_completed': todo.is_completed
    }), 201

@main.route("/tasks/<int:task_id>/progress", methods=["POST"])
@login_required
def save_task_progress(task_id):
    from app import db

    try:
        # Validate CSRF token
        validate_csrf(request.headers.get('X-CSRFToken'))
    except ValidationError:
        return jsonify({"error": "Invalid CSRF token"}), 400

    data = request.get_json()
    progress = TaskProgress(
        task_id=task_id,
        progress=data['progress'],
        notes="Manual save"
    )
    db.session.add(progress)
    db.session.commit()
    return jsonify({'message': 'Progress saved'}), 200

@main.route("/todos/<int:todo_id>", methods=["PUT"])
@login_required
def update_todo(todo_id):
    from app import db
    
    try:
        # Validate CSRF token
        validate_csrf(request.headers.get('X-CSRFToken'))
    except ValidationError:
        return jsonify({"error": "Invalid CSRF token"}), 400

    todo = Todo.query.get_or_404(todo_id)
    data = request.get_json()

    # Update todo content
    if 'content' in data:
        todo.content = data['content']

    # Update completion status
    if 'is_completed' in data:
        todo.is_completed = data['is_completed']

    db.session.commit()
    return jsonify({
        'id': todo.id,
        'content': todo.content,
        'is_completed': todo.is_completed
    }), 200

@main.route("/todos/<int:todo_id>", methods=["DELETE"])
@login_required
def delete_todo(todo_id):
    from app import db

    try:
        # Validate CSRF token
        validate_csrf(request.headers.get('X-CSRFToken'))
    except ValidationError:
        return jsonify({"error": "Invalid CSRF token"}), 400

    todo = Todo.query.get_or_404(todo_id)
    if todo.is_completed:
        # Record undone progress if deleting a completed todo
        progress = TaskProgress(
            task_id=todo.task_id,
            progress=-1,
            notes="Undone via deletion"
        )
        db.session.add(progress)
    db.session.delete(todo)
    db.session.commit()
    return jsonify({'message': 'Todo deleted'}), 200