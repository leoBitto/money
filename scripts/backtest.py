import logging
from datetime import datetime, timedelta
from typing import Callable, Dict, Any
import pandas as pd

from .portfolio import Portfolio
from .risk_manager import generate_signals
from . import database

logger = logging.getLogger(__name__)


def run_backtest(
    strategy_fn: Callable,
    start_date: str,
    end_date: str,
    initial_cash: float = 10000.0,
) -> pd.DataFrame:
    """
    Backtest semplificato:
    - Genera segnali ogni venerdì
    - Esegue trade il lunedì successivo
    - Tiene traccia del valore del portfolio
    - Restituisce DataFrame con timeline

    Parametri
    ---------
    strategy_fn : Callable
        Funzione di strategia, legge i parametri da config.
    start_date : str
    end_date : str
    initial_cash : float

    Ritorna
    -------
    pd.DataFrame
        Colonne: [date, cash, positions_value, total_value, trades]
    """
    # Setup
    portfolio = Portfolio.create("backtest", start_date, initial_cash, backtest=True)

    # Carica tutto il dataset una sola volta
    df = database.load_price_history(start_date, end_date)

    analysis_dates, execution_dates = _generate_calendar(start_date, end_date)
    records = []

    for analysis_date, execution_date in zip(analysis_dates, execution_dates):
        # Slice dati fino alla data di analisi
        df_analysis = df[df["date"] <= analysis_date]

        # 1. Aggiorna portfolio alla data di analisi
        portfolio.update(analysis_date, df_analysis)

        # 2. Genera segnali
        signals = generate_signals(strategy_fn, df_analysis, analysis_date, portfolio)

        # Slice dati fino alla data di esecuzione
        df_exec = df[df["date"] <= execution_date]

        # 3. Aggiorna portfolio alla data di esecuzione
        portfolio.update(execution_date, df_exec)

        # 4. Esegui trade lunedì
        trades = portfolio.execute_trades(signals, execution_date)

        # 5. Registra snapshot
        records.append({
            "date": execution_date,
            "cash": portfolio.cash,
            "positions_value": portfolio.positions_value,
            "total_value": portfolio.value(),
            "trades": trades
        })

    return pd.DataFrame(records)


def _generate_calendar(start_date: str, end_date: str):
    """Genera coppie (venerdì, lunedì successivo)."""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    # primo venerdì
    while start.weekday() != 4:  # 4 = Friday
        start += timedelta(days=1)

    analysis_dates, execution_dates = [], []
    current = start
    while current <= end:
        analysis_dates.append(current.strftime("%Y-%m-%d"))
        monday = current + timedelta(days=3)
        execution_dates.append(monday.strftime("%Y-%m-%d"))
        current += timedelta(days=7)

    return analysis_dates, execution_dates
