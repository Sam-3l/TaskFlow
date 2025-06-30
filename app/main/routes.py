import math
from flask.helpers import flash
from flask import Blueprint, render_template, redirect, url_for, current_app, abort
from flask_login import login_required, current_user
from flask import request, jsonify
from flask_wtf.csrf import validate_csrf
from wtforms import ValidationError
from sqlalchemy.sql import func
from sqlalchemy import and_, or_, not_
from sqlalchemy import case
from sqlalchemy.orm import aliased

# Data viz
import plotly
import plotly.graph_objs as go

import json
import requests
import os
from werkzeug.utils import secure_filename
import time
import re
from types import SimpleNamespace

from app.models import Task, User, TaskAssignment, Todo, TaskProgress, membership, Project, task_user_association, ProjectDiscussion, TaskAssignmentComment, upvotes, Notification
from app.forms import CreateTask, CreateProject
from app.utils.notifications import get_unread_count, mark_notifications_as_read, get_user_notifications, add_notification
from app.utils.s3_upload import upload_file_to_s3
from app.utils.ai_handler import generate_ai_subtasks, generate_task_priority_analysis

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

@main.app_template_filter('time_ago')
def time_ago_filter(dt):
    now = datetime.utcnow()
    diff = now - dt
    
    seconds = diff.total_seconds()
    minutes = seconds / 60
    hours = minutes / 60
    days = hours / 24
    
    if seconds < 60:
        return "just now"
    elif minutes < 60:
        return f"{int(minutes)} minute{'s' if int(minutes) != 1 else ''} ago"
    elif hours < 24:
        return f"{int(hours)} hour{'s' if int(hours) != 1 else ''} ago"
    elif days < 7:
        return f"{int(days)} day{'s' if int(days) != 1 else ''} ago"
    else:
        return dt.strftime("%b %d, %Y")

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
        Task.query.filter(Task.assigned_users.any(id=current_user.id))
        .order_by(Task.updated_at.desc())  # Order by most recently updated
        .limit(3)
        .all()
    )

    # Filter tasks based on status
    total_tasks = Task.query.filter(Task.assigned_users.any(id=current_user.id)).count()
    completed_tasks = Task.query.filter(
                            Task.assigned_users.any(id=current_user.id),
                            Task.status == "completed"
                        ).count()

    # Count active projects the user is a member of
    active_projects = db.session.query(membership).filter(
        membership.c.user_id == current_user.id,
        membership.c.status == "active"
    ).count()

    # Count tasks with deadlines today
    deadlines_today = Task.query.filter(
        Task.assigned_users.any(id=current_user.id), func.date(Task.deadline) == date.today()
    ).all()

    # Stats dictionary
    stats = {
        "total_tasks": total_tasks,
        "pending_tasks": total_tasks - completed_tasks,
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
    priority_order = case(
        {
            'critical': 1,
            'high-priority': 2,
            'medium-priority': 3,
            'low-priority': 4,
            'optional': 5
        },
        value=Task.priority,
        else_=6
    )
    # Fetch tasks assigned to the current user
    tasks_query = Task.query.filter(Task.assigned_users.any(id=current_user.id))
    tasks = tasks_query.order_by(priority_order, Task.updated_at.desc()).all()
    today = datetime.today().date()

    # Calculate deadline_from_now for each task
    for task in tasks:
        if task.deadline:
            deadline_from_now = (task.deadline.date() - today).days
        else:
            deadline_from_now = None
        task.deadline_from_now = deadline_from_now

    return render_template("tasks.html", user=current_user, tasks=tasks, active_page="tasks", today=today)

@main.route("/tasks/<int:task_id>/personal-status", methods=["PATCH"])
@login_required
def update_personal_task_status(task_id):
    task = Task.query.get_or_404(task_id)
    
    # Verify user owns the task or is assigned to it
    if not any(u.id == current_user.id for u in task.assigned_users):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    new_status = request.json.get('status')
    if new_status not in ['pending', 'in progress', 'review', 'completed']:
        return jsonify({'success': False, 'error': 'Invalid status'}), 400
    
    task.status = new_status
    db.session.commit()
    
    return jsonify({'success': True})

@main.route("/dashboard/projects")
@login_required
def projects():
    from app import db
    # Get all projects where the user is a member
    user_projects = Project.query.filter(Project.active_members.any(id=current_user.id)).all()
    
    # Add progress, task count, and user role to each project
    for project in user_projects:
        # Calculate project progress based on completed tasks
        total_tasks = sum([len(assignment.task) for assignment in project.task_assignment])
        project.task_count = total_tasks
        
        # Get user's role in this project
        membership_record = db.session.query(membership).filter(
            membership.c.project_id == project.id,
            membership.c.user_id == current_user.id
        ).first()
        project.user_role = membership_record.role if membership_record else None
    
    return render_template("projects.html", 
                         user=current_user, 
                         active_page="projects",
                         projects=user_projects,
                        )

@main.route("/dashboard/projects/new", methods=['GET', 'POST'])
@login_required
def create_projects():
    from app import db
    
    form = CreateProject()
    if form.validate_on_submit():
        form_data = form.data
        form_data.pop("submit", None)
        form_data.pop("csrf_token", None)
        
        # Handle empty project_links
        if not form_data.get('project_links', '').strip():
            form_data['project_links'] = None
            
        # Remove cover_image from form_data as we'll handle it separately
        form_data.pop("cover_image", None)
        
        # Create the project
        project = Project(**form_data)
        
        # Handle cover image upload
        if form.cover_image.data:
            file = form.cover_image.data
            if file:
                filename = secure_filename(file.filename)
                # Generate unique filename
                base, ext = os.path.splitext(filename)
                filename = f"{base}_{int(time.time())}{ext}"
                s3_key = f"static/images/uploads/project_covers/{filename}"
                
                if current_app.config['USE_S3']:
                    upload_file_to_s3(file, s3_key)
                else:
                    # Ensure the upload directory exists
                    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'project_covers')
                    os.makedirs(upload_dir, exist_ok=True)
                    # Save the file
                    file.save(os.path.join(upload_dir, filename))

                project.cover_image = filename
        
        db.session.add(project)
        db.session.commit()
        
        # Add the creator as a project manager
        db.session.execute(
            membership.insert().values(
                project_id=project.id,
                user_id=current_user.id,
                role="project_manager",
                status="active"
            )
        )
        db.session.commit()
        
        flash("Project created successfully", "success")
        return redirect(url_for("main.projects"))
        
    return render_template("new_project.html", user=current_user, active_page="projects", form=form)

