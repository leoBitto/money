# scripts/database.py
"""
Modulo: database
================

Funzioni di utilità per interagire con il database PostgreSQL.

Config utilizzati (da scripts/config.py):
- DB_SECRET_NAME: nome del secret che contiene le credenziali DB (es. "db_info")

Funzionalità principali:
------------------------
1. Connessione al database (interna)
   - _get_connection(db_info: dict) -> psycopg2.connection
   - _get_connection_context(db_info: dict)

2. Esecuzione query generiche
   - execute_query(query: str, params: tuple | None = None, fetch: bool = True) -> list[tuple] | None
   - execute_many(query: str, params_list: list[tuple]) -> None

3. Operazioni sulla tabella `universe`
   - insert_batch_universe(data: list[tuple], conflict_resolution: str = "DO NOTHING") -> int
   - get_available_tickers() -> list[str]
   - get_universe_data(start_date: str | None = None,
                       end_date: str | None = None,
                       tickers: list[str] | None = None) -> pd.DataFrame

Casi d'uso:
-----------
- Recuperare tickers disponibili:
    >>> from scripts.database import get_available_tickers
    >>> tickers = get_available_tickers()

- Inserire dati nella tabella universe:
    >>> from scripts.database import insert_batch_universe
    >>> rows = insert_batch_universe(data)

- Eseguire query custom:
    >>> from scripts.database import execute_query
    >>> res = execute_query("SELECT COUNT(*) FROM universe")

Note:
-----
- Le credenziali DB sono caricate dal Secret Manager tramite `google_services.get_secret`.
- Le funzioni interne (_get_connection, _get_connection_context) non dovrebbero essere usate direttamente fuori dal modulo.
"""

import psycopg2
import psycopg2.extras
import pandas as pd
from contextlib import contextmanager
from typing import Optional, List, Tuple

from . import config
from .google_services import get_secret


# ================================
# Internal helpers
# ================================

def _get_db_info() -> dict:
    """Recupera le credenziali del DB dal Secret Manager."""
    return get_secret(config.DB_SECRET_NAME)


def _get_connection(db_info: Optional[dict] = None):
    """Crea una connessione al DB PostgreSQL."""
    if db_info is None:
        db_info = _get_db_info()
    return psycopg2.connect(
        host=db_info["DB_HOST"],
        port=db_info["DB_PORT"],
        database=db_info["DB_NAME"],
        user=db_info["DB_USER"],
        password=db_info["DB_PASSWORD"],
    )


@contextmanager
def _get_connection_context(db_info: Optional[dict] = None):
    """Context manager per gestire automaticamente connessioni e transazioni."""
    conn = None
    try:
        conn = _get_connection(db_info)
        yield conn
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


# ================================
# External functions
# ================================

def execute_query(query: str, params: Optional[Tuple] = None, fetch: bool = True):
    """Esegue una query SQL generica e restituisce risultati + nomi colonne."""
    with _get_connection_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            results = cursor.fetchall() if fetch else []
            column_names = [desc[0] for desc in cursor.description] if cursor.description else []
            return results, column_names

def execute_many(query: str, params_list: List[Tuple]) -> None:
    """Esegue la stessa query con parametri multipli (batch insert/update)."""
    with _get_connection_context() as conn:
        with conn.cursor() as cursor:
            cursor.executemany(query, params_list)


def insert_batch_universe(data: List[Tuple], conflict_resolution: str = "DO NOTHING") -> int:
    """
    Inserisce dati nella tabella universe in batch.

    Args:
        data: Lista di tuple (date, ticker, open, high, low, close, volume)
        conflict_resolution: "DO NOTHING" (default) o "DO UPDATE"

    Returns:
        Numero di righe processate
    """
    if conflict_resolution == "DO NOTHING":
        query = """
        INSERT INTO universe (date, ticker, open, high, low, close, volume)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (date, ticker) DO NOTHING
        """
    elif conflict_resolution == "DO UPDATE":
        query = """
        INSERT INTO universe (date, ticker, open, high, low, close, volume)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (date, ticker) DO UPDATE 
        SET open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume
        """
    else:
        raise ValueError("conflict_resolution must be 'DO NOTHING' or 'DO UPDATE'")

    execute_many(query, data)
    return len(data)


def get_available_tickers() -> List[str]:
    """Recupera tutti i ticker disponibili dal DB."""
    query = "SELECT DISTINCT ticker FROM universe ORDER BY ticker"
    results = execute_query(query)
    return [row[0] for row in results] if results else []


def get_universe_data(start_date: Optional[str] = None,
                      end_date: Optional[str] = None,
                      tickers: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Recupera dati dalla tabella universe, filtrati per tickers e intervallo di date.

    Args:
        start_date: Data di inizio (inclusiva, 'YYYY-MM-DD'), opzionale
        end_date: Data di fine (inclusiva, 'YYYY-MM-DD'), opzionale
        tickers: Lista di ticker specifici, opzionale

    Returns:
        DataFrame con i dati storici richiesti
    """
    conditions = []
    params: List = []

    if tickers:
        placeholders = ','.join(['%s'] * len(tickers))
        conditions.append(f"ticker IN ({placeholders})")
        params.extend(tickers)

    if start_date:
        conditions.append("date >= %s")
        params.append(start_date)

    if end_date:
        conditions.append("date <= %s")
        params.append(end_date)

    where_clause = " AND ".join(conditions) if conditions else "TRUE"

    query = f"""
        SELECT ticker, date, open, high, low, close, volume
        FROM universe
        WHERE {where_clause}
        ORDER BY ticker, date
    """

    results = execute_query(query, tuple(params))
    if not results:
        return pd.DataFrame()

    columns = ['ticker', 'date', 'open', 'high', 'low', 'close', 'volume']
    df = pd.DataFrame(results, columns=columns)
    df['date'] = pd.to_datetime(df['date'])
    return df.rename(columns={
        'open': 'Open',
        'high': 'High',
        'low': 'Low',
        'close': 'Close',
        'volume': 'Volume',
    })
