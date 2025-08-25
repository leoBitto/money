# scripts/utils/data_utils.py
import pandas as pd
import yfinance as yf
from typing import List, Dict, Any, Optional
from datetime import datetime

def download_yfinance_data(tickers: List[str], period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """
    Scarica dati da yfinance e li normalizza
    
    Args:
        tickers: Lista di ticker da scaricare
        period: Periodo dei dati ("1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max")
        interval: Intervallo dei dati ("1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo")
    
    Returns:
        DataFrame normalizzato con colonne: date, ticker, open, high, low, close, volume
    """
    print(f"Scaricando dati per {len(tickers)} ticker (periodo: {period}, intervallo: {interval})")
    
    # Scarica i dati
    prices = yf.download(
        tickers, 
        period=period, 
        interval=interval, 
        group_by="ticker", 
        auto_adjust=True, 
        progress=False
    )
    
    return normalize_price_data(prices, tickers)

def normalize_price_data(prices_df: pd.DataFrame, tickers: List[str]) -> pd.DataFrame:
    """
    Normalizza i dati di prezzo in formato standard
    
    Args:
        prices_df: DataFrame restituito da yfinance
        tickers: Lista di ticker
    
    Returns:
        DataFrame normalizzato con colonne: date, ticker, open, high, low, close, volume
    """
    records = []
    
    for ticker in tickers:
        try:
            # Gestisci il caso di singolo ticker vs multipli
            if len(tickers) == 1:
                df_ticker = prices_df.copy()
            else:
                df_ticker = prices_df[ticker]
            
            # Assicurati di avere le colonne necessarie
            required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            df_ticker = df_ticker[required_cols].reset_index()
            
            # Aggiungi ticker
            df_ticker['Ticker'] = ticker
            
            # Rinomina colonne
            df_ticker = df_ticker.rename(columns={
                'Date': 'date',
                'Open': 'open',
                'High': 'high', 
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume',
                'Ticker': 'ticker'
            })
            
            # Converti in lista di dizionari
            records.extend(df_ticker.to_dict(orient='records'))
            
        except Exception as e:
            print(f"Errore processando {ticker}: {e}")
            continue
    
    return pd.DataFrame(records)

def prepare_db_batch(df: pd.DataFrame) -> List[tuple]:
    """
    Prepara i dati per l'inserimento batch nel database
    
    Args:
        df: DataFrame con colonne: date, ticker, open, high, low, close, volume
    
    Returns:
        Lista di tuple pronte per l'inserimento DB
    """
    batch = []
    for _, row in df.iterrows():
        # Converte la data se necessario
        date_val = row['date'].date() if hasattr(row['date'], 'date') else row['date']
        
        batch.append((
            date_val,
            row['ticker'],
            float(row['open']) if pd.notna(row['open']) else None,
            float(row['high']) if pd.notna(row['high']) else None, 
            float(row['low']) if pd.notna(row['low']) else None,
            float(row['close']) if pd.notna(row['close']) else None,
            float(row['volume']) if pd.notna(row['volume']) else None
        ))
    
    return batch

def clean_dataframe(df: pd.DataFrame, drop_na_columns: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Pulisce un DataFrame rimuovendo righe con valori mancanti
    
    Args:
        df: DataFrame da pulire
        drop_na_columns: Lista di colonne specifiche da controllare per NA. Se None, controlla tutte
    
    Returns:
        DataFrame pulito
    """
    if drop_na_columns:
        return df.dropna(subset=drop_na_columns)
    else:
        return df.dropna()

def calculate_returns(prices: pd.Series) -> pd.Series:
    """
    Calcola i rendimenti percentuali di una serie di prezzi
    
    Args:
        prices: Serie di prezzi
    
    Returns:
        Serie di rendimenti percentuali
    """
    return prices.pct_change()

def resample_ohlcv(df: pd.DataFrame, freq: str, price_col: str = 'Close') -> pd.DataFrame:
    """
    Ricampiona i dati OHLCV a una frequenza diversa
    
    Args:
        df: DataFrame con dati OHLCV e colonna 'date'
        freq: Frequenza di ricampionamento ('D', 'W', 'M', etc.)
        price_col: Nome della colonna prezzo principale
    
    Returns:
        DataFrame ricampionato
    """
    df = df.copy()
    df = df.set_index('date')
    
    agg_dict = {
        'Open': 'first',
        'High': 'max', 
        'Low': 'min',
        'Close': 'last',
        'Volume': 'sum'
    }
    
    # Usa solo le colonne presenti
    agg_dict = {k: v for k, v in agg_dict.items() if k in df.columns}
    
    resampled = df.resample(freq).agg(agg_dict)
    return resampled.reset_index()

def merge_signals_with_data(data_df: pd.DataFrame, signals_df: pd.DataFrame, 
                           on_columns: List[str] = ['ticker']) -> pd.DataFrame:
    """
    Unisce i dati di prezzo con i segnali di trading
    
    Args:
        data_df: DataFrame con dati di prezzo
        signals_df: DataFrame con segnali
        on_columns: Colonne su cui fare il merge
    
    Returns:
        DataFrame unito
    """
    return pd.merge(data_df, signals_df, on=on_columns, how='left')