@main.route("/dashboard/projects/<int:project_id>")
@login_required
def project(project_id):
    from app import db

    # Get project and verify access
    project = Project.query.get_or_404(project_id)

    # Check if user has active membership
    current_membership = db.session.query(membership).filter_by(
        project_id=project.id,
        user_id=current_user.id,
        status='active'  # Only consider active memberships
    ).first()

    # Handle private project access
    if project.type == 'private' and not current_membership:
        flash('This is a private project. You need to be invited to access it.', 'error')
        return redirect(url_for('main.projects'))
    
    # Get all members with their roles
    members = db.session.query(
        User,
        membership.c.role,
        membership.c.status
    ).join(
        membership, User.id == membership.c.user_id
    ).filter(
        membership.c.project_id == project.id,
        membership.c.status == 'active'
    ).all()
    
    # Get task assignments
    task_assignments = TaskAssignment.query.filter_by(
        source_project_id=project.id
    ).order_by(
        TaskAssignment.assigned_at.desc()
    ).all()
    
    # Get regular project discussions
    discussions = ProjectDiscussion.query.filter_by(
        project_id=project.id
    ).all()

    # Get task assignment comments for this project
    comments = TaskAssignmentComment.query.join(
        TaskAssignment
    ).filter(
        TaskAssignment.source_project_id == project.id
    ).all()

    # Add type attribute and combine
    combined = []
    for d in discussions:
        d.type = 'discussion'  # This will be used in the template
        combined.append(d)

    for c in comments:
        c.type = 'assignment_comment'  # This matches your template condition
        combined.append(c)

    # Sort by created_at (newest first)
    sorted_discussions = sorted(
        combined,
        key=lambda x: x.created_at,
        reverse=True
    )
    
    # Get tasks for Kanban board
    tasks = Task.query.join(
        TaskAssignment
    ).filter(
        TaskAssignment.source_project_id == project.id
    ).all()
    
    # Organize tasks by status for Kanban
    kanban_columns = {
        'pending': ('To Do', []),
        'in progress': ('In Progress', []),
        'review': ('Review', []),
        'completed': ('Done', [])
    }
    
    for task in tasks:
        status = task.status if task.status in kanban_columns else 'pending'
        kanban_columns[status][1].append(task)

    # Check if user is logged in and has pending request
    has_pending_request = False
    if current_user.is_authenticated:
        has_pending_request = db.session.query(membership).filter(
            membership.c.project_id == project_id,
            membership.c.user_id == current_user.id,
            membership.c.status == 'pending'
        ).first() is not None
    
    # Get pending requests count for managers
    pending_requests_count = 0
    if current_user.is_authenticated:
        is_manager = db.session.query(membership).filter(
            membership.c.project_id == project_id,
            membership.c.user_id == current_user.id,
            membership.c.role == 'project_manager',
            membership.c.status == 'active'
        ).first()
        if is_manager:
            pending_requests_count = db.session.query(membership).filter(
                membership.c.project_id == project_id,
                membership.c.status == 'pending'
            ).count()
    
    return render_template(
        'project.html',
        user=current_user,
        active_page="projects",
        project=project,
        current_membership=current_membership,
        members=members,
        task_assignments=task_assignments,
        has_pending_request=has_pending_request,
        pending_requests_count=pending_requests_count,
        discussions=sorted_discussions,
        kanban_columns=kanban_columns
    )

@main.route('/projects/<int:project_id>/request_join', methods=['POST'])
@login_required
def request_join(project_id):
    project = Project.query.get_or_404(project_id)
    
    if project.type != 'public-open':
        return jsonify({'success': False, 'message': 'This project is not open for joining'})
    
    # Check if user is already a member (active or pending)
    existing_membership = db.session.query(membership).filter(
        membership.c.project_id == project_id,
        membership.c.user_id == current_user.id
    ).first()

    if existing_membership and existing_membership.status == 'rejected':
        update_stmt = membership.update().where(
            (membership.c.project_id == project_id) &
            (membership.c.user_id == current_user.id)
        ).values(status='pending')
        
        db.session.execute(update_stmt)
        db.session.commit()

        # Add notification for project managers
        notify_project_managers(project, current_user)
        return jsonify({'success': True})
    
    if existing_membership:
        status = 'active' if existing_membership.status == 'active' else 'pending'
        return jsonify({
            'success': False, 
            'message': f'You already have a {status} membership for this project'
        })
    
    # Create new membership with pending status
    insert_stmt = membership.insert().values(
        project_id=project_id,
        user_id=current_user.id,
        role='contributor',
        status='pending',
        joined_at=datetime.utcnow()
    )
    db.session.execute(insert_stmt)
    db.session.commit()
    
    # Add notification for project managers
    notify_project_managers(project, current_user)
    return jsonify({'success': True})

def notify_project_managers(project, requesting_user):
    """Notify all project managers about join request"""
    
    # Get all users with manager role in this project
    managers = db.session.query(User).join(
        membership, (membership.c.user_id == User.id)
    ).filter(
        membership.c.project_id == project.id,
        membership.c.role == 'project_manager',
        membership.c.status == 'active'
    ).all()
    
    for manager in managers:
        add_notification(
            user_id=manager.id,
            message=f"{requesting_user.username} requested to join project {project.title}",
            link=url_for('main.join_requests', project_id=project.id),
            icon="project",
            sender_id=requesting_user.id
        )

@main.route('/projects/<int:project_id>/cancel_request', methods=['POST'])
@login_required
def cancel_request(project_id):
    # Delete the membership record
    delete_stmt = membership.delete().where(
        (membership.c.project_id == project_id) &
        (membership.c.user_id == current_user.id) &
        (membership.c.status == 'pending')
    )
    result = db.session.execute(delete_stmt)
    db.session.commit()
    
    if result.rowcount == 0:
        return jsonify({'success': False, 'message': 'No pending request found'})
    
    return jsonify({'success': True})

@main.route('/projects/<int:project_id>/join_requests')
@login_required
def join_requests(project_id):
    project = Project.query.get_or_404(project_id)
    
    # Check if current user is a project manager
    is_manager = db.session.query(membership).filter(
        membership.c.project_id == project_id,
        membership.c.user_id == current_user.id,
        membership.c.role == 'project_manager',
        membership.c.status == 'active'
    ).first()
    
    if not is_manager:
        abort(403)
    
    # Get all join requests with user info
    pending_requests = db.session.execute(
        db.select(
            membership.c.user_id,
            membership.c.joined_at,
            membership.c.status,
            User
        ).join(
            User, User.id == membership.c.user_id
        ).where(
            membership.c.project_id == project_id,
            membership.c.status != 'active'
        ).order_by(
            membership.c.joined_at.desc()
        )
    ).all()

    # Structure the data for the template
    join_requests = []
    for req in pending_requests:
        join_requests.append({
            'user_id': req.user_id,
            'joined_at': req.joined_at,
            'status': req.status,
            'user': req.User  # The User object
        })
    
    # Get counts
    pending_count = len(pending_requests)
    total_count = db.session.query(membership).filter(
        membership.c.project_id == project_id
    ).count()
    
    return render_template(
        'join_requests.html',
        user=current_user,
        project=project,
        join_requests=join_requests,
        pending_requests_count=pending_count,
        total_requests=total_count
    )

@main.route('/projects/<int:project_id>/process_request', methods=['POST'])
@login_required
def process_request(project_id):
    data = request.get_json()
    user_id = data.get('user_id')
    action = data.get('action')
    
    if not user_id or not action:
        return jsonify({'success': False, 'message': 'Missing parameters'})
    
    # Verify the current user is a manager of this project
    is_manager = db.session.query(membership).filter(
        membership.c.project_id == project_id,
        membership.c.user_id == current_user.id,
        membership.c.role == 'project_manager',
        membership.c.status == 'active'
    ).first()
    
    if not is_manager:
        return jsonify({'success': False, 'message': 'Unauthorized'})
    
    # Update the membership status based on action
    if action == 'accept':
        update_stmt = membership.update().where(
            (membership.c.project_id == project_id) &
            (membership.c.user_id == user_id)
        ).values(status='active')

        project = Project.query.get_or_404(project_id)
        
        # For accepted join requests (when manager approves a user's request)
        add_notification(
            user_id=user_id,
            message=f"Your request to join '{project.title}' was accepted! You're now a contributor.",
            link=url_for('main.project', project_id=project.id),
            icon="project",
            sender_id=current_user.id
        )

    elif action == 'reject':
        update_stmt = membership.update().where(
            (membership.c.project_id == project_id) &
            (membership.c.user_id == user_id)
        ).values(status='rejected')
    elif action == 'remove':
        delete_stmt = membership.delete().where(
            (membership.c.project_id == project_id) &
            (membership.c.user_id == user_id)
        )
        db.session.execute(delete_stmt)
        db.session.commit()
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'message': 'Invalid action'})
    
    db.session.execute(update_stmt)
    db.session.commit()
    
    return jsonify({'success': True})

