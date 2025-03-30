import math
from flask.helpers import flash
from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from flask import request, jsonify
from flask_wtf.csrf import validate_csrf
from wtforms import ValidationError
from sqlalchemy.sql import func


from app.models import Task, User, TaskAssignment, Todo, TaskProgress, membership
from app.forms import CreateTask

from datetime import datetime, date, timedelta

def format_date(date_obj : datetime):
    if not date_obj:
        return None
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
    return render_template("index.html", active_page="home")

@main.route("/features")
def features():
    return render_template("features.html", active_page="features")

@main.route("/dashboard")
@login_required
def dashboard():
    from app import db

    # Get the three most recent tasks assigned to the user
    recent_tasks = (
        Task.query.filter_by(assigned_to_user_id=current_user.id)
        .order_by(Task.updated_at.desc())  # Order by most recently updated
        .limit(3)
        .all()
    )

    # Filter tasks based on status
    pending_tasks = Task.query.filter_by(assigned_to_user_id=current_user.id, status="pending").count()
    completed_tasks = Task.query.filter_by(assigned_to_user_id=current_user.id, status="completed").count()

    # Count active projects the user is a member of
    active_projects = db.session.query(membership).filter(
        membership.c.user_id == current_user.id,
        membership.c.status == "active"
    ).count()

    # Count tasks with deadlines today
    deadlines_today = Task.query.filter(
        Task.assigned_to_user_id == current_user.id, func.date(Task.deadline) == date.today()
    ).all()

    # Stats dictionary
    stats = {
        "total_tasks": pending_tasks + completed_tasks,
        "pending_tasks": pending_tasks,
        "completed_tasks": completed_tasks,
        "active_projects": active_projects,
        "deadlines_today": deadlines_today,
        "deadlines_today_count": len(deadlines_today)
    }

    today = datetime.today().date()

    return render_template("dashboard.html", user=current_user, active_page="home", stats=stats, recent_tasks=recent_tasks, today=today)

@main.route('/dashboard/tasks')
@login_required
def tasks():
    # Fetch tasks assigned to the current user
    tasks = Task.query.filter_by(assigned_to_user_id=current_user.id).all()
    today = datetime.today().date()

    # Calculate deadline_from_now for each task
    for task in tasks:
        if task.deadline:
            deadline_from_now = (task.deadline.date() - today).days
        else:
            deadline_from_now = None
        task.deadline_from_now = deadline_from_now

    return render_template("tasks.html", user=current_user, tasks=tasks, active_page="tasks", today=today)

@main.route("/dashboard/projects")
@login_required
def projects():
    return render_template("projects.html", user=current_user, active_page="projects")

@main.route("/dashboard/projects/new")
@login_required
def create_projects():
    return render_template("projects.html", user=current_user, active_page="projects")

