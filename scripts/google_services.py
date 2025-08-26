# scripts/google_services.py
"""
Modulo: google_services
=======================

Funzioni di utilità per interagire con Google Cloud Secret Manager e 
Google Sheets/Drive, senza classi e con configurazioni centralizzate.

Config utilizzati (da scripts/config.py):
- GCP_PROJECT_ID: ID del progetto su Google Cloud (default: "trading-469418")
- SERVICE_ACCOUNT_SECRET_NAME: nome del secret che contiene le credenziali
  del Service Account (es. "service_account")

Funzionalità principali:
------------------------
1. Lettura dei secret da Secret Manager
   - get_secret(secret_name: str, version: str = "latest") -> dict

2. Recupero credenziali Service Account dal Secret Manager
   - get_service_account_info() -> dict

3. Creazione di un client Google Sheets/Drive autenticato
   - get_gsheet_client(service_account_info: dict | None = None,
                       scopes: list[str] | None = None) -> gspread.Client

Casi d'uso:
-----------
- Caricare le credenziali DB dal Secret Manager:
    >>> from scripts.google_services import get_secret
    >>> db_info = get_secret("db_info")

- Ottenere un client Google Sheets:
    >>> from scripts.google_services import get_gsheet_client
    >>> client = get_gsheet_client()
    >>> sheet = client.open_by_key(config.UNIVERSE_SPREADSHEET_ID)

- Usare un set di scope personalizzato:
    >>> custom_scopes = ["https://www.googleapis.com/auth/drive.readonly"]
    >>> client = get_gsheet_client(scopes=custom_scopes)

Note:
-----
- I nomi dei secret da usare (es. "db_info", "service_account") 
  sono definiti in scripts/config.py e gestiti centralmente.
- Le funzioni sono pensate per essere semplici entrypoint e non richiedono
  classi o oggetti wrapper.
"""
# scripts/google_services.py
import json
import gspread
from google.cloud import secretmanager
from google.oauth2.service_account import Credentials

from . import config

DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def get_secret(secret_name: str, version: str = "latest") -> dict:
    """
    Recupera un secret dal Google Cloud Secret Manager.
    """
    client = secretmanager.SecretManagerServiceClient()
    secret_path = f"projects/{config.GCP_PROJECT_ID}/secrets/{secret_name}/versions/{version}"
    response = client.access_secret_version(name=secret_path)
    return json.loads(response.payload.data.decode("UTF-8"))

def get_service_account_info() -> dict:
    """
    Recupera le credenziali del service account da Secret Manager.
    """
    return get_secret(config.SERVICE_ACCOUNT_SECRET_NAME)

def get_gsheet_client(service_account_info: dict | None = None,
                      scopes: list[str] | None = None) -> gspread.Client:
    """
    Restituisce un client autenticato per Google Sheets/Drive.
    """
    if service_account_info is None:
        service_account_info = get_service_account_info()
    if scopes is None:
        scopes = DEFAULT_SCOPES
    
    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    return gspread.authorize(creds)