@main.route('/projects/<int:project_id>/upvote', methods=['POST', 'DELETE'])
@login_required
def upvote_project(project_id):
    project = Project.query.get_or_404(project_id)
    
    if request.method == 'POST':
        if current_user not in project.upvotes:
            project.upvotes.append(current_user)
            db.session.commit()

            # Notify project members about the upvote (excluding the upvoter)
            notify_project_upvote(project, current_user, action='added')

            return jsonify({
                'success': True,
                'new_count': len(project.upvotes),
                'action': 'added'
            })
    
    elif request.method == 'DELETE':
        if current_user in project.upvotes:
            project.upvotes.remove(current_user)
            db.session.commit()
            return jsonify({
                'success': True,
                'new_count': len(project.upvotes),
                'action': 'removed'
            })
    
    return jsonify({'success': False}), 400

def notify_project_upvote(project, upvoter, action):
    """Notify project members when someone upvotes their project"""
    # Get all active project members except the upvoter
    members = User.query.join(
        membership, (membership.c.user_id == User.id)
    ).filter(
        membership.c.project_id == project.id,
        membership.c.status == 'active',
        User.id != upvoter.id  # Don't notify the upvoter
    ).all()
    
    for member in members:
        if action == 'added':
            message = f"{upvoter.username} upvoted your project {project.title}"
            icon = "heart-fill"
            
        add_notification(
            user_id=member.id,
            message=message,
            link=url_for('main.project', project_id=project.id),
            icon=icon,
            sender_id=upvoter.id
        )

@main.route('/dashboard/upvotes')
@login_required
def upvoted_projects():
    upvoted_projects = (
        db.session.query(Project)
        .join(upvotes, Project.id == upvotes.c.project_id)
        .filter(upvotes.c.user_id == current_user.id)
        .add_columns(db.func.count(upvotes.c.user_id).label('upvote_count'))
        .group_by(Project.id)
        .order_by(db.desc('upvote_count'))
        .all()
    )
    
    # Extract just the Project objects from the result
    projects = [project for project, upvote_count in upvoted_projects]

    for project in projects:
        # Calculate project progress based on completed tasks
        total_tasks = sum([len(assignment.task) for assignment in project.task_assignment])
        project.task_count = total_tasks
    
    return render_template('upvoted_projects.html', 
                         projects=projects,
                         user=current_user,
                         active_page="upvotes",
                         title="Your Upvoted Projects")

@main.route('/assignment/<int:assignment_id>', methods=['GET', 'POST'])
@login_required
def task_assignment(assignment_id):
    # Get the assignment with all related data including tasks
    assignment = TaskAssignment.query.options(
        db.joinedload(TaskAssignment.user),
        db.joinedload(TaskAssignment.source),
        db.joinedload(TaskAssignment.task).joinedload(Task.assigned_users),
        db.joinedload(TaskAssignment.task).joinedload(Task.todos),
        db.joinedload(TaskAssignment.task).joinedload(Task.task_progress),
        db.joinedload(TaskAssignment.comments).joinedload(TaskAssignmentComment.user)
    ).get_or_404(assignment_id)

    if not assignment.source:
        flash("Assignment not found", "error")
        return redirect(url_for('main.dashboard'))
    
    # Get the assigned_by user
    assigned_by = User.query.get(assignment.assigned_by_user_id)
    
    # Check permissions
    if not current_user in assignment.source.active_members:
        flash("You don't have permission to view this assignment", "error")
        return redirect(url_for('main.dashboard'))
    
    # Handle comment submission
    if request.method == 'POST':
        try:
            # Validate CSRF token first
            validate_csrf(request.form.get('csrf_token'))
            
            # Then process your form
            comment_content = request.form.get('comment')
            if comment_content and comment_content.strip():
                new_comment = TaskAssignmentComment(
                    content=comment_content.strip(),
                    user_id=current_user.id,
                    assignment_id=assignment.id
                )
                db.session.add(new_comment)
                db.session.commit()
                return redirect(url_for('main.task_assignment', assignment_id=assignment_id))
                
        except ValidationError:
            flash('Invalid form submission. Please try again.', 'error')
            return redirect(url_for('main.task_assignment', assignment_id=assignment_id))
    
    return render_template('task_assignment.html', 
                        assignment=assignment, 
                        user=current_user,
                        assigned_by=assigned_by)

from app import db

@main.route('/projects/<int:project_id>/update_cover', methods=['POST'])
@login_required
def update_project_cover(project_id):
    project = Project.query.get_or_404(project_id)
    is_manager = db.session.execute(
        db.select(membership).where(
            and_(
                membership.c.project_id == project.id,
                membership.c.user_id == current_user.id,
                membership.c.role == 'project_manager',
                membership.c.status == 'active'
            )
        )
    ).first()
    
    if not is_manager:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    if 'cover_image' not in request.files:
        return jsonify({'success': False, 'message': 'No file uploaded'}), 400
    
    file = request.files['cover_image']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No selected file'}), 400
    
    if file:
        filename = secure_filename(f"project_{project_id}_{datetime.now().timestamp()}.{file.filename.split('.')[-1]}")
        s3_key = f"static/images/uploads/project_covers/{filename}"

        if current_app.config['USE_S3']:
            upload_file_to_s3(file, s3_key)
        else:
            upload_folder = os.path.join(current_app.root_path, 'static', 'images', 'uploads', 'project_covers')
            os.makedirs(upload_folder, exist_ok=True)
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)
        
        if not project.cover_image.startswith('default_project'):
            old_filepath = os.path.join(upload_folder, project.cover_image)
            if os.path.exists(old_filepath):
                os.remove(old_filepath)
        
        project.cover_image = filename
        db.session.commit()
        
        return jsonify({'success': True, 'filename': filename})
    
    return jsonify({'success': False, 'message': 'File upload failed'}), 500

@main.route('/projects/<int:project_id>/update_title', methods=['POST'])
@login_required
def update_project_title(project_id):
    project = Project.query.get_or_404(project_id)
    is_manager = db.session.execute(
        db.select(membership).where(
            and_(
                membership.c.project_id == project.id,
                membership.c.user_id == current_user.id,
                membership.c.role == 'project_manager',
                membership.c.status == 'active'
            )
        )
    ).first()
    
    if not is_manager:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.get_json()
    if not data or 'title' not in data:
        return jsonify({'success': False, 'message': 'Invalid request'}), 400
    
    new_title = data['title'].strip()
    if not new_title:
        return jsonify({'success': False, 'message': 'Title cannot be empty'}), 400
    
    project.title = new_title
    db.session.commit()
    
    return jsonify({'success': True})

@main.route('/projects/<int:project_id>/update_type', methods=['POST'])
@login_required
def update_project_type(project_id):
    project = Project.query.get_or_404(project_id)
    is_manager = db.session.execute(
        db.select(membership).where(
            and_(
                membership.c.project_id == project.id,
                membership.c.user_id == current_user.id,
                membership.c.role == 'project_manager',
                membership.c.status == 'active'
            )
        )
    ).first()
    
    if not is_manager:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.get_json()
    if not data or 'type' not in data:
        return jsonify({'success': False, 'message': 'Invalid request'}), 400
    
    new_type = data['type'].strip()
    if not new_type:
        return jsonify({'success': False, 'message': 'Title cannot be empty'}), 400
    
    project.type = new_type
    db.session.commit()
    
    return jsonify({'success': True})

