from flask import Blueprint, render_template
from flask_login import login_required

views_bp = Blueprint("views", __name__)

@views_bp.route("/welcome")
@login_required
def welcome():
    return render_template("welcome.html")

@views_bp.route("/analytics")
@login_required
def analytics():
    return render_template("analytics.html")

@views_bp.route("/portfolio")
@login_required
def portfolio():
    return render_template("portfolio.html")

@views_bp.route("/database")
@login_required
def database():
    return render_template("database.html")
