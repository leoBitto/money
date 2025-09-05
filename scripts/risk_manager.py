# risk_manager.py

from .portfolio import Portfolio
from .database import *
from .config import *
from typing import Dict, Any, Callable, Optional, List
from datetime import datetime, timedelta
import pandas as pd
import logging

logger = logging.getLogger(__name__)

def get_signals(strategy_fn: Callable, date, portfolio_name):
    # prendi il portfolio alla data di interesse
    portfolio = Portfolio(portfolio_name, date)
    df_universe = get_universe_data()

    df_signals_raw = _generate_signals_df(strategy_fn, df_universe)

    return _refine_signals(df_signals_raw, portfolio)


def _generate_signals_df(strategy_fn: Callable, df: pd.DataFrame, **strategy_params) -> pd.DataFrame:
    """
    Applica una strategia ai dati e genera segnali.

    Args:
        strategy_fn: funzione strategia (es. moving_average_crossover, rsi_strategy, breakout_strategy)
        df: DataFrame con colonne ['date','ticker','Open','High','Low','Close','Volume']
        **strategy_params: parametri da passare alla strategia

    Returns:
        DataFrame con ['ticker','signal'], dove signal è "BUY","SELL","HOLD"
    """
    results = []

    for ticker in df["ticker"].unique():
        df_ticker = df[df["ticker"] == ticker].copy()
        if df_ticker.empty:
            results.append({"ticker": ticker, "signal": "HOLD"})
            continue

        # Ordina per data
        df_ticker = df_ticker.sort_values("date").reset_index(drop=True)

        try:
            # Applica la strategia → la strategia deve restituire df con colonna 'signal'
            df_with_signals = strategy_fn(df_ticker, **strategy_params)

            # Prendi l’ultimo segnale valido
            valid_signals = df_with_signals["signal"].dropna()
            if not valid_signals.empty:
                signal_num = int(valid_signals.iloc[-1])
            else:
                signal_num = 0

        except Exception as e:
            print(f"Errore nell'applicare la strategia {strategy_fn.__name__} al ticker {ticker}: {e}")
            signal_num = 0

        signal_label = config.SIGNAL_MAP.get(signal_num, "HOLD")
        results.append({"ticker": ticker, "signal": signal_label})

    return pd.DataFrame(results)


def _refine_signals(df_signals, portfolio) -> Dict[str, Dict[str, Any]]:
    """
    Raffina segnali grezzi (BUY, SELL, HOLD) con logica di risk management.

    Parameters
    ----------
    df_signals : pd.DataFrame
        Deve avere colonne ["ticker", "signal"].
    portfolio : Portfolio
        Oggetto che gestisce posizioni e cash.


    Returns
    -------
    dict_enriched : dict
        Dizionario arricchito con decisioni finali.
    """
    max_positions = config.DEFAULT_MAX_POSITIONS
    risk_per_trade = config.DEFAULT_RISK_PCT_PER_TRADE
    atr_factor = config.DEFAULT_ATR_MULTIPLIER

    dict_enriched = {"HOLD": {}, "SELL": {}, "BUY": {}}

    for _, row in df_signals.iterrows():
        ticker, signal = row["ticker"], row["signal"].upper()

        if signal == "HOLD":
            _process_hold(ticker, portfolio, dict_enriched)

        elif signal == "SELL":
            _process_sell(ticker, portfolio, dict_enriched)

        elif signal == "BUY":
            _process_buy(ticker, portfolio, dict_enriched,
                         max_positions=max_positions,
                         risk_per_trade=risk_per_trade,
                         atr_factor=atr_factor)

    return dict_enriched


# ---------- Helper functions ----------

def _process_hold(ticker, portfolio, dict_enriched):
    pos = portfolio.get_position(ticker)
    if pos is None:
        return
    if pos.is_stop_loss_hit():  
        dict_enriched["SELL"][ticker] = {
            "reason": "STOP LOSS",
            "quantity": pos.shares
        }
    else:
        dict_enriched["HOLD"][ticker] = {
            "reason": "KEEP"
        }


def _process_sell(ticker, portfolio, dict_enriched):
    pos = portfolio.get_position(ticker)
    if pos:
        dict_enriched["SELL"][ticker] = {
            "reason": "STRATEGY SELL",
            "quantity": pos.shares
        }

  
def _calculate_atr(portfolio, ticker, period: int = 14) -> float:
    """
    Calcola Average True Range per un DataFrame con OHLC.
    
    Args:
        df: DataFrame con columns high, low, close
        period: Periodo per media mobile ATR
        
    Returns:
        ATR value
    """
    start_date = portfolio.date
    end_date = start_date - timedelta(days=period)

    start_date = start_date.strftime('%Y-%m-%d')
    end_date = end_date.strftime('%Y-%m-%d')

    logger.info(f"start_date : {start_date}")
    logger.info(f"end_date : {end_date}")

    df = get_universe_data(start_date=start_date, end_date=end_date, tickers=ticker)
    logger.info(f"Data for ATR calculation for {ticker}: {df}")
    
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


def _process_buy(ticker, portfolio, dict_enriched, max_positions, risk_per_trade, atr_factor):
    logger.info(f"Processing BUY for ticker {ticker}")

    positions_count = portfolio.get_positions_count()
    logger.info(f"Current positions count: {positions_count} / Max allowed: {max_positions}")
    if positions_count >= max_positions:
        logger.info(f"Max positions reached, skipping BUY for {ticker}")
        return

    available_cash = portfolio.get_available_cash()
    logger.info(f"Available cash: {available_cash}")

    equity = portfolio.get_total_value()
    logger.info(f"Portfolio total value: {equity}")

    risk_amount = equity * risk_per_trade
    logger.info(f"Risk amount ({risk_per_trade*100:.2f}% of total value): {risk_amount}")

    # Calcolo ATR
    atr = _calculate_atr(portfolio, ticker)
    logger.info(f"ATR for {ticker}: {atr}")
    if atr == 0:
        logger.warning(f"ATR is zero for {ticker}, cannot calculate position size")
        return

    risk_distance = atr * atr_factor
    logger.info(f"Risk distance (ATR * factor {atr_factor}): {risk_distance}")
    if risk_distance == 0:
        logger.warning(f"Risk distance is zero for {ticker}, skipping BUY")
        return

    price = database.get_last_close(ticker)
    logger.info(f"Last close price for {ticker}: {price}")

    position_size = risk_amount / risk_distance
    logger.info(f"Calculated position size before cash check: {position_size}")

    # Controllo cash disponibile
    if position_size < 1 or position_size * price > available_cash:
        logger.info(f"Position size too small or exceeds available cash, skipping BUY for {ticker}")
        return

    stop = price - risk_distance
    dict_enriched["BUY"][ticker] = {
        "size": int(position_size),
        "price": price,
        "stop": stop,
        "risk": risk_amount
    }

    logger.info(f"BUY signal prepared for {ticker}: {dict_enriched['BUY'][ticker]}")
