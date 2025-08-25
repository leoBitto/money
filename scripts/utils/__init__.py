 scripts/utils/__init__.py
"""
Utilities Package

Moduli:
- gcp_utils: Google Cloud Platform utilities
- data_utils: Data processing e yfinance
- trading_utils: Trading signals e strategie utilities
- db: Database utilities
"""

from .gcp_utils import SecretManager, GoogleSheetsManager
from .data_utils import download_yfinance_data, normalize_price_data, prepare_db_batch
from .trading_utils import (
    format_signal_text, 
    format_signals_column,
    calculate_signal_distribution,
    create_signals_summary
)

__all__ = [
    # GCP
    'SecretManager',
    'GoogleSheetsManager',
    # Data
    'download_yfinance_data',
    'normalize_price_data', 
    'prepare_db_batch',
    # Trading
    'format_signal_text',
    'format_signals_column',
    'calculate_signal_distribution',
    'create_signals_summary'
]