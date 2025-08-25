# scripts/utils/trading_utils.py
import pandas as pd
import inspect
from typing import Callable, Dict, List, Optional, Any, Tuple
from datetime import datetime

def format_signal_text(signal_value: int) -> str:
    """
    Converte segnali numerici in testo leggibile
    
    Args:
        signal_value: Valore numerico del segnale (-1, 0, 1)
    
    Returns:
        Stringa rappresentante il segnale ("SELL", "HOLD", "BUY")
    """
    signal_map = {-1: "SELL", 0: "HOLD", 1: "BUY"}
    return signal_map.get(signal_value, "UNKNOWN")

def format_signals_column(df: pd.DataFrame, signal_col: str = 'signal') -> pd.DataFrame:
    """
    Converte una colonna di segnali numerici in testo
    
    Args:
        df: DataFrame contenente i segnali
        signal_col: Nome della colonna contenente i segnali numerici
    
    Returns:
        DataFrame con segnali in formato testo
    """
    df = df.copy()
    df[signal_col] = df[signal_col].map(format_signal_text)
    return df

def calculate_signal_distribution(signals_df: pd.DataFrame, signal_col: str = 'signal') -> Dict[str, int]:
    """
    Calcola la distribuzione dei segnali
    
    Args:
        signals_df: DataFrame con i segnali
        signal_col: Nome della colonna contenente i segnali
    
    Returns:
        Dizionario con il conteggio di ogni tipo di segnale
    """
    if signal_col not in signals_df.columns:
        return {"BUY": 0, "HOLD": 0, "SELL": 0}
    
    # Se i segnali sono numerici, convertili prima
    if signals_df[signal_col].dtype in ['int64', 'float64']:
        temp_df = format_signals_column(signals_df, signal_col)
        return temp_df[signal_col].value_counts().to_dict()
    else:
        return signals_df[signal_col].value_counts().to_dict()

def get_strategy_functions(strategies_module) -> List[Tuple[str, Callable]]:
    """
    Recupera tutte le funzioni strategia da un modulo
    
    Args:
        strategies_module: Modulo contenente le strategie
    
    Returns:
        Lista di tuple (nome_strategia, funzione_strategia)
    """
    strategy_functions = []
    for name, func in inspect.getmembers(strategies_module, inspect.isfunction):
        # Filtra solo le funzioni che hanno il parametro 'df' (sono strategie)
        sig = inspect.signature(func)
        if 'df' in sig.parameters:
            strategy_functions.append((name, func))
    return strategy_functions

def apply_strategy_to_ticker(df_ticker: pd.DataFrame, strategy_func: Callable, **strategy_kwargs) -> int:
    """
    Applica una strategia a un singolo ticker e restituisce l'ultimo segnale
    
    Args:
        df_ticker: DataFrame con dati OHLCV per un singolo ticker
        strategy_func: Funzione strategia da applicare
        **strategy_kwargs: Parametri aggiuntivi per la strategia
    
    Returns:
        Ultimo segnale valido (-1, 0, o 1)
    """
    if df_ticker.empty:
        return 0
    
    try:
        # Applica la strategia
        df_with_signals = strategy_func(df_ticker, **strategy_kwargs)
        
        # Prendi l'ultimo segnale valido (non NaN)
        valid_signals = df_with_signals['signal'].dropna()
        if not valid_signals.empty:
            return int(valid_signals.iloc[-1])
        else:
            return 0
            
    except Exception as e:
        print(f"Errore nell'applicare la strategia: {e}")
        return 0

def validate_strategy_parameters(strategy_func: Callable, **kwargs) -> Dict[str, Any]:
    """
    Valida i parametri per una strategia specifica
    
    Args:
        strategy_func: Funzione strategia
        **kwargs: Parametri da validare
    
    Returns:
        Dizionario con parametri validati
    """
    sig = inspect.signature(strategy_func)
    valid_params = {}
    
    for param_name, param in sig.parameters.items():
        if param_name == 'df':
            continue
            
        if param_name in kwargs:
            valid_params[param_name] = kwargs[param_name]
        elif param.default != inspect.Parameter.empty:
            valid_params[param_name] = param.default
    
    return valid_params

