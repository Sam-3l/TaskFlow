import math
from flask.helpers import flash
from flask import Blueprint, render_template, redirect, url_for, current_app
from flask_login import login_required, current_user
from flask import request, jsonify
from flask_wtf.csrf import validate_csrf
from wtforms import ValidationError
from sqlalchemy.sql import func
from sqlalchemy import case

import plotly
import plotly.graph_objs as go
import pandas as pd
import json
import os
from werkzeug.utils import secure_filename
import time

from app.models import Task, User, TaskAssignment, Todo, TaskProgress, membership, Project, task_user_association, ProjectDiscussion, TaskAssignmentComment
from app.forms import CreateTask, CreateProject

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

@main.route("/dashboard/projects")
@login_required
def projects():
    from app import db
    # Get all projects where the user is a member
    user_projects = Project.query.filter(Project.members.any(id=current_user.id)).all()
    
    # Add progress, task count, and user role to each project
    for project in user_projects:
        # Calculate project progress based on completed tasks
        total_tasks = len(project.task_assignment)
        completed_tasks = len([t for t in project.task_assignment if t.status == "completed"])
        project.progress = int((completed_tasks / total_tasks * 100) if total_tasks > 0 else 0)
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
                # Ensure the upload directory exists
                upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'project_covers')
                os.makedirs(upload_dir, exist_ok=True)
                # Save the file
                file.save(os.path.join(upload_dir, filename))
                project.cover_image = filename
        
        db.session.add(project)
        db.session.commit()  # Commit first to get project.id
        
        # Add the creator as a project manager
        db.session.execute(
            membership.insert().values(
                project_id=project.id,  # Now we have the project.id
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

    project = Project.query.get_or_404(project_id)
    current_membership = db.session.query(membership).filter_by(
        project_id=project.id,
        user_id=current_user.id
    ).first()
    
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
    
    # Get discussions
    discussions = ProjectDiscussion.query.filter_by(
        project_id=project.id
    ).order_by(
        ProjectDiscussion.created_at.desc()
    ).all()
    
    # Get tasks for Kanban board
    tasks = Task.query.join(
        TaskAssignment
    ).filter(
        TaskAssignment.source_project_id == project.id
    ).all()
    
    # Organize tasks by status for Kanban
    kanban_columns = {
        'Backlog': [],
        'To Do': [],
        'In Progress': [],
        'Review': [],
        'Done': []
    }
    
    for task in tasks:
        status = task.status if task.status in kanban_columns else 'Backlog'
        kanban_columns[status].append(task)
    
    return render_template(
        'project.html',
        user=current_user,
        active_page="projects",
        project=project,
        current_membership=current_membership,
        members=members,
        task_assignments=task_assignments,
        discussions=discussions,
        kanban_columns=kanban_columns
    )

from app import db

@main.route('/projects/<int:project_id>/update_cover', methods=['POST'])
@login_required
def update_project_cover(project_id):
    project = Project.query.get_or_404(project_id)
    membership = db.session.query(membership).filter_by(
        project_id=project.id,
        user_id=current_user.id,
        role='project_manager'
    ).first()
    
    if not membership:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    if 'cover_image' not in request.files:
        return jsonify({'success': False, 'message': 'No file uploaded'}), 400
    
    file = request.files['cover_image']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No selected file'}), 400
    
    if file:
        filename = secure_filename(f"project_{project_id}_{datetime.now().timestamp()}.{file.filename.split('.')[-1]}")
        upload_folder = os.path.join(current_app.root_path, 'static', 'images', 'project_covers')
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
    membership = db.session.query(membership).filter_by(
        project_id=project.id,
        user_id=current_user.id,
        role='project_manager'
    ).first()
    
    if not membership:
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

@main.route('/projects/<int:project_id>/update_description', methods=['POST'])
@login_required
def update_project_description(project_id):
    project = Project.query.get_or_404(project_id)
    membership = db.session.query(membership).filter_by(
        project_id=project.id,
        user_id=current_user.id,
        role='project_manager'
    ).first()
    
    if not membership:
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
    
    # Search in connections first
    connections = current_user.get_connections().filter(
        (User.username.ilike(f'%{query}%')) | 
        (User.email.ilike(f'%{query}%')) |
        (User.fname.ilike(f'%{query}%')) |
        (User.lname.ilike(f'%{query}%'))
    ).limit(10).all()
    
    # Then search in all users if not enough results
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
    membership = db.session.query(membership).filter_by(
        project_id=project.id,
        user_id=current_user.id,
        role='project_manager'
    ).first()
    
    if not membership:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.get_json()
    if not data or 'user_id' not in data or 'role' not in data:
        return jsonify({'success': False, 'message': 'Invalid request'}), 400
    
    user_id = data['user_id']
    role = data['role']
    
    if role not in ['project_manager', 'task_coordinator', 'contributor']:
        return jsonify({'success': False, 'message': 'Invalid role'}), 400
    
    # Check if user is already a member
    existing_member = db.session.query(membership).filter_by(
        project_id=project.id,
        user_id=user_id
    ).first()
    
    if existing_member:
        return jsonify({'success': False, 'message': 'User is already a member'}), 400
    
    # Add new member
    db.session.execute(
        membership.insert().values(
            project_id=project.id,
            user_id=user_id,
            role=role,
            status='active'
        )
    )
    db.session.commit()
    
    new_member = User.query.get(user_id)
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
    requesting_membership = db.session.query(membership).filter_by(
        project_id=project.id,
        user_id=current_user.id,
        role='project_manager'
    ).first()
    
    if not requesting_membership:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.get_json()
    if not data or 'user_id' not in data or 'role' not in data:
        return jsonify({'success': False, 'message': 'Invalid request'}), 400
    
    user_id = data['user_id']
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
        user_id=current_user.id,
        role='project_manager'
    ).first()
    
    if not requesting_membership:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.get_json()
    if not data or 'user_id' not in data:
        return jsonify({'success': False, 'message': 'Invalid request'}), 400
    
    user_id = data['user_id']
    
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
    
    is_assigned = current_user in task.assigned_users
    is_manager_or_coordinator = False
    
    if not is_assigned:
        assignment = TaskAssignment.query.get(task.assignment_id)
        if assignment:
            membership = db.session.query(membership).filter_by(
                project_id=assignment.source_project_id,
                user_id=current_user.id
            ).first()
            
            if membership and membership.role in ['project_manager', 'task_coordinator']:
                is_manager_or_coordinator = True
    
    if not is_assigned and not is_manager_or_coordinator:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.get_json()
    if not data or 'status' not in data:
        return jsonify({'success': False, 'message': 'Status required'}), 400
    
    task.status = data['status']
    db.session.commit()
    
    return jsonify({'success': True})

@main.route('/projects/<int:project_id>/create_assignment', methods=['POST'])
@login_required
def create_task_assignment(project_id):
    project = Project.query.get_or_404(project_id)
    membership = db.session.query(membership).filter_by(
        project_id=project.id,
        user_id=current_user.id
    ).first()
    
    if not membership or membership.role not in ['project_manager', 'task_coordinator']:
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
        comment=comment,
        assigned_by_user_id=current_user.id,
        source_project_id=project_id,
        status='pending'
    )
    db.session.add(assignment)
    db.session.flush()
    
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
            priority=task_data.get('priority', 'normal'),
            status='backlog',
            assignment_id=assignment.id
        )
        
        for todo_content in task_data.get('todos', []):
            if todo_content.strip():
                task.todos.append(Todo(content=todo_content.strip()))
        
        for user_id in task_data.get('assignees', []):
            user = User.query.get(user_id)
            if user and user in project.members:
                task.assigned_users.append(user)
        
        db.session.add(task)
    
    db.session.commit()
    
    return jsonify({
        'success': True, 
        'assignment': {
            'id': assignment.id,
            'title': assignment.title,
            'assigned_at': assignment.assigned_at.isoformat(),
            'status': assignment.status,
            'comment': assignment.comment,
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
    membership = db.session.query(membership).filter_by(
        project_id=project.id,
        user_id=current_user.id
    ).first()
    
    if not membership:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.get_json()
    if not data or 'content' not in data:
        return jsonify({'success': False, 'message': 'Content required'}), 400
    
    content = data['content'].strip()
    if not content:
        return jsonify({'success': False, 'message': 'Content cannot be empty'}), 400
    
    assignment_id = data.get('assignment_id')
    
    if assignment_id:
        # Add as task assignment comment
        comment = TaskAssignmentComment(
            assignment_id=assignment_id,
            user_id=current_user.id,
            content=content
        )
        db.session.add(comment)
    else:
        # Add as regular project discussion
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
    
    # Get regular discussions
    discussions = ProjectDiscussion.query.filter_by(
        project_id=project.id
    ).order_by(
        ProjectDiscussion.created_at.desc()
    ).all()
    
    # Get task assignment comments
    assignment_comments = TaskAssignmentComment.query.join(
        TaskAssignment
    ).filter(
        TaskAssignment.source_project_id == project.id
    ).order_by(
        TaskAssignmentComment.created_at.desc()
    ).all()
    
    # Combine and sort by created_at
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
    
    # Sort all by created_at descending
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
            user.fname = data.get('fname', user.fname)
            user.lname = data.get('lname', user.lname)
            user.bio = data.get('bio', user.bio)
            user.phone = data.get('phone', user.phone)
            user.dob = data.get('dob', user.dob)  # Ensure proper date parsing
            user.address = data.get('address', user.address)
            user.city = data.get('city', user.city)
            user.state = data.get('state', user.state)
            user.zip = data.get('zip', user.zip)
            
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
            save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'profile_img', filename)
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            
            # Save the file
            file.save(save_path)
            
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
    user_projects = Project.query.filter(Project.members.any(id=user_profile.id)).all()
    
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
            Project.type == 'public',
            Project.members.any(id=current_user.id)
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
                Project.type == 'public',
                Project.members.any(id=current_user.id)
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

@main.route('/explore')
@login_required
def explore():
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
    
    return render_template('explore.html',
                         users=users,
                         pagination=pagination,
                         user=current_user)

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
    
    if not completed:
        task.status = "pending"
    elif completed == len(task.todos):
        task.status = "completed"
    else:
        task.status = "in progress"
    task.updated_at = func.now()
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