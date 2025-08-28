# scripts/portfolio.py
"""
Modulo: portfolio
=================

Gestione completa dello stato dei portafogli e delle loro metriche.

FUNZIONALITÀ PRINCIPALI:
1. Inizializzazione tabelle DB (`create_portfolio_tables`)
2. Creazione portafogli (`create_portfolio`)  
3. Registrazione operazioni (`add_operation`)
4. Aggiornamento giornaliero (`update_portfolio`)
5. Lettura dati (`get_portfolio_*`)

DIPENDENZE:
- database.execute_query() per tutte le operazioni DB
- universe table per prezzi correnti

USO TIPICO:
>>> from scripts.portfolio import create_portfolio_tables, create_portfolio, add_operation
>>> create_portfolio_tables()  # Prima volta
>>> create_portfolio("demo", 10000.0)
>>> add_operation("demo", "BUY", "AAPL", 10, 150.0, "2025-08-28")
"""

import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from . import database


# ================================
# 1. INIZIALIZZAZIONE DATABASE
# ================================

def create_portfolio_tables() -> None:
    """
    Crea le tabelle necessarie per il tracking dei portafogli.
    
    TABELLE CREATE:
    - portfolio_snapshots: metriche aggregate per data/portfolio
    - portfolio_positions: posizioni dettagliate per data/portfolio
    """
    
    # Tabella snapshots (metriche aggregate)
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
    
    # Tabella posizioni dettagliate
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
        
        -- Metriche posizione
        position_weight_pct DECIMAL(8,4),
        position_pnl_pct DECIMAL(8,4),
        position_volatility DECIMAL(8,4),
        
        -- Metadata
        created_at TIMESTAMP DEFAULT NOW(),
        
        PRIMARY KEY (date, portfolio_name, ticker)
    );
    """
    
    # Indici per performance
    indices_query = """
    CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_date 
        ON portfolio_snapshots(date);
    CREATE INDEX IF NOT EXISTS idx_portfolio_positions_ticker 
        ON portfolio_positions(ticker);
    CREATE INDEX IF NOT EXISTS idx_portfolio_positions_weight 
        ON portfolio_positions(position_weight_pct DESC);
    """
    
    # Esegui creazione
    database.execute_query(snapshots_query, fetch=False)
    database.execute_query(positions_query, fetch=False)
    database.execute_query(indices_query, fetch=False)
    
    print("✅ Tabelle portfolio create con successo:")
    print("   📊 portfolio_snapshots")
    print("   📈 portfolio_positions")
    print("   🔍 Indici di performance")


# ================================
# 2. CREAZIONE PORTAFOGLI
# ================================

def create_portfolio(name: str, 
                     initial_cash: float,
                     positions: Optional[Dict[str, Dict[str, float]]] = None,
                     date: Optional[str] = None,
                     overwrite: bool = True) -> None:
    """
    Crea un nuovo portafoglio con cash iniziale e posizioni opzionali.
    
    Args:
        name: Nome del portafoglio
        initial_cash: Cash iniziale disponibile
        positions: Posizioni iniziali {"AAPL": {"shares": 10, "avg_cost": 150.0}}
        date: Data creazione (default: oggi)
        overwrite: Se True, sovrascrive portfolio esistente
    """
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    
    # Verifica esistenza (e rimuovi se overwrite)
    if overwrite:
        _delete_portfolio_data(name, date)
    else:
        check_query = """
            SELECT COUNT(*) FROM portfolio_snapshots 
            WHERE portfolio_name = %s AND date = %s
        """
        result = database.execute_query(check_query, (name, date))
        if result and result[0][0] > 0:
            raise ValueError(f"Portfolio '{name}' già esiste per {date}")
    
    # Portfolio vuoto (solo cash)
    if not positions:
        snapshot_data = {
            'total_value': initial_cash,
            'cash_balance': initial_cash,
            'positions_count': 0,
            'daily_return_pct': 0.0
        }
        _insert_snapshot(date, name, snapshot_data)
        print(f"✅ Portfolio '{name}' creato con €{initial_cash:,.2f} cash")
        return
    
    # Portfolio con posizioni iniziali
    _create_portfolio_with_positions(name, initial_cash, positions, date)


def _create_portfolio_with_positions(name: str, initial_cash: float, 
                                   positions: Dict, date: str) -> None:
    """Helper per creare portfolio con posizioni iniziali"""
    
    # 1. Ottieni prezzi correnti
    tickers = list(positions.keys())
    current_prices = _get_current_prices(tickers, date)
    
    # 2. Calcola metriche posizioni
    positions_data = []
    total_positions_value = 0.0
    
    for ticker, pos_data in positions.items():
        shares = pos_data['shares']
        avg_cost = pos_data['avg_cost']
        current_price = current_prices[ticker]
        current_value = shares * current_price
        pnl_pct = (current_price - avg_cost) / avg_cost
        
        positions_data.append({
            'ticker': ticker,
            'shares': shares,
            'avg_cost': avg_cost,
            'current_price': current_price,
            'current_value': current_value,
            'position_pnl_pct': pnl_pct
        })
        total_positions_value += current_value
    
    # 3. Calcola pesi %
    total_value = initial_cash + total_positions_value
    for pos in positions_data:
        pos['position_weight_pct'] = (pos['current_value'] / total_value) * 100
    
    # 4. Inserisci nel DB
    for pos in positions_data:
        _insert_position(date, name, pos)
    
    snapshot_data = {
        'total_value': total_value,
        'cash_balance': initial_cash,
        'positions_count': len(positions_data),
        'daily_return_pct': 0.0
    }
    _insert_snapshot(date, name, snapshot_data)
    
    print(f"✅ Portfolio '{name}' creato:")
    print(f"   💰 Cash: €{initial_cash:,.2f}")
    print(f"   📊 Posizioni: €{total_positions_value:,.2f}")
    print(f"   🎯 Totale: €{total_value:,.2f}")


# ================================
# 3. REGISTRAZIONE OPERAZIONI
# ================================

def add_operation(portfolio_name: str,
                 action: str,  # "BUY" o "SELL"
                 ticker: str,
                 shares: int,
                 price: float,
                 date: Optional[str] = None,
                 update_portfolio_after: bool = True) -> None:
    """
    Registra un'operazione di compravendita e aggiorna il portafoglio.
    
    Args:
        portfolio_name: Nome del portafoglio
        action: "BUY" o "SELL"
        ticker: Ticker del titolo
        shares: Numero di azioni
        price: Prezzo per azione (dal tuo broker)
        date: Data operazione (default: oggi)
        update_portfolio_after: Se aggiornare automaticamente il portfolio
        
    Esempio:
        add_operation("demo", "BUY", "AAPL", 10, 155.50, "2025-08-28")
        add_operation("demo", "SELL", "MSFT", 5, 310.00)
    """
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    
    if action not in ["BUY", "SELL"]:
        raise ValueError("Action deve essere 'BUY' o 'SELL'")
    
    # 1. Ottieni stato portfolio corrente
    current_snapshot = get_portfolio_snapshot(date, portfolio_name)
    if not current_snapshot:
        raise ValueError(f"Portfolio '{portfolio_name}' non trovato per {date}")
    
    current_cash = current_snapshot['cash_balance']
    total_value = shares * price
    
    # 2. Verifica cash per acquisti
    if action == "BUY" and current_cash < total_value:
        raise ValueError(f"Cash insufficiente: €{current_cash:,.2f} < €{total_value:,.2f}")
    
    # 3. Aggiorna posizioni esistenti
    existing_positions = get_portfolio_positions(date, portfolio_name)
    updated_positions = _process_operation(existing_positions, action, ticker, shares, price)
    
    # 4. Aggiorna cash
    if action == "BUY":
        new_cash = current_cash - total_value
    else:  # SELL
        new_cash = current_cash + total_value
    
    # 5. Salva nel DB (rimuovi vecchi dati della data)
    _delete_portfolio_data(portfolio_name, date)
    
    # Inserisci posizioni aggiornate
    for pos in updated_positions:
        if pos['shares'] > 0:  # Solo posizioni con shares > 0
            _insert_position(date, portfolio_name, pos)
    
    # Inserisci snapshot aggiornato
    positions_value = sum(pos['current_value'] for pos in updated_positions if pos['shares'] > 0)
    snapshot_data = {
        'total_value': new_cash + positions_value,
        'cash_balance': new_cash,
        'positions_count': len([p for p in updated_positions if p['shares'] > 0]),
        'daily_return_pct': 0.0  # Da ricalcolare se serve
    }
    _insert_snapshot(date, portfolio_name, snapshot_data)
    
    print(f"✅ Operazione registrata: {action} {shares} {ticker} @ €{price:.2f}")
    print(f"   💰 Nuovo cash: €{new_cash:,.2f}")
    
    # 6. Aggiorna portfolio se richiesto
    if update_portfolio_after:
        update_portfolio(date, portfolio_name)


def _process_operation(existing_positions: pd.DataFrame, 
                      action: str, ticker: str, shares: int, price: float) -> List[Dict]:
    """Processa un'operazione aggiornando le posizioni esistenti"""
    
    positions_dict = {}
    
    # Converti posizioni esistenti in dict
    for _, row in existing_positions.iterrows():
        positions_dict[row['ticker']] = {
            'ticker': row['ticker'],
            'shares': row['shares'],
            'avg_cost': row['avg_cost'],
            'current_price': row['current_price'],
            'current_value': row['current_value'],
            'position_weight_pct': row.get('position_weight_pct', 0),
            'position_pnl_pct': row.get('position_pnl_pct', 0)
        }
    
    # Processa operazione
    if action == "BUY":
        if ticker in positions_dict:
            # Aggiorna posizione esistente (media dei costi)
            old_pos = positions_dict[ticker]
            old_shares = old_pos['shares']
            old_cost = old_pos['avg_cost']
            
            new_shares = old_shares + shares
            new_avg_cost = ((old_shares * old_cost) + (shares * price)) / new_shares
            
            positions_dict[ticker].update({
                'shares': new_shares,
                'avg_cost': new_avg_cost,
                'current_price': price,  # Aggiorna al prezzo più recente
                'current_value': new_shares * price
            })
        else:
            # Nuova posizione
            positions_dict[ticker] = {
                'ticker': ticker,
                'shares': shares,
                'avg_cost': price,
                'current_price': price,
                'current_value': shares * price,
                'position_weight_pct': 0,  # Da ricalcolare
                'position_pnl_pct': 0      # Da ricalcolare
            }
    
    elif action == "SELL":
        if ticker not in positions_dict:
            raise ValueError(f"Non puoi vendere {ticker}: posizione non esistente")
        
        old_pos = positions_dict[ticker]
        if old_pos['shares'] < shares:
            raise ValueError(f"Shares insufficienti: {old_pos['shares']} < {shares}")
        
        new_shares = old_pos['shares'] - shares
        positions_dict[ticker].update({
            'shares': new_shares,
            'current_price': price,
            'current_value': new_shares * price if new_shares > 0 else 0
        })
    
    return list(positions_dict.values())


