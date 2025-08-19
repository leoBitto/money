import gspread
from google.oauth2.service_account import Credentials
from google.cloud import secretmanager
import pandas as pd
from datetime import datetime
import json
import psycopg2

# --- 1. Leggi il JSON della SA dal Secret Manager ---
SECRET_NAME = "projects/trading-469418/secrets/service_account/versions/latest"

client_sm = secretmanager.SecretManagerServiceClient()
response = client_sm.access_secret_version(name=SECRET_NAME)
service_account_info = json.loads(response.payload.data.decode("UTF-8"))

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
client = gspread.authorize(creds)

# --- 2. Apri lo Sheet ---
SPREADSHEET_ID = '1Uh3S3YCyvupZ5yZh2uDi0XYGaZIkEkupxsYed6xRxgA'
sheet = client.open_by_key(SPREADSHEET_ID)
worksheet = sheet.sheet1

# --- 3. Leggi i dati ---
data = worksheet.get_all_records()

# --- 4. Trasforma in DataFrame e aggiungi data corrente ---
df = pd.DataFrame(data)
df['Data'] = datetime.today().strftime('%Y-%m-%d')
df_to_insert = df[['Ticker', 'Data', 'Prezzo']]
df_to_insert['Prezzo'] = (
    df_to_insert['Prezzo']
    .astype(str)                      # assicura che siano stringhe
    .str.replace('$', '', regex=False)  # rimuove il simbolo del dollaro
    .astype(float)                    # converte in float
)


# --- 4. Leggi i secret del DB ---
SECRET_DB_NAME = "projects/trading-469418/secrets/db_info/versions/latest"
response_db = client_sm.access_secret_version(name=SECRET_DB_NAME)
db_info = json.loads(response_db.payload.data.decode("UTF-8"))

# Connessione PostgreSQL
conn = psycopg2.connect(
    host=db_info["DB_HOST"],
    port=db_info["DB_PORT"],
    database=db_info["DB_NAME"],
    user=db_info["DB_USER"],
    password=db_info["DB_PASSWORD"]
)
cursor = conn.cursor()

# --- 5. Scrivi i dati sul DB ---
# Assumiamo una tabella 'storico_prezzi' con colonne: ticker, data, prezzo
for index, row in df_to_insert.iterrows():
    cursor.execute("""
        INSERT INTO universe (ticker, data, prezzo)
        VALUES (%s, %s, %s)
        ON CONFLICT (ticker, data) DO UPDATE SET prezzo = EXCLUDED.prezzo;
    """, (row['Ticker'], row['Data'], row['Prezzo']))

conn.commit()
cursor.close()
conn.close()

print(f"{len(df_to_insert)} righe aggiornate su PostgreSQL")
