# run_daily_update_portfolio.py - Ultra Semplificato
import logging
import os
from datetime import datetime

from scripts.portfolio import get_portfolio_names, Portfolio

# Setup logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename="logs/run_daily_update_portfolio.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

def main():
    today = datetime.today().strftime("%Y-%m-%d")
    logging.info("🚀 Avvio aggiornamento snapshot portfolio")

    try:
        portfolios = get_portfolio_names()
        logging.info(f"Trovati {len(portfolios)} portfolio nel DB")

        if not portfolios:
            logging.warning("Nessun portfolio trovato, uscita.")
            return

        for name in portfolios:
            logging.info(f"📊 Aggiornamento portfolio: {name}")

            try:
                # Carica portfolio (ultima data disponibile)
                pf = Portfolio(name)
                
                # Una sola riga fa tutto!
                pf.update_to_date(today)

                logging.info(
                    f"✅ Portfolio {name} aggiornato: "
                    f"valore=€{pf.get_total_value():,.2f}, "
                    f"cash=€{pf.get_cash_balance():,.2f}, "
                    f"posizioni={pf.get_positions_count()}"
                )

            except Exception as e:
                logging.exception(f"❌ Errore su portfolio {name}: {e}")

    except Exception as e:
        logging.exception(f"❌ Errore generale: {e}")
        raise

if __name__ == "__main__":
    main()