# ================================
# 4. LETTURA DATI
# ================================

def get_portfolio_snapshot(date: str, portfolio_name: str = "default") -> Optional[Dict]:
    """Legge snapshot portfolio per una data specifica"""
    query = """
        SELECT * FROM portfolio_snapshots 
        WHERE date = %s AND portfolio_name = %s
    """
    result = database.execute_query(query, (date, portfolio_name))
    if not result:
        return None
        
    row = result[0]
    return {
        'date': row[0],
        'portfolio_name': row[1], 
        'total_value': float(row[2]),
        'cash_balance': float(row[3]),
        'positions_count': row[4],
        'daily_return_pct': float(row[5]) if row[5] else 0.0,
        'portfolio_volatility': float(row[6]) if row[6] else 0.0,
        'current_drawdown_pct': float(row[7]) if row[7] else 0.0
    }


def get_portfolio_positions(date: str, portfolio_name: str = "default") -> pd.DataFrame:
    """Legge posizioni portfolio per una data specifica"""
    query = """
        SELECT ticker, shares, avg_cost, current_price, current_value,
               position_weight_pct, position_pnl_pct, position_volatility
        FROM portfolio_positions
        WHERE date = %s AND portfolio_name = %s
        ORDER BY current_value DESC
    """
    result = database.execute_query(query, (date, portfolio_name))
    if not result:
        return pd.DataFrame()
    
    columns = ['ticker', 'shares', 'avg_cost', 'current_price', 'current_value',
               'position_weight_pct', 'position_pnl_pct', 'position_volatility']
    return pd.DataFrame(result, columns=columns)


