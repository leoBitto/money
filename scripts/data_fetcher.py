# scripts/data_fetcher.py
"""
Modulo: data_fetcher
====================

Funzioni di utilità per scaricare e preparare dati da Yahoo Finance (yfinance).

Config utilizzati (da scripts/config.py):
- YFINANCE_DEFAULT_PERIOD
- YFINANCE_DEFAULT_INTERVAL
- YFINANCE_HISTORY_PERIOD
- YFINANCE_MAX_RETRIES
- YFINANCE_RETRY_DELAY

Funzionalità principali:
------------------------
1. Recupero dati da yfinance (interna)
   - _fetch_yfinance_data(tickers: list[str], period: str = ..., interval: str = ...) -> pd.DataFrame

2. Normalizzazione dei dati (interna)
   - _normalize_yf_dataframe(df: pd.DataFrame) -> pd.DataFrame

3. Preparazione dei dati pronti per l’inserimento nel DB
   - get_daily_data_for_db(tickers: list[str]) -> list[tuple]

Casi d'uso:
-----------
- Scaricare e normalizzare i dati:
    >>> from scripts.data_fetcher import get_daily_data_for_db
    >>> rows = get_daily_data_for_db(["AAPL", "TSLA"])
    >>> # rows è una lista di tuple pronta per insert_batch_universe()

Note:
-----
- Le funzioni interne (_fetch_yfinance_data, _normalize_yf_dataframe) non dovrebbero essere usate direttamente.
- I retry sono configurati tramite scripts/config.py.
"""

import time
import pandas as pd
import yfinance as yf
from typing import List, Tuple

from . import config


# ================================
# Internal helpers
# ================================

def _fetch_yfinance_data(
    tickers: List[str],
    period: str = config.YFINANCE_DEFAULT_PERIOD,
    interval: str = config.YFINANCE_DEFAULT_INTERVAL,
) -> pd.DataFrame:
    """
    Scarica dati da yfinance per una lista di ticker.

    Args:
        tickers: lista di ticker
        period: periodo (es. '1d', '5d')
        interval: intervallo (es. '1d', '1h')

    Returns:
        DataFrame con i dati grezzi di yfinance
    """
    retries = 0
    while retries < config.YFINANCE_MAX_RETRIES:
        try:
            df = yf.download(
                tickers=tickers,
                period=period,
                interval=interval,
                group_by="ticker",
                auto_adjust=False,
                threads=True,
                progress=False,
            )
            return df
        except Exception as e:
            retries += 1
            if retries >= config.YFINANCE_MAX_RETRIES:
                raise
            time.sleep(config.YFINANCE_RETRY_DELAY)


def _normalize_yf_dataframe(df: pd.DataFrame, tickers: List[str]) -> pd.DataFrame:
    """
    Normalizza il DataFrame yfinance:
    - colonne lowercase
    - aggiunge colonna 'ticker'
    - converte date in datetime

    Args:
        df: DataFrame yfinance multi-ticker
        tickers: lista di ticker scaricati

    Returns:
        DataFrame normalizzato
    """
    if isinstance(df.columns, pd.MultiIndex):
        # Caso multi-ticker
        frames = []
        for ticker in tickers:
            if ticker not in df.columns.levels[0]:
                continue
            sub = df[ticker].copy()
            sub["ticker"] = ticker
            frames.append(sub)
        df = pd.concat(frames)
    else:
        # Caso singolo ticker
        df = df.copy()
        df["ticker"] = tickers[0]

    # Normalizza nomi colonne
    df.columns = [c.lower() for c in df.columns]

    df = df.reset_index()
    df.rename(columns={df.columns[0]: "date"}, inplace=True)
    df["date"] = pd.to_datetime(df["date"])

    return df[["date", "ticker", "open", "high", "low", "close", "volume"]]


# ================================
# External functions
# ================================

def get_daily_data_for_db(tickers: List[str]) -> List[Tuple]:
    """
    Recupera i dati giornalieri da yfinance e li normalizza per il DB.

    Args:
        tickers: lista di ticker

    Returns:
        Lista di tuple (date, ticker, open, high, low, close, volume)
    """
    raw_df = _fetch_yfinance_data(tickers, period="1d", interval=config.YFINANCE_DEFAULT_INTERVAL)
    norm_df = _normalize_yf_dataframe(raw_df, tickers)

    # Converte in lista di tuple
    return list(norm_df.itertuples(index=False, name=None))


def get_data_for_db_between_dates(
    tickers: List[str],
    start_date: str,
    end_date: str | None = None
) -> List[Tuple]:
    """
    Scarica dati da yfinance tra due date e li normalizza per il DB.

    Args:
        tickers: lista di ticker
        start_date: data inizio (YYYY-MM-DD)
        end_date: data fine (YYYY-MM-DD), se None usa oggi

    Returns:
        Lista di tuple (date, ticker, open, high, low, close, volume)
    """
    raw_df = yf.download(
        tickers=tickers,
        start=start_date,
        end=end_date,
        interval=config.YFINANCE_DEFAULT_INTERVAL,
        group_by="ticker",
        auto_adjust=False,
        threads=True,
        progress=False,
    )
    norm_df = _normalize_yf_dataframe(raw_df, tickers)
    return list(norm_df.itertuples(index=False, name=None))