# scripts/trading/generate_signals.py (REFACTORED)
import pandas as pd
from typing import Callable, List, Optional, Dict
from datetime import datetime

# Import delle utilities - CORREZIONE IMPORT PATHS
from scripts.utils.db.db_utils import DatabaseManager
from scripts.utils.trading_utils import apply_strategy_to_ticker, validate_strategy_parameters
from .strategies import *

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
    # Inizializza il database manager
    db_manager = DatabaseManager()
    
    # Se non sono specificati ticker, prendi tutti quelli disponibili
    if tickers is None:
        tickers = db_manager.get_available_tickers()
        print(f"Trovati {len(tickers)} ticker nel database")
    
    if not tickers:
        raise ValueError("Nessun ticker disponibile nel database")
    
    # Recupera i dati storici
    hist = db_manager.get_universe_data(date, tickers)
    
    if hist.empty:
        print(f"Nessun dato trovato per la data {date}")
        # Ritorna segnali neutri per tutti i ticker
        return pd.DataFrame([{'ticker': tk, 'signal': 0} for tk in tickers])
    
    # Valida i parametri della strategia
    validated_kwargs = validate_strategy_parameters(strategy_func, **strategy_kwargs)
    
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
        
        # Usa la funzione utility per applicare la strategia
        signal = apply_strategy_to_ticker(df_ticker, strategy_func, **validated_kwargs)
        results.append({'ticker': ticker, 'signal': signal})
        processed_count += 1
    
    print(f"Processati {processed_count}/{len(tickers)} ticker con successo")
    return pd.DataFrame(results)

def generate_all_strategies_signals(date: str, tickers: Optional[List[str]] = None) -> Dict[str, pd.DataFrame]:
    """
    Genera segnali per tutte le strategie disponibili.
    
    Returns:
    --------
    dict
        Dizionario con chiavi = nomi strategie, valori = DataFrame con segnali
    """
    strategies_config = {
        'moving_average_crossover': {'short_window': 3, 'long_window': 5},
        'rsi_strategy': {'period': 14, 'overbought': 70, 'oversold': 30},
        'breakout_strategy': {'lookback': 20}
    }
    
    all_signals = {}
    
    for strategy_name, params in strategies_config.items():
        print(f"Generando segnali per strategia: {strategy_name}")
        try:
            # Ottieni la funzione strategia dal modulo
            strategy_func = globals()[strategy_name]
            signals = generate_signals(strategy_func, date, tickers, **params)
            all_signals[strategy_name] = signals
        except Exception as e:
            print(f"Errore nella strategia {strategy_name}: {e}")
            all_signals[strategy_name] = pd.DataFrame()
    
    return all_signals