def get_portfolio_snapshots_bulk(start_date: str, end_date: str, 
                                portfolio_name: str = "default") -> Dict[str, Dict]:
    """Legge snapshots multipli per backtest (ottimizzato)"""
    query = """
        SELECT date, total_value, cash_balance, positions_count,
               daily_return_pct, portfolio_volatility, current_drawdown_pct
        FROM portfolio_snapshots
        WHERE date BETWEEN %s AND %s AND portfolio_name = %s
        ORDER BY date
    """
    result = database.execute_query(query, (start_date, end_date, portfolio_name))
    if not result:
        return {}
    
    snapshots = {}
    for row in result:
        date_str = row[0].strftime('%Y-%m-%d') if hasattr(row[0], 'strftime') else str(row[0])
        snapshots[date_str] = {
            'total_value': float(row[1]),
            'cash_balance': float(row[2]),
            'positions_count': row[3],
            'daily_return_pct': float(row[4]) if row[4] else 0.0,
            'portfolio_volatility': float(row[5]) if row[5] else 0.0,
            'current_drawdown_pct': float(row[6]) if row[6] else 0.0
        }
    
    return snapshots


# ================================
# 5. AGGIORNAMENTO (da implementare)
# ================================

def update_portfolio(date: str, portfolio_name: str = "default") -> None:
    """Aggiorna portfolio con prezzi correnti (da implementare)"""
    # TODO: implementare aggiornamento completo
    print(f"TODO: Aggiornamento portfolio '{portfolio_name}' per {date}")


