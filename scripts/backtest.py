# scripts/backtest.py
"""
Sistema di Backtesting per Strategie di Trading
===============================================

Questo modulo implementa un sistema di backtesting che simula il processo di trading reale:
- I segnali vengono calcolati il venerdì usando i dati disponibili fino a quel giorno
- Le operazioni vengono eseguite il lunedì successivo ai prezzi di apertura
- Il portfolio viene ribilanciato settimanalmente con equal weight

LIMITAZIONI E DEBOLEZZE DEL SISTEMA:
-----------------------------------
1. EQUAL WEIGHT: Ogni posizione ha lo stesso peso, ignorando volatilità/correlazioni
2. LOOK-AHEAD BIAS: Potenziale uso di dati futuri (da verificare nelle strategie)
3. SURVIVOR BIAS: Testa solo ticker che sono sopravvissuti fino ad oggi
4. MARKET IMPACT: Non considera l'impatto sul prezzo di ordini grandi
5. SLIPPAGE: Assume esecuzione esatta al prezzo di apertura
6. LIQUIDITÀ: Non considera problemi di liquidità o gap di prezzo
7. REGIME CHANGE: Non gestisce cambi di regime di mercato
8. OVERFITTING: Rischio di ottimizzare troppo sui dati storici

LOGICA DI FUNZIONAMENTO:
-----------------------
1. Ogni venerdì: calcola segnali basati sui dati disponibili
2. Ogni lunedì: esegue trade ai prezzi di apertura
3. Portfolio equal-weighted: 1/N del capitale per ogni posizione BUY
4. Stop-loss implicito: SELL elimina completamente la posizione

STRUTTURA DATI RISULTATI:
------------------------
I risultati vengono salvati in formato CSV con le seguenti tabelle:
- portfolio_history.csv: evoluzione del valore del portfolio
- trades_history.csv: storico di tutti i trade eseguiti  
- signals_history.csv: storico dei segnali generati
- backtest_summary.csv: metriche di performance aggregate

Config utilizzati (da scripts/config.py):
- BACKTEST_START_DATE: data di inizio backtest
- BACKTEST_INITIAL_CAPITAL: capitale iniziale
- BACKTEST_COMMISSION: commissioni per trade
- DEFAULT_STRATEGY_PARAMS: parametri delle strategie
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Callable, Tuple, Optional
import os

from . import config
from .database import get_universe_data
from .signals import generate_signals_df


def get_next_trading_day(date: datetime, target_weekday: int) -> datetime:
    """
    Trova il prossimo giorno della settimana specificato.
    
    Args:
        date (datetime): Data di partenza
        target_weekday (int): Giorno target (0=lunedì, 4=venerdì, etc.)
        
    Returns:
        datetime: Prossima data corrispondente al giorno della settimana
    """
    days_ahead = target_weekday - date.weekday()
    if days_ahead <= 0:  # Il giorno target è già passato questa settimana
        days_ahead += 7
    return date + timedelta(days=days_ahead)


def calculate_portfolio_metrics(portfolio_history: pd.DataFrame, 
                               initial_capital: float) -> Dict[str, float]:
    """
    Calcola le metriche di performance del portfolio.
    
    Args:
        portfolio_history (pd.DataFrame): Storia valori portfolio con colonne 'date', 'total_value'
        initial_capital (float): Capitale iniziale
        
    Returns:
        Dict[str, float]: Dizionario con tutte le metriche calcolate
            - total_return: rendimento totale percentuale
            - annualized_return: rendimento annualizzato percentuale  
            - volatility: volatilità annualizzata percentuale
            - sharpe_ratio: sharpe ratio (assumendo risk-free = 2%)
            - max_drawdown: massimo drawdown percentuale
            - calmar_ratio: rendimento annualizzato / max drawdown
            - days_traded: giorni totali del backtest
    """
    if portfolio_history.empty or len(portfolio_history) < 2:
        return {}
    
    values = portfolio_history['total_value']
    final_value = values.iloc[-1]
    days = len(portfolio_history)
    
    # Rendimenti giornalieri
    returns = values.pct_change().dropna()
    
    # Rendimento totale
    total_return = (final_value / initial_capital - 1) * 100
    
    # Rendimento annualizzato
    years = days / 365.25
    annualized_return = ((final_value / initial_capital) ** (1/years) - 1) * 100 if years > 0 else 0
    
    # Volatilità annualizzata
    volatility = returns.std() * np.sqrt(252) * 100 if len(returns) > 1 else 0
    
    # Sharpe ratio (risk-free rate = 2%)
    excess_return = (annualized_return - 2) / 100
    sharpe_ratio = excess_return / (volatility / 100) if volatility > 0 else 0
    
    # Max drawdown
    running_max = values.expanding().max()
    drawdown = (values - running_max) / running_max * 100
    max_drawdown = drawdown.min()
    
    # Calmar ratio
    calmar_ratio = annualized_return / abs(max_drawdown) if max_drawdown < 0 else 0
    
    return {
        'total_return': total_return,
        'annualized_return': annualized_return, 
        'volatility': volatility,
        'sharpe_ratio': sharpe_ratio,
        'max_drawdown': max_drawdown,
        'calmar_ratio': calmar_ratio,
        'days_traded': days
    }


def calculate_trade_metrics(trades_history: pd.DataFrame) -> Dict[str, float]:
    """
    Calcola le metriche sui trade eseguiti.
    
    Args:
        trades_history (pd.DataFrame): Storia dei trade con colonna 'pnl'
        
    Returns:
        Dict[str, float]: Metriche sui trade
            - num_trades: numero totale di trade
            - profitable_trades: numero di trade profittevoli
            - win_rate: percentuale di trade vincenti
            - avg_profit: profitto medio per trade
            - profit_factor: somma profitti / somma perdite
    """
    if trades_history.empty:
        return {'num_trades': 0, 'profitable_trades': 0, 'win_rate': 0, 
                'avg_profit': 0, 'profit_factor': 0}
    
    # Filtra solo le vendite (che hanno P&L calcolato)
    sell_trades = trades_history[trades_history['action'] == 'SELL'].copy()
    
    if sell_trades.empty:
        return {'num_trades': 0, 'profitable_trades': 0, 'win_rate': 0,
                'avg_profit': 0, 'profit_factor': 0}
    
    num_trades = len(sell_trades)
    profitable = sell_trades[sell_trades['pnl'] > 0]
    profitable_trades = len(profitable)
    win_rate = (profitable_trades / num_trades) * 100
    avg_profit = sell_trades['pnl'].mean()
    
    # Profit factor
    total_profits = sell_trades[sell_trades['pnl'] > 0]['pnl'].sum()
    total_losses = abs(sell_trades[sell_trades['pnl'] < 0]['pnl'].sum())
    profit_factor = total_profits / total_losses if total_losses > 0 else 0
    
    return {
        'num_trades': num_trades,
        'profitable_trades': profitable_trades, 
        'win_rate': win_rate,
        'avg_profit': avg_profit,
        'profit_factor': profit_factor
    }


def execute_weekly_trades(signals_df: pd.DataFrame,
                         prices_df: pd.DataFrame,
                         execution_date: str,
                         current_positions: Dict[str, int],
                         cash: float,
                         total_portfolio_value: float,
                         commission_rate: float) -> Tuple[List[Dict], Dict[str, int], float]:
    """
    Esegue i trade settimanali basati sui segnali.
    
    LOGICA EQUAL WEIGHT:
    - Per ogni segnale BUY: investe 1/N del valore totale del portfolio
    - Per ogni segnale SELL: vende completamente la posizione
    - DEBOLEZZA: Non considera correlazioni, volatilità o momentum dei singoli titoli
    
    Args:
        signals_df (pd.DataFrame): Segnali con colonne 'ticker', 'signal'
        prices_df (pd.DataFrame): Prezzi con colonne 'ticker', 'date', 'Open'
        execution_date (str): Data di esecuzione formato 'YYYY-MM-DD'
        current_positions (Dict[str, int]): Posizioni attuali {ticker: num_shares}
        cash (float): Cash disponibile
        total_portfolio_value (float): Valore totale del portfolio
        commission_rate (float): Tasso di commissione (es. 0.001 = 0.1%)
        
    Returns:
        Tuple[List[Dict], Dict[str, int], float]: (trade_records, nuove_posizioni, nuovo_cash)
    """
    # Filtra prezzi per la data di esecuzione
    execution_prices = prices_df[prices_df['date'] == execution_date]
    if execution_prices.empty:
        return [], current_positions.copy(), cash
    
    price_dict = dict(zip(execution_prices['ticker'], execution_prices['Open']))
    trades = []
    new_positions = current_positions.copy()
    remaining_cash = cash
    
    # Prima fase: SELL (libera cash)
    sell_signals = signals_df[signals_df['signal'] == 'SELL']
    for _, row in sell_signals.iterrows():
        ticker = row['ticker']
        if ticker not in price_dict or ticker not in new_positions:
            continue
            
        shares = new_positions[ticker]
        if shares <= 0:
            continue
            
        price = price_dict[ticker]
        gross_proceeds = shares * price
        net_proceeds = gross_proceeds * (1 - commission_rate)
        
        remaining_cash += net_proceeds
        del new_positions[ticker]
        
        trades.append({
            'date': execution_date,
            'ticker': ticker,
            'action': 'SELL',
            'shares': shares,
            'price': price,
            'gross_amount': gross_proceeds,
            'commission': gross_proceeds * commission_rate,
            'net_amount': net_proceeds,
            'pnl': 0  # Sarà calcolato dopo confrontando con il trade di acquisto
        })
    
    # Seconda fase: BUY (equal weight)
    buy_signals = signals_df[signals_df['signal'] == 'BUY']
    if not buy_signals.empty:
        # Calcola valore target per ogni posizione (equal weight)
        num_positions = len(buy_signals)
        position_value = total_portfolio_value / num_positions
        
        for _, row in buy_signals.iterrows():
            ticker = row['ticker']
            if ticker not in price_dict or ticker in new_positions:
                continue
                
            price = price_dict[ticker]
            target_shares = int(position_value / price)
            gross_cost = target_shares * price
            total_cost = gross_cost * (1 + commission_rate)
            
            if total_cost <= remaining_cash and target_shares > 0:
                remaining_cash -= total_cost
                new_positions[ticker] = target_shares
                
                trades.append({
                    'date': execution_date,
                    'ticker': ticker,
                    'action': 'BUY',
                    'shares': target_shares,
                    'price': price,
                    'gross_amount': gross_cost,
                    'commission': gross_cost * commission_rate,
                    'net_amount': total_cost,
                    'pnl': 0
                })
    
    return trades, new_positions, remaining_cash


def calculate_trade_pnl(trades_history: List[Dict]) -> List[Dict]:
    """
    Calcola il P&L per ogni trade di vendita abbinandolo al trade di acquisto.
    
    Args:
        trades_history (List[Dict]): Lista di tutti i trade
        
    Returns:
        List[Dict]: Lista di trade con P&L calcolato per le vendite
    """
    trades_with_pnl = []
    buy_trades = {}  # {ticker: ultimo_trade_buy}
    
    for trade in trades_history:
        trade_copy = trade.copy()
        
        if trade['action'] == 'BUY':
            buy_trades[trade['ticker']] = trade
            
        elif trade['action'] == 'SELL':
            ticker = trade['ticker']
            if ticker in buy_trades:
                buy_trade = buy_trades[ticker]
                buy_cost = buy_trade['net_amount']
                sell_proceeds = trade['net_amount']
                trade_copy['pnl'] = sell_proceeds - buy_cost
                del buy_trades[ticker]  # Rimuovi dopo aver calcolato P&L
        
        trades_with_pnl.append(trade_copy)
    
    return trades_with_pnl


def run_backtest(strategy_fn: Callable,
                start_date: str,
                end_date: str,
                tickers: List[str],
                initial_capital: float = None,
                commission_rate: float = None,
                output_dir: str = "backtest_results",
                **strategy_params) -> Dict[str, any]:
    """
    Esegue un backtest completo di una strategia di trading.
    
    PROCESSO:
    1. Ogni venerdì: calcola segnali usando dati fino a quel giorno
    2. Ogni lunedì: esegue trade ai prezzi di apertura
    3. Portfolio equal-weighted: stesso $ amount per ogni posizione BUY
    
    Args:
        strategy_fn (Callable): Funzione strategia da testare
        start_date (str): Data inizio backtest formato 'YYYY-MM-DD'
        end_date (str): Data fine backtest formato 'YYYY-MM-DD' 
        tickers (List[str]): Lista ticker da includere nel test
        initial_capital (float, optional): Capitale iniziale. Default da config
        commission_rate (float, optional): Tasso commissioni. Default da config
        output_dir (str, optional): Directory output files. Default 'backtest_results'
        **strategy_params: Parametri aggiuntivi da passare alla strategia
        
    Returns:
        Dict[str, any]: Dizionario con i risultati del backtest
            - strategy_name: nome strategia
            - start_date, end_date: periodo testato
            - initial_capital, final_capital: capitale iniziale e finale
            - portfolio_metrics: dict con metriche portfolio
            - trade_metrics: dict con metriche trade
            - output_files: lista file CSV generati
    
    Raises:
        ValueError: Se non ci sono dati per il periodo specificato
        Exception: Per errori durante l'esecuzione del backtest
    """
    # Parametri default
    if initial_capital is None:
        initial_capital = config.BACKTEST_INITIAL_CAPITAL
    if commission_rate is None:
        commission_rate = config.BACKTEST_COMMISSION
    
    print(f"🔄 Avvio backtest per strategia: {strategy_fn.__name__}")
    print(f"📅 Periodo: {start_date} → {end_date}")
    print(f"💰 Capitale iniziale: ${initial_capital:,.2f}")
    print(f"📊 Ticker: {len(tickers)} ({', '.join(tickers[:5])}{'...' if len(tickers) > 5 else ''})")
    
    # Carica dati dal database
    df_prices = get_universe_data(start_date=start_date, end_date=end_date, tickers=tickers)
    if df_prices.empty:
        raise ValueError(f"Nessun dato trovato per ticker {tickers} nel periodo {start_date}-{end_date}")
    
    # Inizializza stato portfolio
    cash = initial_capital
    positions = {}  # {ticker: num_shares}
    portfolio_history = []
    trades_history = []
    signals_history = []
    
    # Date di inizio e fine
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    
    # Prima data di calcolo segnali (primo venerdì)
    signal_date = get_next_trading_day(start_dt, 4)  # 4 = venerdì
    week_count = 0
    
    print(f"🔍 Inizio simulazione settimanale...")
    
    while signal_date <= end_dt:
        week_count += 1
        signal_date_str = signal_date.strftime("%Y-%m-%d")
        
        # Data di esecuzione (lunedì successivo)
        execution_date = get_next_trading_day(signal_date, 0)  # 0 = lunedì
        execution_date_str = execution_date.strftime("%Y-%m-%d")
        
        if execution_date > end_dt:
            break
            
        print(f"  Settimana {week_count}: Segnali {signal_date_str} → Esecuzione {execution_date_str}")
        
        try:
            # 1. Calcola segnali usando dati disponibili fino al venerdì
            available_data = df_prices[df_prices['date'] <= signal_date_str]
            if available_data.empty:
                signal_date = get_next_trading_day(signal_date + timedelta(days=1), 4)
                continue
            
            signals_df = generate_signals_df(strategy_fn, available_data, **strategy_params)
            
            # Salva segnali per analisi
            signals_with_date = signals_df.copy()
            signals_with_date['signal_date'] = signal_date_str
            signals_with_date['execution_date'] = execution_date_str
            signals_history.append(signals_with_date)
            
            # 2. Calcola valore portfolio corrente per equal weight
            execution_prices = df_prices[df_prices['date'] == execution_date_str]
            if execution_prices.empty:
                signal_date = get_next_trading_day(signal_date + timedelta(days=1), 4)
                continue
                
            price_dict = dict(zip(execution_prices['ticker'], execution_prices['Open']))
            positions_value = sum(shares * price_dict.get(ticker, 0) 
                                for ticker, shares in positions.items())
            total_portfolio_value = cash + positions_value
            
            # 3. Esegui trade
            weekly_trades, positions, cash = execute_weekly_trades(
                signals_df=signals_df,
                prices_df=df_prices,
                execution_date=execution_date_str,
                current_positions=positions,
                cash=cash,
                total_portfolio_value=total_portfolio_value,
                commission_rate=commission_rate
            )
            
            trades_history.extend(weekly_trades)
            
            # 4. Registra valore portfolio
            new_positions_value = sum(shares * price_dict.get(ticker, 0) 
                                    for ticker, shares in positions.items())
            new_total_value = cash + new_positions_value
            
            portfolio_history.append({
                'date': execution_date_str,
                'cash': cash,
                'positions_value': new_positions_value,
                'total_value': new_total_value,
                'num_positions': len(positions)
            })
            
        except Exception as e:
            print(f"    ⚠️ Errore settimana {signal_date_str}: {e}")
        
        # Prossima settimana
        signal_date = get_next_trading_day(signal_date + timedelta(days=1), 4)
    
    # Calcola P&L sui trade
    trades_history = calculate_trade_pnl(trades_history)
    
    # Converti a DataFrame
    portfolio_df = pd.DataFrame(portfolio_history)
    trades_df = pd.DataFrame(trades_history)
    signals_df = pd.concat(signals_history, ignore_index=True) if signals_history else pd.DataFrame()
    
    # Calcola metriche
    portfolio_metrics = calculate_portfolio_metrics(portfolio_df, initial_capital)
    trade_metrics = calculate_trade_metrics(trades_df)
    
    final_capital = portfolio_df['total_value'].iloc[-1] if not portfolio_df.empty else initial_capital
    
    # Salva risultati
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    strategy_name = strategy_fn.__name__
    
    output_files = []
    
    # Portfolio history
    if not portfolio_df.empty:
        portfolio_file = f"{output_dir}/portfolio_{strategy_name}_{timestamp}.csv"
        portfolio_df.to_csv(portfolio_file, index=False)
        output_files.append(portfolio_file)
    
    # Trades history  
    if not trades_df.empty:
        trades_file = f"{output_dir}/trades_{strategy_name}_{timestamp}.csv"
        trades_df.to_csv(trades_file, index=False)
        output_files.append(trades_file)
    
    # Signals history
    if not signals_df.empty:
        signals_file = f"{output_dir}/signals_{strategy_name}_{timestamp}.csv"
        signals_df.to_csv(signals_file, index=False)
        output_files.append(signals_file)
    
    # Summary
    summary = {
        'strategy_name': strategy_name,
        'start_date': start_date,
        'end_date': end_date,
        'initial_capital': initial_capital,
        'final_capital': final_capital,
        'weeks_processed': week_count,
        **portfolio_metrics,
        **trade_metrics
    }
    
    summary_file = f"{output_dir}/summary_{strategy_name}_{timestamp}.csv"
    pd.DataFrame([summary]).to_csv(summary_file, index=False)
    output_files.append(summary_file)
    
    print(f"✅ Backtest completato: {week_count} settimane processate")
    print(f"💰 Capitale finale: ${final_capital:,.2f}")
    print(f"📈 Rendimento totale: {portfolio_metrics.get('total_return', 0):.2f}%")
    print(f"📁 File salvati: {len(output_files)}")
    
    return {
        'strategy_name': strategy_name,
        'start_date': start_date,
        'end_date': end_date, 
        'initial_capital': initial_capital,
        'final_capital': final_capital,
        'portfolio_metrics': portfolio_metrics,
        'trade_metrics': trade_metrics,
        'output_files': output_files,
        'portfolio_history': portfolio_df,
        'trades_history': trades_df,
        'signals_history': signals_df
    }