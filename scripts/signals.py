# scripts/signals.py
"""
Modulo: signals
===============

Funzioni per applicare strategie di trading ai dati storici e generare segnali.

Config utilizzati (da scripts/config.py):
- SIGNAL_MAP: mapping dei segnali {-1, 0, 1} → {"SELL", "HOLD", "BUY"}

Funzionalità principali:
------------------------
- generate_signals_df(strategy_fn, df, **strategy_params) -> pd.DataFrame

Casi d'uso:
-----------
>>> from scripts.signals import generate_signals_df
>>> from scripts.trading.strategies import moving_average_crossover
>>> df = get_universe_data(end_date="2025-08-25", tickers=["AAPL"])
>>> signals = generate_signals_df(moving_average_crossover, df, short_window=3, long_window=5)
"""

import pandas as pd
from typing import Callable
from . import config


def generate_signals_df(strategy_fn: Callable, df: pd.DataFrame, **strategy_params) -> pd.DataFrame:
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