# ================================
# 6. HELPER FUNCTIONS
# ================================

def _get_current_prices(tickers: List[str], date: str) -> Dict[str, float]:
    """Ottiene prezzi correnti dal DB universe"""
    prices = {}
    for ticker in tickers:
        query = """
            SELECT close FROM universe 
            WHERE ticker = %s AND date <= %s 
            ORDER BY date DESC LIMIT 1
        """
        result = database.execute_query(query, (ticker, date))
        if not result:
            raise ValueError(f"Prezzo non trovato per {ticker} alla data {date}")
        prices[ticker] = float(result[0][0])
    return prices


def _insert_position(date: str, portfolio_name: str, pos_data: Dict) -> None:
    """Inserisce singola posizione nel DB"""
    query = """
        INSERT INTO portfolio_positions 
        (date, portfolio_name, ticker, shares, avg_cost, current_price, 
         current_value, position_weight_pct, position_pnl_pct)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (date, portfolio_name, ticker) 
        DO UPDATE SET
            shares = EXCLUDED.shares,
            avg_cost = EXCLUDED.avg_cost,
            current_price = EXCLUDED.current_price,
            current_value = EXCLUDED.current_value,
            position_weight_pct = EXCLUDED.position_weight_pct,
            position_pnl_pct = EXCLUDED.position_pnl_pct
    """
    params = (
        date, portfolio_name, pos_data['ticker'], pos_data['shares'],
        pos_data['avg_cost'], pos_data['current_price'], pos_data['current_value'],
        pos_data.get('position_weight_pct', 0), pos_data.get('position_pnl_pct', 0)
    )
    database.execute_query(query, params, fetch=False)


def _insert_snapshot(date: str, portfolio_name: str, snapshot: Dict) -> None:
    """Inserisce snapshot nel DB"""
    query = """
        INSERT INTO portfolio_snapshots
        (date, portfolio_name, total_value, cash_balance, positions_count, daily_return_pct)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (date, portfolio_name)
        DO UPDATE SET
            total_value = EXCLUDED.total_value,
            cash_balance = EXCLUDED.cash_balance,
            positions_count = EXCLUDED.positions_count,
            daily_return_pct = EXCLUDED.daily_return_pct
    """
    params = (
        date, portfolio_name, snapshot['total_value'], snapshot['cash_balance'],
        snapshot['positions_count'], snapshot['daily_return_pct']
    )
    database.execute_query(query, params, fetch=False)


def _delete_portfolio_data(portfolio_name: str, date: str) -> None:
    """Rimuove dati portfolio per una data specifica (per overwrite)"""
    database.execute_query(
        "DELETE FROM portfolio_positions WHERE portfolio_name = %s AND date = %s",
        (portfolio_name, date), fetch=False
    )
    database.execute_query(
        "DELETE FROM portfolio_snapshots WHERE portfolio_name = %s AND date = %s", 
        (portfolio_name, date), fetch=False
    )