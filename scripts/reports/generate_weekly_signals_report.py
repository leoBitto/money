# scripts/reports/generate_weekly_signals_report.py

import inspect
import json
from datetime import datetime
from typing import Optional, Dict, List
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from google.cloud import secretmanager

from scripts.trading.generate_signals import generate_signals
from scripts.trading import strategies

# --- Configurazione Google Sheets ---
SECRET_NAME = "projects/trading-469418/secrets/service_account/versions/latest"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
WEEKLY_FOLDER_ID = "1pGSxyPjc8rotTFZp-HA-Xrl7yZHjDWDh"

def setup_google_client():
    """Configura e ritorna il client Google Sheets"""
    try:
        client_sm = secretmanager.SecretManagerServiceClient()
        response = client_sm.access_secret_version(name=SECRET_NAME)
        service_account_info = json.loads(response.payload.data.decode("UTF-8"))
        creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"❌ Errore configurazione Google Sheets: {e}")
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

def create_enhanced_signals_dataframe(df_signals: pd.DataFrame, 
                                     strategy_name: str, 
                                     date: str) -> pd.DataFrame:
    """Arricchisce il DataFrame con informazioni aggiuntive"""
    df_enhanced = df_signals.copy()
    
    # Aggiungi colonne informative
    df_enhanced['strategy'] = strategy_name
    df_enhanced['date'] = date
    df_enhanced['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Converti segnali numerici in descrizioni
    signal_map = {-1: 'SELL', 0: 'HOLD', 1: 'BUY'}
    df_enhanced['signal_description'] = df_enhanced['signal'].map(signal_map)
    
    # Riordina colonne
    cols = ['ticker', 'signal', 'signal_description', 'strategy', 'date', 'timestamp']
    df_enhanced = df_enhanced[cols]
    
    return df_enhanced

def create_statistics_data(df_signals: pd.DataFrame, strategy_name: str) -> List[List]:
    """Crea i dati delle statistiche per il Google Sheet"""
    total_tickers = len(df_signals)
    signal_counts = df_signals['signal'].value_counts()
    
    buy_count = signal_counts.get(1, 0)
    hold_count = signal_counts.get(0, 0)
    sell_count = signal_counts.get(-1, 0)
    
    stats_data = [
        ['Statistica', 'Valore', 'Percentuale'],
        ['Ticker Totali', total_tickers, '100.0%'],
        ['Segnali BUY', buy_count, f'{(buy_count/total_tickers*100):.1f}%' if total_tickers > 0 else '0%'],
        ['Segnali HOLD', hold_count, f'{(hold_count/total_tickers*100):.1f}%' if total_tickers > 0 else '0%'],
        ['Segnali SELL', sell_count, f'{(sell_count/total_tickers*100):.1f}%' if total_tickers > 0 else '0%'],
        [],
        ['Strategia', strategy_name, ''],
        ['Generato il', datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ''],
    ]
    
    return stats_data

def create_google_sheet(sheet_name: str, 
                       df_signals: pd.DataFrame, 
                       strategy_name: str, 
                       gc) -> Optional[str]:
    """Crea un Google Sheet con i dati dei segnali"""
    try:
        # Crea il sheet principale
        sh = gc.create(sheet_name, folder_id=WEEKLY_FOLDER_ID)
        worksheet = sh.sheet1
        worksheet.update_title("Signals")
        
        # Prepara e carica i dati principali
        data_to_upload = [df_signals.columns.tolist()] + df_signals.values.tolist()
        worksheet.update(data_to_upload)
        
        # Formatta header
        worksheet.format('A1:Z1', {
            'backgroundColor': {'red': 0.2, 'green': 0.6, 'blue': 0.9},
            'textFormat': {'bold': True, 'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}}
        })
        
        # Aggiungi sheet con statistiche
        stats_sheet = sh.add_worksheet(title="Statistics", rows="50", cols="5")
        stats_data = create_statistics_data(df_signals, strategy_name)
        stats_sheet.update(stats_data)
        
        # Formatta header statistiche
        stats_sheet.format('A1:C1', {
            'backgroundColor': {'red': 0.9, 'green': 0.6, 'blue': 0.2},
            'textFormat': {'bold': True}
        })
        
        return sh.url
        
    except Exception as e:
        print(f"❌ Errore creazione Google Sheet {sheet_name}: {e}")
        return None

def generate_single_strategy_report(strategy_name: str, 
                                  strategy_func, 
                                  date: str, 
                                  gc, 
                                  strategy_params: Optional[Dict] = None) -> Optional[str]:
    """Genera un report per una singola strategia"""
    try:
        print(f"📊 Generando report per {strategy_name}...")
        
        # Genera i segnali
        if strategy_params:
            df_signals = generate_signals(strategy_func, date, **strategy_params)
        else:
            df_signals = generate_signals(strategy_func, date)
        
        if df_signals.empty:
            print(f"⚠️  Nessun segnale per {strategy_name}")
            return None
        
        # Arricchisci il DataFrame
        df_enhanced = create_enhanced_signals_dataframe(df_signals, strategy_name, date)
        
        # Crea il Google Sheet
        sheet_name = f"{strategy_name}_{date}"
        url = create_google_sheet(sheet_name, df_enhanced, strategy_name, gc)
        
        if url:
            signal_counts = df_signals['signal'].value_counts()
            print(f"✅ {strategy_name}: {len(df_signals)} ticker, "
                  f"Buy: {signal_counts.get(1, 0)}, "
                  f"Hold: {signal_counts.get(0, 0)}, "
                  f"Sell: {signal_counts.get(-1, 0)}")
            return url
        else:
            return None
            
    except Exception as e:
        print(f"❌ Errore {strategy_name}: {e}")
        return None

def generate_weekly_signals_report(date: Optional[str] = None) -> Dict[str, Optional[str]]:
    """
    Funzione principale per generare i report settimanali.
    
    Parameters:
    -----------
    date : Optional[str]
        Data per cui generare i report (formato YYYY-MM-DD).
        Se None, usa la data odierna.
    
    Returns:
    --------
    Dict[str, Optional[str]]
        Dizionario con nome_strategia -> URL del Google Sheet (None se errore)
    """
    if date is None:
        date = datetime.today().strftime("%Y-%m-%d")
    
    print("🚀 GENERAZIONE REPORT SETTIMANALI")
    print("=" * 50)
    print(f"📅 Data: {date}")
    
    # Setup Google Sheets client
    try:
        gc = setup_google_client()
        print("✅ Google Sheets client configurato")
    except Exception as e:
        print(f"❌ Impossibile configurare Google Sheets: {e}")
        return {}
    
    # Recupera le strategie disponibili
    strategy_functions = get_strategy_functions()
    print(f"📈 Trovate {len(strategy_functions)} strategie: {[name for name, _ in strategy_functions]}")
    
    # Parametri di default per le strategie
    default_params = {
        'moving_average_crossover': {'short_window': 3, 'long_window': 5},
        'rsi_strategy': {'period': 14, 'overbought': 70, 'oversold': 30},
        'breakout_strategy': {'lookback': 20}
    }
    
    # Genera report per ogni strategia
    report_urls = {}
    successful_reports = 0
    
    print(f"\n📊 Generando report...")
    for strategy_name, strategy_func in strategy_functions:
        params = default_params.get(strategy_name, {})
        url = generate_single_strategy_report(strategy_name, strategy_func, date, gc, params)
        report_urls[strategy_name] = url
        
        if url:
            successful_reports += 1
    
    # Riepilogo finale
    print(f"\n🎉 COMPLETATO!")
    print(f"📊 Report generati: {successful_reports}/{len(strategy_functions)}")
    print(f"\n📋 RIEPILOGO:")
    
    for strategy_name, url in report_urls.items():
        if url:
            print(f"✅ {strategy_name}: {url}")
        else:
            print(f"❌ {strategy_name}: Errore o nessun dato")
    
    return report_urls

