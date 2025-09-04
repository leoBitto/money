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
    - Risk management (capital at risk, concentration) - calculated on-the-fly
    - Operazioni (execute trades, update positions)
    
    Attributes:
        name (str): Nome del portfolio
        date (str): Data dello snapshot (YYYY-MM-DD)
        backtest (bool): Flag per indicare se è un backtest
        _snapshot (dict): Metriche aggregate del portfolio
        _positions (dict): Posizioni dettagliate {ticker: Position}
    """
    
    def __init__(self, name: str, date: Optional[str] = None, backtest: bool = False):
        """
        Carica portfolio esistente dal DB.
        
        Args:
            name: Nome del portfolio
            date: Data specifica (default: ultima data disponibile)
            backtest: Flag per indicare se è un backtest
            
        Raises:
            PortfolioNotFoundError: Se il portfolio non esiste
        """
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
                f"Portfolio '{name}' non trovato per la data {self.date}. "
                f"Verifica che la combinazione nome-data sia corretta."
            )
            
        logger.info(f"Portfolio '{name}' caricato per {self.date} (backtest={backtest})")

    @classmethod
    def create(cls, name: str, date: str, initial_cash: float = 10000.0, 
               backtest: bool = False) -> 'Portfolio':
        """
        Crea un nuovo portfolio nel database.
        
        Args:
            name: Nome del portfolio
            date: Data di creazione (YYYY-MM-DD)
            initial_cash: Cash iniziale
            backtest: Flag per indicare se è un backtest
            
        Returns:
            Portfolio object creato
            
        Raises:
            PortfolioExistsError: Se il portfolio esiste già per quella data
            
        Example:
            >>> portfolio = Portfolio.create("demo", "2025-09-01", 5000)
            >>> portfolio.get_cash_balance()  # 5000.0
        """
        # Controlla se esiste già
        table_suffix = "_backtest" if backtest else ""
        check_query = f"""
            SELECT COUNT(*) FROM portfolio_snapshots{table_suffix}
            WHERE date = %s AND portfolio_name = %s
        """
        result, _ = database.execute_query(check_query, (date, name))
        
        if result[0][0] > 0:
            raise PortfolioExistsError(
                f"Portfolio '{name}' esiste già per la data {date}. "
                f"Usa Portfolio.__init__() per caricarlo."
            )
        
        logger.info(f"Creando nuovo portfolio '{name}' con cash iniziale €{initial_cash:,.2f}")
        
        # Crea snapshot iniziale nel DB
        insert_query = f"""
            INSERT INTO portfolio_snapshots{table_suffix}
            (date, portfolio_name, total_value, cash_balance, positions_count, 
             daily_return_pct, total_return_pct, volatility_pct, current_drawdown_pct, 
             max_drawdown_pct, sharpe_ratio, win_rate_pct)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (date, name, initial_cash, initial_cash, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        database.execute_query(insert_query, params, fetch=False)
        
        # Carica il nuovo portfolio
        new_portfolio = cls(name, date, backtest)
        logger.info(f"Portfolio '{name}' creato con successo")
        return new_portfolio
    
    @classmethod  
    def list_available(cls, backtest: bool = False) -> List[str]:
        """
        Lista tutti i portfolio disponibili nel database.
        
        Args:
            backtest: Se True, cerca nei portfolio di backtest
            
        Returns:
            Lista dei nomi portfolio
        """
        table_suffix = "_backtest" if backtest else ""
        query = f"""
            SELECT DISTINCT portfolio_name 
            FROM portfolio_snapshots{table_suffix} 
            ORDER BY portfolio_name
        """
        result, _ = database.execute_query(query)
        return [row[0] for row in result]
    
    @classmethod
    def delete_portfolio(cls, name: str, backtest: bool = False) -> bool:
        """
        Elimina completamente un portfolio dal database.
        
        Args:
            name: Nome del portfolio da eliminare
            backtest: Se True, elimina dai portfolio di backtest
            
        Returns:
            True se eliminato con successo
        """
        try:
            table_suffix = "_backtest" if backtest else ""
            
            # Elimina posizioni
            delete_positions = f"""
                DELETE FROM portfolio_positions{table_suffix} 
                WHERE portfolio_name = %s
            """
            database.execute_query(delete_positions, (name,), fetch=False)
            
            # Elimina trade (quando implementato)
            delete_trades = f"""
                DELETE FROM portfolio_trades{table_suffix} 
                WHERE portfolio_name = %s
            """
            # database.execute_query(delete_trades, (name,), fetch=False)
            
            # Elimina snapshots
            delete_snapshots = f"""
                DELETE FROM portfolio_snapshots{table_suffix} 
                WHERE portfolio_name = %s
            """
            database.execute_query(delete_snapshots, (name,), fetch=False)
            
            logger.info(f"Portfolio '{name}' eliminato dal database (backtest={backtest})")
            return True
            
        except Exception as e:
            logger.error(f"Errore nell'eliminare portfolio '{name}': {e}")
            return False

    # =============================
    # CORE METHODS
    # =============================
    
    def get_cash_balance(self) -> float:
        """Ritorna il cash disponibile nel portfolio."""
        if not self._snapshot:
            return 0.0
        return float(self._snapshot['cash_balance'])
    
    def get_total_value(self) -> float:
        """Ritorna il valore totale del portfolio (cash + posizioni)."""
        if not self._snapshot:
            return 0.0
        return float(self._snapshot['total_value'])
    
    def get_positions_count(self) -> int:
        """Ritorna il numero di posizioni attive."""
        return len([pos for pos in self._positions.values() if pos.shares > 0])
    
    def get_position(self, ticker: str) -> Optional['Position']:
        """
        Ritorna la posizione per un ticker specifico.
        
        Args:
            ticker: Symbol del titolo
            
        Returns:
            Position object o None se non esiste
        """
        return self._positions.get(ticker)
    
    def execute_trade(self, ticker: str, operation: str, quantity: int,
                      stop_loss: Optional[float] = None, 
                      profit_target: Optional[float] = None,
                      **kwargs) -> None:
        """
        Esegue un trade (BUY/SELL) modificando cash balance e posizioni.
        
        Args:
            ticker: Symbol del titolo
            operation: "BUY" o "SELL"
            quantity: Numero di azioni da comprare/vendere
            stop_loss: Stop loss per BUY operations (opzionale)
            profit_target: Profit target per BUY operations (opzionale)
            **kwargs: Altri parametri per future estensioni
            
        Raises:
            InsufficientCashError: Cash insufficiente per BUY
            InsufficientSharesError: Azioni insufficienti per SELL
            PriceNotFoundError: Prezzo non trovato per il ticker
            ValueError: Operazione non valida
            
        Example:
            >>> portfolio.execute_trade("AAPL", "BUY", 10, stop_loss=150.0)
            >>> portfolio.execute_trade("AAPL", "SELL", 5)  # Vendita parziale
        """
        operation = operation.upper()
        if operation not in ["BUY", "SELL"]:
            raise ValueError(f"Operazione '{operation}' non valida. Usa BUY o SELL.")
        
        # Ottieni prezzo corrente
        current_price = self._get_current_price(ticker)
        total_value = current_price * quantity
        
        if operation == "BUY":
            # Controlla cash disponibile
            if total_value > self.get_cash_balance():
                raise InsufficientCashError(
                    f"Cash insufficiente per acquisto {quantity} {ticker}. "
                    f"Richiesto: €{total_value:.2f}, Disponibile: €{self.get_cash_balance():.2f}"
                )
            
            # Modifica cash balance
            self._snapshot['cash_balance'] -= total_value
            
            # Aggiungi/aggiorna posizione
            self._add_or_update_position(ticker, quantity, current_price, 
                                       stop_loss, profit_target)
            
            logger.info(f"ACQUISTO: {quantity} {ticker} @ €{current_price:.2f} "
                       f"(Totale: €{total_value:.2f})")
        
        elif operation == "SELL":
            # Controlla posizione esistente
            existing_position = self.get_position(ticker)
            if not existing_position or existing_position.shares < quantity:
                available = existing_position.shares if existing_position else 0
                raise InsufficientSharesError(
                    f"Azioni insufficienti per vendita {quantity} {ticker}. "
                    f"Richiesto: {quantity}, Disponibile: {available}"
                )
            
            # Modifica cash balance
            self._snapshot['cash_balance'] += total_value
            
            # Aggiorna posizione
            existing_position.shares -= quantity
            existing_position.current_price = current_price
            
            # Se vendita totale, rimuovi target
            if existing_position.shares == 0:
                existing_position.stop_loss = None
                existing_position.profit_target = None
            
            logger.info(f"VENDITA: {quantity} {ticker} @ €{current_price:.2f} "
                       f"(Totale: €{total_value:.2f})")
        
        # Ricalcola valore totale
        self._recalculate_total_value()
        
        # Salva trade nel DB (placeholder)
        self._save_trade(ticker, operation, quantity, current_price, total_value, 
                commission=kwargs.get('commission', 0.0),
                notes=kwargs.get('notes'))

        # Salva stato aggiornato
        self._save_to_db()
        
        if existing_position:
            existing_position._save_to_db()

    def _add_or_update_position(self, ticker: str, quantity: int, price: float,
                               stop_loss: Optional[float] = None,
                               profit_target: Optional[float] = None) -> None:
        """Aggiunge o aggiorna una posizione."""
        existing = self._positions.get(ticker)
        
        if existing and existing.shares > 0:
            # Aggiorna posizione esistente (media costi)
            old_shares = existing.shares
            old_cost = existing.avg_cost
            
            new_shares = old_shares + quantity
            new_avg_cost = ((old_shares * old_cost) + (quantity * price)) / new_shares
            
            existing.shares = new_shares
            existing.avg_cost = new_avg_cost
            existing.current_price = price
            
            # Aggiorna target solo se specificati
            if stop_loss is not None:
                existing.stop_loss = stop_loss
            if profit_target is not None:
                existing.profit_target = profit_target
                
            logger.info(f"Posizione {ticker} aggiornata: {new_shares} shares @ €{new_avg_cost:.2f}")
        else:
            # Nuova posizione
            position = Position(
                ticker=ticker,
                shares=quantity,
                avg_cost=price,
                current_price=price,
                stop_loss=stop_loss,
                profit_target=profit_target,
                portfolio=self
            )
            self._positions[ticker] = position
            logger.info(f"Nuova posizione {ticker}: {quantity} shares @ €{price:.2f}")
    
    def _recalculate_total_value(self) -> None:
        """Ricalcola il valore totale del portfolio."""
        cash = self.get_cash_balance()
        positions_value = sum(pos.get_current_value() for pos in self._positions.values() 
                            if pos.shares > 0)
        self._snapshot['total_value'] = cash + positions_value
        self._snapshot['positions_count'] = self.get_positions_count()
    
    def _save_trade(self, ticker: str, operation: str, quantity: int, 
                price: float, total_value: float, commission: float = 0.0,
                notes: Optional[str] = None) -> int:
        """
        Salva il trade nella tabella trades utilizzando la classe Trade.
        
        Args:
            ticker: Symbol del titolo
            operation: "BUY" o "SELL"
            quantity: Numero di azioni
            price: Prezzo di esecuzione
            total_value: Valore totale del trade
            commission: Commissioni applicate (default: 0.0)
            notes: Note aggiuntive (opzionale)
            
        Returns:
            ID del trade salvato
            
        Example:
            >>> trade_id = portfolio._save_trade("AAPL", "BUY", 10, 150.0, 1500.0, 5.0)
            >>> print(f"Trade salvato con ID: {trade_id}")
        """
        try:
            # Crea oggetto Trade
            trade = Trade(
                date=self.date,
                portfolio_name=self.name,
                ticker=ticker,
                operation=operation,
                quantity=quantity,
                price=price,
                commission=commission,
                notes=notes,
                portfolio=self
            )
            
            # Salva nel database e ottieni l'ID
            trade_id = trade.save_to_db()
            
            logger.info(f"Trade registrato: {operation} {quantity} {ticker} @ €{price:.2f} "
                    f"(ID: {trade_id}, Totale: €{total_value:.2f})")
            
            return trade_id
            
        except Exception as e:
            logger.error(f"Errore nel salvare trade {operation} {quantity} {ticker}: {e}")
            raise

    # =============================
    # PERFORMANCE METRICS (from DB)
    # =============================
    
    def get_total_return_pct(self) -> Optional[float]:
        """Ritorna il return totale percentuale (stored in DB)."""
        if not self._snapshot:
            return None
        return self._snapshot.get('total_return_pct')
    
    def get_current_drawdown(self) -> Optional[float]:
        """Ritorna il drawdown corrente (stored in DB)."""
        if not self._snapshot:
            return None
        return self._snapshot.get('current_drawdown_pct')
    
    def get_max_drawdown(self) -> Optional[float]:
        """Ritorna il massimo drawdown (stored in DB)."""
        if not self._snapshot:
            return None
        return self._snapshot.get('max_drawdown_pct')
    
    def get_portfolio_volatility(self) -> Optional[float]:
        """Ritorna la volatilità del portfolio (stored in DB)."""
        if not self._snapshot:
            return None
        return self._snapshot.get('volatility_pct')
    
    def get_sharpe_ratio(self) -> Optional[float]:
        """Ritorna il Sharpe ratio (stored in DB)."""
        if not self._snapshot:
            return None
        return self._snapshot.get('sharpe_ratio')
    
    def get_win_rate(self) -> Optional[float]:
        """Ritorna il win rate (stored in DB)."""
        if not self._snapshot:
            return None
        return self._snapshot.get('win_rate_pct')

    # =============================
    # HEALTH METRICS (calculated on-the-fly)
    # =============================
    
    def get_largest_position_pct(self) -> float:
        """Ritorna la percentuale del portfolio della posizione più grande."""
        if not self._positions:
            return 0.0
        
        total_value = self.get_total_value()
        if total_value == 0:
            return 0.0
        
        largest_value = max(pos.get_current_value() for pos in self._positions.values() 
                          if pos.shares > 0)
        return (largest_value / total_value) * 100
    
    def get_cash_utilization(self) -> float:
        """Ritorna la percentuale di capitale investito (vs cash)."""
        total_value = self.get_total_value()
        cash_balance = self.get_cash_balance()
        
        if total_value == 0:
            return 0.0
        
        return ((total_value - cash_balance) / total_value) * 100
    
    def get_winning_positions(self) -> List['Position']:
        """Ritorna lista delle posizioni in profitto."""
        return [pos for pos in self._positions.values() 
                if pos.shares > 0 and pos.get_unrealized_pnl_pct() > 0]
    
    def get_losing_positions(self) -> List['Position']:
        """Ritorna lista delle posizioni in perdita."""
        return [pos for pos in self._positions.values() 
                if pos.shares > 0 and pos.get_unrealized_pnl_pct() < 0]
    
    def get_capital_at_risk(self) -> Dict[str, float]:
        """
        Calcola il capitale totalmente a rischio nel portfolio.
        
        Returns:
            Dict con 'total_risk' e dettaglio per posizione
        """
        risk_breakdown = {}
        total_risk = 0.0
        
        for ticker, position in self._positions.items():
            if position.shares > 0 and position.stop_loss:
                risk = position.get_capital_at_risk()
                risk_breakdown[ticker] = risk
                total_risk += risk
        
        return {
            'total_risk': total_risk,
            'positions': risk_breakdown
        }
    
    def get_total_risk_pct(self) -> float:
        """Ritorna il rischio totale come percentuale del portfolio."""
        total_value = self.get_total_value()
        if total_value == 0:
            return 0.0
        
        capital_at_risk = self.get_capital_at_risk()
        return (capital_at_risk['total_risk'] / total_value) * 100
    
    def is_risk_limit_exceeded(self) -> bool:
        """Controlla se il rischio totale supera il limite configurato."""
        return self.get_total_risk_pct() > config.MAX_PORTFOLIO_RISK_PCT

    def get_available_cash(self, buffer_pct: float = config.DEFAULT_CASH_BUFFER * 100) -> float:
        """
        Ritorna cash disponibile considerando il buffer di sicurezza.
        
        Args:
            buffer_pct: Percentuale buffer da mantenere (default: 10%)
            
        Returns:
            Cash disponibile per nuovi investimenti
        """
        total_cash = self.get_cash_balance()
        buffer_amount = total_cash * (buffer_pct / 100.0)
        return max(0, total_cash - buffer_amount)
    
    # =============================
    # INTERNAL METHODS
    # =============================
    
    def _get_latest_date(self, portfolio_name: str) -> Optional[str]:
        """Trova l'ultima data disponibile per un portfolio."""
        table_suffix = "_backtest" if self.backtest else ""
        query = f"""
            SELECT MAX(date) FROM portfolio_snapshots{table_suffix} 
            WHERE portfolio_name = %s
        """
        result, _ = database.execute_query(query, (portfolio_name,))
        if result and result[0][0]:
            return result[0][0].strftime('%Y-%m-%d')
        return None
    
    def _load_from_db(self) -> bool:
        """
        Carica snapshot e posizioni dal database.
        
        Returns:
            True se caricamento riuscito, False altrimenti
        """
        table_suffix = "_backtest" if self.backtest else ""
        
        # Load snapshot
        snapshot_query = f"""
            SELECT total_value, cash_balance, positions_count,
                   daily_return_pct, total_return_pct, volatility_pct, 
                   current_drawdown_pct, max_drawdown_pct, sharpe_ratio, win_rate_pct
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
            'daily_return_pct': float(row[3]) if row[3] else 0.0,
            'total_return_pct': float(row[4]) if row[4] else 0.0,
            'volatility_pct': float(row[5]) if row[5] else 0.0,
            'current_drawdown_pct': float(row[6]) if row[6] else 0.0,
            'max_drawdown_pct': float(row[7]) if row[7] else 0.0,
            'sharpe_ratio': float(row[8]) if row[8] else 0.0,
            'win_rate_pct': float(row[9]) if row[9] else 0.0
        }
        
        # Load positions
        positions_query = f"""
        SELECT ticker, shares, avg_cost, current_price, 
               stop_loss, profit_target, breakeven, first_half_sold,
               entry_atr
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
                breakeven=float(row[6]) if row[6] else None,
                first_half_sold=bool(row[7]) if row[7] else False,
                entry_atr=float(row[8]) if row[8] else None, 
                portfolio=self
            )
        
        return True
    
    def _get_current_price(self, ticker: str) -> float:
        """
        Ottiene il prezzo corrente dal DB universe.
        
        Args:
            ticker: Symbol del titolo
            
        Returns:
            Prezzo di chiusura più recente
            
        Raises:
            PriceNotFoundError: Se il prezzo non è disponibile
        """
        query = """
            SELECT close FROM universe 
            WHERE ticker = %s AND date <= %s 
            ORDER BY date DESC LIMIT 1
        """
        result, _ = database.execute_query(query, (ticker, self.date))
        if not result:
            raise PriceNotFoundError(
                f"Prezzo non trovato per {ticker} alla data {self.date}. "
                f"Verifica che i dati siano disponibili nella tabella universe."
            )
        return float(result[0][0])
    
    def _save_to_db(self) -> None:
        """Salva lo snapshot del portfolio nel database."""
        table_suffix = "_backtest" if self.backtest else ""
        
        query = f"""
            INSERT INTO portfolio_snapshots{table_suffix}
            (date, portfolio_name, total_value, cash_balance, positions_count, 
             daily_return_pct, total_return_pct, volatility_pct, 
             current_drawdown_pct, max_drawdown_pct, sharpe_ratio, win_rate_pct)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date, portfolio_name)
            DO UPDATE SET
                total_value = EXCLUDED.total_value,
                cash_balance = EXCLUDED.cash_balance,
                positions_count = EXCLUDED.positions_count,
                daily_return_pct = EXCLUDED.daily_return_pct,
                total_return_pct = EXCLUDED.total_return_pct,
                volatility_pct = EXCLUDED.volatility_pct,
                current_drawdown_pct = EXCLUDED.current_drawdown_pct,
                max_drawdown_pct = EXCLUDED.max_drawdown_pct,
                sharpe_ratio = EXCLUDED.sharpe_ratio,
                win_rate_pct = EXCLUDED.win_rate_pct
        """
        params = (
            self.date, self.name, 
            self._snapshot['total_value'], 
            self._snapshot['cash_balance'],
            self._snapshot['positions_count'], 
            self._snapshot.get('daily_return_pct', 0.0),
            self._snapshot.get('total_return_pct', 0.0),
            self._snapshot.get('volatility_pct', 0.0),
            self._snapshot.get('current_drawdown_pct', 0.0),
            self._snapshot.get('max_drawdown_pct', 0.0),
            self._snapshot.get('sharpe_ratio', 0.0),
            self._snapshot.get('win_rate_pct', 0.0)
        )
        database.execute_query(query, params, fetch=False)


