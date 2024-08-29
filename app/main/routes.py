from flask import Blueprint, render_template
from flask_login import login_required, current_user

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