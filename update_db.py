# %%
import gspread
from google.auth import default
from google.auth.transport.requests import Request
import pandas as pd
from datetime import datetime
import os

# %%
# --- 1. Configurazione credenziali tramite ADC (Service Account della VM) ---
# Non serve il file JSON, la VM impersona già la SA con i permessi necessari
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]

creds, project = default(scopes=SCOPES)

# Aggiorna il token se necessario
creds.refresh(Request())

client = gspread.authorize(creds)

# %%
# --- 2. Apri lo Sheet ---
SPREADSHEET_ID = '1Uh3S3YCyvupZ5yZh2uDi0XYGaZIkEkupxsYed6xRxgA'
sheet = client.open_by_key(SPREADSHEET_ID)
worksheet = sheet.sheet1

# %%
# --- 3. Leggi i dati ---
data = worksheet.get_all_records()

# %%
# --- 4. Trasforma in DataFrame e aggiungi data corrente ---
df = pd.DataFrame(data)
df['Data'] = datetime.today().strftime('%Y-%m-%d')
df_csv = df[['Ticker', 'Data', 'Prezzo']]

# %%
CSV_FILE = './storico_prezzi.csv'

# Controlla se il file esiste
if os.path.exists(CSV_FILE):
    df_existing = pd.read_csv(CSV_FILE, sep=';')
    df_csv = pd.concat([df_existing, df_csv], ignore_index=True)
else:
    df_csv = df_csv.copy()

# Salva/aggiorna il CSV
df_csv.to_csv(CSV_FILE, index=False, sep=';')
print(f"CSV aggiornato: {CSV_FILE}")
