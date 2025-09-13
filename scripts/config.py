# scripts/config.py - Centralized Configuration
"""
Centralized configuration for the Money trading project.
All constants, parameters, and settings should be defined here.
"""
import os
from pathlib import Path

# =============================================================================
# FLASK APP
# =============================================================================
SECRET_KEY = "supersecret"  
USERNAME = "admin"
PASSWORD = "trading123"

# =============================================================================
# PROJECT PATHS
# =============================================================================
PROJECT_ROOT = Path(__file__).parent.parent  # money/ folder
LOGS_DIR = PROJECT_ROOT / "logs"
DOCS_DIR = PROJECT_ROOT / "docs"

# =============================================================================
# GOOGLE CLOUD & SERVICES
# =============================================================================
GCP_PROJECT_ID = "trading-469418"

# Google Sheets IDs
UNIVERSE_SPREADSHEET_ID = "1Uh3S3YCyvupZ5yZh2uDi0XYGaZIkEkupxsYed6xRxgA"
WEEKLY_REPORTS_FOLDER_ID = "1pGSxyPjc8rotTFZp-HA-Xrl7yZHjDWDh"
TEST_SHEET_ID = "1fGTT6O197auwyHGnEBKwvHm3oZwwWz9r8Nm4hz76jKM"

# Secret Manager secret names
DB_SECRET_NAME = "db_info"
SERVICE_ACCOUNT_SECRET_NAME = "service_account"

# =============================================================================
# DATABASE
# =============================================================================
# These will be loaded from Secret Manager at runtime
DB_TABLE_UNIVERSE = "universe"

# =============================================================================
# DATA FETCHING (yfinance)
# =============================================================================
# Default periods for data fetching
YFINANCE_DEFAULT_PERIOD = "1d"
YFINANCE_DEFAULT_INTERVAL = "1d"
YFINANCE_HISTORY_PERIOD = "1y"  # For historical data download

# API rate limiting
YFINANCE_MAX_RETRIES = 3
YFINANCE_RETRY_DELAY = 2  # seconds

# =============================================================================
# TRADING STRATEGIES PARAMETERS  
# =============================================================================

# Moving Average Crossover
MA_SHORT_WINDOW = 3
MA_LONG_WINDOW = 5

# RSI Strategy
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

# Breakout Strategy  
BREAKOUT_LOOKBACK = 20

# Signal mapping
SIGNAL_MAP = {
    -1: "SELL",
    0: "HOLD", 
    1: "BUY"
}

# Default strategy parameters for reports
DEFAULT_STRATEGY_PARAMS = {
    'moving_average_crossover': {
        'short_window': MA_SHORT_WINDOW,
        'long_window': MA_LONG_WINDOW
    },
    'rsi_strategy': {
        'period': RSI_PERIOD,
        'overbought': RSI_OVERBOUGHT,
        'oversold': RSI_OVERSOLD
    },
    'breakout_strategy': {
        'lookback': BREAKOUT_LOOKBACK
    }
}

# =============================================================================
# REPORTING
# =============================================================================
# Google Sheets settings
SHEET_DEFAULT_ROWS = "1000"
SHEET_DEFAULT_COLS = "20" 

# Report worksheet names
SUMMARY_WORKSHEET_NAME = "Summary"
METADATA_WORKSHEET_NAME = "Metadata"

# =============================================================================
# LOGGING
# =============================================================================
# Log file names
DAILY_UPDATE_LOG = "daily_update.log"
WEEKLY_REPORT_LOG = "weekly_report.log"
BACKTEST_LOG = "backtest.log"
ERROR_LOG = "error.log"

# Log format
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Log levels by module
LOG_LEVELS = {
    'daily_update': 'INFO',
    'weekly_report': 'INFO', 
    'backtest': 'INFO',
    'database': 'INFO',
    'google_services': 'INFO',
    'data_fetcher': 'WARNING',  # yfinance can be noisy
    'strategies': 'INFO',
    'signals': 'INFO',
    'reports': 'INFO'
}

