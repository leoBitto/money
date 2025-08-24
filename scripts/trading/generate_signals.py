# generate_signals.py
import pandas as pd
import psycopg2
import json
from google.cloud import secretmanager
from datetime import datetime
from typing import Callable
from .strategies import *

def get_db_connection(secret_name: str = "projects/trading-469418/secrets/db_info/versions/latest"):
    """
    Get PostgreSQL connection using secret stored in Google Secret Manager.
    
    Returns
    -------
    conn : psycopg2.connection
    """
    client_sm = secretmanager.SecretManagerServiceClient()
    response = client_sm.access_secret_version(name=secret_name)
    db_info = json.loads(response.payload.data.decode("UTF-8"))

    conn = psycopg2.connect(
        host=db_info["DB_HOST"],
        port=db_info["DB_PORT"],
        database=db_info["DB_NAME"],
        user=db_info["DB_USER"],
        password=db_info["DB_PASSWORD"]
    )
    return conn

def fetch_universe_data(conn, tickers: list, end_date: str) -> pd.DataFrame:
    """
    Fetch historical data from universe table up to end_date for given tickers.
    
    Parameters
    ----------
    conn : psycopg2.connection
        Database connection
    tickers : list
        List of tickers to fetch
    end_date : str
        Date string in 'YYYY-MM-DD'
    
    Returns
    -------
    pd.DataFrame
        DataFrame with historical data for tickers
    """
    cursor = conn.cursor()
    tickers_placeholder = ','.join(['%s'] * len(tickers))
    query = f"""
        SELECT ticker, date, open, high, low, close, volume
        FROM universe
        WHERE ticker IN ({tickers_placeholder})
        AND date <= %s
        ORDER BY ticker, date
    """
    cursor.execute(query, (*tickers, end_date))
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    df = pd.DataFrame(rows, columns=columns)
    cursor.close()
    return df

def generate_signals(strategy_func: Callable, tickers: list, end_date: str) -> pd.DataFrame:
    """
    Generate trading signals for a given strategy and tickers up to end_date.
    
    Parameters
    ----------
    strategy_func : Callable
        Function from strategies module that computes signals. Must accept DataFrame of historical data.
    tickers : list
        List of tickers to evaluate
    end_date : str
        Date string in 'YYYY-MM-DD'
    
    Returns
    -------
    pd.DataFrame
        DataFrame with columns: ticker, signal
    """
    conn = get_db_connection()
    df_hist = fetch_universe_data(conn, tickers, end_date)
    conn.close()

    signals_list = []

    for ticker in tickers:
        df_ticker = df_hist[df_hist['ticker'] == ticker].copy()
        if df_ticker.empty:
            continue
        signal = strategy_func(df_ticker)
        signals_list.append({'ticker': ticker, 'signal': signal})

    df_signals = pd.DataFrame(signals_list)
    return df_signals
