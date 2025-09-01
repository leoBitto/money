# scripts/risk_manager.py
"""
Modulo: risk_manager
====================

Sistema di gestione del rischio per trading sistematico con strategia 2-for-1.

FUNZIONALITÀ PRINCIPALI:
1. Trasforma segnali grezzi (HOLD/BUY/SELL) in decisioni operative concrete
2. Applica position sizing basato su rischio percentuale (2% default)
3. Implementa strategia 2-for-1 per massimizzare profitti limitando perdite
4. Gestisce priorità delle decisioni (SELL > BUY)
5. Limita esposizione massima (5 posizioni simultanee default)

LOGICA OPERATIVA:
- SELL ha sempre priorità assoluta (protezione capitale)
- BUY viene filtrato per disponibilità cash e volatilità
- Stop loss fisso a 2x ATR sotto entry price  
- First target a 2x rischio per vendita 50% posizione
- Secondo target a breakeven per rimanente 50%

DIPENDENZE:
- portfolio.py per stato corrente e aggiornamenti
- database.py per tracking operazioni
- pandas per manipolazione dati

USO TIPICO:
>>> from scripts.risk_manager import process_signals
>>> refined_signals = process_signals(raw_signals, portfolio_name="demo")
>>> # Esegui gli ordini refinati...
"""

import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import logging

from . import portfolio
from . import database

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ================================
# 1. CONFIGURATION PARAMETERS
# ================================

# Risk management settings
DEFAULT_RISK_PCT = 2.0          # Risk per trade as % of total portfolio
DEFAULT_MAX_POSITIONS = 5       # Maximum simultaneous positions
DEFAULT_ATR_MULTIPLIER = 2.0    # Stop loss distance in ATR units
DEFAULT_CASH_BUFFER = 0.10      # Keep 10% cash buffer
DEFAULT_PROFIT_RATIO = 2.0      # First target at 2x risk distance

# Signal selection preferences  
VOLATILITY_PREFERENCE = "low"   # "low" = conservative, "high" = aggressive


# ================================
# 2. MAIN SIGNAL PROCESSING
# ================================

def process_signals(raw_signals: List[Dict], 
                   portfolio_name: str = "default",
                   date: Optional[str] = None,
                   risk_pct: float = DEFAULT_RISK_PCT,
                   max_positions: int = DEFAULT_MAX_POSITIONS) -> List[Dict]:
    """
    Transform raw signals into executable orders with risk management applied.
    
    This is the main entry point for the risk manager. Takes simple HOLD/BUY/SELL
    signals and outputs concrete orders with position sizing, stops, and targets.
    
    Args:
        raw_signals: List of signal dicts with keys: action, ticker, price, atr
        portfolio_name: Name of portfolio to analyze
        date: Date for analysis (default: today)
        risk_pct: Risk percentage per trade (default: 2.0%)
        max_positions: Maximum simultaneous positions (default: 5)
        
    Returns:
        List of refined signal dicts with execution details
        
    Example:
        >>> signals = [
        ...     {"action": "BUY", "ticker": "AAPL", "price": 150.0, "atr": 3.5},
        ...     {"action": "SELL", "ticker": "MSFT", "price": 310.0, "atr": 8.2}
        ... ]
        >>> refined = process_signals(signals, "demo")
        >>> # Returns executable orders with stops/targets
    """
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    
    logger.info(f"Processing {len(raw_signals)} signals for portfolio '{portfolio_name}' on {date}")
    
    # Get current portfolio state
    portfolio_state = get_portfolio_state(portfolio_name, date)
    if not portfolio_state:
        logger.error(f"Portfolio '{portfolio_name}' not found for date {date}")
        return []
    
    refined_signals = []
    
    # PRIORITY 1: Process SELL signals (capital protection)
    sell_signals = [s for s in raw_signals if s['action'] == 'SELL']
    hold_signals = [s for s in raw_signals if s['action'] == 'HOLD']
    
    # Check both explicit SELL signals and HOLD signals for existing positions
    all_check_signals = sell_signals + hold_signals
    
    for signal in all_check_signals:
        ticker = signal['ticker']
        current_price = signal['price']
        
        if ticker in portfolio_state['positions']:
            sell_orders = check_sell_conditions(
                portfolio_state['positions'][ticker],
                current_price,
                signal['action']
            )
            refined_signals.extend(sell_orders)
    
    # PRIORITY 2: Process BUY signals (growth opportunities)  
    buy_signals = [s for s in raw_signals if s['action'] == 'BUY']
    if buy_signals:
        buy_orders = process_buy_signals(
            buy_signals,
            portfolio_state,
            risk_pct,
            max_positions
        )
        refined_signals.extend(buy_orders)
    
    logger.info(f"Generated {len(refined_signals)} refined signals:")
    for signal in refined_signals:
        logger.info(f"  {signal['action']} {signal.get('shares', 0)} {signal['ticker']} @ {signal.get('price', 0):.2f}")
    
    return refined_signals


