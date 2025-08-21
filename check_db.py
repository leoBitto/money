# init_db.py
import json
from google.cloud import secretmanager
import psycopg2

# --- 1. Leggi il secret DB dal Secret Manager ---
SECRET_DB_NAME = "projects/trading-469418/secrets/db_info/versions/latest"
client_sm = secretmanager.SecretManagerServiceClient()
response = client_sm.access_secret_version(name=SECRET_DB_NAME)
db_info = json.loads(response.payload.data.decode("UTF-8"))

# --- 2. Connessione a PostgreSQL ---
conn = psycopg2.connect(
    host=db_info["DB_HOST"],
    port=db_info["DB_PORT"],
    database=db_info["DB_NAME"],
    user=db_info["DB_USER"],
    password=db_info["DB_PASSWORD"]
)
cursor = conn.cursor()

# --- 3. Creazione tabella universe ---
cursor.execute("""
select *
from universe

""")

conn.commit()
cursor.close()
conn.close()

print("Tabella 'universe' pronta!")
