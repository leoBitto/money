# scripts/risk_manager.py
"""
Risk Manager minimale e deterministico.

CONTRATTO:
- Caller deve passare `df` già FILTRATO fino a `date` (incluso).
- Strategie leggono i loro iperparametri da `config`.
- Output: dict_enriched con chiavi "BUY","SELL","HOLD" contenente SOLO
  le informazioni utili a portfolio.execute_trades(...).

Firma principale:
    generate_signals(strategy_fn, df, date, portfolio) -> Dict[str, Dict[str, Any]]
"""

import logging
from typing import Callable, Dict, Any
import pandas as pd

from . import config

logger = logging.getLogger(__name__)


# -------------------------
# Helper: ATR (usa solo il df fornito)
# -------------------------
def _calculate_atr_from_df(df_ticker: pd.DataFrame, period: int) -> float:
    """
    Calcola ATR usando le righe fornite in df_ticker (assunte fino alla data di analisi).
    Restituisce 0.0 se non ci sono abbastanza dati.
    """
    if df_ticker is None or len(df_ticker) < 2:
        return 0.0

    # Assumo che df_ticker sia ordinato per date asc
    df = df_ticker.copy()
    df["prev_close"] = df["close"].shift(1)
    df["tr1"] = df["high"] - df["low"]
    df["tr2"] = (df["high"] - df["prev_close"]).abs()
    df["tr3"] = (df["low"] - df["prev_close"]).abs()
    df["true_range"] = df[["tr1", "tr2", "tr3"]].max(axis=1)

    # Rolling mean su 'true_range' e prendo l'ultimo valore
    if len(df["true_range"].dropna()) < 1:
        return 0.0

    # Se non ci sono abbastanza righe per il periodo, uso la media disponibile sulle ultime N
    atr_series = df["true_range"].rolling(window=period, min_periods=1).mean()
    atr = atr_series.iloc[-1]
    return float(atr) if pd.notna(atr) else 0.0


# -------------------------
# Helper: genera segnali grezzi (usa la strategy_fn)
# -------------------------
def _generate_signals_df(strategy_fn: Callable, df: pd.DataFrame) -> pd.DataFrame:
    """
    Applica la strategy_fn a ogni ticker del df (che DEVE essere troncato fino a date)
    e restituisce DataFrame con colonne ['ticker','signal'] dove signal è 'BUY'/'SELL'/'HOLD'.
    La strategy_fn deve restituire un DataFrame con colonna 'signal' (1/-1/0).
    """
    results = []
    available_tickers = df["ticker"].unique()

    for ticker in available_tickers:
        df_t = df[df["ticker"] == ticker].copy()
        if df_t.empty:
            results.append({"ticker": ticker, "signal": "HOLD"})
            continue

        df_t = df_t.sort_values("date").reset_index(drop=True)

        try:
            out = strategy_fn(df_t)  # la strategy legge i suoi parametri da config
            series = out["signal"].dropna()
            signal_num = int(series.iloc[-1]) if not series.empty else 0
        except Exception as e:
            logger.warning(f"Strategy error for {ticker}: {e}")
            signal_num = 0

        # map numeric -> label (config.SIGNAL_MAP expected)
        signal_label = config.SIGNAL_MAP.get(signal_num, "HOLD")
        results.append({"ticker": ticker, "signal": signal_label})

    return pd.DataFrame(results)


