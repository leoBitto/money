from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required
from datetime import datetime
from scripts.database import insert_batch_universe, execute_query
from scripts.google_services import get_universe_tickers_from_gsheet
from scripts.data_fetcher import get_data_for_db_between_dates


views_bp = Blueprint("views", __name__)

@views_bp.route("/")
@login_required
def welcome():
    return render_template("welcome.html")

@views_bp.route("/run-script", methods=["POST"])
def run_script():
    try:
        start_date = request.form.get("start_date")
        end_date = request.form.get("end_date") or datetime.today().strftime("%Y-%m-%d")

        if not start_date:
            flash("Devi specificare una data di inizio", "danger")
            return redirect(url_for("views.welcome"))

        # 1. Prendo i tickers da Google Sheets
        tickers = get_universe_tickers_from_gsheet()
        flash(f"Tickers : {tickers}")
        # 2. Trunco la tabella universe
        execute_query("TRUNCATE TABLE universe RESTART IDENTITY CASCADE", fetch=False)

        # 3. Scarico i dati da yfinance
        rows = get_data_for_db_between_dates(tickers, start_date, end_date)

        # 4. Inserisco i dati nel DB
        inserted = insert_batch_universe(rows, conflict_resolution="DO NOTHING")

        flash(f"Script eseguito correttamente ✅ ({inserted} righe inserite)", "success")
    except Exception as e:
        flash(f"Errore durante l'esecuzione: {e}", "danger")

    return redirect(url_for("views.welcome"))

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