@main.route('/projects/<int:project_id>/update_description', methods=['POST'])
@login_required
def update_project_description(project_id):
    project = Project.query.get_or_404(project_id)
    is_manager = db.session.execute(
        db.select(membership).where(
            and_(
                membership.c.project_id == project.id,
                membership.c.user_id == current_user.id,
                membership.c.role == 'project_manager',
                membership.c.status == 'active'
            )
        )
    ).first()
    
    if not is_manager:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.get_json()
    if not data or 'description' not in data:
        return jsonify({'success': False, 'message': 'Invalid request'}), 400
    
    new_description = data['description'].strip()
    project.description = new_description
    db.session.commit()
    
    return jsonify({'success': True})

@main.route('/projects/<int:project_id>/search_users', methods=['GET'])
@login_required
def search_users_to_add(project_id):
    query = request.args.get('query', '').strip()
    if not query:
        return jsonify({'success': False, 'message': 'Search query required'}), 400
    
    connections = current_user.get_connections().filter(
        (User.username.ilike(f'%{query}%')) | 
        (User.email.ilike(f'%{query}%')) |
        (User.fname.ilike(f'%{query}%')) |
        (User.lname.ilike(f'%{query}%'))
    ).limit(10).all()
    
    if len(connections) < 10:
        additional_users = User.query.filter(
            (User.username.ilike(f'%{query}%')) | 
            (User.email.ilike(f'%{query}%')) |
            (User.fname.ilike(f'%{query}%')) |
            (User.lname.ilike(f'%{query}%')),
            ~User.id.in_([c.id for c in connections]),
            User.id != current_user.id
        ).limit(10 - len(connections)).all()
        connections.extend(additional_users)
    
    results = [{
        'id': user.id,
        'name': f"{user.fname} {user.lname}",
        'username': user.username,
        'email': user.email,
        'avatar': url_for('static', filename='images/profiles/' + user.profile_img),
        'is_connection': user in current_user.get_connections().all()
    } for user in connections]
    
    return jsonify({'success': True, 'users': results})

@main.route('/projects/<int:project_id>/add_member', methods=['POST'])
@login_required
def add_project_member(project_id):
    project = Project.query.get_or_404(project_id)
    is_manager = db.session.execute(
        db.select(membership).where(
            and_(
                membership.c.project_id == project.id,
                membership.c.user_id == current_user.id,
                membership.c.role == 'project_manager',
                membership.c.status == 'active'
            )
        )
    ).first()
    
    if not is_manager:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.get_json()
    if not data or 'user_id' not in data or 'role' not in data:
        return jsonify({'success': False, 'message': 'Invalid request'}), 400
    
    user_id = data['user_id']
    role = data['role']
    
    if role not in ['project_manager', 'task_coordinator', 'contributor']:
        return jsonify({'success': False, 'message': 'Invalid role'}), 400
    
    existing_member = db.session.execute(
        db.select(membership).where(
            and_(
                membership.c.project_id == project.id,
                membership.c.user_id == user_id,
            )
        )
    ).first()
    
    if existing_member:
        if existing_member.status == 'active':
            return jsonify({'success': False, 'message': 'User is already a member'}), 400
        else:
            stmt = (
                membership.update()
                .where(
                    and_(
                        membership.c.project_id == project.id,
                        membership.c.user_id == user_id
                    )
                )
                .values(status='active', role=role)
            )
            db.session.execute(stmt)
    else:  
        db.session.execute(
            membership.insert().values(
                project_id=project.id,
                user_id=user_id,
                role=role,
                status='active'
            )
        )

    new_member = User.query.get(user_id)
    
    # Send notification to the new member
    add_notification(
        user_id=user_id,
        message=f"You've been added to project '{project.title}' as a {role.replace('_', ' ')}",
        link=url_for('main.project', project_id=project.id),
        icon="project",
        sender_id=current_user.id
    )

    db.session.commit()
    
    return jsonify({
        'success': True,
        'member': {
            'id': new_member.id,
            'name': f"{new_member.fname} {new_member.lname}",
            'username': new_member.username,
            'role': role,
            'avatar': url_for('static', filename='images/profiles/' + new_member.profile_img)
        }
    })

@main.route('/projects/<int:project_id>/change_role', methods=['POST'])
@login_required
def change_member_role(project_id):
    project = Project.query.get_or_404(project_id)
    is_manager = db.session.execute(
        db.select(membership).where(
            and_(
                membership.c.project_id == project.id,
                membership.c.user_id == current_user.id,
                membership.c.role == 'project_manager',
                membership.c.status == 'active'
            )
        )
    ).first()
    
    if not is_manager:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.get_json()
    if not data or 'username' not in data or 'role' not in data:
        return jsonify({'success': False, 'message': 'Invalid request'}), 400
    
    user = User.query.filter_by(username=data['username']).first()
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    user_id = user.id
    new_role = data['role']
    
    if new_role not in ['project_manager', 'task_coordinator', 'contributor']:
        return jsonify({'success': False, 'message': 'Invalid role'}), 400
    
    if str(user_id) == str(current_user.id):
        return jsonify({'success': False, 'message': 'Cannot change your own role'}), 400
    
    db.session.execute(
        membership.update()
        .where(membership.c.project_id == project_id)
        .where(membership.c.user_id == user_id)
        .values(role=new_role)
    )
    db.session.commit()
    
    return jsonify({'success': True})

@main.route('/projects/<int:project_id>/remove_member', methods=['POST'])
@login_required
def remove_project_member(project_id):
    project = Project.query.get_or_404(project_id)
    requesting_membership = db.session.query(membership).filter_by(
        project_id=project.id,
        user_id=current_user.id
    ).filter(
        membership.c.role == 'project_manager'
    ).first()
    
    if not requesting_membership:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.get_json()
    if not data or 'username' not in data:
        return jsonify({'success': False, 'message': 'Invalid request'}), 400

    username = data['username']
    user = User.query.filter_by(username=username).first()
    if user:
        user_id = user.id
    else:
        user_id = None
    
    
    if str(user_id) == str(current_user.id):
        return jsonify({'success': False, 'message': 'Cannot remove yourself'}), 400
    
    db.session.execute(
        membership.delete()
        .where(membership.c.project_id == project_id)
        .where(membership.c.user_id == user_id)
    )
    
    tasks_to_unassign = Task.query.join(
        TaskAssignment
    ).filter(
        TaskAssignment.source_project_id == project_id,
        Task.assigned_users.any(id=user_id)
    ).all()
    
    for task in tasks_to_unassign:
        task.assigned_users = [u for u in task.assigned_users if u.id != user_id]
    
    db.session.commit()
    
    return jsonify({'success': True})

@main.route('/tasks/<int:task_id>/update_status', methods=['POST'])
@login_required
def update_task_status(task_id):
    task = Task.query.get_or_404(task_id)
    
    # Check if user is project manager of the task's project
    is_project_manager = db.session.query(membership).filter_by(
        project_id=task.assignment.source_project_id,
        user_id=current_user.id,
        status='active',
        role='project_manager'
    ).first() is not None
    
    # Check if user is task coordinator AND either assigned the task or is assigned to it
    is_task_coordinator = False
    if not is_project_manager:
        task_coordinator = db.session.query(membership).filter_by(
            project_id=task.assignment.source_project_id,
            user_id=current_user.id,
            status='active',
            role='task_coordinator'
        ).first()
        
        if task_coordinator:
            # Check if user assigned this task or is assigned to it
            is_task_coordinator = (
                task.assignment.assigned_by_user_id == current_user.id or
                current_user in task.assigned_users
            )
    
    # Check if user is contributor assigned to the task
    is_assigned_contributor = (
        not is_project_manager and 
        not is_task_coordinator and 
        current_user in task.assigned_users and
        current_user in Project.query.filter_by(id=task.assignment.source_project_id).first().active_members
    )
    # Testing.
    print("Test Kanban board permissions")
    
    if not any([is_project_manager, is_task_coordinator, is_assigned_contributor]):
        return jsonify({
            'success': False, 
            'message': 'Unauthorized: You do not have permission to modify this task',
            'draggable': False
        }), 403
    
    data = request.get_json()
    if not data or 'status' not in data:
        return jsonify({'success': False, 'message': 'Status required'}), 400
    
    task.status = data['status']
    db.session.commit()

    # Update assignment status
    assignment = task.assignment
    completed_tasks = sum(1 for t in assignment.task if t.status == "completed")
    
    if completed_tasks == 0:
        assignment.status = "pending"
    elif completed_tasks == len(assignment.task):
        assignment.status = "completed"
    else:
        assignment.status = f"{completed_tasks}/{len(assignment.task)} tasks completed"
    
    db.session.commit()
    
    return jsonify({'success': True, 'draggable': True})

