# run_daily_update_db.py
import logging
import os
from scripts import config
from scripts.google_services import get_universe_tickers_from_gsheet
from scripts.data_fetcher import get_daily_data_for_db
from scripts.database import insert_batch_universe
import pandas as pd
# Assicura che la cartella logs/ esista
os.makedirs("logs", exist_ok=True)

# Setup logging
logging.basicConfig(
    filename="logs/run_daily_update_db.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

def main():
    logging.info("🚀 Avvio aggiornamento DB giornaliero")

    try:
        # 1. Ottieni tickers dallo Sheet
        tickers = get_universe_tickers_from_gsheet()
        logging.info(f"Trovati {len(tickers)} ticker dallo sheet")

        if not tickers:
            logging.warning("Nessun ticker trovato, uscita.")
            return

        # 2. Scarica dati da yfinance (lista di tuple già pronta)
        rows = get_daily_data_for_db(tickers)
        logging.info(f"Scaricati {len(rows)} record da yfinance")

        if not rows:
            logging.warning("Nessun dato scaricato da yfinance, uscita.")
            return

        # 3. Inserisci/aggiorna DB
        count = insert_batch_universe(rows, conflict_resolution="DO UPDATE")
        logging.info(f"✅ Inserite/aggiornate {count} righe nel DB")

    except Exception as e:
        logging.exception(f"❌ Errore durante aggiornamento DB: {e}")
        raise

if __name__ == "__main__":
    main()
