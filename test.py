# test.py
import logging
from datetime import datetime

from scripts.portfolio import Portfolio, create_portfolio_tables, create_new_portfolio

logging.basicConfig(level=logging.INFO)

def main():
    today = datetime.today().strftime("%Y-%m-%d")

    # 1. Inizializza tabelle (solo la prima volta)
    create_portfolio_tables()

    # 2. Crea un nuovo portfolio (esempio)
    portfolio_name = "demo"
    create_new_portfolio(portfolio_name, initial_cash=10000)

    # 3. Carica il portfolio
    pf = Portfolio(portfolio_name, today)

    # 4. Aggiungi posizioni di esempio
    pf.add_position("AAPL", 10, 180.0)  # Apple
    pf.add_position("MSFT", 5, 310.0)   # Microsoft
    pf.add_position("NVDA", 3, 450.0)   # Nvidia

    # 5. Aggiorna snapshot
    pf._update_snapshot()

    logging.info(f"Portfolio '{portfolio_name}' creato e popolato.")
    logging.info(f"Totale: {pf.get_total_value():,.2f}, Cash: {pf.get_cash_balance():,.2f}")

if __name__ == "__main__":
    main()