def create_signals_summary(all_signals: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Crea un riassunto di tutti i segnali delle strategie
    
    Args:
        all_signals: Dizionario con chiave=nome_strategia, valore=DataFrame segnali
    
    Returns:
        DataFrame riassuntivo con statistiche per strategia
    """
    summary_data = []
    
    for strategy_name, signals_df in all_signals.items():
        if signals_df.empty:
            summary_data.append({
                'Strategy': strategy_name,
                'Total_Tickers': 0,
                'BUY': 0,
                'HOLD': 0,
                'SELL': 0,
                'BUY_Pct': 0.0,
                'SELL_Pct': 0.0
            })
            continue
        
        # Calcola distribuzione
        distribution = calculate_signal_distribution(signals_df)
        total = len(signals_df)
        
        summary_data.append({
            'Strategy': strategy_name,
            'Total_Tickers': total,
            'BUY': distribution.get('BUY', 0),
            'HOLD': distribution.get('HOLD', 0), 
            'SELL': distribution.get('SELL', 0),
            'BUY_Pct': round(distribution.get('BUY', 0) / total * 100, 1) if total > 0 else 0.0,
            'SELL_Pct': round(distribution.get('SELL', 0) / total * 100, 1) if total > 0 else 0.0
        })
    
    return pd.DataFrame(summary_data)

def filter_signals_by_type(signals_df: pd.DataFrame, signal_type: str, signal_col: str = 'signal') -> pd.DataFrame:
    """
    Filtra segnali per tipo specifico
    
    Args:
        signals_df: DataFrame con i segnali
        signal_type: Tipo di segnale ("BUY", "SELL", "HOLD" o -1, 0, 1)
        signal_col: Nome della colonna contenente i segnali
    
    Returns:
        DataFrame filtrato
    """
    # Mappa per conversione testo -> numero
    text_to_num = {"SELL": -1, "HOLD": 0, "BUY": 1}
    num_to_text = {-1: "SELL", 0: "HOLD", 1: "BUY"}
    
    # Converti il tipo richiesto se necessario
    if isinstance(signal_type, str) and signal_type in text_to_num:
        target_value = text_to_num[signal_type]
    elif isinstance(signal_type, int) and signal_type in num_to_text:
        target_value = num_to_text[signal_type]
    else:
        target_value = signal_type
    
    return signals_df[signals_df[signal_col] == target_value]

def combine_strategy_signals(signals_dict: Dict[str, pd.DataFrame], 
                            combination_method: str = "majority") -> pd.DataFrame:
    """
    Combina segnali di multiple strategie
    
    Args:
        signals_dict: Dizionario con segnali delle diverse strategie
        combination_method: Metodo di combinazione ("majority", "unanimous", "any_buy")
    
    Returns:
        DataFrame con segnali combinati
    """
    if not signals_dict:
        return pd.DataFrame()
    
    # Prendi tutti i ticker
    all_tickers = set()
    for df in signals_dict.values():
        if not df.empty:
            all_tickers.update(df['ticker'].tolist())
    
    combined_signals = []
    
    for ticker in all_tickers:
        ticker_signals = []
        
        # Raccogli segnali per questo ticker da tutte le strategie
        for strategy_name, df in signals_dict.items():
            ticker_data = df[df['ticker'] == ticker]
            if not ticker_data.empty:
                signal = ticker_data.iloc[0]['signal']
                # Converti in numerico se necessario
                if isinstance(signal, str):
                    signal = {"SELL": -1, "HOLD": 0, "BUY": 1}.get(signal, 0)
                ticker_signals.append(signal)
        
        if not ticker_signals:
            combined_signal = 0
        elif combination_method == "majority":
            # Segnale maggioritario
            combined_signal = max(set(ticker_signals), key=ticker_signals.count)
        elif combination_method == "unanimous":
            # Tutti devono essere d'accordo
            if len(set(ticker_signals)) == 1:
                combined_signal = ticker_signals[0]
            else:
                combined_signal = 0  # Hold se non unanimi
        elif combination_method == "any_buy":
            # Buy se almeno una strategia dice buy
            combined_signal = 1 if 1 in ticker_signals else (max(ticker_signals) if ticker_signals else 0)
        else:
            combined_signal = 0
        
        combined_signals.append({'ticker': ticker, 'signal': combined_signal})
    
    return pd.DataFrame(combined_signals)