# scripts/utils/gcp_utils.py
import json
from google.cloud import secretmanager
import gspread
from google.oauth2.service_account import Credentials
from typing import Optional, Dict, Any

class SecretManager:
    """Gestisce l'accesso ai secret di Google Cloud Secret Manager"""
    
    def __init__(self, project_id: str = "trading-469418"):
        self.project_id = project_id
        self.client = secretmanager.SecretManagerServiceClient()
    
    def get_secret(self, secret_name: str, version: str = "latest") -> Dict[str, Any]:
        """
        Recupera un secret dal Secret Manager
        
        Args:
            secret_name: Nome del secret (es. 'db_info', 'service_account')
            version: Versione del secret (default: 'latest')
        
        Returns:
            Dict contenente i dati del secret
        """
        secret_path = f"projects/{self.project_id}/secrets/{secret_name}/versions/{version}"
        response = self.client.access_secret_version(name=secret_path)
        return json.loads(response.payload.data.decode("UTF-8"))

class GoogleSheetsManager:
    """Gestisce le operazioni con Google Sheets"""
    
    DEFAULT_SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    def __init__(self, service_account_info: Optional[Dict] = None, scopes: Optional[list] = None):
        """
        Inizializza il manager Google Sheets
        
        Args:
            service_account_info: Dict con le credenziali SA. Se None, le carica da Secret Manager
            scopes: Lista di scopes. Se None, usa quelli di default
        """
        if service_account_info is None:
            secret_manager = SecretManager()
            service_account_info = secret_manager.get_secret("service_account")
        
        if scopes is None:
            scopes = self.DEFAULT_SCOPES
            
        self.creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        self.client = gspread.authorize(self.creds)
    
    def get_sheet_by_id(self, spreadsheet_id: str):
        """Apre un foglio Google Sheets tramite ID"""
        return self.client.open_by_key(spreadsheet_id)
    
    def get_tickers_from_sheet(self, spreadsheet_id: str, worksheet_index: int = 0, ticker_column: str = 'Ticker') -> list:
        """
        Estrae i ticker da un Google Sheet
        
        Args:
            spreadsheet_id: ID del foglio Google Sheets
            worksheet_index: Indice del worksheet (default: 0 = primo)
            ticker_column: Nome della colonna contenente i ticker
        
        Returns:
            Lista di ticker unici
        """
        import pandas as pd
        
        sheet = self.get_sheet_by_id(spreadsheet_id)
        worksheet = sheet.get_worksheet(worksheet_index)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        return df[ticker_column].dropna().unique().tolist()
    
    def create_sheet_in_folder(self, sheet_name: str, folder_id: str):
        """Crea un nuovo foglio in una cartella specifica"""
        return self.client.create(sheet_name, folder=folder_id)

# Funzioni di convenienza per compatibilità con codice esistente
def get_secret(secret_name: str, project_id: str = "trading-469418") -> Dict[str, Any]:
    """Funzione di convenienza per recuperare un singolo secret"""
    sm = SecretManager(project_id)
    return sm.get_secret(secret_name)

def get_gsheet_client(service_account_info: Optional[Dict] = None) -> gspread.Client:
    """Funzione di convenienza per ottenere un client Google Sheets"""
    gsm = GoogleSheetsManager(service_account_info)
    return gsm.client