# ================================
# 2. POSITION CLASS
# ================================

class Position:
    """
    Rappresenta una singola posizione nel portfolio.
    
    Gestisce:
    - Dati base (ticker, shares, avg_cost, current_price)
    - Risk management (stop_loss, profit_target, 2-for-1 logic)
    - Performance tracking (PnL, holding period)
    
    Attributes:
        ticker (str): Symbol del titolo
        shares (int): Numero di azioni possedute
        avg_cost (float): Prezzo medio di carico
        current_price (float): Prezzo corrente
        stop_loss (float): Prezzo di stop loss
        profit_target (float): Primo target di profitto
        breakeven (float): Prezzo di breakeven
        first_half_sold (bool): Flag 2-for-1 strategy
        portfolio (Portfolio): Riferimento al portfolio padre
    """
    
    def __init__(self, ticker: str, shares: int, avg_cost: float, current_price: float,
                 stop_loss: Optional[float] = None, profit_target: Optional[float] = None,
                 breakeven: Optional[float] = None, entry_atr: Optional[float] = None, 
                 first_half_sold: bool = False, portfolio: Optional[Portfolio] = None):
        """
        Inizializza una posizione.
        
        Args:
            ticker: Symbol del titolo
            shares: Numero di azioni
            avg_cost: Prezzo medio di carico
            current_price: Prezzo corrente
            stop_loss: Prezzo di stop loss (opzionale)
            profit_target: Primo target (opzionale) 
            breakeven: Prezzo breakeven (opzionale)
            first_half_sold: Flag per 2-for-1 strategy
            portfolio: Riferimento al portfolio padre
        """
        self.ticker = ticker
        self.shares = shares
        self.avg_cost = avg_cost
        self.current_price = current_price
        self.stop_loss = stop_loss
        self.profit_target = profit_target
        self.breakeven = breakeven
        self.entry_atr = entry_atr
        self.first_half_sold = first_half_sold
        self.portfolio = portfolio
    
    # =============================
    # RISK MANAGER METHODS
    # =============================
    
    def is_stop_loss_hit(self, current_price: float) -> bool:
        """
        Controlla se il prezzo corrente ha raggiunto lo stop loss.
        
        Args:
            current_price: Prezzo corrente del titolo
            
        Returns:
            True se stop loss è stato raggiunto
        """
        if not self.stop_loss:
            return False
        return current_price <= self.stop_loss
    
    def is_profit_target_hit(self, current_price: float) -> bool:
        """
        Controlla se il prezzo corrente ha raggiunto il profit target.
        
        Args:
            current_price: Prezzo corrente del titolo
            
        Returns:
            True se profit target è stato raggiunto
        """
        if not self.profit_target or self.first_half_sold:
            return False
        return current_price >= self.profit_target
    
    def is_breakeven_hit(self, current_price: float) -> bool:
        """
        Controlla se il prezzo corrente ha raggiunto il breakeven.
        
        Args:
            current_price: Prezzo corrente del titolo
            
        Returns:
            True se breakeven è stato raggiunto
        """
        if not self.breakeven:
            return False
        return current_price >= self.breakeven
    
    def calculate_2for1_targets(self, entry_price: float, atr: float) -> Dict[str, float]:
        """
        Calcola i target per la strategia 2-for-1.
        
        Args:
            entry_price: Prezzo di entrata
            atr: Average True Range per calcolo distanze
            
        Returns:
            Dict con stop_loss, profit_target, breakeven
        """
        risk_distance = atr * config.DEFAULT_ATR_MULTIPLIER
        profit_distance = risk_distance * config.DEFAULT_PROFIT_RATIO
        
        targets = {
            'stop_loss': entry_price - risk_distance,
            'profit_target': entry_price + profit_distance,
            'breakeven': entry_price
        }
        
        logger.info(f"Calcolati target 2-for-1 per {self.ticker}: {targets}")
        return targets
    
    def update_targets(self, **kwargs) -> None:
        """
        Aggiorna i target della posizione.
        
        Args:
            **kwargs: stop_loss, profit_target, breakeven, first_half_sold
        """
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        
        self._save_to_db()
        logger.info(f"Target aggiornati per {self.ticker}: {kwargs}")
    
    # =============================
    # PERFORMANCE METHODS
    # =============================
    
    def get_unrealized_pnl_pct(self) -> float:
        """Ritorna il PnL non realizzato come percentuale."""
        if self.avg_cost == 0:
            return 0.0
        return ((self.current_price - self.avg_cost) / self.avg_cost) * 100
    
    def get_unrealized_pnl(self) -> float:
        """Ritorna il PnL non realizzato in valore assoluto."""
        return (self.current_price - self.avg_cost) * self.shares
    
    def get_current_value(self) -> float:
        """Ritorna il valore corrente della posizione."""
        return self.current_price * self.shares
    
    def get_days_held(self) -> int:
        """
        Calcola i giorni di possesso della posizione.
        
        Returns:
            Giorni dalla prima apparizione nel DB
        """
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
        """
        Calcola il capitale a rischio per questa posizione.
        
        Returns:
            Capitale a rischio (differenza tra valore corrente e stop loss)
        """
        if not self.stop_loss:
            return 0.0
        
        current_value = self.get_current_value()
        stop_value = self.stop_loss * self.shares
        
        return max(0, current_value - stop_value)
    
    def get_position_weight(self, total_portfolio_value: float) -> float:
        """
        Calcola il peso della posizione nel portfolio.
        
        Args:
            total_portfolio_value: Valore totale del portfolio
            
        Returns:
            Peso percentuale della posizione
        """
        if total_portfolio_value == 0:
            return 0.0
        return (self.get_current_value() / total_portfolio_value) * 100
    
    # =============================
    # INTERNAL METHODS
    # =============================
    
    def _save_to_db(self) -> None:
        """Salva la posizione nel database."""
        if not self.portfolio:
            logger.warning(f"Impossibile salvare posizione {self.ticker}: portfolio non impostato")
            return
        
        table_suffix = "_backtest" if self.portfolio.backtest else ""
        
        # Calcola metriche posizione
        current_value = self.get_current_value()
        pnl_pct = self.get_unrealized_pnl_pct()
        
        # Usa valore cached del portfolio invece di ricalcolare
        total_value = self.portfolio.get_total_value()
        weight_pct = self.get_position_weight(total_value)
        
        logger.info(f"Salvando posizione {self.ticker}: {self.shares} shares @ €{self.current_price:.2f}")

        query = f"""
            INSERT INTO portfolio_positions{table_suffix} 
            (date, portfolio_name, ticker, shares, avg_cost, current_price, 
            current_value, stop_loss, profit_target, breakeven, first_half_sold,
            entry_atr, position_weight_pct, position_pnl_pct)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date, portfolio_name, ticker) 
            DO UPDATE SET
                shares = EXCLUDED.shares,
                avg_cost = EXCLUDED.avg_cost,
                current_price = EXCLUDED.current_price,
                current_value = EXCLUDED.current_value,
                stop_loss = EXCLUDED.stop_loss,
                profit_target = EXCLUDED.profit_target,
                breakeven = EXCLUDED.breakeven,
                first_half_sold = EXCLUDED.first_half_sold,
                entry_atr = EXCLUDED.entry_atr,
                position_weight_pct = EXCLUDED.position_weight_pct,
                position_pnl_pct = EXCLUDED.position_pnl_pct
        """
        params = (
            self.portfolio.date,
            self.portfolio.name,
            self.ticker,
            self.shares,
            self.avg_cost,
            self.current_price,
            current_value,
            self.stop_loss,
            self.profit_target,
            self.breakeven,
            self.first_half_sold,
            self.entry_atr,  
            weight_pct,
            pnl_pct,
        )

        database.execute_query(query, params, fetch=False)


