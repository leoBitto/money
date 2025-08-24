# ~/money/main.py

from scripts.trading.generate_signals import generate_signals
from scripts.trading import strategies
from scripts.reports.create_weekly_signals_report import generate_weekly_signals_report

def test_signals():
    """
    Test function to generate signals for a single strategy on a given date.
    """
    print("Testing single strategy signals generation...")
    df = generate_signals(strategy=strategies.moving_average_crossover, date='2025-08-23')
    print(df.head())

def test_all_signals():
    """
    Test function to generate signals for all strategies.
    """
    print("Generating signals for all strategies...")
    strategy_list = [
        strategies.moving_average_crossover,
        strategies.rsi_strategy,
        strategies.momentum_breakout
        # aggiungi altre strategie qui
    ]

    for strat in strategy_list:
        df = generate_signals(strategy=strat, date='2025-08-23')
        print(f"Signals for {strat.__name__}:")
        print(df.head())

def test_weekly_report():
    """
    Test the weekly signals report generation.
    """
    print("Generating weekly signals report...")
    generate_weekly_signals_report()

if __name__ == "__main__":
    # commenta e decommenta quello che vuoi testare
    test_signals()
    # test_all_signals()
    # test_weekly_report()