@main.route('/tasks/<int:task_id>/can_edit', methods=['GET'])
@login_required
def can_edit_task(task_id):
    task = Task.query.get_or_404(task_id)
    
    # Same permission logic as update_status
    is_project_manager = db.session.query(membership).filter_by(
        project_id=task.assignment.source_project_id,
        user_id=current_user.id,
        status='active',
        role='project_manager'
    ).first() is not None
    
    is_task_coordinator = False
    if not is_project_manager:
        task_coordinator = db.session.query(membership).filter_by(
            project_id=task.assignment.source_project_id,
            user_id=current_user.id,
            status='active',
            role='task_coordinator'
        ).first()
        
        if task_coordinator:
            is_task_coordinator = (
                task.assignment.assigned_by_user_id == current_user.id or
                current_user in task.assigned_users
            )
    
    is_assigned_contributor = (
        not is_project_manager and 
        not is_task_coordinator and 
        current_user in task.assigned_users and
        current_user in Project.query.filter_by(id=task.assignment.source_project_id).first().active_members
    )
    
    can_edit = any([is_project_manager, is_task_coordinator, is_assigned_contributor])
    
    return jsonify({'can_edit': can_edit})

@main.route('/projects/<int:project_id>/create_assignment', methods=['POST'])
@login_required
def create_task_assignment(project_id):
    project = Project.query.get_or_404(project_id)
    member = db.session.query(membership).filter_by(
        project_id=project.id,
        user_id=current_user.id,
        status='active'
    ).first()
    
    if not member or member.role not in ['project_manager', 'task_coordinator']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.get_json()
    if not data or 'title' not in data or 'tasks' not in data or not isinstance(data['tasks'], list):
        return jsonify({'success': False, 'message': 'Invalid request'}), 400
    
    title = data['title'].strip()
    comment = data.get('comment', '').strip()
    tasks_data = data['tasks']
    
    if not title or not tasks_data:
        return jsonify({'success': False, 'message': 'Title and at least one task required'}), 400
    
    assignment = TaskAssignment(
        title=title,
        assigned_by_user_id=current_user.id,
        source_project_id=project_id,
        status='pending'
    )

    # Then if there's a comment, create a TaskAssignmentComment
    if comment:
        assignment_comment = TaskAssignmentComment(
            content=comment,
            user_id=current_user.id,
            assignment=assignment  # This links the comment to the assignment
        )
        db.session.add(assignment_comment)

    db.session.add(assignment)
    db.session.flush()

    # Create a dictionary to track users and their assigned task counts
    user_task_counts = {}
    
    for task_data in tasks_data:
        if 'title' not in task_data or not task_data['title'].strip():
            continue
            
        deadline = None
        if 'deadline' in task_data and task_data['deadline']:
            try:
                deadline = datetime.fromisoformat(task_data['deadline'])
            except ValueError:
                pass
        
        task = Task(
            title=task_data['title'].strip(),
            description=task_data.get('description', '').strip(),
            deadline=deadline,
            priority=task_data.get('priority', 'medium-priority'),
            status='pending',
            assignment_id=assignment.id
        )
        
        for todo_content in task_data.get('todos', []):
            if todo_content.strip():
                task.todos.append(Todo(content=todo_content.strip()))
        
        for user_id in task_data.get('assignees', []):
            user = User.query.get(user_id)
            if user and user in project.active_members:
                task.assigned_users.append(user)
                # Track task count per user
                if user.id not in user_task_counts:
                    user_task_counts[user.id] = 1
                else:
                    user_task_counts[user.id] += 1
        
        db.session.add(task)
    
    # Send notifications with accurate task counts per user
    for user_id, count in user_task_counts.items():
        add_notification(
            user_id=user_id,
            message=f"You were assigned {count} new task{'s' if count > 1 else ''} in '{title}' for project {project.title}",
            link=url_for('main.task_assignment', assignment_id=assignment.id),
            icon="task",
            sender_id=current_user.id
        )
        
    db.session.commit()
    
    return jsonify({
        'success': True, 
        'assignment': {
            'id': assignment.id,
            'title': assignment.title,
            'assigned_at': assignment.assigned_at.isoformat(),
            'status': assignment.status,
            'comment': comment,
            'assigned_by': {
                'id': current_user.id,
                'name': f"{current_user.fname} {current_user.lname}"
            },
            'task_count': len(assignment.task)
        }
    })


@main.route('/projects/<int:project_id>/add_discussion', methods=['POST'])
@login_required
def add_project_discussion(project_id):
    project = Project.query.get_or_404(project_id)
    is_member = db.session.execute(
        db.select(membership).where(
            and_(
                membership.c.project_id == project.id,
                membership.c.user_id == current_user.id,
                membership.c.status == "active"
            )
        )
    ).first()
    
    if not is_member:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.get_json()
    if not data or 'content' not in data:
        return jsonify({'success': False, 'message': 'Content required'}), 400
    
    content = data['content'].strip()
    if not content:
        return jsonify({'success': False, 'message': 'Content cannot be empty'}), 400
    
    assignment_id = data.get('assignment_id')
    
    if assignment_id:
        comment = TaskAssignmentComment(
            assignment_id=assignment_id,
            user_id=current_user.id,
            content=content
        )
        db.session.add(comment)
    else:
        discussion = ProjectDiscussion(
            project_id=project_id,
            user_id=current_user.id,
            content=content
        )
        db.session.add(discussion)
    
    db.session.commit()
    
    return jsonify({'success': True})


@main.route('/projects/<int:project_id>/discussions', methods=['GET'])
@login_required
def get_project_discussions(project_id):
    project = Project.query.get_or_404(project_id)
    
    discussions = ProjectDiscussion.query.filter_by(
        project_id=project.id
    ).order_by(
        ProjectDiscussion.created_at.desc()
    ).all()
    
    assignment_comments = TaskAssignmentComment.query.join(
        TaskAssignment
    ).filter(
        TaskAssignment.source_project_id == project.id
    ).order_by(
        TaskAssignmentComment.created_at.desc()
    ).all()
    
    all_comments = []
    
    for d in discussions:
        all_comments.append({
            'type': 'discussion',
            'id': d.id,
            'content': d.content,
            'created_at': d.created_at,
            'user': {
                'id': d.user.id,
                'name': f"{d.user.fname} {d.user.lname}",
                'username': d.user.username,
                'avatar': url_for('static', filename='images/profiles/' + d.user.profile_img)
            }
        })
    
    for c in assignment_comments:
        all_comments.append({
            'type': 'assignment_comment',
            'id': c.id,
            'content': c.content,
            'created_at': c.created_at,
            'user': {
                'id': c.user.id,
                'name': f"{c.user.fname} {c.user.lname}",
                'username': c.user.username,
                'avatar': url_for('static', filename='images/profiles/' + c.user.profile_img)
            },
            'assignment': {
                'id': c.assignment.id,
                'title': c.assignment.title
            }
        })
    
    all_comments.sort(key=lambda x: x['created_at'], reverse=True)
    
    return jsonify({'success': True, 'discussions': all_comments})

