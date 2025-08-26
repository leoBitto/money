# scripts/utils/db/db_utils.py
import psycopg2
import psycopg2.extras
import pandas as pd
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager
from ..gcp_utils import SecretManager

class DatabaseManager:
    """Gestisce le operazioni con il database PostgreSQL"""
    
    def __init__(self, db_info: Optional[Dict] = None):
        """
        Inizializza il manager del database
        
        Args:
            db_info: Dict con le credenziali DB. Se None, le carica da Secret Manager
        """
        if db_info is None:
            secret_manager = SecretManager()
            db_info = secret_manager.get_secret("db_info")
        self.db_info = db_info
    
    def get_connection(self):
        """Crea una nuova connessione al database"""
        return psycopg2.connect(
            host=self.db_info["DB_HOST"],
            port=self.db_info["DB_PORT"],
            database=self.db_info["DB_NAME"],
            user=self.db_info["DB_USER"],
            password=self.db_info["DB_PASSWORD"]
        )
    
    @contextmanager
    def get_connection_context(self):
        """Context manager per gestire automaticamente connessioni e transazioni"""
        conn = None
        try:
            conn = self.get_connection()
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            raise e
        finally:
            if conn:
                conn.close()
    
    def execute_query(self, query: str, params: Optional[Tuple] = None, fetch: bool = True) -> Optional[List[Tuple]]:
        """
        Esegue una query SQL
        
        Args:
            query: Query SQL da eseguire
            params: Parametri per la query (opzionale)
            fetch: Se True, ritorna i risultati (default: True)
        
        Returns:
            Lista di tuple con i risultati se fetch=True, None altrimenti
        """
        with self.get_connection_context() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchall() if fetch else None
    
    def execute_many(self, query: str, params_list: List[Tuple]) -> None:
        """
        Esegue la stessa query con parametri multipli (batch insert/update)
        
        Args:
            query: Query SQL da eseguire
            params_list: Lista di tuple con i parametri per ogni esecuzione
        """
        with self.get_connection_context() as conn:
            with conn.cursor() as cursor:
                cursor.executemany(query, params_list)
    
    def insert_batch_universe(self, data: List[Tuple], conflict_resolution: str = "DO NOTHING") -> int:
        """
        Inserisce dati nella tabella universe in batch
        
        Args:
            data: Lista di tuple (date, ticker, open, high, low, close, volume)
            conflict_resolution: Strategia per conflitti ("DO NOTHING" o "DO UPDATE SET ...")
        
        Returns:
            Numero di righe processate
        """
        query = f"""
        INSERT INTO universe (date, ticker, open, high, low, close, volume)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (date, ticker) {conflict_resolution}
        """
        
        if conflict_resolution.startswith("DO UPDATE"):
            # Per update, usa la clausola completa
            query = query.replace("DO UPDATE SET ...", """DO UPDATE 
            SET open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume""")
        
        self.execute_many(query, data)
        return len(data)
    
    def get_available_tickers(self) -> List[str]:
        """Recupera tutti i ticker disponibili nel database"""
        query = "SELECT DISTINCT ticker FROM universe ORDER BY ticker"
        results = self.execute_query(query)
        return [row[0] for row in results] if results else []
    
    def get_universe_data(self, end_date: str, tickers: Optional[List[str]] = None) -> pd.DataFrame:
        """
        Recupera dati dalla tabella universe
        
        Args:
            end_date: Data limite (formato 'YYYY-MM-DD')
            tickers: Lista di ticker specifici. Se None, prende tutti
        
        Returns:
            DataFrame con i dati storici
        """
        if tickers:
            placeholders = ','.join(['%s'] * len(tickers))
            query = f"""
                SELECT ticker, date, open, high, low, close, volume
                FROM universe
                WHERE ticker IN ({placeholders})
                  AND date <= %s
                ORDER BY ticker, date
            """
            params = tuple(tickers) + (end_date,)
        else:
            query = """
                SELECT ticker, date, open, high, low, close, volume
                FROM universe
                WHERE date <= %s
                ORDER BY ticker, date
            """
            params = (end_date,)
        
        results = self.execute_query(query, params)
        if not results:
            return pd.DataFrame()
        
        # Converti in DataFrame
        columns = ['ticker', 'date', 'open', 'high', 'low', 'close', 'volume']
        df = pd.DataFrame(results, columns=columns)
        df['date'] = pd.to_datetime(df['date'])
        
        # Rinomina colonne per compatibilità con strategie
        df = df.rename(columns={
            'open': 'Open',
            'high': 'High', 
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume'
        })
        
        return df

# Rimosse funzioni di compatibilità - usa direttamente DatabaseManager()