@main.route("/profile")
@login_required
def profile():
    user = current_user
    formatted_date_joined = format_date(user.date_joined.date() if isinstance(user.date_joined, datetime) else user.date_joined)
    formatted_dob = format_date(user.dob.date() if isinstance(user.dob, datetime) else user.dob)
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
    todos_total = len(task.todos)
    
    # Determine date range
    today = datetime.today().date()
    created_date = task.created_at.date() if task.created_at else today
    deadline_date = task.deadline.date() if task.deadline else None
    
    # Calculate dynamic date range (max 7 days)
    date_range_days = min((today - created_date).days + 1, 7)
    start_date = today - timedelta(days=date_range_days - 1)
    
    # Generate all dates in range
    dates = [start_date + timedelta(days=i) for i in range(date_range_days)]
    date_labels = [d.strftime("%a %d") for d in dates]

    # Get all progress entries
    progress_entries = TaskProgress.query.filter(
        TaskProgress.task_id == task_id,
        TaskProgress.date_made.between(start_date, today+timedelta(days=1))
    ).order_by(TaskProgress.date_made).all()

    # Structure data for chart
    max_value = 0
    current_value = 0
    x = 0
    chart_data = [{'x': x, 'y': current_value, 'day': start_date.isoformat(),},]
    
    for date in dates:
        # Get all progress changes for this date
        daily_changes = []
        for entry in progress_entries:
            print(entry.date_made)
            if entry.date_made.date() == date:
                daily_changes.extend(entry.progress)

        if not daily_changes:
            x += 1
            # No changes - maintain current value
            chart_data.append({
                'x': x, 
                'y': current_value,
                'day': date.isoformat(),
                })
            continue

            
        # Calculate positions for intra-day changes
        for change in daily_changes:
            x += 1
            current_value += change
            chart_data.append({
                'x': x, 
                'y': current_value,
                'day': date.isoformat(),
            })
            
    has_progress = any(entry.progress for entry in progress_entries) if progress_entries else False
    
    if task.status == "completed":
        advice = "Great job! Keep going and complete more tasks at your own pace."
    elif task.deadline:
        if (task.deadline.date() - today).days <= 0:
            advice = "You're past the deadline, but don't worry! Just focus on completing as many tasks as you can."
        else:
            days_to_finish = (task.deadline.date() - task.created_at.date()).days
            todos_per_day = math.ceil(len(task.todos)/days_to_finish)
            todos_expected_to_be_completed_today = ((today - task.created_at.date()).days + 1)*todos_per_day  # How much todos should have been done by end of today
            todos_completed = sum(1 for todo in task.todos if todo.is_completed)
            todos_left = len(task.todos) - todos_completed
            todos_to_be_done_today = min(todos_expected_to_be_completed_today - todos_completed, todos_left)  # Todos expected to be done added to completed today.
            if todos_per_day == 1:
                if todos_to_be_done_today <= 0:
                    advice = "You're on track! Try to complete at least one task per day, or even more if you feel up to it."
                elif todos_to_be_done_today == 1:
                    advice = "You're almost there! One more todo will keep you on pace."
                else:
                    advice = f"Try to complete at least one todo per day. You have {todos_to_be_done_today} left for today, but feel free to go beyond!"
            elif todos_per_day > 1:
                if todos_to_be_done_today <= 0:
                    advice = f"You're doing great! Aim for at least {todos_per_day} todos per day, or more if you're feeling productive."
                elif todos_to_be_done_today == 1:
                    advice = f"Nice work! Just one more todo will keep you on track."
                else:
                    advice = f"Keep up the momentum! {todos_to_be_done_today} more to reach today's goal ({todos_per_day} per day), but you can always push ahead!"
            else:
                advice = "Kickstart your productivity."
    else:
        advice = "Stay productive at your own pace. Small steps add up!"

    print(chart_data)
    
    info = {'total': len(task.todos), 'advice': advice}
    return render_template("task.html", 
                            user=current_user, 
                            task=task, 
                            active_page="tasks", 
                            info=info,
                            chart_data=chart_data,
                            date_labels=date_labels,
                            todos_total=todos_total,
                            max_value=max(max_value, todos_total),
                            has_progress=has_progress,
                            deadline=deadline_date if (deadline_date and start_date <= deadline_date <= today) else None
                        )

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

    task = Task.query.get(task_id)
    completed = sum(1 for todo in task.todos if todo.is_completed)
    if completed == len(task.todos) and len(task.todos) != 0:
        task.status = "completed"
    else:
        task.status = "pending"
    task.updated_at = datetime.utcnow()
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
        notes=data['notes']
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

    task = Task.query.get(todo.task_id)
    completed = sum(1 for todo in task.todos if todo.is_completed)
    if completed == len(task.todos) and len(task.todos) != 0:
        task.status = "completed"
    else:
        task.status = "pending"
    task.updated_at = datetime.utcnow()
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
            progress=[-1,],
            notes="Undone via deletion"
        )
        db.session.add(progress)
    db.session.delete(todo)
    db.session.commit()

    task = Task.query.get(todo.task_id)
    completed = sum(1 for todo in task.todos if todo.is_completed)
    if completed == len(task.todos) and len(task.todos) != 0:
        task.status = "completed"
    else:
        task.status = "pending"
    task.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'message': 'Todo deleted'}), 200