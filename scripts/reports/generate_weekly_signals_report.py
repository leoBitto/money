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

TEST_SHEET_ID = "1fGTT6O197auwyHGnEBKwvHm3oZwwWz9r8Nm4hz76jKM"  # file già esistente

def generate_weekly_report():
    client = setup_google_client()  # client Google
    today = datetime.today().strftime('%Y-%m-%d')
    functions = get_strategy_functions()

    # apri il file esistente
    spreadsheet = client.open_by_key(TEST_SHEET_ID)

    # === 1. Aggiorna worksheet strategie ===
    metadata_row = {"Date": today}

    for f in functions:
        strategy_name = f[0]
        df_signals = generate_signals(f[1], today)

        # converti i segnali numerici in testo
        df_signals["signal"] = df_signals["signal"].map({
            -1: "SELL",
             0: "HOLD",
             1: "BUY"
        })

        # calcola conteggi
        counts = df_signals["signal"].value_counts().to_dict()
        metadata_row[f"{strategy_name}_BUY"] = counts.get("BUY", 0)
        metadata_row[f"{strategy_name}_HOLD"] = counts.get("HOLD", 0)
        metadata_row[f"{strategy_name}_SELL"] = counts.get("SELL", 0)

        # controlla se esiste già un worksheet con quel nome
        try:
            worksheet = spreadsheet.worksheet(strategy_name)
            worksheet.clear()  # pulisci prima di scrivere
        except Exception:
            worksheet = spreadsheet.add_worksheet(
                title=strategy_name,
                rows=str(len(df_signals)+1),
                cols=str(len(df_signals.columns))
            )

        # scrivi il DataFrame
        set_with_dataframe(worksheet, df_signals)
        print(f"✅ Foglio '{strategy_name}' aggiornato con {len(df_signals)} segnali")

    # === 2. Aggiorna foglio Metadata ===
    try:
        meta_ws = spreadsheet.worksheet("Metadata")
    except Exception:
        # crea il foglio se non esiste
        meta_ws = spreadsheet.add_worksheet(
            title="Metadata",
            rows="100",
            cols="20"
        )
        # scrivi intestazioni
        headers = list(metadata_row.keys())
        meta_ws.append_row(headers)

    # prendi intestazioni correnti
    existing_headers = meta_ws.row_values(1)

    # se ci sono nuove strategie, aggiorna intestazioni
    new_headers = list(metadata_row.keys())
    if existing_headers != new_headers:
        meta_ws.clear()
        meta_ws.append_row(new_headers)

    # aggiungi nuova riga
    row_values = [metadata_row[h] for h in new_headers]
    meta_ws.append_row(row_values)

    print(f"✅ Metadata_Log aggiornato con i dati del {today}")