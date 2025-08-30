from flask import Blueprint, render_template, request
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
    query = request.form.get("query", "")
    results = []
    columns = []
    error = None

    if not query.strip():
        error = "⚠️ Nessuna query inviata"
    else:
        try:
            fetched, column_names = execute_query(query)
            if fetched:
                columns = column_names  # qui metti i nomi reali
                results = fetched
            else:
                error = "⚠️ Nessun risultato"
        except Exception as e:
            error = f"❌ Errore SQL: {e}"


    return render_template(
        "fragments/query_results.html",
        results=results,
        columns=columns,
        error=error
    )