def get_portfolio_state(portfolio_name: str, date: str) -> Optional[Dict]:
    """
    Get comprehensive portfolio state for risk analysis.
    
    Returns dict with keys:
    - snapshot: portfolio totals and cash
    - positions: dict of current positions keyed by ticker
    """
    # Get portfolio snapshot
    snapshot = portfolio.get_portfolio_snapshot(date, portfolio_name)
    if not snapshot:
        return None
        
    # Get detailed positions
    positions_df = portfolio.get_portfolio_positions(date, portfolio_name)
    
    # Convert positions to dict for easier access
    positions_dict = {}
    for _, row in positions_df.iterrows():
        ticker = row['ticker']
        positions_dict[ticker] = {
            'ticker': ticker,
            'shares': int(row['shares']),
            'avg_cost': float(row['avg_cost']),
            'current_price': float(row['current_price']),
            'current_value': float(row['current_value']),
            'stop_loss': float(row['stop_loss']) if pd.notna(row['stop_loss']) else None,
            'first_target': float(row['first_target']) if pd.notna(row['first_target']) else None,
            'breakeven': float(row['breakeven']) if pd.notna(row['breakeven']) else None,
            'first_half_sold': bool(row['first_half_sold']) if pd.notna(row['first_half_sold']) else False,
            'position_weight_pct': float(row['position_weight_pct']) if pd.notna(row['position_weight_pct']) else 0.0,
            'position_pnl_pct': float(row['position_pnl_pct']) if pd.notna(row['position_pnl_pct']) else 0.0
        }
    
    return {
        'snapshot': snapshot,
        'positions': positions_dict
    }


# ================================
# 3. SELL SIGNAL PROCESSING (PRIORITY 1)
# ================================

