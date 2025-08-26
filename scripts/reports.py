# scripts/reports.py
"""
Modulo: reports
===============

Generazione di report settimanali dei segnali di trading su Google Sheets.

Config utilizzati (da scripts/config.py):
- WEEKLY_REPORTS_FOLDER_ID: cartella su Drive (non usata direttamente, ma disponibile)
- TEST_SHEET_ID: ID del foglio Google Sheets usato per i test
- DEFAULT_STRATEGY_PARAMS: parametri di default per ciascuna strategia
- SIGNAL_MAP: mapping numerico → stringa ("BUY","HOLD","SELL")

Funzionalità principali:
------------------------
- generate_weekly_report(): genera un Google Sheet con segnali e summary
"""

from datetime import datetime
import inspect
import pandas as pd
from gspread_dataframe import set_with_dataframe

from . import config
from .google_services import get_gsheet_client
from .signals import generate_signals_df
from .trading import strategies
from .database import get_universe_data, get_available_tickers


# ================================
# Internal helpers
# ================================

def _get_strategy_functions(strategies_module):
    """
    Recupera tutte le funzioni strategia da un modulo.

    Args:
        strategies_module: Modulo contenente le strategie

    Returns:
        Lista di tuple (nome_strategia, funzione_strategia)
    """
    strategy_functions = []
    for name, func in inspect.getmembers(strategies_module, inspect.isfunction):
        sig = inspect.signature(func)
        if "df" in sig.parameters:  # euristica: le strategie prendono df come input
            strategy_functions.append((name, func))
    return strategy_functions


def _calculate_signal_distribution(df_signals: pd.DataFrame) -> dict:
    """Conta i segnali BUY/HOLD/SELL in un DataFrame di segnali."""
    return df_signals["signal"].value_counts().to_dict()


def _create_signals_summary(all_signals: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Crea un riassunto delle distribuzioni dei segnali per tutte le strategie.

    Args:
        all_signals: dict {nome_strategia: DataFrame segnali}

    Returns:
        DataFrame con righe = strategie, colonne = BUY/HOLD/SELL
    """
    summary = {}
    for strategy_name, df in all_signals.items():
        summary[strategy_name] = _calculate_signal_distribution(df)
    return pd.DataFrame(summary).fillna(0).astype(int).T


# ================================
# Main function
# ================================

def generate_weekly_report():
    """
    Genera il report settimanale con tutti i segnali delle strategie
    e aggiorna i fogli Google Sheets.
    """
    print("📈 Inizio generazione report settimanale...")
    today = datetime.today().strftime("%Y-%m-%d")

    # Setup client Google Sheets
    try:
        client = get_gsheet_client()
        spreadsheet = client.open_by_key(config.TEST_SHEET_ID)
        print("✅ Foglio Google Sheets aperto")
    except Exception as e:
        print(f"❌ Errore apertura foglio: {e}")
        return

    # Recupera strategie disponibili
    strategy_functions = _get_strategy_functions(strategies)
    print(f"🔍 Trovate {len(strategy_functions)} strategie: {[n for n, _ in strategy_functions]}")
    if not strategy_functions:
        print("❌ Nessuna strategia trovata!")
        return

    # Recupera tickers dal DB
    tickers = get_available_tickers()
    if not tickers:
        print("❌ Nessun ticker disponibile nel database")
        return

    # Recupera dati storici fino a oggi
    hist = get_universe_data(end_date=today, tickers=tickers)
    if hist.empty:
        print(f"❌ Nessun dato disponibile nel database fino a {today}")
        return

    all_signals = {}
    metadata_row = {"Date": today}

    # --- 1. Genera segnali per ogni strategia ---
    for strategy_name, strategy_fn in strategy_functions:
        print(f"🔄 Processando strategia: {strategy_name}")

        try:
            params = config.DEFAULT_STRATEGY_PARAMS.get(strategy_name, {})
            df_signals = generate_signals_df(strategy_fn, hist, **params)

            if df_signals.empty:
                print(f"⚠️ Nessun segnale generato per {strategy_name}")
                continue

            all_signals[strategy_name] = df_signals

            # Aggiorna metadata
            distribution = _calculate_signal_distribution(df_signals)
            metadata_row[f"{strategy_name}_BUY"] = distribution.get("BUY", 0)
            metadata_row[f"{strategy_name}_HOLD"] = distribution.get("HOLD", 0)
            metadata_row[f"{strategy_name}_SELL"] = distribution.get("SELL", 0)

            print(f"✅ {strategy_name}: {len(df_signals)} segnali generati")

        except Exception as e:
            print(f"❌ Errore in strategia {strategy_name}: {e}")
            continue

    if not all_signals:
        print("❌ Nessun segnale generato da nessuna strategia!")
        return

    # --- 2. Scrivi fogli per ogni strategia ---
    for strategy_name, df_signals in all_signals.items():
        try:
            try:
                worksheet = spreadsheet.worksheet(strategy_name)
                worksheet.clear()
                print(f"🔄 Aggiornamento foglio esistente: {strategy_name}")
            except:
                worksheet = spreadsheet.add_worksheet(
                    title=strategy_name,
                    rows=str(len(df_signals) + 10),
                    cols=str(len(df_signals.columns) + 2),
                )
                print(f"📄 Creato nuovo foglio: {strategy_name}")

            set_with_dataframe(worksheet, df_signals)
            print(f"✅ Foglio '{strategy_name}' aggiornato con {len(df_signals)} segnali")

        except Exception as e:
            print(f"❌ Errore scrittura foglio {strategy_name}: {e}")

    # --- 3. Summary ---
    try:
        summary_df = _create_signals_summary(all_signals)
        try:
            summary_ws = spreadsheet.worksheet("Summary")
            summary_ws.clear()
        except:
            summary_ws = spreadsheet.add_worksheet(
                title="Summary",
                rows=str(len(summary_df) + 5),
                cols=str(len(summary_df.columns) + 2),
            )
        set_with_dataframe(summary_ws, summary_df)
        print("✅ Foglio 'Summary' creato/aggiornato")
    except Exception as e:
        print(f"❌ Errore creazione summary: {e}")

    # --- 4. Metadata ---
    try:
        try:
            meta_ws = spreadsheet.worksheet("Metadata")
        except:
            meta_ws = spreadsheet.add_worksheet(title="Metadata", rows="100", cols="20")
            headers = list(metadata_row.keys())
            meta_ws.append_row(headers)
            print("📄 Creato foglio Metadata")

        existing_headers = meta_ws.row_values(1)
        new_headers = list(metadata_row.keys())
        if existing_headers != new_headers:
            meta_ws.clear()
            meta_ws.append_row(new_headers)
            print("🔄 Aggiornate intestazioni Metadata")

        row_values = [metadata_row.get(h, "") for h in new_headers]
        meta_ws.append_row(row_values)
        print(f"✅ Metadata aggiornato con i dati del {today}")

    except Exception as e:
        print(f"❌ Errore aggiornamento metadata: {e}")

    print("🎉 Report settimanale generato con successo!")
    print("📊 Statistiche finali:")
    for strategy_name in all_signals.keys():
        distribution = _calculate_signal_distribution(all_signals[strategy_name])
        total = sum(distribution.values())
        print(
            f"   • {strategy_name}: "
            f"{distribution.get('BUY', 0)} BUY, "
            f"{distribution.get('HOLD', 0)} HOLD, "
            f"{distribution.get('SELL', 0)} SELL "
            f"(tot: {total})"
        )


