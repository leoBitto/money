import logging
import json
from datetime import datetime
from scripts.risk_manager import get_signals 
from scripts.strategies import rsi_strategy, moving_average_crossover, breakout_strategy
from scripts.database import *
from scripts.portfolio import Portfolio

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

start_date = "2025-09-01"

def main():

    reset_entire_db(True)
    create_portfolio_tables()
    p = Portfolio.create("demo", start_date)

    dict_result = get_signals(rsi_strategy, datetime.strptime(start_date, '%Y-%m-%d'), "demo")
    print("\n=== Signals Result ===")
    print(json.dumps(dict_result, indent=4, sort_keys=False, default=str))

if __name__ == "__main__":
    main()