def check_sell_conditions(position: Dict, 
                         current_price: float,
                         signal_action: str) -> List[Dict]:
    """
    Check all sell conditions for an existing position using 2-for-1 strategy.
    
    Sell triggers (in order of priority):
    1. Stop loss hit -> sell all shares immediately
    2. First target hit -> sell 50% + move stop to breakeven  
    3. Breakeven hit (after first target) -> sell remaining 50%
    4. Strategy SELL signal -> sell all (if not in 2-for-1 sequence)
    
    Args:
        position: Position dict with current state
        current_price: Current market price
        signal_action: "SELL", "HOLD", or "BUY" from strategy
        
    Returns:
        List of sell order dicts
    """
    sell_orders = []
    
    ticker = position['ticker']
    shares = position['shares']
    stop_loss = position['stop_loss']
    first_target = position['first_target']
    breakeven = position['breakeven']
    first_half_sold = position['first_half_sold']
    
    # Skip if no shares (shouldn't happen)
    if shares <= 0:
        return []
    
    # 1. STOP LOSS HIT (highest priority)
    if stop_loss and current_price <= stop_loss:
        sell_orders.append({
            'action': 'SELL',
            'ticker': ticker,
            'shares': shares,
            'price': current_price,
            'reason': 'STOP_LOSS',
            'priority': 1
        })
        logger.warning(f"STOP LOSS triggered for {ticker}: {current_price:.2f} <= {stop_loss:.2f}")
        return sell_orders
    
    # 2. FIRST TARGET HIT (2-for-1 strategy activation)
    if first_target and not first_half_sold and current_price >= first_target:
        half_shares = shares // 2
        if half_shares > 0:
            sell_orders.append({
                'action': 'SELL',
                'ticker': ticker, 
                'shares': half_shares,
                'price': current_price,
                'reason': 'FIRST_TARGET_2FOR1',
                'priority': 2,
                'update_position': {
                    'first_half_sold': True,
                    'stop_loss': position['avg_cost'],  # Move stop to breakeven
                    'breakeven': position['avg_cost']
                }
            })
            logger.info(f"FIRST TARGET hit for {ticker}: selling {half_shares} shares at {current_price:.2f}")
        return sell_orders
    
    # 3. BREAKEVEN HIT (after first target sold)
    if first_half_sold and breakeven and current_price <= breakeven:
        remaining_shares = shares - (shares // 2)
        if remaining_shares > 0:
            sell_orders.append({
                'action': 'SELL',
                'ticker': ticker,
                'shares': remaining_shares, 
                'price': current_price,
                'reason': 'BREAKEVEN_2FOR1',
                'priority': 3
            })
            logger.info(f"BREAKEVEN hit for {ticker}: selling remaining {remaining_shares} shares at {current_price:.2f}")
        return sell_orders
    
    # 4. STRATEGY SELL SIGNAL (if not in 2-for-1 sequence)
    if signal_action == 'SELL' and not first_half_sold:
        sell_orders.append({
            'action': 'SELL',
            'ticker': ticker,
            'shares': shares,
            'price': current_price,
            'reason': 'STRATEGY_SIGNAL',
            'priority': 4
        })
        logger.info(f"STRATEGY SELL signal for {ticker}: selling {shares} shares at {current_price:.2f}")
    
    return sell_orders


# ================================
# 4. BUY SIGNAL PROCESSING (PRIORITY 2)  
# ================================

def process_buy_signals(buy_signals: List[Dict],
                       portfolio_state: Dict,
                       risk_pct: float,
                       max_positions: int) -> List[Dict]:
    """
    Process BUY signals with position sizing and selection logic.
    
    Steps:
    1. Filter signals for available positions slots
    2. Rank signals by conservativeness (low volatility first)
    3. Calculate position sizes based on risk percentage
    4. Generate orders with stop loss and profit targets
    
    Args:
        buy_signals: List of BUY signal dicts
        portfolio_state: Current portfolio state
        risk_pct: Risk percentage per trade
        max_positions: Maximum simultaneous positions
        
    Returns:
        List of BUY order dicts with position sizing and targets
    """
    # Check available position slots
    current_positions = len([p for p in portfolio_state['positions'].values() if p['shares'] > 0])
    available_slots = max_positions - current_positions
    
    if available_slots <= 0:
        logger.info(f"No available position slots (current: {current_positions}/{max_positions})")
        return []
    
    logger.info(f"Available position slots: {available_slots}/{max_positions}")
    
    # Filter out tickers we already own
    existing_tickers = set(portfolio_state['positions'].keys())
    new_buy_signals = [s for s in buy_signals if s['ticker'] not in existing_tickers]
    
    if not new_buy_signals:
        logger.info("No new BUY signals (all tickers already owned)")
        return []
    
    # Rank signals by conservativeness (lower volatility = lower risk)
    ranked_signals = rank_buy_signals_by_conservativeness(new_buy_signals)
    
    # Select best signals within available slots
    selected_signals = ranked_signals[:available_slots]
    logger.info(f"Selected {len(selected_signals)} BUY signals from {len(new_buy_signals)} candidates")
    
    # Calculate position sizes and generate orders
    buy_orders = []
    total_portfolio_value = portfolio_state['snapshot']['total_value']
    available_cash = portfolio_state['snapshot']['cash_balance']
    
    for signal in selected_signals:
        order = calculate_buy_order(
            signal,
            total_portfolio_value,
            available_cash,
            risk_pct
        )
        
        if order:
            buy_orders.append(order)
            # Reduce available cash for next calculation
            available_cash -= order['shares'] * order['price']
            logger.info(f"Generated BUY order: {order['shares']} {order['ticker']} @ {order['price']:.2f}")
        else:
            logger.warning(f"Could not generate BUY order for {signal['ticker']} (insufficient funds)")
    
    return buy_orders


def rank_buy_signals_by_conservativeness(buy_signals: List[Dict]) -> List[Dict]:
    """
    Rank BUY signals by conservativeness (lower volatility = more conservative).
    
    Conservative approach prioritizes:
    1. Lower ATR (lower volatility)
    2. Alphabetical order as tiebreaker (consistent selection)
    
    Args:
        buy_signals: List of BUY signal dicts with 'atr' values
        
    Returns:
        Sorted list with most conservative signals first
    """
    if VOLATILITY_PREFERENCE == "low":
        # Sort by ATR ascending (lower volatility first), then alphabetically
        ranked = sorted(buy_signals, key=lambda x: (x['atr'], x['ticker']))
        logger.info(f"Ranked signals by conservativeness (low volatility first):")
        for i, signal in enumerate(ranked[:5]):  # Show top 5
            logger.info(f"  {i+1}. {signal['ticker']} (ATR: {signal['atr']:.2f})")
    else:
        # Alternative: high volatility first (more aggressive)
        ranked = sorted(buy_signals, key=lambda x: (-x['atr'], x['ticker']))
        logger.info(f"Ranked signals by aggressiveness (high volatility first):")
    
    return ranked


def calculate_buy_order(signal: Dict,
                       total_portfolio_value: float,
                       available_cash: float, 
                       risk_pct: float) -> Optional[Dict]:
    """
    Calculate position size and targets for a BUY order using 2% risk rule.
    
    Position sizing logic:
    - Risk amount = total_portfolio_value * risk_pct%
    - Stop loss distance = 2 * ATR  
    - Shares = risk_amount / stop_loss_distance
    - Verify we have enough cash for the purchase
    
    Args:
        signal: BUY signal dict with ticker, price, atr
        total_portfolio_value: Total portfolio value for risk calculation
        available_cash: Cash available for purchases
        risk_pct: Risk percentage per trade
        
    Returns:
        BUY order dict with position sizing and targets, or None if insufficient funds
    """
    ticker = signal['ticker']
    entry_price = signal['price']
    atr = signal['atr']
    
    # Calculate risk-based position size
    risk_amount = total_portfolio_value * (risk_pct / 100.0)
    stop_loss_distance = DEFAULT_ATR_MULTIPLIER * atr
    stop_loss_price = entry_price - stop_loss_distance
    
    # Position size based on risk
    if stop_loss_distance <= 0:
        logger.error(f"Invalid stop loss distance for {ticker}: {stop_loss_distance}")
        return None
        
    shares = int(risk_amount / stop_loss_distance)
    
    if shares <= 0:
        logger.warning(f"Position size too small for {ticker}: {shares} shares")
        return None
    
    # Check if we can afford it (with cash buffer)
    total_cost = shares * entry_price
    max_allowed_cost = available_cash * (1 - DEFAULT_CASH_BUFFER)
    
    if total_cost > max_allowed_cost:
        logger.warning(f"Insufficient funds for {ticker}: need €{total_cost:,.2f}, have €{max_allowed_cost:,.2f}")
        return None
    
    # Calculate 2-for-1 targets
    targets = calculate_2for1_targets(entry_price, atr)
    
    return {
        'action': 'BUY',
        'ticker': ticker,
        'shares': shares,
        'price': entry_price,
        'reason': 'STRATEGY_SIGNAL',
        'priority': 5,
        'risk_amount': risk_amount,
        'total_cost': total_cost,
        'targets': targets
    }


def calculate_2for1_targets(entry_price: float, atr: float) -> Dict[str, float]:
    """
    Calculate stop loss and profit targets for 2-for-1 strategy.
    
    2-for-1 strategy setup:
    - Stop loss: entry_price - (2 * ATR) 
    - Risk per share: entry_price - stop_loss
    - First target: entry_price + (2 * risk_per_share)  [sell 50%]
    - Breakeven: entry_price  [stop for remaining 50% after first target]
    
    Args:
        entry_price: Entry price for the position
        atr: Average True Range for volatility measure
        
    Returns:
        Dict with stop_loss, first_target, breakeven, risk_per_share
    """
    stop_loss = entry_price - (DEFAULT_ATR_MULTIPLIER * atr)
    risk_per_share = entry_price - stop_loss
    first_target = entry_price + (DEFAULT_PROFIT_RATIO * risk_per_share)
    
    return {
        'stop_loss': round(stop_loss, 4),
        'first_target': round(first_target, 4),
        'breakeven': round(entry_price, 4),
        'risk_per_share': round(risk_per_share, 4)
    }



def validate_signal_format(signal: Dict) -> bool:
    """
    Validate that a signal has required fields and valid values.
    
    Required fields: action, ticker, price, atr
    Valid actions: HOLD, BUY, SELL
    
    Args:
        signal: Signal dict to validate
        
    Returns:
        True if valid, False otherwise
    """
    required_fields = ['action', 'ticker', 'price', 'atr']
    
    # Check required fields exist
    for field in required_fields:
        if field not in signal:
            logger.error(f"Missing required field '{field}' in signal: {signal}")
            return False
    
    # Check action is valid
    if signal['action'] not in ['HOLD', 'BUY', 'SELL']:
        logger.error(f"Invalid action '{signal['action']}' in signal: {signal}")
        return False
    
    # Check numeric fields are positive
    if signal['price'] <= 0 or signal['atr'] <= 0:
        logger.error(f"Price and ATR must be positive in signal: {signal}")
        return False
    
    return True