@main.route("/profile")
@login_required
def profile():
    user = current_user
    formatted_date_joined = format_date(user.joined_at.date() if isinstance(user.joined_at, datetime) else user.joined_at)
    formatted_dob = format_date(user.dob.date() if isinstance(user.dob, datetime) else user.dob)
    dates = {'joined': formatted_date_joined, 'birth': formatted_dob}
    return render_template("profile.html", user=current_user, user_profile_info=current_user, active_page=None, dates=dates)

def clean(value):
    return None if value in (None, '') else value

@main.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    from app import db

    if request.method == 'POST':
        try:
            data = request.get_json()
            
            # Update user profile in database
            # Example (adjust according to your ORM):
            user = User.query.get(current_user.id)
            user.fname = clean(data.get('fname', user.fname))
            user.lname = clean(data.get('lname', user.lname))
            user.bio = clean(data.get('bio', user.bio))
            user.phone = clean(data.get('phone', user.phone))
            dob_str = data.get('dob')
            if dob_str:
                try:
                    user.dob = datetime.strptime(dob_str, "%m/%d/%Y")
                except ValueError:
                    return jsonify({'success': False, 'error': 'Invalid date format. Use MM/DD/YYYY.'}), 400
            else:
                user.dob = None
            user.address = clean(data.get('address', user.address))
            user.city = clean(data.get('city', user.city))
            user.state = clean(data.get('state', user.state))
            user.zip = clean(data.get('zip', user.zip))
            
            db.session.commit()
            return jsonify({'success': True}), 200
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 400

@main.route('/update_profile_image', methods=['POST'])
@login_required
def update_profile_image():
    from app import db

    if 'profile_image' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400
    
    file = request.files['profile_image']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No selected file'}), 400
    
    if file:
        try:
            # Generate filename
            filename = f"profile_{current_user.id}.jpg"
            s3_key = f"static/images/uploads/profile_img/{filename}"
            
            if current_app.config['USE_S3']:
                upload_file_to_s3(file, s3_key)
            else:
                # Local filesystem
                local_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'profile_img')
                os.makedirs(local_path, exist_ok=True)
                file.save(os.path.join(local_path, filename))
            
            # Update database
            user = User.query.get(current_user.id)
            user.profile_img = filename
            db.session.commit()
            
            return jsonify({'success': True}), 200
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
        
@main.route('/user/<username>')
def public_profile(username):
    from app import db
    
    # Check if user is viewing their own profile
    if current_user.is_authenticated and current_user.username == username:
        return redirect(url_for('main.profile'))
    
    # Get the requested user's profile
    user_profile = User.query.filter_by(username=username).first_or_404()
    
    # Get projects where the user is a member
    user_projects = Project.query.filter(
        Project.active_members.any(id=user_profile.id)
    ).all()
    
    for project in user_projects:
        # Calculate project progress based on completed tasks
        total_tasks = len(project.task_assignment)
        project.task_count = total_tasks
        
        # Get user's role in this project
        membership_record = db.session.query(membership).filter(
            membership.c.project_id == project.id,
            membership.c.user_id == user_profile.id
        ).first()
        project.user_role = membership_record.role if membership_record else None

    return render_template('public_profile.html', 
                         user_profile=user_profile, 
                         user=current_user, 
                         projects=user_projects)

@main.route('/connect/<username>', methods=['POST'])
@login_required
def connect_user(username):
    from app import db

    user = User.query.filter_by(username=username).first_or_404()
    if current_user.is_connected(user):
        return jsonify({'success': False, 'error': 'Already connected'})
    
    current_user.connect(user)
    
    # Add notification to the user being followed
    add_notification(
        user_id=user.id,
        message=f"{current_user.username} connected with you",
        link=url_for('main.connections'),
        icon="user-follow",
        sender_id=current_user.id
    )
    
    db.session.commit()
    return jsonify({
        'success': True,
        'new_count': user.followers.count()
    })

@main.route('/disconnect/<username>', methods=['POST'])
@login_required
def disconnect_user(username):
    from app import db
    
    user = User.query.filter_by(username=username).first_or_404()
    if not current_user.is_connected(user):
        return jsonify({'success': False, 'error': 'Not connected'})
    
    current_user.disconnect(user)
    db.session.commit()
    return jsonify({
        'success': True,
        'new_count': user.followers.count()
    })

@main.route('/my-connections')
@login_required
def connections():
    from app import db

    try:
        connections = current_user.get_connections().all()
        followers = current_user.followers.all()
        
        # Get suggestions in same transaction
        suggested_users = current_user.get_suggested_users(limit=6)
        
        return render_template('connections.html',
                            connections=connections,
                            followers=followers,
                            suggested_users=suggested_users,
                            user=current_user,
                            active_page="connections")
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Connections page error: {str(e)}")
        flash("An error occurred while loading connections", "error")
        return redirect(url_for('main.dashboard'))
    
@main.route('/connections/<username>')
@login_required
def user_connections(username):
    # Get the user whose connections we want to view
    profile_user = User.query.filter_by(username=username).first_or_404()
    
    # Don't allow viewing your own connections through this route
    if current_user.id == profile_user.id:
        return redirect(url_for('main.connections'))
    
    # Get the user's connections and followers
    connections = profile_user.get_connections().all()
    followers = profile_user.followers.all()
    
    return render_template('connections.html',
                        connections=connections,
                        followers=followers,
                        suggested_users=[],  # No suggestions when viewing others' connections
                        profile_user=profile_user,  # Pass the profile user
                        user=current_user,
                        active_page="connections")

@main.route('/search')
@login_required
def search():
    from app import db

    query = request.args.get('q', '').strip()
    if not query:
        return redirect(request.referrer or url_for('main.index'))

    # Search Users (public)
    users = User.query.filter(
        User.id != current_user.id,
        db.or_(
            User.username.ilike(f'%{query}%'),
            User.fname.ilike(f'%{query}%'),
            User.lname.ilike(f'%{query}%')
        )
    ).limit(5).all()

    # Search Projects (user is member or public projects)
    projects = Project.query.filter(
        db.or_(
            Project.title.ilike(f'%{query}%'),
            Project.description.ilike(f'%{query}%')
        ),
        db.or_(
            Project.type == 'public-open',
            Project.type == 'public-closed',
            Project.active_members.any(id=current_user.id)
        )
    ).limit(5).all()

    # Search Tasks (only tasks assigned to current user)
    tasks = Task.query.join(
        task_user_association,
        (task_user_association.c.task_id == Task.id)
    ).filter(
        task_user_association.c.user_id == current_user.id,
        db.or_(
            Task.title.ilike(f'%{query}%'),
            Task.description.ilike(f'%{query}%')
        )
    ).limit(5).all()

    return render_template('search_results.html',
                         query=query,
                         users=users,
                         projects=projects,
                         tasks=tasks,
                         user=current_user,)

@main.route('/search/suggest')
@login_required
def search_suggest():
    from app import db

    query = request.args.get('q', '').strip()
    results = []
    
    if len(query) >= 2:  # Only search if query has at least 2 characters
        # Users
        users = User.query.filter(
            User.id != current_user.id,
            db.or_(
                User.username.ilike(f'%{query}%'),
                User.fname.ilike(f'%{query}%'),
                User.lname.ilike(f'%{query}%')
            )
        ).limit(3).all()
        
        # Projects (user is member or public)
        projects = Project.query.filter(
            db.or_(
                Project.title.ilike(f'%{query}%'),
                Project.description.ilike(f'%{query}%')
            ),
            db.or_(
                Project.type == 'public-open',
                Project.type == 'public-closed',
                Project.active_members.any(id=current_user.id)
            )
        ).limit(3).all()
        
        # Format results
        results = [
            *[{
                'type': 'user',
                'name': f"{u.fname} {u.lname} (@{u.username})",
                'username': u.username
            } for u in users],
            *[{
                'type': 'project', 
                'name': p.title,
                'id': p.id
            } for p in projects]
        ]
    
    return jsonify(results)

