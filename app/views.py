from flask import Blueprint, render_template
from flask_login import login_required

views_bp = Blueprint("views", __name__)

@views_bp.route("/")
def home():
    return render_template("welcome.html")

@views_bp.route("/welcome")
@login_required
def welcome():
    return render_template("welcome.html")

@views_bp.route("/analytics")
@login_required
def analytics():
    return "<h2>📊 Analytics page (work in progress)</h2>"
