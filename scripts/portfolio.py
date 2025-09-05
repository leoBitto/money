# scripts/portfolio.py
"""
Modulo: portfolio (Refactored with OOP)
=======================================

Gestione completa dello stato dei portafogli tramite classi Portfolio e Position.

CLASSI PRINCIPALI:
1. Portfolio: Container per tutte le posizioni e metriche di un portfolio
2. Position: Singola posizione con risk management e performance tracking

CUSTOM EXCEPTIONS:
- PortfolioNotFoundError: Portfolio non trovato nel DB
- PortfolioExistsError: Portfolio già esistente
- InsufficientCashError: Cash insufficiente per operazione
- InsufficientSharesError: Azioni insufficienti per vendita

FUNZIONI MODULO:
- create_new_portfolio(): Factory per nuovi portfolio
- get_portfolio_names(): Lista portfolio disponibili

DIPENDENZE:
- database.execute_query() per tutte le operazioni DB
- universe table per prezzi correnti  
- config.py per parametri e defaults

USO TIPICO:
>>> from scripts.portfolio import Portfolio, create_portfolio_tables
>>> create_portfolio_tables()  # Prima volta
>>> portfolio = Portfolio.create("demo", "2025-09-01", initial_cash=10000)
>>> portfolio.execute_trade("AAPL", "BUY", 10, stop_loss=150.0, profit_target=180.0)
>>> portfolio.get_positions_count()  # 1
>>> portfolio.get_cash_balance()     # 8500.0 (circa)
"""

import pandas as pd
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from statistics import stdev

from . import database
from . import config

# Setup logging
logger = logging.getLogger(__name__)


# ================================
# CUSTOM EXCEPTIONS
# ================================

class PortfolioNotFoundError(Exception):
    """Raised when trying to load a portfolio that doesn't exist in the database."""
    def __init__(self, message: str):
        super().__init__(message)
        logger.error(f"PortfolioNotFoundError: {message}")

class PortfolioExistsError(Exception):
    """Raised when trying to create a portfolio that already exists."""
    def __init__(self, message: str):
        super().__init__(message)
        logger.error(f"PortfolioExistsError: {message}")

class InsufficientCashError(Exception):
    """Raised when trying to execute a trade without sufficient cash."""
    def __init__(self, message: str):
        super().__init__(message)
        logger.error(f"InsufficientCashError: {message}")

class InsufficientSharesError(Exception):
    """Raised when trying to sell more shares than owned."""
    def __init__(self, message: str):
        super().__init__(message)
        logger.error(f"InsufficientSharesError: {message}")

class PriceNotFoundError(Exception):
    """Raised when price data is not available for a ticker."""
    def __init__(self, message: str):
        super().__init__(message)
        logger.error(f"PriceNotFoundError: {message}")


# ================================
# 1. PORTFOLIO CLASS
# ================================

