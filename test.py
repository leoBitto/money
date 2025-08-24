# ~/money/test.py

from scripts.trading.generate_signals import generate_signals, generate_all_strategies_signals
from scripts.trading import strategies
from scripts.reports.generate_weekly_signals_report import generate_weekly_report
import pandas as pd
from datetime import datetime, timedelta




if __name__ == "__main__":
    print("=" * 60)
    print("🧪 TESTING ")
    print("=" * 60)
    
    generate_weekly_report()