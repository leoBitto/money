from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required
from datetime import datetime
from scripts.database import insert_batch_universe, execute_query
from scripts.google_services import get_universe_tickers_from_gsheet
from scripts.data_fetcher import get_data_for_db_between_dates
from scripts.portfolio import Portfolio, Position, get_portfolio_names

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
            current_app.logger.warning("Esecuzione script fallita: data di inizio mancante")
            return redirect(url_for("views.welcome"))

        # 1. Prendo i tickers da Google Sheets
        tickers = get_universe_tickers_from_gsheet()
        current_app.logger.info(f"Tickers scaricati: {tickers}")

        execute_query("TRUNCATE TABLE universe RESTART IDENTITY CASCADE", fetch=False)
        current_app.logger.info("Tabella universe troncata")

        rows = get_data_for_db_between_dates(tickers, start_date, end_date)
        inserted = insert_batch_universe(rows, conflict_resolution="DO NOTHING")

        current_app.logger.info(f"Script eseguito correttamente: {inserted} righe inserite")
    except Exception as e:
        flash(f"Errore durante l'esecuzione: {e}", "danger")
        current_app.logger.exception(f"Errore esecuzione script: {e}")  # stacktrace completo

    return redirect(url_for("views.welcome"))

@views_bp.route("/analytics")
@login_required
def analytics():
    return render_template("analytics.html")

@views_bp.route("/portfolio", methods=["GET", "POST"])
@login_required
def portfolio():
    # Lista portfolio disponibili (da DB o configurazione)
    portfolios = Portfolio.list_available()  # puoi sostituire con query DB
    
    selected_portfolio = request.form.get("portfolio")  # ricevi il portfolio selezionato
    
    portfolio_data = None
    positions_data = []
    
    if selected_portfolio:
        p = Portfolio(selected_portfolio)  # istanzia il portfolio
        portfolio_data = {
            "name": p.name,
            "date": p.date,
            "cash": p.get_cash_balance(),
            "total_value": p.get_total_value(),
            "positions_count": p.get_positions_count(),
            "total_risk_pct": p.get_total_risk_pct(),
            "total_return_pct": p.get_total_return_pct(),
            "current_drawdown": p.get_current_drawdown(),
            "max_drawdown": p.get_max_drawdown(),
            "portfolio_volatility": p.get_portfolio_volatility(),
            "sharpe_ratio": p.get_sharpe_ratio(),
            "win_rate": p.get_win_rate(),
            "total_risk_pct": p.get_total_risk_pct(),
            "largest_position_pct": p.get_largest_position_pct(),
        }
        positions_data = [
            {
                "ticker": pos.ticker,
                "shares": pos.shares,
                "avg_cost": pos.avg_cost,
                "current_price": pos.current_price,
                "current_value": pos.get_current_value(),
                "pnl_pct": pos.get_unrealized_pnl_pct(),
                "stop_loss": pos.stop_loss,
                "first_target": pos.first_target,
                "breakeven": pos.breakeven,
            }
            for pos in p._positions.values()
        ]
    
    return render_template(
        "portfolio.html",
        portfolios=portfolios,
        selected_portfolio=selected_portfolio,
        portfolio_data=portfolio_data,
        positions_data=positions_data,
    )

@views_bp.route("/database", methods=["GET"])
@login_required
def database():
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
                current_app.logger.info(f"Query eseguita correttamente: {query}")
            else:
                error = "⚠️ Nessun risultato"
                current_app.logger.warning(f"Query senza risultati: {query}")
        except Exception as e:
            error = f"❌ Errore SQL: {e}"
            current_app.logger.exception(f"Errore SQL durante l'esecuzione della query: {query}")

    return render_template(
        "fragments/query_results.html",
        results=results,
        columns=columns,
        error=error
    )
