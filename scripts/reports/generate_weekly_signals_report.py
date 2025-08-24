# scripts/reports/generate_weekly_signals_report.py

import inspect
import json
from datetime import datetime
from typing import Optional, Dict, List
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from google.cloud import secretmanager
import io

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

def create_simple_csv_file(df_signals: pd.DataFrame, 
                          strategy_name: str, 
                          date_str: str, 
                          gc) -> Optional[str]:
    """Crea un file CSV semplice nella cartella Google Drive"""
    try:
        # Formatta la data per il nome file (dd_mm_yyyy)
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        formatted_date = date_obj.strftime("%d_%m_%Y")
        file_name = f"{strategy_name}_{formatted_date}.csv"
        
        # Aggiungi informazioni base al DataFrame
        df_enhanced = df_signals.copy()
        df_enhanced['strategy'] = strategy_name
        df_enhanced['date'] = date_str
        df_enhanced['generated_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Converti segnali in descrizioni leggibili
        signal_map = {-1: 'SELL', 0: 'HOLD', 1: 'BUY'}
        df_enhanced['signal_description'] = df_enhanced['signal'].map(signal_map)
        
        # Riordina colonne per chiarezza
        cols = ['ticker', 'signal', 'signal_description', 'strategy', 'date', 'generated_at']
        df_enhanced = df_enhanced[cols]
        
        # Converti DataFrame in CSV
        csv_buffer = io.StringIO()
        df_enhanced.to_csv(csv_buffer, index=False)
        csv_content = csv_buffer.getvalue()
        
        # Carica il file su Google Drive
        drive_service = gc.auth.service
        file_metadata = {
            'name': file_name,
            'parents': [WEEKLY_FOLDER_ID]
        }
        
        media = drive_service.files().create(
            body=file_metadata,
            media_body=csv_content,
            fields='id,webViewLink'
        ).execute()
        
        file_url = media.get('webViewLink')
        print(f"✅ File creato: {file_name}")
        return file_url
        
    except Exception as e:
        print(f"❌ Errore creazione file per {strategy_name}: {e}")
        return None

def generate_strategy_file(strategy_name: str, 
                          strategy_func, 
                          date: str, 
                          gc, 
                          strategy_params: Optional[Dict] = None) -> Optional[str]:
    """Genera un file per una singola strategia"""
    try:
        print(f"📊 Processando {strategy_name}...")
        
        # Genera i segnali
        if strategy_params:
            df_signals = generate_signals(strategy_func, date, **strategy_params)
        else:
            df_signals = generate_signals(strategy_func, date)
        
        if df_signals.empty:
            print(f"⚠️  Nessun segnale per {strategy_name}")
            return None
        
        # Crea il file CSV
        file_url = create_simple_csv_file(df_signals, strategy_name, date, gc)
        
        if file_url:
            # Statistiche semplici
            signal_counts = df_signals['signal'].value_counts()
            total = len(df_signals)
            buy_count = signal_counts.get(1, 0)
            hold_count = signal_counts.get(0, 0) 
            sell_count = signal_counts.get(-1, 0)
            
            print(f"   📈 Totale: {total} ticker | Buy: {buy_count} | Hold: {hold_count} | Sell: {sell_count}")
            return file_url
        else:
            return None
            
    except Exception as e:
        print(f"❌ Errore {strategy_name}: {e}")
        return None

def generate_weekly_signals_report(date: Optional[str] = None) -> Dict[str, Optional[str]]:
    """
    Funzione principale semplificata per generare i file settimanali.
    
    Parameters:
    -----------
    date : Optional[str]
        Data per cui generare i report (formato YYYY-MM-DD).
        Se None, usa la data odierna.
    
    Returns:
    --------
    Dict[str, Optional[str]]
        Dizionario con nome_strategia -> URL del file (None se errore)
    """
    if date is None:
        date = datetime.today().strftime("%Y-%m-%d")
    
    print("🚀 GENERAZIONE FILE SEGNALI SETTIMANALI")
    print("=" * 45)
    print(f"📅 Data: {date}")
    
    # Setup Google client
    try:
        gc = setup_google_client()
        print("✅ Google Drive client configurato")
    except Exception as e:
        print(f"❌ Impossibile configurare Google Drive: {e}")
        return {}
    
    # Recupera le strategie disponibili
    strategy_functions = get_strategy_functions()
    print(f"📈 Trovate {len(strategy_functions)} strategie")
    
    # Parametri di default per le strategie
    default_params = {
        'moving_average_crossover': {'short_window': 3, 'long_window': 5},
        'rsi_strategy': {'period': 14, 'overbought': 70, 'oversold': 30},
        'breakout_strategy': {'lookback': 20}
    }
    
    # Genera file per ogni strategia
    file_urls = {}
    successful_files = 0
    
    print(f"\n📁 Generando file...")
    for strategy_name, strategy_func in strategy_functions:
        params = default_params.get(strategy_name, {})
        url = generate_strategy_file(strategy_name, strategy_func, date, gc, params)
        file_urls[strategy_name] = url
        
        if url:
            successful_files += 1
    
    # Riepilogo finale
    print(f"\n🎉 COMPLETATO!")
    print(f"📁 File generati: {successful_files}/{len(strategy_functions)}")
    
    if successful_files > 0:
        print(f"\n📋 FILE CREATI:")
        for strategy_name, url in file_urls.items():
            if url:
                date_obj = datetime.strptime(date, "%Y-%m-%d")
                formatted_date = date_obj.strftime("%d_%m_%Y")
                print(f"✅ {strategy_name}_{formatted_date}.csv")
            else:
                print(f"❌ {strategy_name}: Errore o nessun dato")
    
    return file_urls

