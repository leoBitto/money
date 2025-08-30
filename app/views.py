from flask import Blueprint, render_template
from flask_login import login_required
from scripts.database import execute_query

views_bp = Blueprint("views", __name__)

@views_bp.route("/")
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

@views_bp.route("/database", methods=["GET"])
@login_required
def database():
    # Mostriamo la pagina con il form, niente risultati ancora
    return render_template("database.html")


@views_bp.route("/database/run", methods=["POST"])
@login_required
def run_query():
    query = request.form.get("query")
    results = []
    columns = []

    if query:
        try:
            fetched = execute_query(query)
            if fetched:
                columns = [desc[0] for desc in fetched[0]._fields] if hasattr(fetched[0], "_fields") else [f"Col{i}" for i in range(len(fetched[0]))]
                results = fetched
        except Exception as e:
            return f"<div class='alert alert-danger'>❌ Errore: {e}</div>"

    # Ritorniamo solo il frammento HTML della tabella
    return render_template("fragments/query_results.html", results=results, columns=columns)
