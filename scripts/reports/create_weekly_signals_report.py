import inspect
from scripts.trading import strategies
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from generate_signals import generate_signals
from google.cloud import secretmanager
import json
from datetime import datetime

# --- 1. Google Drive / Sheets setup ---
SECRET_NAME = "projects/trading-469418/secrets/service_account/versions/latest"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

client_sm = secretmanager.SecretManagerServiceClient()
response = client_sm.access_secret_version(name=SECRET_NAME)
service_account_info = json.loads(response.payload.data.decode("UTF-8"))
creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
gc = gspread.authorize(creds)

# --- 2. ID cartella Drive ---
WEEKLY_FOLDER_ID = "1pGSxyPjc8rotTFZp-HA-Xrl7yZHjDWDh"

# --- 3. Lista delle strategie (automatico usando inspect) ---
strategy_functions = [f for n, f in inspect.getmembers(strategies, inspect.isfunction)]

# --- 4. Data odierna ---
today_str = datetime.today().strftime("%Y-%m-%d")

# --- 5. Ciclo su strategie ---
for strat_func in strategy_functions:
    strat_name = strat_func.__name__
    try:
        # genera signals
        df_signals = generate_signals(strat_func, date=today_str)
        if df_signals.empty:
            print(f"No signals generated for {strat_name}, skipping report.")
            continue

        # crea report su Google Sheet
        report_name = f"{strat_name}_{today_str}"
        sh = gc.create(report_name, folder_id=WEEKLY_FOLDER_ID)
        worksheet = sh.sheet1
        worksheet.update([df_signals.columns.values.tolist()] + df_signals.values.tolist())
        print(f"Report generated for {strat_name}: {report_name}")

    except Exception as e:
        print(f"Error generating report for {strat_name}: {e}")

print("All strategy reports generated successfully.")
