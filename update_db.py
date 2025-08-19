# %%
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
import os

# %%
# --- 1. Configurazione credenziali ---
SERVICE_ACCOUNT_FILE = './service_account.json'  # percorso del tuo JSON
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]

creds = Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=SCOPES
)

client = gspread.authorize(creds)

# %%
# --- 2. Apri lo Sheet ---
SPREADSHEET_ID = '1Uh3S3YCyvupZ5yZh2uDi0XYGaZIkEkupxsYed6xRxgA'  # prende l'ID dall'URL dello Sheet
sheet = client.open_by_key(SPREADSHEET_ID)
worksheet = sheet.sheet1  # prima tab del foglio

# %%

# --- 3. Leggi i dati ---
data = worksheet.get_all_records()  # ritorna lista di dict

# %%

# --- 4. Trasforma in DataFrame e aggiungi data corrente ---
df = pd.DataFrame(data)
df['Data'] = datetime.today().strftime('%Y-%m-%d')
df_csv = df[['Ticker', 'Data', 'Prezzo']]



# %%

CSV_FILE = './storico_prezzi.csv'

# Controlla se il file esiste
if os.path.exists(CSV_FILE):
    # Se esiste, leggi il CSV esistente e concatena i nuovi dati
    df_existing = pd.read_csv(CSV_FILE, sep=';')
    df_csv = pd.concat([df_existing, df_csv], ignore_index=True)
else:
    # Se non esiste, usa solo i nuovi dati
    df_csv = df_csv.copy()

# Salva/aggiorna il CSV
df_csv.to_csv(CSV_FILE, index=False, sep=';')
print(f"CSV aggiornato: {CSV_FILE}")




