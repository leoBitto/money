import logging
import psycopg2
import psycopg2.extras
import pandas as pd
from contextlib import contextmanager
from typing import Optional, List, Tuple

from . import config
from .google_services import get_secret

logger = logging.getLogger(__name__)

def _get_db_info() -> dict:
    return get_secret(config.DB_SECRET_NAME)

def _get_connection(db_info: Optional[dict] = None):
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
    conn = None
    try:
        conn = _get_connection(db_info)
        yield conn
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("DB error: %s", e, exc_info=True)
        raise
    finally:
        if conn:
            conn.close()

def execute_query(query: str, params: Optional[Tuple] = None, fetch: bool = True, with_columns: bool = True):
    """Esegue query SQL generica. Restituisce solo i dati o anche nomi colonne se richiesto."""
    with _get_connection_context() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            if not fetch:
                return []
            rows = cursor.fetchall()
            if with_columns:
                colnames = [desc[0] for desc in cursor.description] if cursor.description else []
                return rows, colnames
            return rows

def execute_many(query: str, params_list: List[Tuple]) -> None:
    """Batch insert/update più efficiente con execute_values."""
    with _get_connection_context() as conn:
        with conn.cursor() as cursor:
            psycopg2.extras.execute_values(cursor, query, params_list)

def insert_batch_universe(data: List[Tuple], conflict_resolution: str = "DO NOTHING") -> int:
    if conflict_resolution == "DO NOTHING":
        query = """
        INSERT INTO universe (date, ticker, open, high, low, close, volume)
        VALUES %s
        ON CONFLICT (date, ticker) DO NOTHING
        """
    elif conflict_resolution == "DO UPDATE":
        query = """
        INSERT INTO universe (date, ticker, open, high, low, close, volume)
        VALUES %s
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
    query = "SELECT DISTINCT ticker FROM universe ORDER BY ticker"
    rows = execute_query(query)
    return [row[0] for row in rows]

def get_universe_data(start_date: Optional[str] = None,
                      end_date: Optional[str] = None,
                      tickers: Optional[List[str]] = None) -> pd.DataFrame:
    conditions, params = [], []
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
    rows, colnames = execute_query(query, tuple(params), with_columns=True)
    if not rows:
        return pd.DataFrame(columns=colnames)
    df = pd.DataFrame(rows, columns=colnames)
    df['date'] = pd.to_datetime(df['date'])
    return df.rename(columns=str.capitalize)


def create_universe_table():
    universe_query = """
        CREATE TABLE universe (
        date DATE NOT NULL,
        ticker VARCHAR(50) NOT NULL,
        open NUMERIC(18,6),
        high NUMERIC(18,6),
        low NUMERIC(18,6),
        close NUMERIC(18,6),
        volume NUMERIC(20,2),
        PRIMARY KEY (date, ticker)
        """

    execute_query(universe_query, fetch=False)

def create_portfolio_tables():
    """
    Crea tabelle portfolio con schema aggiornato incluso entry_atr.
    """
    snapshots_query = """
    CREATE TABLE IF NOT EXISTS portfolio_snapshots (
        date DATE NOT NULL,
        portfolio_name VARCHAR(50) NOT NULL DEFAULT 'default',
        
        -- Valori base portafoglio
        total_value DECIMAL(12,2) NOT NULL,
        cash_balance DECIMAL(12,2) NOT NULL,
        positions_count INTEGER DEFAULT 0,
        
        -- Metriche performance
        daily_return_pct DECIMAL(8,4),
        portfolio_volatility DECIMAL(8,4),
        current_drawdown_pct DECIMAL(8,4),
        peak_value DECIMAL(12,2),
        
        -- Metadata
        created_at TIMESTAMP DEFAULT NOW(),
        
        PRIMARY KEY (date, portfolio_name)
    );
    """

    positions_query = """
    CREATE TABLE IF NOT EXISTS portfolio_positions (
        date DATE NOT NULL,
        portfolio_name VARCHAR(50) NOT NULL DEFAULT 'default',
        ticker VARCHAR(10) NOT NULL,
        
        -- Dati posizione
        shares INTEGER NOT NULL,
        avg_cost DECIMAL(10,4) NOT NULL,
        current_price DECIMAL(10,4) NOT NULL,
        current_value DECIMAL(12,2) NOT NULL,

        -- Risk management  
        stop_loss DECIMAL(10,4),
        first_target DECIMAL(10,4),
        breakeven DECIMAL(10,4),
        first_half_sold BOOLEAN DEFAULT FALSE,
        entry_atr DECIMAL(6,4),  

        -- Metriche posizione
        position_weight_pct DECIMAL(8,4),
        position_pnl_pct DECIMAL(8,4),
        position_volatility DECIMAL(8,4),
        
        -- Metadata
        created_at TIMESTAMP DEFAULT NOW(),
        
        PRIMARY KEY (date, portfolio_name, ticker)
    );
    """

    indices_query = """
    CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_date 
        ON portfolio_snapshots(date);

    CREATE INDEX IF NOT EXISTS idx_portfolio_positions_ticker 
        ON portfolio_positions(ticker);

    CREATE INDEX IF NOT EXISTS idx_portfolio_positions_weight 
        ON portfolio_positions(position_weight_pct DESC);
    """

    # Esegui creazione tabelle
    execute_query(snapshots_query, fetch=False)
    execute_query(positions_query, fetch=False)
    execute_query(indices_query, fetch=False)
    
    # Assicurati che entry_atr esista su DB esistenti
    add_entry_atr_column()
    
    logger.info("Tabelle portfolio create/aggiornate con successo")