@main.route('/explore-users')
@login_required
def explore_users():
    from app import db
    
    page = request.args.get('page', 1, type=int)
    query = request.args.get('q', '')

    # Base query with proper exclusions
    users_query = User.query.filter(
        User.id != current_user.id,
        ~User.followers.any(id=current_user.id)
    )
    
    if query:
        # Search logic
        users_query = users_query.filter(
            db.or_(
                User.username.ilike(f'%{query}%'),
                User.fname.ilike(f'%{query}%'),
                User.lname.ilike(f'%{query}%')
            )
        )
    else:
        # Enhanced discovery with fallbacks
        users_query = users_query.order_by(
            db.case(
                # Boost users from same projects
                (User.id.in_([u.id for u in current_user._get_same_project_users([], 100)]), 0),
                # Then second-degree connections
                (User.id.in_([u.id for u in current_user._get_second_degree_connections([], 100)]), 1),
                else_=2
            ),
            User.joined_at.desc()  # Secondary ordering
        )
    
    pagination = users_query.paginate(page=page, per_page=20, error_out=False)
    users = pagination.items
    
    return render_template('explore_users.html',
                         users=users,
                         pagination=pagination,
                         user=current_user)

@main.route("/explore-projects")
@login_required
def explore_projects():
    # Get filter parameters
    search_query = request.args.get('q', '')
    project_type = request.args.get('type', 'all')
    sort_by = request.args.get('sort', 'popular')
    min_upvotes = request.args.get('min_upvotes', 0, type=int)
    
    # Base query
    query = Project.query

    query = query.filter(
        or_(
            Project.type == 'public-open',
            Project.type == 'public-closed',
        )
    ).filter(
    not_(
        Project.members.any(
            and_(
                membership.c.user_id == current_user.id,
            )
        )
    ))
    
    # Apply filters
    if search_query:
        query = query.filter(
            or_(
                Project.title.ilike(f'%{search_query}%'),
                Project.description.ilike(f'%{search_query}%')
            )
        )
    
    if project_type != 'all':
        query = query.filter(Project.type == project_type)

    UpvoteAlias = aliased(upvotes)

    # Join upvotes if sorting by popular or filtering by min_upvotes
    if sort_by == 'popular' or min_upvotes > 0:
        query = query.outerjoin(UpvoteAlias, Project.id == UpvoteAlias.c.project_id)

    # Apply sorting
    if sort_by == 'recent':
        query = query.order_by(Project.created_at.desc())
    elif sort_by == 'title':
        query = query.order_by(Project.title.asc())
    elif sort_by == 'active':
        query = query.order_by(Project.updated_at.desc())
    elif sort_by == 'popular':
        query = query.group_by(Project.id).order_by(func.count(UpvoteAlias.c.user_id).desc())

    # Apply min upvotes filter
    if min_upvotes > 0:
        query = query.group_by(Project.id).having(func.count(UpvoteAlias.c.user_id) >= min_upvotes)

    projects = query.all()

    return render_template(
        'explore_projects.html',
        projects=projects,
        user=current_user,
        search_query=search_query,
        project_type=project_type,
        sort_by=sort_by,
        min_upvotes=min_upvotes
    )

@main.route("/dashboard/tasks/new", methods=['GET','POST'])
@login_required
def create_task():
    from app import db

    form = CreateTask()
    if form.validate_on_submit():
        form_data = form.data
        form_data.pop("submit", None)
        form_data.pop("csrf_token", None)
        
        # Create the task
        task = Task(**form_data)
        
        # Create the task assignment
        assignment = TaskAssignment()
        assignment.title = "Self Assigned Task"
        assignment.task.append(task)
        assignment.user = current_user
        
        # Add the current user to the task's assigned users
        task.assigned_users.append(current_user)
        
        db.session.add_all([task, assignment])
        db.session.commit()
        flash("Task created successfully", "success")
        return redirect(url_for("main.task", task_id=task.id))
    return render_template("new_task.html", user=current_user, active_page="tasks", form=form)

