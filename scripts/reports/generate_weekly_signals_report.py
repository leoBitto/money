# scripts/reports/generate_weekly_signals_report.py

import inspect
import json
from datetime import datetime
from typing import Optional, Dict, List
import pandas as pd
import gspread
from gspread_dataframe import set_with_dataframe
from google.oauth2.service_account import Credentials
from google.cloud import secretmanager

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

def save_df_to_google_sheet(df, sheet_name):
    client = setup_google_client()  # ottieni il client
    # crea un nuovo foglio
    spreadsheet = client.create(sheet_name, folder=WEEKLY_FOLDER_ID)
    worksheet = spreadsheet.get_worksheet(0)  # prende il primo foglio
    # scrive il DataFrame
    set_with_dataframe(worksheet, df)
    print(f"✅ Foglio '{sheet_name}' creato in Google Drive")

def generate_weekly_report():
    client = setup_google_client()  # ottieni il client Google
    today = datetime.today().strftime('%Y-%m-%d')
    functions = get_strategy_functions()
    print(client)
    # crea un unico Google Sheet per tutte le strategie
    spreadsheet_name = f"Weekly_Signals_{today}"
    spreadsheet = client.create(title=spreadsheet_name, folder_id=WEEKLY_FOLDER_ID)
    spreadsheet.share('leonardo_bitto1@gmail.com', perm_type='user', role='editor')
    print(f"📂 Creata cartella principale: {spreadsheet_name}")
    
    first_sheet = True  # serve perché il file di default ha già un foglio

    for f in functions:
        strategy_name = f[0]
        df_signals = generate_signals(f[1], today)

        # converti i segnali numerici in testo
        df_signals["signal"] = df_signals["signal"].map({
            -1: "SELL",
             0: "HOLD",
             1: "BUY"
        })

        # se è il primo foglio, usa quello di default, altrimenti aggiungi un nuovo foglio
        if first_sheet:
            worksheet = spreadsheet.get_worksheet(0)
            worksheet.update(title=strategy_name)
            first_sheet = False
        else:
            worksheet = spreadsheet.add_worksheet(title=strategy_name, rows=str(len(df_signals)+1), cols=str(len(df_signals.columns)))
        
        # scrivi il DataFrame
        set_with_dataframe(worksheet, df_signals)
        print(f"✅ Foglio '{strategy_name}' aggiornato con {len(df_signals)} segnali")

    print(f"🔗 Link al file completo: https://docs.google.com/spreadsheets/d/{spreadsheet.id}/edit")

