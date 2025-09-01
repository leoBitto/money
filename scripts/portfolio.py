# scripts/portfolio.py
"""
Modulo: portfolio (Refactored with OOP)
=======================================

Gestione completa dello stato dei portafogli tramite classi Portfolio e Position.

CLASSI PRINCIPALI:
1. Portfolio: Container per tutte le posizioni e metriche di un portfolio
2. Position: Singola posizione con risk management e performance tracking

FUNZIONI MODULO:
- create_portfolio_tables(): Inizializzazione tabelle DB
- create_new_portfolio(): Factory per nuovi portfolio
- get_portfolio_names(): Lista portfolio disponibili

DIPENDENZE:
- database.execute_query() per tutte le operazioni DB
- universe table per prezzi correnti  
- config.py per parametri e defaults

USO TIPICO:
>>> from scripts.portfolio import Portfolio, create_portfolio_tables
>>> create_portfolio_tables()  # Prima volta
>>> portfolio = Portfolio("demo", "2025-09-01")
>>> portfolio.get_positions_count()  # 3
>>> portfolio.get_cash_balance()     # 5000.0
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


def create_new_portfolio(name: str, initial_cash: float = 10000.0, date: Optional[str] = None):
    """
    Crea un nuovo portfolio nel DB con solo cash iniziale.
    
    Args:
        name: Nome del portfolio
        initial_cash: Cash iniziale
        date: Data (default: oggi)
    """
    from datetime import datetime
    date = date or datetime.today().strftime("%Y-%m-%d")

    query = """
        INSERT INTO portfolio_snapshots
        (date, portfolio_name, total_value, cash_balance, positions_count, daily_return_pct)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (date, portfolio_name) DO NOTHING
    """
    params = (date, name, initial_cash, initial_cash, 0, 0.0)
    database.execute_query(query, params, fetch=False)


# ================================
# 1. PORTFOLIO CLASS
# ================================

class Portfolio:
    """
    Container per un portfolio specifico (nome + data).
    
    Gestisce:
    - Stato corrente (cash, posizioni, valore totale)
    - Metriche performance (returns, drawdown, volatility, Sharpe)
    - Risk management (capital at risk, concentration)
    - Operazioni (add/update positions)
    
    Attributes:
        name (str): Nome del portfolio
        date (str): Data dello snapshot (YYYY-MM-DD)
        _snapshot (dict): Metriche aggregate del portfolio
        _positions (dict): Posizioni dettagliate {ticker: Position}
    """
    
    def __init__(self, name: str, date: Optional[str] = None):
        """
        Inizializza portfolio caricando dati dal DB.
        
        Args:
            name: Nome del portfolio
            date: Data specifica (default: ultima data disponibile)
        """
        self.name = name
        self.date = date or self._get_latest_date(name)
        self._snapshot = None
        self._positions = {}
        
        if self.date:
            self._load_from_db()
            logger.info(f"Portfolio '{name}' caricato per {self.date}")
        else:
            logger.warning(f"Portfolio '{name}' non trovato nel DB")
    
    # =============================
    # CORE METHODS (Risk Manager)
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
    
    def add_position(self, ticker: str, shares: int, avg_cost: float, 
                     current_price: Optional[float] = None) -> 'Position':
        """
        Aggiunge o aggiorna una posizione nel portfolio.
        
        Args:
            ticker: Symbol del titolo
            shares: Numero di azioni
            avg_cost: Prezzo medio di carico
            current_price: Prezzo corrente (default: cerca nel DB)
            
        Returns:
            Position object creata/aggiornata
        """
        if current_price is None:
            current_price = self._get_current_price(ticker)
        
        # Controlla se è aggiornamento o nuova posizione
        existing = self._positions.get(ticker)
        if existing and existing.shares > 0:
            # Aggiorna posizione esistente (media costi)
            old_shares = existing.shares
            old_cost = existing.avg_cost
            
            new_shares = old_shares + shares
            new_avg_cost = ((old_shares * old_cost) + (shares * avg_cost)) / new_shares
            
            existing.shares = new_shares
            existing.avg_cost = new_avg_cost
            existing.current_price = current_price
            
            position = existing
            logger.info(f"Posizione {ticker} aggiornata: {new_shares} shares @ €{new_avg_cost:.2f}")
        else:
            # Nuova posizione
            position = Position(
                ticker=ticker,
                shares=shares,
                avg_cost=avg_cost,
                current_price=current_price,
                portfolio=self
            )
            self._positions[ticker] = position
            logger.info(f"Nuova posizione {ticker}: {shares} shares @ €{avg_cost:.2f}")
        
        # Salva nel DB
        position._save_to_db()
        self._update_snapshot()
        
        return position
    
    def update_position_targets(self, ticker: str, targets: Dict) -> None:
        """
        Aggiorna i target di risk management per una posizione.
        
        Args:
            ticker: Symbol del titolo
            targets: Dict con stop_loss, first_target, breakeven
        """
        position = self._positions.get(ticker)
        if not position:
            raise ValueError(f"Posizione {ticker} non trovata")
        
        position.stop_loss = targets.get('stop_loss')
        position.first_target = targets.get('first_target') 
        position.breakeven = targets.get('breakeven')
        
        position._save_to_db()
        logger.info(f"Target aggiornati per {ticker}: SL={targets.get('stop_loss'):.2f}")
    
    # =============================
    # PERFORMANCE METRICS 
    # =============================
    
    def get_total_return_pct(self, start_date: Optional[str] = None) -> Optional[float]:
        """
        Calcola il return percentuale del portfolio.
        
        Args:
            start_date: Data di inizio calcolo (default: 30 giorni fa)
            
        Returns:
            Return percentuale o None se dati insufficienti
        """
        if start_date is None:
            start_date = (datetime.strptime(self.date, '%Y-%m-%d') - timedelta(days=30)).strftime('%Y-%m-%d')
        
        # Ottieni snapshot iniziale
        query = """
            SELECT total_value FROM portfolio_snapshots
            WHERE portfolio_name = %s AND date >= %s
            ORDER BY date ASC LIMIT 1
        """
        result, _ = database.execute_query(query, (self.name, start_date))
        if not result:
            return None
        
        initial_value = float(result[0][0])
        current_value = self.get_total_value()
        
        if initial_value == 0:
            return None
        
        return ((current_value - initial_value) / initial_value) * 100
    
    def get_current_drawdown(self) -> Optional[float]:
        """
        Calcola il drawdown corrente dal peak più recente.
        
        Returns:
            Drawdown percentuale (negativo) o None se dati insufficienti
        """
        # Cerca il peak negli ultimi 60 giorni
        start_date = (datetime.strptime(self.date, '%Y-%m-%d') - timedelta(days=60)).strftime('%Y-%m-%d')
        
        query = """
            SELECT MAX(total_value) as peak_value FROM portfolio_snapshots
            WHERE portfolio_name = %s AND date BETWEEN %s AND %s
        """
        result, _ = database.execute_query(query, (self.name, start_date, self.date))
        if not result or not result[0][0]:
            return None
        
        peak_value = float(result[0][0])
        current_value = self.get_total_value()
        
        if peak_value == 0:
            return None
        
        drawdown = ((current_value - peak_value) / peak_value) * 100
        return min(drawdown, 0)  # Drawdown è sempre <= 0
    
    def get_max_drawdown(self, days: int = config.DRAWDOWN_CALCULATION_DAYS) -> Optional[float]:
        """
        Calcola il massimo drawdown in un periodo.
        
        Args:
            days: Giorni di lookback (default: 252 = 1 anno)
            
        Returns:
            Max drawdown percentuale o None se dati insufficienti
        """
        start_date = (datetime.strptime(self.date, '%Y-%m-%d') - timedelta(days=days)).strftime('%Y-%m-%d')
        
        query = """
            SELECT date, total_value FROM portfolio_snapshots
            WHERE portfolio_name = %s AND date BETWEEN %s AND %s
            ORDER BY date
        """
        result, _ = database.execute_query(query, (self.name, start_date, self.date))
        if len(result) < 2:
            return None
        
        values = [float(row[1]) for row in result]
        max_dd = 0
        peak = values[0]
        
        for value in values[1:]:
            if value > peak:
                peak = value
            else:
                dd = (value - peak) / peak * 100
                max_dd = min(max_dd, dd)
        
        return max_dd
    
    def get_portfolio_volatility(self, days: int = config.VOLATILITY_CALCULATION_DAYS) -> Optional[float]:
        """
        Calcola la volatilità del portfolio (standard deviation dei daily returns).
        
        Args:
            days: Giorni di lookback (default: 30)
            
        Returns:
            Volatilità annualizzata percentuale o None se dati insufficienti
        """
        start_date = (datetime.strptime(self.date, '%Y-%m-%d') - timedelta(days=days)).strftime('%Y-%m-%d')
        
        query = """
            SELECT total_value FROM portfolio_snapshots
            WHERE portfolio_name = %s AND date BETWEEN %s AND %s
            ORDER BY date
        """
        result, _ = database.execute_query(query, (self.name, start_date, self.date))
        if len(result) < 2:
            return None
        
        values = [float(row[0]) for row in result]
        daily_returns = []
        
        for i in range(1, len(values)):
            daily_return = (values[i] - values[i-1]) / values[i-1]
            daily_returns.append(daily_return)
        
        if len(daily_returns) < 2:
            return None
        
        daily_vol = stdev(daily_returns)
        annualized_vol = daily_vol * (252 ** 0.5) * 100  # Annualizza e converti in %
        
        return annualized_vol
    
    def get_sharpe_ratio(self, risk_free_rate: float = config.DEFAULT_RISK_FREE_RATE) -> Optional[float]:
        """
        Calcola il Sharpe ratio del portfolio.
        
        Args:
            risk_free_rate: Tasso risk-free annuale (default: 2%)
            
        Returns:
            Sharpe ratio o None se dati insufficienti
        """
        annual_return = self.get_total_return_pct()
        volatility = self.get_portfolio_volatility()
        
        if annual_return is None or volatility is None or volatility == 0:
            return None
        
        # Converti annual return in decimal per il calcolo
        excess_return = (annual_return / 100) - risk_free_rate
        return excess_return / (volatility / 100)
    
    def get_win_rate(self, days: int = config.VOLATILITY_CALCULATION_DAYS) -> Optional[float]:
        """
        Calcola la percentuale di giorni con return positivo.
        
        Args:
            days: Giorni di lookback (default: 30)
            
        Returns:
            Win rate percentuale o None se dati insufficienti
        """
        start_date = (datetime.strptime(self.date, '%Y-%m-%d') - timedelta(days=days)).strftime('%Y-%m-%d')
        
        query = """
            SELECT total_value FROM portfolio_snapshots
            WHERE portfolio_name = %s AND date BETWEEN %s AND %s
            ORDER BY date
        """
        result, _ = database.execute_query(query, (self.name, start_date, self.date))
        if len(result) < 2:
            return None
        
        values = [float(row[0]) for row in result]
        positive_days = 0
        total_days = 0
        
        for i in range(1, len(values)):
            daily_return = (values[i] - values[i-1]) / values[i-1]
            if daily_return > 0:
                positive_days += 1
            total_days += 1
        
        if total_days == 0:
            return None
        
        return (positive_days / total_days) * 100
    
    # =============================
    # PORTFOLIO HEALTH
    # =============================
    
    def get_largest_position_pct(self) -> float:
        """Ritorna la percentuale del portfolio della posizione più grande."""
        if not self._positions:
            return 0.0
        
        total_value = self.get_total_value()
        if total_value == 0:
            return 0.0
        
        largest_value = max(pos.get_current_value() for pos in self._positions.values() if pos.shares > 0)
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
    
    # =============================
    # INTERNAL METHODS
    # =============================
    
    def _get_latest_date(self, portfolio_name: str) -> Optional[str]:
        """Trova l'ultima data disponibile per un portfolio."""
        query = """
            SELECT MAX(date) FROM portfolio_snapshots 
            WHERE portfolio_name = %s
        """
        result, _ = database.execute_query(query, (portfolio_name,))
        if result and result[0][0]:
            return result[0][0].strftime('%Y-%m-%d')
        return None
    
    def _load_from_db(self) -> None:
        """Carica snapshot e posizioni dal database."""
        # Load snapshot
        snapshot_query = """
            SELECT total_value, cash_balance, positions_count,
                   daily_return_pct, portfolio_volatility, current_drawdown_pct
            FROM portfolio_snapshots
            WHERE date = %s AND portfolio_name = %s
        """
        result, _ = database.execute_query(snapshot_query, (self.date, self.name))
        if result:
            row = result[0]
            self._snapshot = {
                'total_value': float(row[0]),
                'cash_balance': float(row[1]),
                'positions_count': row[2],
                'daily_return_pct': float(row[3]) if row[3] else 0.0,
                'portfolio_volatility': float(row[4]) if row[4] else 0.0,
                'current_drawdown_pct': float(row[5]) if row[5] else 0.0
            }
        
        # Load positions
        positions_query = """
            SELECT ticker, shares, avg_cost, current_price, 
                   stop_loss, first_target, breakeven, first_half_sold
            FROM portfolio_positions
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
                first_target=float(row[5]) if row[5] else None,
                breakeven=float(row[6]) if row[6] else None,
                first_half_sold=bool(row[7]) if row[7] else False,
                portfolio=self
            )
    
    def _get_current_price(self, ticker: str) -> float:
        """Ottiene il prezzo corrente dal DB universe."""
        query = """
            SELECT close FROM universe 
            WHERE ticker = %s AND date <= %s 
            ORDER BY date DESC LIMIT 1
        """
        result, _ = database.execute_query(query, (ticker, self.date))
        if not result:
            raise ValueError(f"Prezzo non trovato per {ticker} alla data {self.date}")
        return float(result[0][0])
    
    def _update_snapshot(self) -> None:
        """Ricalcola e salva lo snapshot del portfolio."""
        cash = self.get_cash_balance()
        positions_value = sum(pos.get_current_value() for pos in self._positions.values() if pos.shares > 0)
        total_value = cash + positions_value
        active_positions = self.get_positions_count()
        
        self._snapshot = {
            'total_value': total_value,
            'cash_balance': cash,
            'positions_count': active_positions,
            'daily_return_pct': 0.0  # Da calcolare se necessario
        }
        
        # Salva nel DB
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
        params = (self.date, self.name, total_value, cash, active_positions, 0.0)
        database.execute_query(query, params, fetch=False)


# ================================
# 2. POSITION CLASS
# ================================

class Position:
    """
    Rappresenta una singola posizione nel portfolio.
    
    Gestisce:
    - Dati base (ticker, shares, avg_cost, current_price)
    - Risk management (stop_loss, targets, 2-for-1 logic)
    - Performance tracking (PnL, holding period)
    
    Attributes:
        ticker (str): Symbol del titolo
        shares (int): Numero di azioni possedute
        avg_cost (float): Prezzo medio di carico
        current_price (float): Prezzo corrente
        stop_loss (float): Prezzo di stop loss
        first_target (float): Primo target di profitto
        breakeven (float): Prezzo di breakeven
        first_half_sold (bool): Flag 2-for-1 strategy
        portfolio (Portfolio): Riferimento al portfolio padre
    """
    
    def __init__(self, ticker: str, shares: int, avg_cost: float, current_price: float,
                 stop_loss: Optional[float] = None, first_target: Optional[float] = None,
                 breakeven: Optional[float] = None, first_half_sold: bool = False,
                 portfolio: Optional[Portfolio] = None):
        """
        Inizializza una posizione.
        
        Args:
            ticker: Symbol del titolo
            shares: Numero di azioni
            avg_cost: Prezzo medio di carico
            current_price: Prezzo corrente
            stop_loss: Prezzo di stop loss (opzionale)
            first_target: Primo target (opzionale)
            breakeven: Prezzo breakeven (opzionale)
            first_half_sold: Flag per 2-for-1 strategy
            portfolio: Riferimento al portfolio padre
        """
        self.ticker = ticker
        self.shares = shares
        self.avg_cost = avg_cost
        self.current_price = current_price
        self.stop_loss = stop_loss
        self.first_target = first_target
        self.breakeven = breakeven
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
    
    def is_first_target_hit(self, current_price: float) -> bool:
        """
        Controlla se il prezzo corrente ha raggiunto il primo target.
        
        Args:
            current_price: Prezzo corrente del titolo
            
        Returns:
            True se primo target è stato raggiunto
        """
        if not self.first_target or self.first_half_sold:
            return False
        return current_price >= self.first_target
    
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
            Dict con stop_loss, first_target, breakeven
        """
        risk_distance = atr * config.DEFAULT_ATR_MULTIPLIER
        profit_distance = risk_distance * config.DEFAULT_PROFIT_RATIO
        
        targets = {
            'stop_loss': entry_price - risk_distance,
            'first_target': entry_price + profit_distance,
            'breakeven': entry_price
        }
        
        logger.info(f"Calcolati target 2-for-1 per {self.ticker}: {targets}")
        return targets
    
    def update_targets(self, **kwargs) -> None:
        """
        Aggiorna i target della posizione.
        
        Args:
            **kwargs: stop_loss, first_target, breakeven, first_half_sold
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
        
        query = """
            SELECT MIN(date) FROM portfolio_positions
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
        
        # Calcola metriche
        current_value = self.get_current_value()
        pnl_pct = self.get_unrealized_pnl_pct()
        weight_pct = self.get_position_weight(self.portfolio.get_total_value())
        
        query = """
            INSERT INTO portfolio_positions 
            (date, portfolio_name, ticker, shares, avg_cost, current_price, 
             current_value, stop_loss, first_target, breakeven, first_half_sold,
             position_weight_pct, position_pnl_pct)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date, portfolio_name, ticker) 
            DO UPDATE SET
                shares = EXCLUDED.shares,
                avg_cost = EXCLUDED.avg_cost,
                current_price = EXCLUDED.current_price,
                current_value = EXCLUDED.current_value,
                stop_loss = EXCLUDED.stop_loss,
                first_target = EXCLUDED.first_target,
                breakeven = EXCLUDED.breakeven,
                first_half_sold = EXCLUDED.first_half_sold,
                position_weight_pct = EXCLUDED.position_weight_pct,
                position_pnl_pct = EXCLUDED.position_pnl_pct
        """