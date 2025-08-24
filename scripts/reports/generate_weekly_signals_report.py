# scripts/reports/generate_weekly_signals_report.py

import inspect
import json
from datetime import datetime
from typing import Optional, Dict, List
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from google.cloud import secretmanager
import io

from scripts.trading.generate_signals import generate_signals
from scripts.trading import strategies

# --- Configurazione Google Sheets/Drive ---
SECRET_NAME = "projects/trading-469418/secrets/service_account/versions/latest"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
WEEKLY_FOLDER_ID = "1pGSxyPjc8rotTFZp-HA-Xrl7yZHjDWDh"

def setup_google_client():
    """Configura e ritorna il client Google Drive/Sheets"""
    try:
        client_sm = secretmanager.SecretManagerServiceClient()
        response = client_sm.access_secret_version(name=SECRET_NAME)
        service_account_info = json.loads(response.payload.data.decode("UTF-8"))
        creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"❌ Errore configurazione Google client: {e}")
        raise

def get_strategy_functions() -> List[tuple]:
    """Recupera tutte le funzioni strategia dal modulo strategies"""
    strategy_functions = []
    for name, func in inspect.getmembers(strategies, inspect.isfunction):
        # Filtra solo le funzioni che hanno il parametro 'df' (sono strategie)
        sig = inspect.signature(func)
        if 'df' in sig.parameters:
            strategy_functions.append((name, func))
    return strategy_functions

def generate_weekly_report():
    functions = get_strategy_functions()
    for f in functions:
        generate_signals(f[1], '2025-08-24')