# -------------------------
# Main API
# -------------------------
def generate_signals(
    strategy_fn: Callable,
    df: pd.DataFrame,
    date: str,
    portfolio
) -> Dict[str, Dict[str, Any]]:
    """
    Genera segnali arricchiti (BUY/SELL/HOLD) utilizzando i dati già passati (df).
    IMPORTANT: `df` DEVE essere troncato fino a `date` (incluso). Se non lo è,
    la funzione solleverà ValueError per evitare look-ahead silenziosi.

    Parametri
    ---------
    strategy_fn : Callable
        Funzione strategia che ritorna un df con colonna 'signal'.
    df : pd.DataFrame
        Universo di dati (multi-ticker) PRE-FILTRATO fino a 'date'.
        Colonne richieste: ['date','ticker','open','high','low','close','volume'].
    date : str (YYYY-MM-DD)
        Data di analisi (il caller deve aver troncato df fino a questa data).
    portfolio :
        Oggetto portfolio (usato per leggere posizioni, cash, total_value ecc.)

    Ritorno
    -------
    dict_enriched : {"BUY": {...}, "SELL": {...}, "HOLD": {...}}
        Dove BUY[ticker] = {"size": int, "price": float, "stop": float, "risk": float}
              SELL[ticker] = {"quantity": int, "price": float, "reason": "STRATEGY SELL"}
              HOLD[ticker] = {"reason": "KEEP"}  (solo se esiste posizione)
    """
    # Sanity check: df deve essere troncato fino a 'date'
    try:
        max_date_in_df = pd.to_datetime(df["date"].max())
        req_date = pd.to_datetime(date)
        if max_date_in_df > req_date:
            raise ValueError(
                "Il DataFrame fornito contiene date successive a 'date'. "
                "Il caller deve passare df troncato fino a 'date'."
            )
    except KeyError:
        raise ValueError("Il df passato non contiene la colonna 'date' richiesta.")

    # segnali grezzi
    raw = _generate_signals_df(strategy_fn, df)

    # container risultato
    dict_enriched: Dict[str, Dict[str, Any]] = {"BUY": {}, "SELL": {}, "HOLD": {}}

    # Stato temporaneo iniziale (solo una volta)
    temp_positions_count = portfolio.get_positions_count()
    temp_available_cash = portfolio.get_available_cash()
    

    # Parametri da config
    max_positions = getattr(config, "DEFAULT_MAX_POSITIONS", 10)
    risk_pct = getattr(config, "DEFAULT_RISK_PCT_PER_TRADE", 0.02)
    atr_multiplier = getattr(config, "DEFAULT_ATR_MULTIPLIER", 2.0)
    atr_period = getattr(config, "DEFAULT_ATR_PERIOD", 14)

    # ciclo ticker per ticker
    for _, row in raw.iterrows():
        ticker = row["ticker"]
        signal = row["signal"].upper()

        # prepara df specifico del ticker (già troncato fino a date)
        df_ticker = df[df["ticker"] == ticker].sort_values("date").reset_index(drop=True)
        if df_ticker.empty:
            continue

        # ultimo prezzo di riferimento (close dell'ultima riga)
        try:
            price = float(df_ticker["close"].iloc[-1])
        except Exception:
            # non posso operare senza prezzo valido
            continue

        # -----------------------
        # HOLD
        # -----------------------
        if signal == "HOLD":
            pos = portfolio.get_position(ticker)
            if pos is not None:
                dict_enriched["HOLD"][ticker] = {"reason": "KEEP"}
            # nessuna modifica a temp_positions_count / temp_available_cash
            continue

        # -----------------------
        # SELL
        # -----------------------
        if signal == "SELL":
            pos = portfolio.get_position(ticker)
            if pos is None:
                # niente da fare, non scriviamo rumore
                continue

            # prezzo di riferimento è quello dal df_ticker
            dict_enriched["SELL"][ticker] = {
                "reason": "STRATEGY SELL",
                "quantity": pos.shares,
                "price": price
            }
            # aggiorno stato temporaneo come se la vendita avvenisse
            temp_positions_count = max(0, temp_positions_count - 1)
            temp_available_cash += pos.shares * price
            continue

        # -----------------------
        # BUY
        # -----------------------
        if signal == "BUY":
            # rispetto a prima: USO temp_* per decidere (non il portfolio reale)
            if temp_positions_count >= max_positions:
                # skip silently
                continue

            # risk amount calcolato su temp_available_cash 
            risk_amount = temp_available_cash * risk_pct

            # calcolo ATR sul df_ticker (uso solo i dati già presenti)
            atr = _calculate_atr_from_df(df_ticker, atr_period)
            if atr <= 0:
                # non posso size-are senza ATR valido
                continue

            risk_distance = atr * atr_multiplier
            if risk_distance <= 0:
                continue

            position_size = int(risk_amount / risk_distance)
            if position_size < 1:
                continue

            cost = position_size * price
            if cost > temp_available_cash:
                # non abbastanza cash secondo lo stato temporaneo -> skip
                continue

            stop = price - risk_distance

            dict_enriched["BUY"][ticker] = {
                "size": position_size,
                "price": price,
                "stop": stop,
                "risk": risk_amount
            }

            # Aggiorno stato temporaneo (come se l'operazione venisse eseguita)
            temp_positions_count += 1
            temp_available_cash -= cost

            continue

    return dict_enriched
