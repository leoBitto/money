import gspread
from google.oauth2.service_account import Credentials
from google.cloud import secretmanager
import pandas as pd
from datetime import datetime
import json
import psycopg2
import yfinance as yf

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

# --- 3. Leggi i ticker dallo Sheet ---
data = worksheet.get_all_records()
df_sheet = pd.DataFrame(data)
tickers = df_sheet['Ticker'].dropna().unique().tolist()

print(f"Trovati {len(tickers)} ticker nello Sheet.")

# --- 4. Scarica i prezzi odierni con yfinance ---
today = datetime.today().strftime('%Y-%m-%d')
prices = yf.download(tickers, period="1d", interval="1d", group_by="ticker", auto_adjust=True, progress=False)

# Normalizza i dati in lista di dizionari per l'inserimento
records = []
for ticker in tickers:
    try:
        df_t = prices[ticker] if len(tickers) > 1 else prices
        df_t = df_t[['Open', 'High', 'Low', 'Close', 'Volume']].reset_index()
        df_t['Ticker'] = ticker
        df_t.rename(columns={
            'Date': 'date',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume',
            'Ticker': 'ticker'
        }, inplace=True)
        records.extend(df_t.to_dict(orient='records'))
    except Exception as e:
        print(f"Errore con {ticker}: {e}")

df_prices = pd.DataFrame(records)
print(f"Righe pronte da inserire: {len(df_prices)}")

# --- 5. Leggi i secret del DB ---
SECRET_DB_NAME = "projects/trading-469418/secrets/db_info/versions/latest"
response_db = client_sm.access_secret_version(name=SECRET_DB_NAME)
db_info = json.loads(response_db.payload.data.decode("UTF-8"))

conn = psycopg2.connect(
    host=db_info["DB_HOST"],
    port=db_info["DB_PORT"],
    database=db_info["DB_NAME"],
    user=db_info["DB_USER"],
    password=db_info["DB_PASSWORD"]
)
cursor = conn.cursor()

# --- 6. Inserisci/aggiorna dati nella tabella universe ---
insert_query = """
INSERT INTO universe (date, ticker, open, high, low, close, volume)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (date, ticker) DO UPDATE 
SET open = EXCLUDED.open,
    high = EXCLUDED.high,
    low = EXCLUDED.low,
    close = EXCLUDED.close,
    volume = EXCLUDED.volume;
"""

batch = [
    (row['date'].date(), row['ticker'], row['open'], row['high'], row['low'], row['close'], row['volume'])
    for _, row in df_prices.iterrows()
]

cursor.executemany(insert_query, batch)
conn.commit()
cursor.close()
conn.close()

print(f"{len(batch)} righe inserite/aggiornate su PostgreSQL")
