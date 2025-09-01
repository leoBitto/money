# test.py
import logging
from datetime import datetime

from scripts.portfolio import Portfolio, create_new_portfolio
from scripts.database import create_portfolio_tables, execute_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def main():
    today = datetime.today().strftime("%Y-%m-%d")
    portfolio_name = "demo"

    logging.info("🚀 Avvio test portfolio")

    # 1. Inizializza tabelle (solo la prima volta)
    create_portfolio_tables()

    # 2. Crea un nuovo portfolio (cash iniziale)
    create_new_portfolio(portfolio_name, initial_cash=10000, date=today)
    logging.info(f"Creato portfolio '{portfolio_name}' con cash iniziale 10,000")

    # 3. Carica il portfolio
    pf = Portfolio(portfolio_name, today)

    # 4. Aggiungi posizioni di esempio
    pf.add_position("AAPL", 10, 180.0)  # Apple
    pf.add_position("MSFT", 5, 310.0)   # Microsoft
    pf.add_position("NVDA", 3, 450.0)   # Nvidia

    # 5. Aggiorna snapshot
    pf._update_snapshot()
    logging.info("Snapshot aggiornato.")

    # 6. Query diretta al DB per verificare le posizioni
    result, _ = execute_query(
        """
        SELECT date, portfolio_name, ticker, shares, avg_cost, current_price, current_value 
        FROM portfolio_positions
        WHERE portfolio_name = %s AND date = %s
        """,
        (portfolio_name, today)
    )
    logging.info("📊 Righe in portfolio_positions:")
    for row in result:
        logging.info(row)

    # 7. Ricarica il portfolio dal DB
    pf_reloaded = Portfolio(portfolio_name, today)
    logging.info(f"🔄 Portfolio ricaricato '{portfolio_name}' al {today}")

    # 8. Mostra snapshot
    logging.info(f"Totale: {pf_reloaded.get_total_value():,.2f}, "
                 f"Cash: {pf_reloaded.get_cash_balance():,.2f}, "
                 f"Posizioni: {pf_reloaded.get_positions_count()}")

    # 9. Stampa dettagli delle posizioni ricaricate
    for ticker, pos in pf_reloaded._positions.items():
        logging.info(
            f"Posizione {ticker}: shares={pos.shares}, avg_cost={pos.avg_cost}, "
            f"current_price={pos.current_price}, value={pos.get_current_value()}, "
            f"PnL%={pos.get_unrealized_pnl_pct():.2f}%"
        )

if __name__ == "__main__":
    main()