class Portfolio:
    """
    Container per un portfolio specifico (nome + data).

    Gestisce:
    - Stato corrente (cash, posizioni, valore totale)
    - Metriche performance (returns, drawdown, volatility, Sharpe) - stored in DB
    - Risk management (capital at risk, concentration) - calcolato on-the-fly
    - Operazioni (execute trades, update positions)

    Attributes:
        name (str): Nome del portfolio
        date (str): Data dello snapshot (YYYY-MM-DD)
        backtest (bool): Flag per indicare se è un backtest
        _snapshot (dict): Metriche aggregate del portfolio
        _positions (dict): Posizioni dettagliate {ticker: Position}
    """

    def __init__(self, name: str, date: Optional[str] = None, backtest: bool = False):
        self.name = name
        self.backtest = backtest

        # Determina data da caricare
        if date is None:
            self.date = self._get_latest_date(name)
            if self.date is None:
                raise PortfolioNotFoundError(
                    f"Portfolio '{name}' non trovato nel database. "
                    f"Usa Portfolio.create() per creare un nuovo portfolio."
                )
        else:
            self.date = date

        # Carica dati dal DB
        self._snapshot = None
        self._positions = {}
        success = self._load_from_db()
        if not success:
            raise PortfolioNotFoundError(
                f"Portfolio '{name}' non trovato per la data {self.date}."
            )
        logger.info(f"Portfolio '{name}' caricato per {self.date} (backtest={backtest})")

    # ----------------------------
    # CREATION / DELETE
    # ----------------------------

    @classmethod
    def create(cls, name: str, date: str, initial_cash: float = 10000.0,
               backtest: bool = False) -> 'Portfolio':
        table_suffix = "_backtest" if backtest else ""
        check_query = f"""
            SELECT COUNT(*) FROM portfolio_snapshots{table_suffix}
            WHERE date = %s AND portfolio_name = %s
        """
        result, _ = database.execute_query(check_query, (date, name))
        if result[0][0] > 0:
            raise PortfolioExistsError(f"Portfolio '{name}' esiste già per {date}")

        insert_query = f"""
            INSERT INTO portfolio_snapshots{table_suffix}
            (date, portfolio_name, total_value, cash_balance, positions_count,
             total_return_pct, max_drawdown_pct, volatility_pct, sharpe_ratio, win_rate_pct)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (date, name, initial_cash, initial_cash, 0, 0.0, 0.0, 0.0, 0.0, 0.0)
        database.execute_query(insert_query, params, fetch=False)
        return cls(name, date, backtest)

    @classmethod
    def list_available(cls, backtest: bool = False) -> List[str]:
        table_suffix = "_backtest" if backtest else ""
        query = f"""
            SELECT DISTINCT portfolio_name FROM portfolio_snapshots{table_suffix}
            ORDER BY portfolio_name
        """
        result, _ = database.execute_query(query)
        return [row[0] for row in result]

    @classmethod
    def delete_portfolio(cls, name: str, backtest: bool = False) -> bool:
        table_suffix = "_backtest" if backtest else ""
        try:
            # elimina posizioni
            delete_positions = f"""
                DELETE FROM portfolio_positions{table_suffix} WHERE portfolio_name = %s
            """
            database.execute_query(delete_positions, (name,), fetch=False)

            # elimina trade
            delete_trades = f"""
                DELETE FROM portfolio_trades{table_suffix} WHERE portfolio_name = %s
            """
            database.execute_query(delete_trades, (name,), fetch=False)

            # elimina snapshot
            delete_snapshots = f"""
                DELETE FROM portfolio_snapshots{table_suffix} WHERE portfolio_name = %s
            """
            database.execute_query(delete_snapshots, (name,), fetch=False)
            return True
        except Exception as e:
            logger.error(f"Errore nell'eliminare portfolio '{name}': {e}")
            return False

    # ----------------------------
    # CASH / VALUE ACCESS
    # ----------------------------

    def get_cash_balance(self) -> float:
        return float(self._snapshot.get('cash_balance', 0.0))

    def get_total_value(self) -> float:
        return float(self._snapshot.get('total_value', 0.0))

    def get_positions_count(self) -> int:
        return len([pos for pos in self._positions.values() if pos.shares > 0])

    def get_position(self, ticker: str) -> Optional['Position']:
        return self._positions.get(ticker)

    def get_position_percentages(self) -> Dict[str, float]:
        """Calcola la percentuale del portafoglio per ogni posizione attiva."""
        total_value = self.get_total_value()
        if total_value == 0:
            return {ticker: 0.0 for ticker in self._positions.keys()}
        return {ticker: (pos.get_current_value() / total_value) * 100
                for ticker, pos in self._positions.items() if pos.shares > 0}

    # ----------------------------
    # TRADING
    # ----------------------------

    def execute_trade(self, ticker: str, operation: str, quantity: int,
                      stop_loss: Optional[float] = None,
                      profit_target: Optional[float] = None,
                      **kwargs) -> None:
        operation = operation.upper()
        if operation not in ["BUY", "SELL"]:
            raise ValueError(f"Operazione '{operation}' non valida. Usa BUY o SELL.")

        current_price = self._get_current_price(ticker)
        total_value = current_price * quantity

        if operation == "BUY":
            if total_value > self.get_cash_balance():
                raise InsufficientCashError(f"Cash insufficiente per acquistare {quantity} {ticker}")
            self._snapshot['cash_balance'] -= total_value
            self._add_or_update_position(ticker, quantity, current_price, stop_loss, profit_target)
        else:  # SELL
            existing_position = self.get_position(ticker)
            if not existing_position or existing_position.shares < quantity:
                available = existing_position.shares if existing_position else 0
                raise InsufficientSharesError(f"Azioni insufficienti per vendita {quantity} {ticker}")
            self._snapshot['cash_balance'] += total_value
            existing_position.shares -= quantity
            existing_position.current_price = current_price
            if existing_position.shares == 0:
                existing_position.stop_loss = None
                existing_position.profit_target = None

        self._recalculate_total_value()
        self._save_trade(ticker, operation, quantity, current_price,
                         commission=kwargs.get('commission', 0.0),
                         notes=kwargs.get('notes'))
        self._save_to_db()
        if operation == "SELL":
            existing_position._save_to_db()

    def _add_or_update_position(self, ticker, quantity, price, stop_loss=None, profit_target=None):
        existing = self._positions.get(ticker)
        if existing and existing.shares > 0:
            old_shares, old_cost = existing.shares, existing.avg_cost
            new_shares = old_shares + quantity
            new_avg_cost = ((old_shares * old_cost) + (quantity * price)) / new_shares
            existing.shares = new_shares
            existing.avg_cost = new_avg_cost
            existing.current_price = price
            if stop_loss is not None:
                existing.stop_loss = stop_loss
            if profit_target is not None:
                existing.profit_target = profit_target
        else:
            position = Position(ticker, quantity, price, price, stop_loss, profit_target, self)
            self._positions[ticker] = position

    def _recalculate_total_value(self):
        cash = self.get_cash_balance()
        positions_value = sum(pos.get_current_value() for pos in self._positions.values() if pos.shares > 0)
        self._snapshot['total_value'] = cash + positions_value
        self._snapshot['positions_count'] = self.get_positions_count()

    # ----------------------------
    # DB METHODS
    # ----------------------------

    def _get_current_price(self, ticker: str) -> float:
        query = """
            SELECT close FROM universe
            WHERE ticker = %s AND date <= %s
            ORDER BY date DESC LIMIT 1
        """
        result, _ = database.execute_query(query, (ticker, self.date))
        if not result:
            raise PriceNotFoundError(f"Prezzo non trovato per {ticker} alla data {self.date}")
        return float(result[0][0])

    def _save_trade(self, ticker, operation, quantity, price, commission=0.0, notes=None):
        trade = Trade(self.date, self.name, ticker, operation, quantity, price,
                      commission, notes, portfolio=self)
        trade.save_to_db()

    def _save_to_db(self):
        table_suffix = "_backtest" if self.backtest else ""
        query = f"""
            INSERT INTO portfolio_snapshots{table_suffix}
            (date, portfolio_name, total_value, cash_balance, positions_count,
             total_return_pct, max_drawdown_pct, volatility_pct, sharpe_ratio, win_rate_pct)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date, portfolio_name) DO UPDATE SET
                total_value = EXCLUDED.total_value,
                cash_balance = EXCLUDED.cash_balance,
                positions_count = EXCLUDED.positions_count,
                total_return_pct = EXCLUDED.total_return_pct,
                max_drawdown_pct = EXCLUDED.max_drawdown_pct,
                volatility_pct = EXCLUDED.volatility_pct,
                sharpe_ratio = EXCLUDED.sharpe_ratio,
                win_rate_pct = EXCLUDED.win_rate_pct
        """
        params = (
            self.date, self.name, self._snapshot['total_value'], self._snapshot['cash_balance'],
            self._snapshot['positions_count'], self._snapshot.get('total_return_pct', 0.0),
            self._snapshot.get('max_drawdown_pct', 0.0), self._snapshot.get('volatility_pct', 0.0),
            self._snapshot.get('sharpe_ratio', 0.0), self._snapshot.get('win_rate_pct', 0.0)
        )
        database.execute_query(query, params, fetch=False)

    def _load_from_db(self) -> bool:
        table_suffix = "_backtest" if self.backtest else ""
        # snapshot
        snapshot_query = f"""
            SELECT total_value, cash_balance, positions_count,
                   total_return_pct, max_drawdown_pct, volatility_pct, sharpe_ratio, win_rate_pct
            FROM portfolio_snapshots{table_suffix}
            WHERE date = %s AND portfolio_name = %s
        """
        result, _ = database.execute_query(snapshot_query, (self.date, self.name))
        if not result:
            return False
        row = result[0]
        self._snapshot = {
            'total_value': float(row[0]),
            'cash_balance': float(row[1]),
            'positions_count': row[2],
            'total_return_pct': float(row[3]) if row[3] else 0.0,
            'max_drawdown_pct': float(row[4]) if row[4] else 0.0,
            'volatility_pct': float(row[5]) if row[5] else 0.0,
            'sharpe_ratio': float(row[6]) if row[6] else 0.0,
            'win_rate_pct': float(row[7]) if row[7] else 0.0
        }
        # posizioni
        positions_query = f"""
            SELECT ticker, shares, avg_cost, current_price, stop_loss, profit_target
            FROM portfolio_positions{table_suffix}
            WHERE date = %s AND portfolio_name = %s
        """
        result, _ = database.execute_query(positions_query, (self.date, self.name))
        for row in result:
            ticker = row[0]
            self._positions[ticker] = Position(
                ticker=ticker,
                shares=int(row[1]),
                avg_cost=float(row[2]),
                current_price=float(row[3]),
                stop_loss=float(row[4]) if row[4] else None,
                profit_target=float(row[5]) if row[5] else None,
                portfolio=self
            )
        return True

    def _get_latest_date(self, portfolio_name: str) -> Optional[str]:
        table_suffix = "_backtest" if self.backtest else ""
        query = f"SELECT MAX(date) FROM portfolio_snapshots{table_suffix} WHERE portfolio_name = %s"
        result, _ = database.execute_query(query, (portfolio_name,))
        if result and result[0][0]:
            return result[0][0].strftime('%Y-%m-%d')
        return None


# ================================
# 2. POSITION CLASS
# ================================

class Position:
    """
    Rappresenta una singola posizione nel portfolio.

    Attributes:
        ticker (str): Symbol del titolo
        shares (int): Numero di azioni possedute
        avg_cost (float): Prezzo medio di carico
        current_price (float): Prezzo corrente
        stop_loss (Optional[float]): Prezzo di stop loss
        profit_target (Optional[float]): Primo target di profitto
        portfolio (Optional[Portfolio]): Riferimento al portfolio padre
    """

    def __init__(self, ticker: str, shares: int, avg_cost: float, current_price: float,
                 stop_loss: Optional[float] = None, profit_target: Optional[float] = None,
                 portfolio: Optional['Portfolio'] = None):
        self.ticker = ticker
        self.shares = shares
        self.avg_cost = avg_cost
        self.current_price = current_price
        self.stop_loss = stop_loss
        self.profit_target = profit_target
        self.portfolio = portfolio

    # ----------------------------
    # RISK MANAGER METHODS
    # ----------------------------
    
    def is_stop_loss_hit(self, current_price: Optional[float] = None) -> bool:
        current_price = current_price if current_price is not None else self.current_price
        if not self.stop_loss:
            return False
        return current_price <= self.stop_loss

    def is_profit_target_hit(self, current_price: Optional[float] = None) -> bool:
        current_price = current_price if current_price is not None else self.current_price
        if not self.profit_target:
            return False
        return current_price >= self.profit_target

    # ----------------------------
    # PERFORMANCE METHODS
    # ----------------------------

    def get_unrealized_pnl_pct(self) -> float:
        if self.avg_cost == 0:
            return 0.0
        return ((self.current_price - self.avg_cost) / self.avg_cost) * 100

    def get_unrealized_pnl(self) -> float:
        return (self.current_price - self.avg_cost) * self.shares

    def get_current_value(self) -> float:
        return self.current_price * self.shares

    def get_days_held(self) -> int:
        if not self.portfolio:
            return 0
        table_suffix = "_backtest" if self.portfolio.backtest else ""
        query = f"""
            SELECT MIN(date) FROM portfolio_positions{table_suffix}
            WHERE portfolio_name = %s AND ticker = %s
        """
        result, _ = database.execute_query(query, (self.portfolio.name, self.ticker))
        if not result or not result[0][0]:
            return 0
        first_date = result[0][0]
        current_date = datetime.strptime(self.portfolio.date, '%Y-%m-%d').date()
        return (current_date - first_date).days

    def get_capital_at_risk(self) -> float:
        if not self.stop_loss:
            return 0.0
        current_value = self.get_current_value()
        stop_value = self.stop_loss * self.shares
        return max(0, current_value - stop_value)

    # ----------------------------
    # INTERNAL METHODS
    # ----------------------------

    def _save_to_db(self) -> None:
        """Salva la posizione nel database."""
        if not self.portfolio:
            logger.warning(f"Impossibile salvare posizione {self.ticker}: portfolio non impostato")
            return

        table_suffix = "_backtest" if self.portfolio.backtest else ""

        query = f"""
            INSERT INTO portfolio_positions{table_suffix} 
            (date, portfolio_name, ticker, shares, avg_cost, current_price, 
             stop_loss, profit_target)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date, portfolio_name, ticker)
            DO UPDATE SET
                shares = EXCLUDED.shares,
                avg_cost = EXCLUDED.avg_cost,
                current_price = EXCLUDED.current_price,
                stop_loss = EXCLUDED.stop_loss,
                profit_target = EXCLUDED.profit_target
        """
        params = (
            self.portfolio.date,
            self.portfolio.name,
            self.ticker,
            self.shares,
            self.avg_cost,
            self.current_price,
            self.stop_loss,
            self.profit_target
        )

        database.execute_query(query, params, fetch=False)


# ================================
# 3. TRADE CLASS
# ================================

class Trade:
    """
    Rappresenta un singolo trade eseguito nel portfolio.

    Attributes:
        id (Optional[int]): ID del trade nel database
        date (str): Data del trade (YYYY-MM-DD)
        portfolio_name (str): Nome del portfolio
        ticker (str): Symbol del titolo
        operation (str): "BUY" o "SELL"
        quantity (int): Numero di azioni
        price (float): Prezzo di esecuzione
        commission (float): Commissioni applicate
        notes (Optional[str]): Note aggiuntive
        portfolio (Optional[Portfolio]): Riferimento al portfolio padre
    """

    def __init__(self, date: str, portfolio_name: str, ticker: str, operation: str,
                 quantity: int, price: float, commission: float = 0.0,
                 notes: Optional[str] = None, portfolio: Optional['Portfolio'] = None,
                 trade_id: Optional[int] = None):
        # Validazione dei dati
        self._validate_trade_data(date, portfolio_name, ticker, operation, quantity, price, commission)

        self.id = trade_id
        self.date = date
        self.portfolio_name = portfolio_name
        self.ticker = ticker.upper()
        self.operation = operation.upper()
        self.quantity = quantity
        self.price = price
        self.commission = commission
        self.notes = notes
        self.portfolio = portfolio

        # Calcola il valore totale in memoria (non salvato nel DB)
        self.total_value = (price * quantity) + commission

    # ----------------------------
    # CLASS METHODS
    # ----------------------------

    @classmethod
    def load_from_db(cls, trade_id: int, backtest: bool = False) -> Optional['Trade']:
        """Carica un trade dal database usando il suo ID."""
        table_suffix = "_backtest" if backtest else ""
        query = f"""
            SELECT id, date, portfolio_name, ticker, operation, quantity, price, commission, notes
            FROM portfolio_trades{table_suffix}
            WHERE id = %s
        """
        result, _ = database.execute_query(query, (trade_id,))
        if not result:
            return None
        row = result[0]
        return cls(
            date=row[1].strftime('%Y-%m-%d'),
            portfolio_name=row[2],
            ticker=row[3],
            operation=row[4],
            quantity=row[5],
            price=float(row[6]),
            commission=float(row[7]) if row[7] else 0.0,
            notes=row[8],
            trade_id=row[0]
        )

    @classmethod
    def get_trades_for_portfolio(cls, portfolio_name: str, date: Optional[str] = None,
                                 backtest: bool = False) -> List['Trade']:
        """Recupera tutti i trade per un portfolio specifico."""
        table_suffix = "_backtest" if backtest else ""
        if date:
            query = f"""
                SELECT id, date, portfolio_name, ticker, operation, quantity, price, commission, notes
                FROM portfolio_trades{table_suffix}
                WHERE portfolio_name = %s AND date = %s
                ORDER BY created_at ASC
            """
            params = (portfolio_name, date)
        else:
            query = f"""
                SELECT id, date, portfolio_name, ticker, operation, quantity, price, commission, notes
                FROM portfolio_trades{table_suffix}
                WHERE portfolio_name = %s
                ORDER BY date DESC, created_at ASC
            """
            params = (portfolio_name,)

        result, _ = database.execute_query(query, params)
        trades = []
        for row in result:
            trades.append(cls(
                date=row[1].strftime('%Y-%m-%d'),
                portfolio_name=row[2],
                ticker=row[3],
                operation=row[4],
                quantity=row[5],
                price=float(row[6]),
                commission=float(row[7]) if row[7] else 0.0,
                notes=row[8],
                trade_id=row[0]
            ))
        return trades

    @classmethod
    def get_trades_for_ticker(cls, ticker: str, portfolio_name: Optional[str] = None,
                              backtest: bool = False) -> List['Trade']:
        """Recupera tutti i trade per un ticker specifico."""
        table_suffix = "_backtest" if backtest else ""
        if portfolio_name:
            query = f"""
                SELECT id, date, portfolio_name, ticker, operation, quantity, price, commission, notes
                FROM portfolio_trades{table_suffix}
                WHERE ticker = %s AND portfolio_name = %s
                ORDER BY date DESC, created_at ASC
            """
            params = (ticker.upper(), portfolio_name)
        else:
            query = f"""
                SELECT id, date, portfolio_name, ticker, operation, quantity, price, commission, notes
                FROM portfolio_trades{table_suffix}
                WHERE ticker = %s
                ORDER BY date DESC, created_at ASC
            """
            params = (ticker.upper(),)

        result, _ = database.execute_query(query, params)
        trades = []
        for row in result:
            trades.append(cls(
                date=row[1].strftime('%Y-%m-%d'),
                portfolio_name=row[2],
                ticker=row[3],
                operation=row[4],
                quantity=row[5],
                price=float(row[6]),
                commission=float(row[7]) if row[7] else 0.0,
                notes=row[8],
                trade_id=row[0]
            ))
        return trades

    # ----------------------------
    # INSTANCE METHODS
    # ----------------------------

    def save_to_db(self) -> int:
        """Salva il trade nel database e ritorna l'ID assegnato."""
        backtest = self.portfolio.backtest if self.portfolio else False
        table_suffix = "_backtest" if backtest else ""

        if self.id is None:
            # INSERT
            query = f"""
                INSERT INTO portfolio_trades{table_suffix}
                (date, portfolio_name, ticker, operation, quantity, price, commission, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """
            params = (self.date, self.portfolio_name, self.ticker, self.operation,
                      self.quantity, self.price, self.commission, self.notes)
            result, _ = database.execute_query(query, params)
            self.id = result[0][0]
        else:
            # UPDATE
            query = f"""
                UPDATE portfolio_trades{table_suffix}
                SET date = %s, portfolio_name = %s, ticker = %s, operation = %s,
                    quantity = %s, price = %s, commission = %s, notes = %s
                WHERE id = %s
            """
            params = (self.date, self.portfolio_name, self.ticker, self.operation,
                      self.quantity, self.price, self.commission, self.notes, self.id)
            database.execute_query(query, params, fetch=False)

        return self.id

    def delete_from_db(self) -> bool:
        """Elimina il trade dal database."""
        if not self.id:
            return False
        backtest = self.portfolio.backtest if self.portfolio else False
        table_suffix = "_backtest" if backtest else ""
        try:
            query = f"DELETE FROM portfolio_trades{table_suffix} WHERE id = %s"
            database.execute_query(query, (self.id,), fetch=False)
            self.id = None
            return True
        except Exception as e:
            logger.error(f"Errore nell'eliminare trade {self.id}: {e}")
            return False

    def get_net_value(self) -> float:
        """Ritorna il valore netto del trade considerando le commissioni."""
        base_value = self.price * self.quantity
        return -(base_value + self.commission) if self.operation == "BUY" else base_value - self.commission

    # ----------------------------
    # VALIDATION
    # ----------------------------

    def _validate_trade_data(self, date: str, portfolio_name: str, ticker: str,
                             operation: str, quantity: int, price: float, commission: float) -> None:
        """Valida i dati del trade."""
        # Data
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            raise ValueError(f"Data non valida: {date}. Formato richiesto: YYYY-MM-DD")
        # Portfolio
        if not portfolio_name.strip():
            raise ValueError("Nome portfolio non può essere vuoto")
        # Ticker
        if not ticker.strip() or len(ticker.strip()) > 10:
            raise ValueError(f"Ticker non valido o troppo lungo: {ticker}")
        # Operation
        if operation.upper() not in ["BUY", "SELL"]:
            raise ValueError(f"Operazione non valida: {operation}")
        # Quantity
        if quantity <= 0:
            raise ValueError(f"Quantità non valida: {quantity}")
        # Price
        if price <= 0:
            raise ValueError(f"Prezzo non valido: {price}")
        # Commission
        if commission < 0:
            raise ValueError(f"Commissione non valida: {commission}")




# ================================
# 0. UTILITY FUNCTIONS
# ================================

def get_portfolio_names(backtest: bool = False) -> List[str]:
    """
    Utility function per ottenere lista portfolio disponibili.
    
    Args:
        backtest: Se True, cerca nei portfolio di backtest
        
    Returns:
        Lista dei nomi portfolio
    """
    return Portfolio.list_available(backtest)


def create_new_portfolio(name: str, date: str, initial_cash: float = 10000.0, 
                        backtest: bool = False) -> Portfolio:
    """
    Utility function per creare un nuovo portfolio.
    
    Args:
        name: Nome del portfolio
        date: Data di creazione
        initial_cash: Cash iniziale
        backtest: Flag backtest
        
    Returns:
        Portfolio object creato
    """
    return Portfolio.create(name, date, initial_cash, backtest)

