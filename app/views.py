from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required
from datetime import datetime
from scripts.database import insert_batch_universe, execute_query
from scripts.google_services import get_universe_tickers_from_gsheet
from scripts.data_fetcher import get_data_for_db_between_dates
import logging
import os
from logging.handlers import TimedRotatingFileHandler

# Assicurati che la cartella esista
os.makedirs("logs", exist_ok=True)

# Logger principale
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Rotating file handler giornaliero
handler = TimedRotatingFileHandler("logs/app.log", when="midnight", interval=1)
handler.suffix = "%Y-%m-%d"
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)


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
            logger.warning("Esecuzione script fallita: data di inizio mancante")
            return redirect(url_for("views.welcome"))

        # 1. Prendo i tickers da Google Sheets
        tickers = get_universe_tickers_from_gsheet()
        logger.info(f"Tickers scaricati: {tickers}")

        execute_query("TRUNCATE TABLE universe RESTART IDENTITY CASCADE", fetch=False)
        logger.info("Tabella universe troncata")

        rows = get_data_for_db_between_dates(tickers, start_date, end_date)
        inserted = insert_batch_universe(rows, conflict_resolution="DO NOTHING")

        flash(f"Script eseguito correttamente ✅ ({inserted} righe inserite)", "success")
        logger.info(f"Script eseguito correttamente: {inserted} righe inserite")
    except Exception as e:
        flash(f"Errore durante l'esecuzione: {e}", "danger")
        logger.exception(f"Errore esecuzione script: {e}")  # logga stacktrace completa


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
                columns = column_names
                results = fetched
                logger.info(f"Query eseguita correttamente: {query}")
            else:
                error = "⚠️ Nessun risultato"
                logger.warning(f"Query senza risultati: {query}")
        except Exception as e:
            error = f"❌ Errore SQL: {e}"
            logger.exception(f"Errore SQL durante l'esecuzione della query: {query}")


    return render_template(
        "fragments/query_results.html",
        results=results,
        columns=columns,
        error=error
    )