@main.route('/tasks/<int:task_id>/generate_subtasks', methods=['POST'])
def generate_subtasks(task_id):
    # For new tasks (task_id = 0), get data from request body
    if task_id == 0:
        data = request.json
        deadline_str = data.get('deadline', None)

        # Convert deadline to datetime if it's provided
        deadline = None
        if deadline_str:
            try:
                deadline = datetime.strptime(deadline_str, "%m-%d-%Y")
            except ValueError:
                # handle unexpected format if needed
                deadline = None

        task = SimpleNamespace(
            title=data.get('title', ''),
            description=data.get('description', ''),
            priority=data.get('priority', 'medium-priority'),
            deadline=deadline
        )
    else:
        task = Task.query.get_or_404(task_id)
    
    try:
        subtasks = generate_ai_subtasks(task)
        return jsonify({
            'success': True,
            'subtasks': subtasks[:7]  # Limit to max 7 subtasks
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

@main.route('/tasks/<int:task_id>/add_subtasks', methods=['POST'])
def add_subtasks(task_id):
    task = Task.query.get_or_404(task_id)
    subtasks = request.json.get('subtasks', [])
    
    if not subtasks:
        return jsonify({'success': False, 'error': 'No subtasks provided'}), 400
    
    try:
        for subtask in subtasks:
            if subtask.strip():  # Skip empty subtasks
                todo = Todo(
                    content=subtask.strip(),
                    task_id=task.id
                )
                db.session.add(todo)
        
        db.session.commit()

        task = Task.query.get(task_id)
        completed = sum(1 for todo in task.todos if todo.is_completed)
        
        if not completed:
            task.status = "pending"
        elif completed == len(task.todos):
            task.status = "completed"
        else:
            task.status = "in progress"
        task.updated_at = func.now()
        db.session.commit()

        assignment = task.assignment
        completed_tasks = sum(1 for task in assignment.task if task.status == "completed")
        if not completed_tasks:
            assignment.status = "pending"
        elif completed_tasks == len(assignment.task):
            assignment.status = "completed"
        else:
            assignment.status = f"{completed_tasks}/{len(assignment.task)} tasks completed"
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@main.route('/tasks/generate_smart_queue', methods=['POST'])
def generate_smart_queue():
    tasks = Task.query.filter(Task.assigned_users.any(id=current_user.id)).all()

    # Filter out completed tasks
    active_tasks = [task for task in tasks if task.status.lower() != 'completed']
    if not active_tasks:
        return jsonify({'success': False, 'message': 'No active tasks found'}), 400
    
    try:
        result = generate_task_priority_analysis(active_tasks)
        return jsonify({
            'success': True,
            'task_order': result["task_order"],
            'summary': result["summary"]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@main.route("/dashboard/tasks/<int:task_id>")
@login_required
def task(task_id):
    task = Task.query.filter_by(id=task_id).first()

    # Todos
    todos = (
        Todo.query.filter_by(task=task)
        .order_by(Todo.created_at.asc())  # Order by most recently updated
        .all()
    )

    completed_todos = [todo for todo in todos if todo.is_completed]
    todos = [todo for todo in todos if not todo.is_completed]
    todos.extend(completed_todos) 

    if not task:
        return "Not Found", 404
    if current_user not in task.assigned_users:
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
        TaskProgress.made_at.between(start_date, today+timedelta(days=1))
    ).order_by(TaskProgress.made_at).all()

    # Structure data for chart
    max_value = 0
    current_value = 0
    x = 0
    chart_data = [{'x': x, 'y': current_value, 'day': start_date.isoformat(),},]
    
    for date in dates:
        # Get all progress changes for this date
        daily_changes = []
        for entry in progress_entries:
            if entry.made_at.date() == date:
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
            max_value=max(max_value, current_value)
            chart_data.append({
                'x': x, 
                'y': current_value,
                'day': date.isoformat(),
            })
            
    has_progress = any(entry.progress for entry in progress_entries) if progress_entries else False

    if task.deadline:
        deadline_from_now = (task.deadline.date() - today).days
    else:
        deadline_from_now = None
    task.deadline_from_now = deadline_from_now
    
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
    
    info = {'total': len(task.todos), 'advice': advice}

    # Other visualizations

    # 1. Prepare Daily Gauge Data
    today = datetime.today().date()
    today_progress = TaskProgress.query.filter(
        TaskProgress.task_id == task_id,
        func.date(TaskProgress.made_at) == today
    ).first()
    
    daily_percent = 0
    if today_progress and task.todos:
        daily_changes = sum(today_progress.progress)
        total_todos = len(task.todos)
        daily_percent = min(100, max(0, (daily_changes / total_todos) * 100))
    
    # 2. Create Mini Timeline Plot
    timeline_dates = []
    timeline_values = []
    for i in range(7, 0, -1):  # Last 7 days
        date = datetime.today() - timedelta(days=i)
        progress = TaskProgress.query.filter(
            TaskProgress.task_id == task_id,
            func.date(TaskProgress.made_at) == date.date()
        ).first()
        
        timeline_dates.append(date.strftime('%b %d'))
        timeline_values.append(sum(progress.progress) if progress else 0)
    
    timeline_fig = go.Figure(
        go.Scatter(
            x=timeline_dates,
            y=timeline_values,
            line=dict(color='#4e79a7', width=3, shape='spline'),
            marker=dict(size=8, color='#4e79a7'),
            fill='tozeroy',
            fillcolor='rgba(78, 121, 167, 0.2)'
        )
    )
    timeline_fig.update_layout(
        margin=dict(t=0, b=30, l=40, r=20),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(showgrid=False),
        yaxis=dict(gridcolor='rgba(255,255,255,0.1)')
    )
    timeline_json = json.dumps(timeline_fig, cls=plotly.utils.PlotlyJSONEncoder)
    
    # 3. Create Heatmap Plot
    heatmap_dates = []
    heatmap_values = []
    for i in range(14, 0, -1):  # Last 14 days
        date = datetime.today() - timedelta(days=i)
        progress = TaskProgress.query.filter(
            TaskProgress.task_id == task_id,
            func.date(TaskProgress.made_at) == date.date()
        ).first()
        
        heatmap_dates.append(date.strftime('%b %d'))
        heatmap_values.append(sum(progress.progress) if progress else 0)
    
    heatmap_fig = go.Figure(
        go.Heatmap(
            x=heatmap_dates,
            y=['Activity'],
            z=[heatmap_values],
            colorscale=[
                [0, 'rgba(255,255,255,0.1)'],
                [0.5, 'rgba(100, 200, 255, 0.5)'],
                [1, '#4e79a7']
            ],
            showscale=False
        )
    )
    heatmap_fig.update_layout(
        margin=dict(t=0, b=30, l=20, r=20),
        paper_bgcolor='rgba(0,0,0,0)'
    )
    heatmap_json = json.dumps(heatmap_fig, cls=plotly.utils.PlotlyJSONEncoder)

    return render_template("task.html", 
                            user=current_user, 
                            task=task, 
                            todos=todos,
                            active_page="tasks", 
                            info=info,
                            chart_data=chart_data,
                            date_labels=date_labels,
                            todos_total=todos_total,
                            max_value=max(max_value, todos_total),
                            has_progress=has_progress,
                            daily_percent=daily_percent,
                            timeline_json=timeline_json,
                            heatmap_json=heatmap_json,
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
    
    if not completed:
        task.status = "pending"
    elif completed == len(task.todos):
        task.status = "completed"
    else:
        task.status = "in progress"
    task.updated_at = func.now()
    db.session.commit()

    assignment = task.assignment
    completed_tasks = sum(1 for task in assignment.task if task.status == "completed")
    if not completed_tasks:
        assignment.status = "pending"
    elif completed_tasks == len(assignment.task):
        assignment.status = "completed"
    else:
        assignment.status = f"{completed_tasks}/{len(assignment.task)} tasks completed"
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

    progress_val = data['progress']
    if not isinstance(progress_val, list) or not all(isinstance(x, (int, float)) for x in progress_val):
        return jsonify({"error": "Invalid progress"}), 400

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
    
    if not completed:
        task.status = "pending"
    elif completed == len(task.todos):
        task.status = "completed"
    else:
        task.status = "in progress"
    task.updated_at = func.now()
    db.session.commit()

    assignment = task.assignment
    completed_tasks = sum(1 for task in assignment.task if task.status == "completed")
    if not completed_tasks:
        assignment.status = "pending"
    elif completed_tasks == len(assignment.task):
        assignment.status = "completed"
    else:
        assignment.status = f"{completed_tasks}/{len(assignment.task)} tasks completed"
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
    
    if not completed:
        task.status = "pending"
    elif completed == len(task.todos):
        task.status = "completed"
    else:
        task.status = "in progress"
    task.updated_at = func.now()
    db.session.commit()

    assignment = task.assignment
    completed_tasks = sum(1 for task in assignment.task if task.status == "completed")
    if not completed_tasks:
        assignment.status = "pending"
    elif completed_tasks == len(assignment.task):
        assignment.status = "completed"
    else:
        assignment.status = f"{completed_tasks}/{len(assignment.task)} tasks completed"
    db.session.commit()

    return jsonify({'message': 'Todo deleted'}), 200

@main.route("/tasks/<int:task_id>/update", methods=["POST"])
@login_required
def update_task(task_id):
    from app import db
    
    try:
        # Validate CSRF token
        validate_csrf(request.headers.get('X-CSRFToken'))
    except ValidationError:
        return jsonify({"error": "Invalid CSRF token"}), 400

    task = Task.query.get_or_404(task_id)
    
    # Check if user has permission to edit this task
    if current_user not in task.assigned_users:
        return jsonify({"error": "You don't have permission to edit this task"}), 403

    data = request.get_json()
    
    # Update task fields if they are present in the request
    if 'title' in data:
        task.title = data['title']
    if 'description' in data:
        task.description = data['description']
    if 'priority' in data:
        task.priority = data['priority']
    if 'deadline' in data:
        if data['deadline']:
            task.deadline = datetime.strptime(data['deadline'], '%Y-%m-%d')
        else:
            task.deadline = None
    
    task.updated_at = func.now()
    db.session.commit()

    return jsonify({"success": True}), 200

@main.route('/dashboard/notifications')
@login_required
def notifications_page():
    # Mark all notifications as read when user visits the page
    mark_notifications_as_read(current_user.id)
    
    notifications = get_user_notifications(current_user.id)
    return render_template('notifications.html', notifications=notifications, user=current_user, active_page="notifications")

@main.route('/api/notifications')
@login_required
def get_notifications():
    notifications = get_user_notifications(current_user.id)
    return jsonify([n.to_dict() for n in notifications])

@main.route('/api/notifications/unread-count')
@login_required
def unread_count():
    count = get_unread_count(current_user.id)
    return jsonify({'count': count})

@main.route('/api/notifications/mark-read', methods=['POST'])
@login_required
def mark_read():
    data = request.get_json()
    notification_ids = data.get('notification_ids', None)
    
    if mark_notifications_as_read(current_user.id, notification_ids):
        return jsonify({'success': True})
    return jsonify({'success': False}), 400