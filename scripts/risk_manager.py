# scripts/risk_manager.py
"""
Modulo: risk_manager (Refactored + Signal Generation)
=====================================================

Sistema completo per generazione segnali + gestione rischio.

RESPONSABILITÀ:
1. Generare segnali trading dalle strategie
2. Enrichire segnali con price/ATR da database  
3. Validare ordini BUY contro limiti di rischio
4. Calcolare position sizing basato su ATR e % rischio
5. Eseguire controlli pre-trade

FLUSSO OPERATIVO:
signals -> enrich_with_market_data -> validate_orders -> execute_orders

USO TIPICO:
>>> from scripts.risk_manager import RiskManager
>>> 
>>> rm = RiskManager("demo", "2025-01-15")  # Supporta backtesting
>>> signals = rm.generate_signals("moving_average_crossover")
>>> approved_orders = rm.validate_signals(signals)
>>> # Esegui ordini approvati...
"""

import pandas as pd
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta

from . import config
from .portfolio import Portfolio, Position
from .database import execute_query, get_universe_data
from .signals import generate_signals_df
from .strategies import moving_average_crossover, rsi_strategy, breakout_strategy

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Gestore completo segnali + rischio per un portfolio.
    
    Combina:
    - Generazione segnali dalle strategie
    - Enrichment con dati di mercato  
    - Validazione contro limiti di rischio
    - Position sizing automatico
    
    Attributes:
        portfolio (Portfolio): Portfolio da gestire
        date (str): Data per analisi (supporta backtesting)
        max_risk_pct (float): Rischio massimo % per trade
        max_positions (int): Numero massimo posizioni
    """
    
    def __init__(self, 
                 portfolio_name: str,
                 date: Optional[str] = None,
                 max_risk_pct: float = config.DEFAULT_RISK_PCT_PER_TRADE,
                 max_positions: int = config.DEFAULT_MAX_POSITIONS):
        """
        Inizializza risk manager con portfolio esistente o nuovo.
        
        Args:
            portfolio_name: Nome del portfolio
            date: Data per analisi (default: oggi, supporta backtesting)
            max_risk_pct: Rischio massimo % per trade
            max_positions: Numero massimo posizioni
        """
        self.date = date or datetime.now().strftime('%Y-%m-%d')
        self.max_risk_pct = max_risk_pct
        self.max_positions = max_positions
        
        # Carica o crea portfolio per la data specifica
        self.portfolio = Portfolio.get_or_create(portfolio_name, self.date)
        
        logger.info(f"RiskManager inizializzato:")
        logger.info(f"  Portfolio: {self.portfolio.name} @ {self.date}")
        logger.info(f"  Cash: €{self.portfolio.get_cash_balance():,.2f}")
        logger.info(f"  Posizioni: {self.portfolio.get_positions_count()}/{max_positions}")


    # ================================
    # 1. GENERAZIONE SEGNALI
    # ================================
    
   def generate_signals(
        self,
        strategy_fn: callable,
        lookback_days: int = 30,
        **strategy_params
    ) -> pd.DataFrame:
        """
        Genera segnali usando una strategia specifica.

        Args:
            strategy_fn: funzione strategia (es: rsi_strategy, moving_average_crossover)
            lookback_days: Giorni di dati storici per calcolo
            **strategy_params: Parametri specifici strategia

        Returns:
            DataFrame con columns: ticker, signal, price, atr, volume
        """
        strategy_name = strategy_fn.__name__

        # Se nessun parametro passato, usa defaults da config
        if not strategy_params:
            strategy_params = config.DEFAULT_STRATEGY_PARAMS.get(strategy_name, {})

        logger.info(f"Generando segnali con strategia '{strategy_name}' per {self.date}")
        logger.info(f"  Parametri: {strategy_params}")

        # Ottieni dati universe per il periodo
        end_date = self.date
        start_date = (
            datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=lookback_days)
        ).strftime("%Y-%m-%d")

        universe_df = get_universe_data(start_date=start_date, end_date=end_date)
        if universe_df.empty:
            logger.warning("Nessun dato universe disponibile per il periodo")
            return pd.DataFrame()

        # Genera segnali base (solo ticker + signal)
        base_signals = generate_signals_df(strategy_fn, universe_df, **strategy_params)

        # Enrichisci con dati di mercato
        enriched_signals = self._enrich_signals_with_market_data(base_signals)

        logger.info(f"Generati {len(enriched_signals)} segnali:")
        for _, row in enriched_signals.iterrows():
            logger.info(
                f"  {row['signal']} {row['ticker']} @ €{row['price']:.2f} (ATR: {row['atr']:.2f})"
            )

        return enriched_signals

    
    def _get_market_data_for_ticker(self, ticker: str) -> Optional[Dict]:
        """
        Ottiene price, ATR, volume per un ticker alla data specifica.
        
        Args:
            ticker: Symbol del titolo
            
        Returns:
            Dict con price, atr, volume o None se dati mancanti
        """
        # Ottieni dati recenti per calcolo ATR (serve almeno 14 giorni)
        lookback_date = (datetime.strptime(self.date, '%Y-%m-%d') - timedelta(days=20)).strftime('%Y-%m-%d')
        
        query = """
            SELECT date, high, low, close, volume
            FROM universe 
            WHERE ticker = %s AND date BETWEEN %s AND %s
            ORDER BY date DESC
            LIMIT 20
        """
        
        rows, cols = execute_query(query, (ticker, lookback_date, self.date))
        if not rows:
            return None
        
        # Converti in DataFrame per calcolo ATR
        df = pd.DataFrame(rows, columns=cols)
        df['date'] = pd.to_datetime(df['date'])
        
        # Prezzo corrente (ultimo close)
        current_price = float(df.iloc[0]['close'])
        current_volume = float(df.iloc[0]['volume']) if df.iloc[0]['volume'] else 0
        
        # Calcola ATR (Average True Range)
        atr = self._calculate_atr(df)
        
        return {
            'price': current_price,
            'atr': atr,
            'volume': current_volume
        }
    
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """
        Calcola Average True Range per un DataFrame con OHLC.
        
        Args:
            df: DataFrame con columns high, low, close
            period: Periodo per media mobile ATR
            
        Returns:
            ATR value
        """
        if len(df) < 2:
            return 0.0
        
        df = df.sort_values('date').copy()
        
        # True Range = max(high-low, high-prev_close, prev_close-low)
        df['prev_close'] = df['close'].shift(1)
        df['tr1'] = df['high'] - df['low']
        df['tr2'] = abs(df['high'] - df['prev_close'])
        df['tr3'] = abs(df['low'] - df['prev_close'])
        df['true_range'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
        
        # ATR = media mobile del True Range
        atr = df['true_range'].tail(min(period, len(df))).mean()
        
        return float(atr) if pd.notna(atr) else 0.0


    # ================================
    # 2. VALIDAZIONE ORDINI
    # ================================
    
    def validate_signals(self, signals_df: pd.DataFrame) -> List[Dict]:
        """
        Valida segnali e genera ordini eseguibili.
        
        Processo:
        1. Filtra solo segnali BUY/SELL (HOLD ignorati)
        2. Priorità SELL per posizioni esistenti
        3. Valida BUY contro limiti rischio
        4. Ritorna ordini approvati
        
        Args:
            signals_df: DataFrame con ticker, signal, price, atr
            
        Returns:
            Lista di ordini validati per esecuzione
        """
        if signals_df.empty:
            logger.info("Nessun segnale da validare")
            return []
        
        validated_orders = []
        
        # PRIORITÀ 1: Gestisci SELL signals per posizioni esistenti
        sell_signals = signals_df[signals_df['signal'] == 'SELL']
        for _, signal in sell_signals.iterrows():
            sell_order = self._validate_sell_signal(signal)
            if sell_order:
                validated_orders.append(sell_order)
        
        # PRIORITÀ 2: Gestisci BUY signals per nuove posizioni
        buy_signals = signals_df[signals_df['signal'] == 'BUY']
        if not buy_signals.empty:
            buy_orders = self._validate_buy_signals_batch(buy_signals)
            validated_orders.extend(buy_orders)
        
        logger.info(f"Validazione completata: {len(validated_orders)} ordini approvati")
        return validated_orders
    
    
    def _validate_sell_signal(self, signal: pd.Series) -> Optional[Dict]:
        """
        Valida un segnale SELL per posizione esistente.
        
        Args:
            signal: Serie con ticker, signal, price
            
        Returns:
            Ordine SELL validato o None
        """
        ticker = signal['ticker']
        current_price = signal['price']
        
        position = self.portfolio.get_position(ticker)
        if not position or position.shares <= 0:
            logger.info(f"SELL signal per {ticker} ignorato: posizione non trovata")
            return None
        
        # Per ora: vendi tutto quando strategia dice SELL
        # TODO: Implementare logica 2-for-1 più sofisticata
        return {
            'action': 'SELL',
            'ticker': ticker,
            'shares': position.shares,
            'price': current_price,
            'reason': 'STRATEGY_SIGNAL',
            'position_value': position.shares * current_price
        }
    
    
    def _validate_buy_signals_batch(self, buy_signals: pd.DataFrame) -> List[Dict]:
        """
        Valida batch di segnali BUY con controlli rischio.
        
        Args:
            buy_signals: DataFrame con ticker, signal, price, atr
            
        Returns:
            Lista ordini BUY approvati
        """
        # Check posizioni disponibili
        current_positions = self.portfolio.get_positions_count()
        available_slots = self.max_positions - current_positions
        
        if available_slots <= 0:
            logger.info(f"Nessuna posizione disponibile ({current_positions}/{self.max_positions})")
            return []
        
        # Filtra ticker già posseduti
        existing_tickers = {ticker for ticker, pos in self.portfolio._positions.items() if pos.shares > 0}
        new_signals = buy_signals[~buy_signals['ticker'].isin(existing_tickers)]
        
        if new_signals.empty:
            logger.info("Tutti i ticker BUY sono già posseduti")
            return []
        
        # Ordina per conservatività (ATR più basso primo)
        ranked_signals = new_signals.sort_values(['atr', 'ticker']).head(available_slots)
        
        # Valida ogni segnale
        validated_orders = []
        
        for _, signal in ranked_signals.iterrows():
            order = self._validate_buy_signal(signal)
            if order and order['approved']:
                validated_orders.append(order)
                # Simula riduzione cash per prossimi ordini
                # (implementazione semplificata)
        
        return validated_orders
    
    
    def _validate_buy_signal(self, signal: pd.Series) -> Optional[Dict]:
        """
        Valida un singolo segnale BUY.
        
        Args:
            signal: Serie con ticker, price, atr
            
        Returns:
            Ordine BUY validato o None
        """
        ticker = signal['ticker']
        entry_price = signal['price']
        atr = signal['atr']
        
        logger.info(f"Validating BUY: {ticker} @ €{entry_price:.2f} (ATR: {atr:.2f})")
        
        # 1. Calcola position sizing
        sizing = self._calculate_position_size(entry_price, atr)
        if not sizing['valid']:
            return {
                'approved': False,
                'ticker': ticker,
                'reason': sizing['reason']
            }
        
        shares = sizing['shares']
        total_cost = sizing['total_cost']
        targets = sizing['targets']
        
        # 2. Check cash disponibile
        available_cash = self.portfolio.get_available_cash()
        if total_cost > available_cash:
            return {
                'approved': False,
                'ticker': ticker,
                'reason': f'Cash insufficiente: serve €{total_cost:,.2f}, disponibile €{available_cash:,.2f}'
            }
        
        # 3. Check concentrazione
        total_value = self.portfolio.get_total_value()
        position_weight = (total_cost / total_value) * 100 if total_value > 0 else 0
        
        if position_weight > config.MAX_SINGLE_POSITION_PCT:
            return {
                'approved': False,
                'ticker': ticker,
                'reason': f'Posizione troppo grande: {position_weight:.1f}% > {config.MAX_SINGLE_POSITION_PCT}%'
            }
        
        # ORDINE APPROVATO
        return {
            'approved': True,
            'action': 'BUY',
            'ticker': ticker,
            'shares': shares,
            'price': entry_price,
            'targets': targets,
            'cost': total_cost,
            'position_weight_pct': position_weight,
            'reason': 'STRATEGY_SIGNAL'
        }
    
    
    def _calculate_position_size(self, entry_price: float, atr: float) -> Dict:
        """
        Calcola position size basata su rischio % del portfolio.
        
        Args:
            entry_price: Prezzo di entrata
            atr: Average True Range
            
        Returns:
            Dict con shares, total_cost, targets, valid, reason
        """
        total_value = self.portfolio.get_total_value()
        if total_value <= 0:
            return {'valid': False, 'reason': 'Portfolio value zero'}
        
        # Risk-based sizing
        risk_amount = total_value * (self.max_risk_pct / 100.0)
        risk_distance = atr * config.DEFAULT_ATR_MULTIPLIER
        
        if risk_distance <= 0:
            return {'valid': False, 'reason': f'ATR troppo basso: {atr}'}
        
        shares = int(risk_amount / risk_distance)
        if shares <= 0:
            return {'valid': False, 'reason': 'Position size troppo piccola'}
        
        total_cost = shares * entry_price
        targets = self._calculate_2for1_targets(entry_price, atr)
        
        return {
            'valid': True,
            'shares': shares,
            'total_cost': total_cost,
            'targets': targets,
            'risk_amount': risk_amount
        }
    
    
    def _calculate_2for1_targets(self, entry_price: float, atr: float) -> Dict:
        """Calcola target per strategia 2-for-1."""
        risk_distance = atr * config.DEFAULT_ATR_MULTIPLIER
        profit_distance = risk_distance * config.DEFAULT_PROFIT_RATIO
        
        return {
            'stop_loss': round(entry_price - risk_distance, 4),
            'first_target': round(entry_price + profit_distance, 4),
            'breakeven': round(entry_price, 4),
            'entry_atr': round(atr, 4)
        }


    # ================================
    # 3. EXECUTION HELPERS
    # ================================
    
    def execute_approved_orders(self, approved_orders: List[Dict]) -> Dict:
        """
        Esegue ordini approvati aggiornando il portfolio.
        
        Args:
            approved_orders: Lista ordini validati
            
        Returns:
            Dict con summary esecuzione
        """
        executed = []
        errors = []
        
        for order in approved_orders:
            try:
                if order['action'] == 'BUY':
                    position = self.portfolio.add_position(
                        ticker=order['ticker'],
                        shares=order['shares'],
                        avg_cost=order['price'],
                        current_price=order['price']
                    )
                    
                    # Imposta target 2-for-1
                    targets = order.get('targets', {})
                    if targets:
                        position.stop_loss = targets.get('stop_loss')
                        position.first_target = targets.get('first_target')
                        position.breakeven = targets.get('breakeven')
                        position.entry_atr = targets.get('entry_atr')
                        position._save_to_db()
                    
                    executed.append(f"BUY {order['shares']} {order['ticker']} @ €{order['price']:.2f}")
                    
                elif order['action'] == 'SELL':
                    # TODO: Implementare vendita posizione
                    # Per ora log dell'operazione
                    executed.append(f"SELL {order['shares']} {order['ticker']} @ €{order['price']:.2f}")
                
            except Exception as e:
                error_msg = f"Errore esecuzione {order['action']} {order['ticker']}: {e}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        return {
            'executed': executed,
            'errors': errors,
            'total_executed': len(executed),
            'total_errors': len(errors)
        }


# ================================
# 4. CONVENIENCE FUNCTIONS
# ================================

def run_full_trading_cycle(portfolio_name: str,
                          strategy_name: str = "moving_average_crossover",
                          date: Optional[str] = None,
                          execute: bool = False,
                          **strategy_params) -> Dict:
    """
    Esegue ciclo completo: genera segnali -> valida -> esegue.
    
    Args:
        portfolio_name: Nome portfolio
        strategy_name: Nome strategia da usare
        date: Data per analisi (supporta backtesting)
        execute: Se True esegue ordini, altrimenti solo simulazione
        **strategy_params: Parametri strategia
        
    Returns:
        Dict con summary completo del ciclo
    """
    logger.info(f"=== TRADING CYCLE START ===")
    logger.info(f"Portfolio: {portfolio_name}, Strategy: {strategy_name}, Date: {date}")
    
    # 1. Setup
    rm = RiskManager(portfolio_name, date)
    
    # 2. Genera segnali
    signals = rm.generate_signals(strategy_name, **strategy_params)
    
    # 3. Valida segnali
    approved_orders = rm.validate_signals(signals)
    
    # 4. Esegui se richiesto
    execution_result = {}
    if execute and approved_orders:
        execution_result = rm.execute_approved_orders(approved_orders)
    
    # 5. Summary
    result = {
        'portfolio_name': portfolio_name,
        'date': rm.date,
        'strategy': strategy_name,
        'signals_generated': len(signals),
        'orders_approved': len(approved_orders),
        'approved_orders': approved_orders,
        'execution_result': execution_result,
        'portfolio_summary': {
            'cash': rm.portfolio.get_cash_balance(),
            'total_value': rm.portfolio.get_total_value(),
            'positions': rm.portfolio.get_positions_count()
        }
    }
    
    logger.info(f"=== TRADING CYCLE END ===")
    logger.info(f"Segnali: {result['signals_generated']}, Ordini: {result['orders_approved']}")
    
    return result


def quick_signal_check(portfolio_name: str,
                      strategy_name: str = "moving_average_crossover",
                      date: Optional[str] = None) -> pd.DataFrame:
    """
    Quick check per vedere segnali senza validazione rischio.
    
    Returns:
        DataFrame con segnali enriched
    """
    rm = RiskManager(portfolio_name, date)
    return rm.generate_signals(strategy_name)