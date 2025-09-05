# run_get_history.py
import logging
import json
from datetime import datetime
from typing import List

import pandas as pd

# Database
from scripts.database import (
    reset_entire_db,
    create_portfolio_tables,
    create_universe_table,
    insert_batch_universe
)

# Portfolio / Risk Manager
from scripts.portfolio import Portfolio
from scripts.risk_manager import get_signals
from scripts.strategies import rsi_strategy

# Google Sheets
from scripts.google_services import get_universe_tickers_from_gsheet
from scripts.data_fetcher import get_data_for_db_between_dates

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def main():
    # Reset e ricreazione tabelle
    reset_entire_db(confirm=True)
    create_portfolio_tables()
    create_universe_table()

    # Lista tickers
    tickers: List[str] = get_universe_tickers_from_gsheet()
    logger.info(f"{len(tickers)} tickers trovati nello sheet")

    # Date
    start_date = (datetime.today().replace(year=datetime.today().year - 3)).strftime('%Y-%m-%d')
    end_date = datetime.today().strftime('%Y-%m-%d')

    # Scarico dati e inserimento
    data = get_data_for_db_between_dates(tickers, start_date, end_date)
    inserted_count = insert_batch_universe(data, conflict_resolution="DO UPDATE")
    logger.info(f"{inserted_count} record inseriti/aggiornati nella tabella universe")

    # Creazione portfolio demo
    demo_date = datetime.today().strftime('%Y-%m-%d')
    try:
        demo_portfolio = Portfolio.create("demo", demo_date)
        logger.info(f"Portfolio demo creato per {demo_date}")
    except Exception as e:
        logger.warning(f"Portfolio demo non creato: {e}")
        demo_portfolio = Portfolio(demo_date, demo_date)  # carico esistente se presente

    # Generazione segnali
    signals = get_signals(rsi_strategy, datetime.strptime(demo_date, '%Y-%m-%d'), "demo")
    print("\n=== Signals Result ===")
    print(json.dumps(signals, indent=4, sort_keys=False, default=str))


if __name__ == "__main__":
    main()
