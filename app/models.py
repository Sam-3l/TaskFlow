from . import db
from flask_login import UserMixin
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy import and_
from sqlalchemy.sql import func
import random
from flask import current_app
from datetime import datetime, timedelta
import secrets

connections = db.Table('user_connections',
    db.Column('follower_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('followed_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('timestamp', db.DateTime, default=func.current_timestamp())
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fname = db.Column(db.String(150), nullable=False)
    lname = db.Column(db.String(150), nullable=False)
    gender = db.Column(db.String(15), nullable=True)
    username = db.Column(db.String(150), nullable=False, unique=True)
    address = db.Column(db.String(150), nullable=True)
    dob = db.Column(db.Date, nullable=True)
    email = db.Column(db.String(150), nullable=False, unique=True)
    phone = db.Column(db.String(50), nullable=True)
    city = db.Column(db.String(150), nullable=True)
    state = db.Column(db.String(150), nullable=True)
    zip = db.Column(db.String(150), nullable=True)
    bio = db.Column(db.Text, default="Hey there.\nStay proactive.")
    joined_at = db.Column(db.DateTime, default=func.current_timestamp())
    password = db.Column(db.String(150), nullable=False)
    profile_img = db.Column(db.String(120), default="default_male.jpg")

    email_verified = db.Column(db.Boolean, default=False)
    email_verification_token = db.Column(db.String(100), unique=True)
    email_verification_sent_at = db.Column(db.DateTime)
    password_reset_token = db.Column(db.String(100), unique=True)
    password_reset_sent_at = db.Column(db.DateTime)

    tasks = db.relationship(
        "Task",
        secondary="task_user_association",
        back_populates="assigned_users"
    )

    task_assignment = db.relationship("TaskAssignment", back_populates="user", cascade="all, delete-orphan")

    followed = db.relationship(
        'User', secondary=connections,
        primaryjoin=(connections.c.follower_id == id),
        secondaryjoin=(connections.c.followed_id == id),
        backref=db.backref('followers', lazy='dynamic'), lazy='dynamic')

    def generate_verification_token(self):
        """Generate a unique verification token"""
        self.email_verification_token = secrets.token_urlsafe(32)
        self.email_verification_sent_at = datetime.utcnow()
        db.session.commit()
        return self.email_verification_token
    
    def generate_password_reset_token(self):
        """Generate a unique password reset token"""
        self.password_reset_token = secrets.token_urlsafe(32)
        self.password_reset_sent_at = datetime.utcnow()
        db.session.commit()
        return self.password_reset_token
    
    def verify_token(self, token, token_type='email'):
        """Verify if token is valid and not expired"""
        if token_type == 'email':
            return (self.email_verification_token == token and 
                    datetime.utcnow() < self.email_verification_sent_at + timedelta(hours=24))
        elif token_type == 'password':
            return (self.password_reset_token == token and 
                    datetime.utcnow() < self.password_reset_sent_at + timedelta(hours=1))
        return False
    
    def connect(self, user):
        if not self.is_connected(user):
            self.followed.append(user)
            return self
    
    def disconnect(self, user):
        if self.is_connected(user):
            self.followed.remove(user)
            return self
    
    def is_connected(self, user):
        try:
            return db.session.query(
                connections.c.followed_id
            ).filter(
                connections.c.follower_id == self.id,
                connections.c.followed_id == user.id
            ).count() > 0
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Connection check failed: {str(e)}")
            return False

    
    def get_connections(self):
        try:
            return User.query.join(
                connections, (connections.c.followed_id == User.id)
            ).filter(
                connections.c.follower_id == self.id
            )
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Failed to get connections: {str(e)}")
            return User.query.filter(False)  # Return empty queryset

    
    def get_suggested_users(self, limit=6, exclude_ids=None):
        """Smart algorithm with multiple fallback strategies"""
        if exclude_ids is None:
            exclude_ids = []
        exclude_ids.append(self.id)
        
        suggestions = []
        
        # Try different strategies in order of preference
        strategies = [
            self._get_same_project_users,
            self._get_second_degree_connections,
            self._get_new_active_users,
            self._get_random_active_users  # Final fallback
        ]
        
        for strategy in strategies:
            if len(suggestions) >= limit:
                break
            try:
                new_suggestions = strategy(exclude_ids, limit - len(suggestions))
                for user in new_suggestions:
                    if user.id not in exclude_ids and not self.is_connected(user):
                        suggestions.append(user)
                        exclude_ids.append(user.id)
            except Exception as e:
                current_app.logger.error(f"Suggestion strategy failed: {str(e)}")
        
        return suggestions[:limit]

    def _get_same_project_users(self, exclude_ids, limit):
        """Users from same projects (strongest signal)"""
        return User.query.join(
            membership, (membership.c.user_id == User.id)
        ).join(
            Project, (Project.id == membership.c.project_id)
        ).filter(
            Project.id.in_([p.id for p in self.member_to]),
            ~User.id.in_(exclude_ids)
        ).order_by(
            User.joined_at.desc()  # Prefer newer members
        ).distinct().limit(limit).all()

    def _get_second_degree_connections(self, exclude_ids, limit):
        """Connections of connections"""
        # First get the IDs of your connections
        your_connections_ids = [u.id for u in self.get_connections().all()]
        
        if not your_connections_ids:
            return []
        
        # Then find who they're connected to
        return User.query.join(
            connections, (connections.c.followed_id == User.id)
        ).filter(
            connections.c.follower_id.in_(your_connections_ids),
            ~User.id.in_(exclude_ids),
            User.id != self.id
        ).order_by(
            User.joined_at.desc()  # Changed from random() to a column that exists in SELECT
        ).distinct().limit(limit).all()

    def _get_new_active_users(self, exclude_ids, limit):
        """Recently joined active users"""
        return User.query.filter(
            User.id != self.id,
            ~User.id.in_(exclude_ids)
        ).order_by(
            User.joined_at.desc()
        ).limit(limit).all()

    def _get_random_active_users(self, exclude_ids, limit):
        """Final fallback - random active users"""
        # For PostgreSQL, we need to use a different approach for random
        return User.query.filter(
            User.id != self.id,
            ~User.id.in_(exclude_ids)
        ).order_by(
            User.joined_at.desc()  # Can't use random() with DISTINCT
        ).limit(limit).all()
    
    def __init__(self, gender, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if gender == "female":
            self.profile_img = "default_female.png"
        elif gender == "male":
            self.profile_img = "default_male.jpg"
        else:
            self.profile_img = "default_custom.jpg"
        self.gender = gender
    
    def __repr__(self) -> str:
        return f"<user {self.username}>"
    
# Association Table for Many to Many Relationship between User and Task
task_user_association = db.Table(
    'task_user_association',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('task_id', db.Integer, db.ForeignKey('task.id'), primary_key=True)
)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(60), nullable=False)
    description = db.Column(db.Text)
    todos = db.relationship("Todo", back_populates='task', lazy=True, cascade='all, delete-orphan')
    created_at = db.Column(db.DateTime, default=func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp())
    deadline = db.Column(db.DateTime, nullable=True)
    priority = db.Column(db.String(30), nullable=True)
    status = db.Column(db.String(30), default="pending") # pending, in progress, review, completed
    
    # User - Task M2M relationship:
    assigned_users = db.relationship(
        "User",
        secondary="task_user_association",
        back_populates="tasks"
    )

    assignment_id = db.Column(db.Integer, db.ForeignKey("task_assignment.id"))
    assignment = db.relationship("TaskAssignment", back_populates="task")
    task_progress = db.relationship("TaskProgress", back_populates="task", cascade="all, delete-orphan")


class Todo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(200), nullable=False)
    is_completed = db.Column(db.Boolean, default=False)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=func.current_timestamp())
    
    # Relationships
    task = db.relationship('Task', back_populates='todos')

class TaskProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("task.id"))
    task = db.relationship("Task", back_populates="task_progress")
    made_at = db.Column(db.DateTime, default=func.current_timestamp())
    progress = db.Column(ARRAY(db.Integer), nullable=False)
    notes = db.Column(db.Text, nullable=True)

# Many To Many Association Tables

membership = db.Table("ProjectMembership",
    db.Column("project_id", db.Integer, db.ForeignKey("project.id"), primary_key=True),
    db.Column("user_id", db.Integer, db.ForeignKey("user.id"), primary_key=True),
    db.Column("joined_at", db.DateTime, default=func.current_timestamp()),
    db.Column("role", db.String(30)),
    db.Column("status", db.String(30)) # pending, active, inactive
    )

upvotes = db.Table("Upvotes",
    db.Column("project_id", db.Integer, db.ForeignKey("project.id"), primary_key=True),
    db.Column("user_id", db.Integer, db.ForeignKey("user.id"), primary_key=True),
    db.Column("upvoted_at", db.DateTime, default=func.current_timestamp())
    )

class ProjectDiscussion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    # Relationships
    project = db.relationship("Project", backref=db.backref("discussions", lazy=True))
    user = db.relationship("User", backref=db.backref("discussions", lazy=True))

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(60), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    type = db.Column(db.String(20), default="public-open") # private, public-open, public-closed
    project_links = db.Column(db.String(255), nullable=True)
    cover_image = db.Column(db.String(255), nullable=True, default=lambda: f"default_project{random.randint(1, 3)}.jpg")
    task_assignment = db.relationship("TaskAssignment", back_populates="source", cascade="all, delete-orphan")
    members = db.relationship("User", secondary=membership, backref="member_to")
    active_members = db.relationship(
        "User",
        secondary=membership,
        primaryjoin=and_(
            membership.c.project_id == id,
            membership.c.status == 'active'
        ),
        backref="active_member_of",
        viewonly=True
    )
    upvotes = db.relationship("User", secondary=upvotes, backref="upvote_to")
    created_at = db.Column(db.DateTime, default=func.current_timestamp())
    updated_at = db.Column(db.DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp())

class TaskAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(60), nullable=False)
    assigned_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    assigned_at = db.Column(db.DateTime, default=func.current_timestamp())
    source_project_id = db.Column(db.Integer, db.ForeignKey("project.id"))
    status = db.Column(db.String(40), default="pending")  # E.g. 3/5 tasks completed

    user = db.relationship("User", back_populates="task_assignment")
    task = db.relationship("Task", back_populates="assignment", cascade="all, delete-orphan")
    source = db.relationship("Project", back_populates="task_assignment")
    comments = db.relationship("TaskAssignmentComment", back_populates="assignment", cascade="all, delete-orphan")

class TaskAssignmentComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('task_assignment.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=func.current_timestamp())

    assignment = db.relationship("TaskAssignment", back_populates="comments")
    user = db.relationship("User") 

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=func.current_timestamp())
    link = db.Column(db.String(255), nullable=True)
    icon = db.Column(db.String(50), nullable=True)  # For different notification types
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='notifications')
    sender = db.relationship('User', foreign_keys=[sender_id])

    def mark_as_read(self):
        self.is_read = True
        db.session.commit()

    def to_dict(self):
        return {
            'id': self.id,
            'message': self.message,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat(),
            'link': self.link,
            'icon': self.icon,
            'sender': {
                'id': self.sender.id if self.sender else None,
                'username': self.sender.username if self.sender else None,
                'profile_img': self.sender.profile_img if self.sender else None
            } if self.sender else None
        }