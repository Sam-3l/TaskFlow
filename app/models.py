from sqlalchemy.orm import backref
from . import db
from flask_login import UserMixin
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.sql import func

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key = True)
    fname = db.Column(db.String(150), nullable=False)
    lname = db.Column(db.String(150), nullable=False)
    gender = db.Column(db.String(15), nullable=False)
    username = db.Column(db.String(150), nullable=False, unique=True)
    address = db.Column(db.String(150), nullable=True)
    dob = db.Column(db.Date, nullable=False)
    email = db.Column(db.String(150), nullable=False, unique=True)
    phone = db.Column(db.String(50), nullable=False)
    city = db.Column(db.String(150), nullable=False)
    state = db.Column(db.String(150), nullable=False)
    zip = db.Column(db.String(150), nullable=False)
    bio = db.Column(db.Text, default="Hey there.\nStay proactive.")
    date_joined = db.Column(db.Date, default=func.current_date())
    password = db.Column(db.String(150), nullable=False)
    profile_img = db.Column(db.String(120), default="default_male.jpg")
    task = db.relationship("Task", back_populates="user", cascade="all, delete-orphan")
    task_assignment = db.relationship("TaskAssignment", back_populates="user", cascade="all, delete-orphan")
    
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

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(60), nullable=False)
    description = db.Column(db.Text) # Can be edited or inputed by the user the task is assigned to
    content = db.Column(db.Text, nullable=True)
    modified_last = db.Column(db.Date, default=func.current_date())
    deadline = db.Column(db.Date, nullable=True)
    priority = db.Column(db.String(30), nullable=True)
    status = db.Column(db.String(30), default="pending")
    assigned_to_user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user = db.relationship("User", back_populates="task")
    assignment_id = db.Column(db.Integer, db.ForeignKey("task_assignment.id"))
    assignment = db.relationship("TaskAssignment", back_populates="task")
    task_progress = db.relationship("TaskProgress", back_populates="task", cascade="all, delete-orphan")

class TaskProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("task.id"))
    task = db.relationship("Task", back_populates="task_progress")
    date_made = db.Column(db.Date, default=func.current_date())
    progress = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.Text, nullable=True)

# Many To Many Association Tables

membership = db.Table("ProjectMembership",
    db.Column("project_id", db.Integer, db.ForeignKey("project.id"), primary_key=True),
    db.Column("user_id", db.Integer, db.ForeignKey("user.id"), primary_key=True),
    db.Column("date_joined", db.Date, default=func.current_date()),
    db.Column("roles", ARRAY(db.String(30))),
    db.Column("status", db.String(30)) # pending, active, inactive(past member)
    )

upvotes = db.Table("Upvotes",
    db.Column("project_id", db.Integer, db.ForeignKey("project.id"), primary_key=True),
    db.Column("user_id", db.Integer, db.ForeignKey("user.id"), primary_key=True),
    db.Column("date_upvoted", db.Date, default=func.current_date())
    )

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(60), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    type = db.Column(db.String(10), default="closed")
    project_links = db.Column(db.String(255), nullable=True)
    task_assignment = db.relationship("TaskAssignment", back_populates="source", cascade="all, delete-orphan")
    members = db.relationship("User", secondary=membership, backref="member_to")
    upvotes = db.relationship("User", secondary=upvotes, backref="upvote_to")

class TaskAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(60), nullable=False)
    assigned_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user = db.relationship("User", back_populates="task_assignment")
    date_assigned = db.Column(db.Date, default=func.current_date())
    task = db.relationship("Task", back_populates="assignment", cascade="all, delete-orphan")
    source_project_id = db.Column(db.Integer, db.ForeignKey("project.id"))
    source = db.relationship("Project", back_populates="task_assignment")
    status = db.Column(db.String(40), default="pending") # E.g 3/5 tasks completed
    comment = db.Column(db.Text, nullable=True)

# 7 Database Tables.