# =========================
# RISK MANAGEMENT
# =========================
DEFAULT_RISK_PCT_PER_TRADE = 0.02    # % of portfolio risked per single trade
DEFAULT_MAX_POSITIONS = 5            # Maximum simultaneous positions  
DEFAULT_ATR_MULTIPLIER = 2.0         # Stop loss distance in ATR units
DEFAULT_CASH_BUFFER = 0.10           # Keep 10% cash buffer
DEFAULT_PROFIT_RATIO = 2.0           # First target at 2x risk distance

# Portfolio risk limits
MAX_PORTFOLIO_RISK_PCT = 10.0        # Maximum total capital at risk
MAX_SINGLE_POSITION_PCT = 20.0       # Maximum single position size
MIN_CASH_RESERVE_PCT = 5.0           # Minimum cash reserve

# =========================  
# PERFORMANCE METRICS
# =========================
DEFAULT_RISK_FREE_RATE = 0.02       # For Sharpe ratio calculation
VOLATILITY_CALCULATION_DAYS = 30     # Days for volatility calculation
DRAWDOWN_CALCULATION_DAYS = 252      # Days for max drawdown

# =========================
# SIGNAL PROCESSING  
# =========================
VOLATILITY_PREFERENCE = "low"       # "low" or "high" for signal ranking
EXECUTION_FREQUENCY = "weekly"       # "daily" or "weekly"

# =========================
# DATABASE
# =========================
DEFAULT_PORTFOLIO_NAME = "default"


# =============================================================================
# BACKTEST CONFIGURATION  
# =============================================================================

# Backtest execution timing
BACKTEST_EXECUTION_DAY = 4  # 0=Monday, 4=Friday - giorno per analisi segnali
BACKTEST_TRADE_DAY = 0      # 0=Monday - giorno per esecuzione trade

# Backtest data management
BACKTEST_SAVE_DAILY_SNAPSHOTS = True   # Salva snapshot ogni giorno
BACKTEST_SAVE_WEEKLY_SNAPSHOTS = True  # Salva snapshot settimanali
BACKTEST_CALCULATE_METRICS = True      # Calcola metriche performance

# Backtest validation  
BACKTEST_MIN_DATA_DAYS = 30            # Minimo giorni dati per iniziare backtest
BACKTEST_SKIP_HOLIDAYS = True          # Salta giorni festivi automaticamente

# Backtest logging
BACKTEST_LOG_LEVEL = 'INFO'
BACKTEST_LOG_TRADES = True
BACKTEST_LOG_SIGNALS = False           # Può essere verboso

# Backtest default parameters
BACKTEST_DEFAULT_INITIAL_CASH = 10000.0
BACKTEST_DEFAULT_COMMISSION = 0.0       # Commissioni per trade (per ora 0)

# Performance calculation
BACKTEST_RISK_FREE_RATE = 0.02         # Tasso risk-free per Sharpe ratio
BACKTEST_BENCHMARK_RETURN = 0.08       # Return benchmark per confronti


# =============================================================================
# VALIDATION
# =============================================================================
def validate_config():
    """Validate configuration at startup"""
    errors = []
    
    # Check required directories exist
    if not LOGS_DIR.exists():
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        
    # Validate strategy parameters
    if MA_SHORT_WINDOW >= MA_LONG_WINDOW:
        errors.append("MA_SHORT_WINDOW must be less than MA_LONG_WINDOW")
        
    if not (0 < RSI_OVERBOUGHT <= 100):
        errors.append("RSI_OVERBOUGHT must be between 0 and 100")
        
    if not (0 <= RSI_OVERSOLD < 100):
        errors.append("RSI_OVERSOLD must be between 0 and 100")
        
    if RSI_OVERSOLD >= RSI_OVERBOUGHT:
        errors.append("RSI_OVERSOLD must be less than RSI_OVERBOUGHT")
    
    if errors:
        raise ValueError(f"Configuration errors: {', '.join(errors)}")

# Run validation when module is imported
validate_config()