# ================================
# 3. UTILITY FUNCTIONS
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


# ================================
# 3. TRADE CLASS
# ================================

class Trade:
    """
    Rappresenta un singolo trade eseguito nel portfolio.
    
    Gestisce:
    - Validazione dati trade
    - Persistenza nel database (portfolio_trades / portfolio_trades_backtest)
    - Recupero trade dal database
    
    Attributes:
        id (Optional[int]): ID del trade nel database
        date (str): Data del trade (YYYY-MM-DD)
        portfolio_name (str): Nome del portfolio
        ticker (str): Symbol del titolo
        operation (str): "BUY" o "SELL"
        quantity (int): Numero di azioni
        price (float): Prezzo di esecuzione
        total_value (float): Valore totale del trade
        commission (float): Commissioni applicate
        notes (Optional[str]): Note aggiuntive
        portfolio (Optional[Portfolio]): Riferimento al portfolio padre
    """
    
    def __init__(self, date: str, portfolio_name: str, ticker: str, operation: str, 
                 quantity: int, price: float, commission: float = 0.0,
                 notes: Optional[str] = None, portfolio: Optional['Portfolio'] = None,
                 trade_id: Optional[int] = None):
        """
        Inizializza un trade con validazione dei dati.
        
        Args:
            date: Data del trade (YYYY-MM-DD)
            portfolio_name: Nome del portfolio
            ticker: Symbol del titolo
            operation: "BUY" o "SELL"
            quantity: Numero di azioni (deve essere > 0)
            price: Prezzo di esecuzione (deve essere > 0)
            commission: Commissioni applicate (default: 0.0)
            notes: Note aggiuntive (opzionale)
            portfolio: Riferimento al portfolio padre (opzionale)
            trade_id: ID del trade se caricato dal DB (opzionale)
            
        Raises:
            ValueError: Se i dati non sono validi
        """
        # Validazione dati
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
        
        # Calcola valore totale
        self.total_value = (price * quantity) + (commission if operation.upper() == "BUY" else -commission)
        
        logger.debug(f"Trade creato: {self.operation} {self.quantity} {self.ticker} @ €{self.price:.2f}")
    
    @classmethod
    def load_from_db(cls, trade_id: int, backtest: bool = False) -> Optional['Trade']:
        """
        Carica un trade dal database usando il suo ID.
        
        Args:
            trade_id: ID del trade da caricare
            backtest: Se True, cerca nella tabella backtest
            
        Returns:
            Trade object o None se non trovato
        """
        table_suffix = "_backtest" if backtest else ""
        query = f"""
            SELECT id, date, portfolio_name, ticker, operation, quantity, 
                   price, total_value, commission, notes
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
            commission=float(row[8]) if row[8] else 0.0,
            notes=row[9],
            trade_id=row[0]
        )
    
    @classmethod
    def get_trades_for_portfolio(cls, portfolio_name: str, date: Optional[str] = None, 
                                backtest: bool = False) -> List['Trade']:
        """
        Recupera tutti i trade per un portfolio specifico.
        
        Args:
            portfolio_name: Nome del portfolio
            date: Data specifica (opzionale, se None prende tutti)
            backtest: Se True, cerca nella tabella backtest
            
        Returns:
            Lista di Trade objects
        """
        table_suffix = "_backtest" if backtest else ""
        
        if date:
            query = f"""
                SELECT id, date, portfolio_name, ticker, operation, quantity, 
                       price, total_value, commission, notes
                FROM portfolio_trades{table_suffix}
                WHERE portfolio_name = %s AND date = %s
                ORDER BY created_at ASC
            """
            params = (portfolio_name, date)
        else:
            query = f"""
                SELECT id, date, portfolio_name, ticker, operation, quantity, 
                       price, total_value, commission, notes
                FROM portfolio_trades{table_suffix}
                WHERE portfolio_name = %s
                ORDER BY date DESC, created_at ASC
            """
            params = (portfolio_name,)
        
        result, _ = database.execute_query(query, params)
        trades = []
        
        for row in result:
            trade = cls(
                date=row[1].strftime('%Y-%m-%d'),
                portfolio_name=row[2],
                ticker=row[3],
                operation=row[4],
                quantity=row[5],
                price=float(row[6]),
                commission=float(row[8]) if row[8] else 0.0,
                notes=row[9],
                trade_id=row[0]
            )
            trades.append(trade)
            
        return trades
    
    @classmethod
    def get_trades_for_ticker(cls, ticker: str, portfolio_name: Optional[str] = None,
                             backtest: bool = False) -> List['Trade']:
        """
        Recupera tutti i trade per un ticker specifico.
        
        Args:
            ticker: Symbol del titolo
            portfolio_name: Nome del portfolio (opzionale)
            backtest: Se True, cerca nella tabella backtest
            
        Returns:
            Lista di Trade objects
        """
        table_suffix = "_backtest" if backtest else ""
        
        if portfolio_name:
            query = f"""
                SELECT id, date, portfolio_name, ticker, operation, quantity, 
                       price, total_value, commission, notes
                FROM portfolio_trades{table_suffix}
                WHERE ticker = %s AND portfolio_name = %s
                ORDER BY date DESC, created_at ASC
            """
            params = (ticker.upper(), portfolio_name)
        else:
            query = f"""
                SELECT id, date, portfolio_name, ticker, operation, quantity, 
                       price, total_value, commission, notes
                FROM portfolio_trades{table_suffix}
                WHERE ticker = %s
                ORDER BY date DESC, created_at ASC
            """
            params = (ticker.upper(),)
        
        result, _ = database.execute_query(query, params)
        trades = []
        
        for row in result:
            trade = cls(
                date=row[1].strftime('%Y-%m-%d'),
                portfolio_name=row[2],
                ticker=row[3],
                operation=row[4],
                quantity=row[5],
                price=float(row[6]),
                commission=float(row[8]) if row[8] else 0.0,
                notes=row[9],
                trade_id=row[0]
            )
            trades.append(trade)
            
        return trades
    
    def save_to_db(self) -> int:
        """
        Salva il trade nel database.
        
        Returns:
            ID del trade salvato
            
        Raises:
            Exception: Se il salvataggio fallisce
        """
        backtest = self.portfolio.backtest if self.portfolio else False
        table_suffix = "_backtest" if backtest else ""
        
        if self.id is None:
            # Nuovo trade - INSERT
            query = f"""
                INSERT INTO portfolio_trades{table_suffix}
                (date, portfolio_name, ticker, operation, quantity, price, 
                 total_value, commission, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """
            params = (
                self.date, self.portfolio_name, self.ticker, self.operation,
                self.quantity, self.price, self.total_value, self.commission, self.notes
            )
            
            result, _ = database.execute_query(query, params)
            self.id = result[0][0]
            
            logger.info(f"Trade salvato con ID {self.id}: {self.operation} {self.quantity} "
                       f"{self.ticker} @ €{self.price:.2f}")
        else:
            # Trade esistente - UPDATE
            query = f"""
                UPDATE portfolio_trades{table_suffix}
                SET date = %s, portfolio_name = %s, ticker = %s, operation = %s,
                    quantity = %s, price = %s, total_value = %s, commission = %s, notes = %s
                WHERE id = %s
            """
            params = (
                self.date, self.portfolio_name, self.ticker, self.operation,
                self.quantity, self.price, self.total_value, self.commission, 
                self.notes, self.id
            )
            
            database.execute_query(query, params, fetch=False)
            logger.info(f"Trade {self.id} aggiornato: {self.operation} {self.quantity} "
                       f"{self.ticker} @ €{self.price:.2f}")
        
        return self.id
    
    def delete_from_db(self) -> bool:
        """
        Elimina il trade dal database.
        
        Returns:
            True se eliminato con successo
        """
        if not self.id:
            logger.warning("Impossibile eliminare trade: ID non impostato")
            return False
        
        backtest = self.portfolio.backtest if self.portfolio else False
        table_suffix = "_backtest" if backtest else ""
        
        try:
            query = f"DELETE FROM portfolio_trades{table_suffix} WHERE id = %s"
            database.execute_query(query, (self.id,), fetch=False)
            
            logger.info(f"Trade {self.id} eliminato dal database")
            self.id = None
            return True
            
        except Exception as e:
            logger.error(f"Errore nell'eliminare trade {self.id}: {e}")
            return False
    
    def get_net_value(self) -> float:
        """
        Ritorna il valore netto del trade considerando le commissioni.
        
        Returns:
            Valore netto del trade
        """
        base_value = self.price * self.quantity
        
        if self.operation == "BUY":
            return -(base_value + self.commission)  # Negativo per acquisti
        else:
            return base_value - self.commission     # Positivo per vendite
    
    def _validate_trade_data(self, date: str, portfolio_name: str, ticker: str, 
                           operation: str, quantity: int, price: float, commission: float) -> None:
        """
        Valida i dati del trade.
        
        Args:
            date, portfolio_name, ticker, operation, quantity, price, commission: Dati da validare
            
        Raises:
            ValueError: Se i dati non sono validi
        """
        # Validazione data
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            raise ValueError(f"Data non valida: {date}. Formato richiesto: YYYY-MM-DD")
        
        # Validazione portfolio_name
        if not portfolio_name or not isinstance(portfolio_name, str) or len(portfolio_name.strip()) == 0:
            raise ValueError("Nome portfolio non può essere vuoto")
        
        # Validazione ticker
        if not ticker or not isinstance(ticker, str) or len(ticker.strip()) == 0:
            raise ValueError("Ticker non può essere vuoto")
        
        if len(ticker.strip()) > 10:
            raise ValueError(f"Ticker troppo lungo: {ticker} (max 10 caratteri)")
        
        # Validazione operation
        if operation.upper() not in ["BUY", "SELL"]:
            raise ValueError(f"Operazione non valida: {operation}. Deve essere 'BUY' o 'SELL'")
        
        # Validazione quantity
        if not isinstance(quantity, int) or quantity <= 0:
            raise ValueError(f"Quantità non valida: {quantity}. Deve essere un intero positivo")
        
        # Validazione price
        if not isinstance(price, (int, float)) or price <= 0:
            raise ValueError(f"Prezzo non valido: {price}. Deve essere un numero positivo")
        
        # Validazione commission
        if not isinstance(commission, (int, float)) or commission < 0:
            raise ValueError(f"Commissione non valida: {commission}. Deve essere un numero >= 0")
    
    def __str__(self) -> str:
        """Rappresentazione stringa del trade."""
        commission_str = f" (comm: €{self.commission:.2f})" if self.commission > 0 else ""
        return (f"Trade[{self.id}]: {self.date} - {self.operation} {self.quantity} "
                f"{self.ticker} @ €{self.price:.2f}{commission_str}")
    
    def __repr__(self) -> str:
        """Rappresentazione dettagliata del trade."""
        return (f"Trade(id={self.id}, date='{self.date}', portfolio='{self.portfolio_name}', "
                f"ticker='{self.ticker}', operation='{self.operation}', quantity={self.quantity}, "
                f"price={self.price}, commission={self.commission})")
