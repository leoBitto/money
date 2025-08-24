# scripts/trading/generate_signals.py
import pandas as pd
import psycopg2
import json
from google.cloud import secretmanager
from typing import Callable, List, Optional
from datetime import datetime
from .strategies import *

def get_db_connection(secret_name: str = "projects/trading-469418/secrets/db_info/versions/latest"):
    """Stabilisce connessione al database usando Google Secret Manager"""
    client_sm = secretmanager.SecretManagerServiceClient()
    response = client_sm.access_secret_version(name=secret_name)
    db_info = json.loads(response.payload.data.decode("UTF-8"))
    return psycopg2.connect(
        host=db_info["DB_HOST"],
        port=db_info["DB_PORT"],
        database=db_info["DB_NAME"],
        user=db_info["DB_USER"],
        password=db_info["DB_PASSWORD"]
    )

def fetch_available_tickers(conn) -> List[str]:
    """Recupera tutti i ticker disponibili nel database"""
    cursor = conn.cursor()
    query = "SELECT DISTINCT ticker FROM universe ORDER BY ticker"
    cursor.execute(query)
    tickers = [row[0] for row in cursor.fetchall()]
    cursor.close()
    return tickers

def fetch_universe_data(conn, end_date: str, tickers: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Recupera i dati storici dal database.
    Se tickers è None, recupera tutti i ticker disponibili.
    """
    cursor = conn.cursor()
    
    if tickers:
        # Usa placeholder per evitare SQL injection
        placeholders = ','.join(['%s'] * len(tickers))
        query = f"""
            SELECT ticker, date, open, high, low, close, volume
            FROM universe
            WHERE ticker IN ({placeholders})
              AND date <= %s
            ORDER BY ticker, date
        """
        cursor.execute(query, tickers + [end_date])
    else:
        query = """
            SELECT ticker, date, open, high, low, close, volume
            FROM universe
            WHERE date <= %s
            ORDER BY ticker, date
        """
        cursor.execute(query, [end_date])
    
    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]
    cursor.close()
    
    df = pd.DataFrame(rows, columns=cols)
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
        # Rinomina le colonne per essere compatibili con le strategie
        df = df.rename(columns={
            'open': 'Open',
            'high': 'High', 
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume'
        })
    return df

def generate_signals(strategy_func: Callable, date: str, tickers: Optional[List[str]] = None, **strategy_kwargs) -> pd.DataFrame:
    """
    Applica la strategia a ciascun ticker e restituisce il segnale alla data specificata.
    
    Parameters:
    -----------
    strategy_func : Callable
        Funzione strategia da applicare (es. moving_average_crossover, rsi_strategy, breakout_strategy)
    date : str
        Data fino alla quale considerare i dati (formato 'YYYY-MM-DD')
    tickers : Optional[List[str]]
        Lista di ticker specifici. Se None, usa tutti i ticker disponibili
    **strategy_kwargs
        Parametri aggiuntivi da passare alla funzione strategia
    
    Returns:
    --------
    pd.DataFrame
        DataFrame con colonne ['ticker', 'signal'] dove signal è in {-1, 0, 1}
    """
    conn = get_db_connection()
    
    try:
        # Se non sono specificati ticker, prendi tutti quelli disponibili
        if tickers is None:
            tickers = fetch_available_tickers(conn)
            print(f"Trovati {len(tickers)} ticker nel database")
        
        if not tickers:
            raise ValueError("Nessun ticker disponibile nel database")
        
        # Recupera i dati storici
        hist = fetch_universe_data(conn, date, tickers)
        
        if hist.empty:
            print(f"Nessun dato trovato per la data {date}")
            # Ritorna segnali neutri per tutti i ticker
            return pd.DataFrame([{'ticker': tk, 'signal': 0} for tk in tickers])
        
    finally:
        conn.close()

    results = []
    processed_count = 0
    
    for ticker in tickers:
        df_ticker = hist[hist['ticker'] == ticker].copy()
        
        if df_ticker.empty:
            # Nessun dato per questo ticker
            results.append({'ticker': ticker, 'signal': 0})
            continue
            
        # Ordina per data e applica la strategia
        df_ticker = df_ticker.sort_values('date').reset_index(drop=True)
        
        try:
            # Applica la strategia con i parametri aggiuntivi
            df_with_signals = strategy_func(df_ticker, **strategy_kwargs)
            
            # Prendi l'ultimo segnale valido (non NaN)
            valid_signals = df_with_signals['signal'].dropna()
            if not valid_signals.empty:
                last_signal = int(valid_signals.iloc[-1])
            else:
                last_signal = 0
                
            results.append({'ticker': ticker, 'signal': last_signal})
            processed_count += 1
            
        except Exception as e:
            print(f"Errore nell'applicare la strategia per {ticker}: {e}")
            results.append({'ticker': ticker, 'signal': 0})
    
    print(f"Processati {processed_count}/{len(tickers)} ticker con successo")
    return pd.DataFrame(results)

def generate_all_strategies_signals(date: str, tickers: Optional[List[str]] = None) -> dict:
    """
    Genera segnali per tutte le strategie disponibili.
    
    Returns:
    --------
    dict
        Dizionario con chiavi = nomi strategie, valori = DataFrame con segnali
    """
    strategies = {
        'moving_average_crossover': (moving_average_crossover, {'short_window': 3, 'long_window': 5}),
        'rsi_strategy': (rsi_strategy, {'period': 14, 'overbought': 70, 'oversold': 30}),
        'breakout_strategy': (breakout_strategy, {'lookback': 20})
    }
    
    all_signals = {}
    
    for strategy_name, (strategy_func, params) in strategies.items():
        print(f"Generando segnali per strategia: {strategy_name}")
        try:
            signals = generate_signals(strategy_func, date, tickers, **params)
            all_signals[strategy_name] = signals
        except Exception as e:
            print(f"Errore nella strategia {strategy_name}: {e}")
            all_signals[strategy_name] = pd.DataFrame()
    
    return all_signals

