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

def get_last_close(ticker: str) -> Optional[float]:
    """
    Ritorna l'ultimo prezzo di chiusura per un ticker dal database UNIVERSE.
    
    Parameters
    ----------
    ticker : str
        Il simbolo del titolo (es. "AAPL").
    
    Returns
    -------
    close : float | None
        L'ultimo prezzo di chiusura, oppure None se il ticker non esiste.
    """
    query = """
        SELECT date, close
        FROM UNIVERSE
        WHERE ticker = %s
        ORDER BY date DESC
        LIMIT 1
    """
    rows, _ = execute_query(query, (ticker,))
    return rows[0][1] if rows else None

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
    return df


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
        );
        """

    execute_query(universe_query, fetch=False)

def create_portfolio_tables():
    """
    Crea tutte le tabelle portfolio (normali e backtest) con schema completo.
    Include snapshots, positions, trades e relativi indici.
    """
    
    # ===============================
    # TABELLE PRINCIPALI
    # ===============================
    
    snapshots_query = """
        CREATE TABLE portfolio_snapshots (
        date DATE NOT NULL,
        portfolio_name VARCHAR(50) NOT NULL,

        -- Stato base del portafoglio
        total_value DECIMAL(12,2) NOT NULL,
        cash_balance DECIMAL(12,2) NOT NULL,
        positions_count INTEGER DEFAULT 0,

        -- Metriche performance
        total_return_pct DECIMAL(8,4),
        max_drawdown_pct DECIMAL(8,4),
        volatility_pct DECIMAL(8,4),
        sharpe_ratio DECIMAL(8,4),
        win_rate_pct DECIMAL(8,4),

        -- Metadata
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),

        PRIMARY KEY (date, portfolio_name)

    );
    """

    positions_query = """
        CREATE TABLE portfolio_positions (
            date DATE NOT NULL,
            portfolio_name VARCHAR(50) NOT NULL,
            ticker VARCHAR(10) NOT NULL,

            -- Dati base
            shares INTEGER NOT NULL,
            avg_cost DECIMAL(10,4) NOT NULL,
            current_price DECIMAL(10,4) NOT NULL,

            -- Risk management
            stop_loss DECIMAL(10,4),
            profit_target DECIMAL(10,4),

            -- Metadata
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),

            PRIMARY KEY (date, portfolio_name, ticker),
            FOREIGN KEY (date, portfolio_name) REFERENCES portfolio_snapshots(date, portfolio_name) ON DELETE CASCADE
        );

    """

    trades_query = """
        CREATE TABLE portfolio_trades (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL,
            portfolio_name VARCHAR(50) NOT NULL,
            ticker VARCHAR(10) NOT NULL,

            operation VARCHAR(4) NOT NULL CHECK (operation IN ('BUY', 'SELL')),
            quantity INTEGER NOT NULL,
            price DECIMAL(10,4) NOT NULL,
            commission DECIMAL(8,2) DEFAULT 0.00,

            notes TEXT,

            created_at TIMESTAMP DEFAULT NOW()
        );
    """
    
    # ===============================
    # TABELLE BACKTEST (stessa struttura)
    # ===============================
    
    snapshots_backtest_query = """
    CREATE TABLE IF NOT EXISTS portfolio_snapshots_backtest (
        date DATE NOT NULL,
        portfolio_name VARCHAR(50) NOT NULL,

        -- Stato base del portafoglio
        total_value DECIMAL(12,2) NOT NULL,
        cash_balance DECIMAL(12,2) NOT NULL,
        positions_count INTEGER DEFAULT 0,

        -- Metriche performance
        total_return_pct DECIMAL(8,4),
        max_drawdown_pct DECIMAL(8,4),
        volatility_pct DECIMAL(8,4),
        sharpe_ratio DECIMAL(8,4),
        win_rate_pct DECIMAL(8,4),

        -- Metadata
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),

        PRIMARY KEY (date, portfolio_name)
    );
    """

    positions_backtest_query = """
    CREATE TABLE IF NOT EXISTS portfolio_positions_backtest (
        date DATE NOT NULL,
        portfolio_name VARCHAR(50) NOT NULL,
        ticker VARCHAR(10) NOT NULL,

        -- Dati base
        shares INTEGER NOT NULL,
        avg_cost DECIMAL(10,4) NOT NULL,
        current_price DECIMAL(10,4) NOT NULL,

        -- Risk management
        stop_loss DECIMAL(10,4),
        profit_target DECIMAL(10,4),

        -- Metadata
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),

        PRIMARY KEY (date, portfolio_name, ticker),
        FOREIGN KEY (date, portfolio_name) REFERENCES portfolio_snapshots(date, portfolio_name) ON DELETE CASCADE
    );
    """

    trades_backtest_query = """
    CREATE TABLE IF NOT EXISTS portfolio_trades_backtest (
        id SERIAL PRIMARY KEY,
        date DATE NOT NULL,
        portfolio_name VARCHAR(50) NOT NULL,
        ticker VARCHAR(10) NOT NULL,

        operation VARCHAR(4) NOT NULL CHECK (operation IN ('BUY', 'SELL')),
        quantity INTEGER NOT NULL,
        price DECIMAL(10,4) NOT NULL,
        commission DECIMAL(8,2) DEFAULT 0.00,

        notes TEXT,

        created_at TIMESTAMP DEFAULT NOW()
    );
    """
    
    # ===============================
    # INDICI PER PERFORMANCE
    # ===============================
    
    indices_query = """
    -- Indici portfolio_snapshots
    CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_date 
        ON portfolio_snapshots(date);
    CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_name_date 
        ON portfolio_snapshots(portfolio_name, date DESC);

    -- Indici portfolio_positions  
    CREATE INDEX IF NOT EXISTS idx_portfolio_positions_ticker 
        ON portfolio_positions(ticker);
    CREATE INDEX IF NOT EXISTS idx_portfolio_positions_date_name 
        ON portfolio_positions(date, portfolio_name);

    -- Indici portfolio_trades
    CREATE INDEX IF NOT EXISTS idx_portfolio_trades_date 
        ON portfolio_trades(date DESC);
    CREATE INDEX IF NOT EXISTS idx_portfolio_trades_ticker 
        ON portfolio_trades(ticker);
    CREATE INDEX IF NOT EXISTS idx_portfolio_trades_portfolio_date 
        ON portfolio_trades(portfolio_name, date DESC);

    -- Indici backtest (stessa struttura)
    CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_backtest_date 
        ON portfolio_snapshots_backtest(date);
    CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_backtest_name_date 
        ON portfolio_snapshots_backtest(portfolio_name, date DESC);

    CREATE INDEX IF NOT EXISTS idx_portfolio_positions_backtest_ticker 
        ON portfolio_positions_backtest(ticker);
    CREATE INDEX IF NOT EXISTS idx_portfolio_positions_backtest_date_name 
        ON portfolio_positions_backtest(date, portfolio_name);

    CREATE INDEX IF NOT EXISTS idx_portfolio_trades_backtest_date 
        ON portfolio_trades_backtest(date DESC);
    CREATE INDEX IF NOT EXISTS idx_portfolio_trades_backtest_ticker 
        ON portfolio_trades_backtest(ticker);
    CREATE INDEX IF NOT EXISTS idx_portfolio_trades_backtest_portfolio_date 
        ON portfolio_trades_backtest(portfolio_name, date DESC);

    """

    # ===============================
    # ESECUZIONE CREAZIONE TABELLE
    # ===============================
    
    tables_to_create = [
        ("portfolio_snapshots", snapshots_query),
        ("portfolio_positions", positions_query), 
        ("portfolio_trades", trades_query),
        ("portfolio_snapshots_backtest", snapshots_backtest_query),
        ("portfolio_positions_backtest", positions_backtest_query),
        ("portfolio_trades_backtest", trades_backtest_query)
    ]
    
    # Crea tabelle in ordine (snapshots prima per foreign keys)
    for table_name, table_query in tables_to_create:
        try:
            execute_query(table_query, fetch=False)
            logger.info(f"Tabella {table_name} creata/verificata con successo")
        except Exception as e:
            logger.error(f"Errore nella creazione tabella {table_name}: {e}")
            raise
    
    # Crea indici
    try:
        execute_query(indices_query, fetch=False)
        logger.info("Indici portfolio creati/verificati con successo")
    except Exception as e:
        logger.error(f"Errore nella creazione indici portfolio: {e}")
        raise
    
    logger.info("Setup completo tabelle portfolio completato con successo")


def reset_entire_db(confirm: bool = False):
    """
    Elimina TUTTE le tabelle gestite dal modulo, inclusa universe.
    ATTENZIONE: cancella tutti i dati!
    
    Parameters
    ----------
    confirm : bool
        Deve essere True per eseguire realmente la cancellazione.
    """
    if not confirm:
        logger.warning("Reset DB non eseguito. Imposta confirm=True per confermare.")
        return
    
    tables = [
        "portfolio_trades",
        "portfolio_positions",
        "portfolio_snapshots",
        "portfolio_trades_backtest",
        "portfolio_positions_backtest",
        "portfolio_snapshots_backtest",
        #"universe"
    ]
    
    with _get_connection_context() as conn:
        with conn.cursor() as cursor:
            for table in tables:
                try:
                    cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
                    logger.info(f"Tabella {table} eliminata con successo")
                except Exception as e:
                    logger.error(f"Errore eliminando tabella {table}: {e}")
                    raise
        conn.commit()
    
    logger.info("Reset completo del database (tabelle universe e portfolio/backtest eliminate)")
