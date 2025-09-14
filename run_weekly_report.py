# run_weekly_report.py - Versione Finale
"""
Entry Point: Report Settimanale Portfolio
=========================================

Workflow semplice e automatico:
1. Scopre automaticamente tutte le strategie dal modulo strategies
2. Genera segnali per ogni strategia (parametri da config)
3. Apre Google Sheet WEEKLY_REPORTS_SHEET_ID
4. Cancella tutti i fogli esistenti
5. Crea N fogli strategia + 1 foglio portfolio snapshots (lun-ven)
6. Fine!

Eseguito ogni venerdì.
"""

import logging
import os
import sys
import inspect
from datetime import datetime, timedelta
import pandas as pd

# Setup logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/run_weekly_report.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def main():
    """Entry point per generazione report settimanale."""
    start_time = datetime.now()
    today = start_time.strftime("%Y-%m-%d")
    
    logger.info("=" * 60)
    logger.info("🚀 AVVIO REPORT SETTIMANALE")
    logger.info("=" * 60)
    logger.info(f"Data: {today}")
    
    try:
        from scripts import database, portfolio, strategies, risk_manager, google_services
        from scripts import config
        
        # 1. SCOPRI STRATEGIE AUTOMATICAMENTE
        strategy_functions = _discover_strategy_functions()
        logger.info(f"🎯 Strategie scoperte: {list(strategy_functions.keys())}")
        
        # 2. CARICA PORTFOLIO DEMO
        logger.info("📊 Caricamento portfolio 'demo'...")
        pf = portfolio.Portfolio("demo", today)
        logger.info(f"Portfolio: valore=€{pf.get_total_value():,.2f}, cash=€{pf.get_cash_balance():,.2f}")
        
        # 3. CARICA DATI UNIVERSE (ultimi 60 giorni per sicurezza)
        days_ago = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
        logger.info(f"📈 Caricamento dati universe dal {days_ago}...")
        df = database.get_universe_data(start_date=days_ago, end_date=today)
        logger.info(f"Dati: {len(df)} righe, {df['ticker'].nunique()} ticker")
        
        # 4. GENERA SEGNALI PER OGNI STRATEGIA
        all_signals = {}
        for strategy_name, strategy_fn in strategy_functions.items():
            logger.info(f"🎯 Generazione segnali: {strategy_name}")
            
            try:
                signals = risk_manager.generate_signals(strategy_fn, df, today, pf)
                signals_df = _convert_signals_to_dataframe(signals, strategy_name)
                all_signals[strategy_name] = signals_df
                
                buy_count = len(signals.get("BUY", {}))
                sell_count = len(signals.get("SELL", {}))
                hold_count = len(signals.get("HOLD", {}))
                logger.info(f"Segnali {strategy_name}: BUY={buy_count}, SELL={sell_count}, HOLD={hold_count}")
                
            except Exception as e:
                logger.error(f"Errore strategia {strategy_name}: {e}")
                # Crea DataFrame vuoto per non rompere il report
                all_signals[strategy_name] = pd.DataFrame()
        
        # 5. GENERA PORTFOLIO SNAPSHOTS (lun-ven)
        logger.info("📸 Caricamento portfolio snapshots settimana...")
        portfolio_df = _get_portfolio_snapshots_week(portfolio_name, today)
        
        # 6. SCRIVI GOOGLE SHEET
        logger.info("📝 Scrittura Google Sheet...")
        sheet_url = _write_to_google_sheet(all_signals, portfolio_df)
        
        # SUCCESS
        duration = datetime.now() - start_time
        logger.info("=" * 60)
        logger.info("✅ REPORT GENERATO CON SUCCESSO!")
        logger.info("=" * 60)
        logger.info(f"Strategie processate: {len(all_signals)}")
        logger.info(f"Portfolio snapshots: {len(portfolio_df)} giorni")
        logger.info(f"Durata: {duration.total_seconds():.1f} secondi")
        logger.info(f"Google Sheet: {sheet_url}")
        logger.info("📊 REPORT PRONTO PER REVIEW!")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.exception(f"❌ Errore critico: {e}")
        raise


def _discover_strategy_functions():
    """Scopre automaticamente tutte le funzioni strategia dal modulo strategies."""
    from scripts import strategies
    
    strategy_functions = {}
    
    # Scandisce tutti gli attributi del modulo strategies
    for name in dir(strategies):
        obj = getattr(strategies, name)
        
        # Controlla se è una funzione (non classe, non built-in, non privata)
        if (inspect.isfunction(obj) and 
            not name.startswith('_') and 
            obj.__module__ == strategies.__name__):
            strategy_functions[name] = obj
    
    return strategy_functions


def _convert_signals_to_dataframe(signals: dict, strategy_name: str) -> pd.DataFrame:
    """Converte dict segnali in DataFrame per Google Sheets."""
    rows = []
    
    # BUY signals
    for ticker, data in signals.get("BUY", {}).items():
        rows.append({
            "Ticker": ticker,
            "Signal": "BUY",
            "Strategy": strategy_name,
            "Size": data.get("size", 0),
            "Price": data.get("price", 0),
            "Stop_Loss": data.get("stop", 0),
            "Risk_Amount": data.get("risk", 0),
            "Notes": f"Size: {data.get('size', 0)} shares at €{data.get('price', 0):.2f}"
        })
    
    # SELL signals
    for ticker, data in signals.get("SELL", {}).items():
        rows.append({
            "Ticker": ticker,
            "Signal": "SELL",
            "Strategy": strategy_name,
            "Size": data.get("quantity", 0),
            "Price": data.get("price", 0),
            "Stop_Loss": "",
            "Risk_Amount": "",
            "Notes": data.get("reason", "Strategy sell")
        })
    
    # HOLD signals
    for ticker, data in signals.get("HOLD", {}).items():
        rows.append({
            "Ticker": ticker,
            "Signal": "HOLD",
            "Strategy": strategy_name,
            "Size": "",
            "Price": "",
            "Stop_Loss": "",
            "Risk_Amount": "",
            "Notes": data.get("reason", "Keep position")
        })
    
    if not rows:
        # Se non ci sono segnali, crea DataFrame con intestazioni vuote
        return pd.DataFrame(columns=["Ticker", "Signal", "Strategy", "Size", "Price", 
                                   "Stop_Loss", "Risk_Amount", "Notes"])
    
    return pd.DataFrame(rows)


def _get_portfolio_snapshots_week(portfolio_name: str, today_str: str) -> pd.DataFrame:
    """Recupera snapshots portfolio da lunedì a venerdì (today-5 giorni lavorativi)."""
    from scripts import database
    
    # Calcola lunedì della settimana corrente (oggi è venerdì)
    today = datetime.strptime(today_str, "%Y-%m-%d")
    monday = today - timedelta(days=4)  # Venerdì - 4 giorni = Lunedì
    
    start_date = monday.strftime("%Y-%m-%d")
    end_date = today_str
    
    logger.info(f"Caricamento snapshots da {start_date} a {end_date}")
    
    query = """
        SELECT date, total_value, cash_balance, positions_count,
               total_return_pct, max_drawdown_pct, volatility_pct, sharpe_ratio, win_rate_pct
        FROM portfolio_snapshots
        WHERE portfolio_name = %s AND date BETWEEN %s AND %s
        ORDER BY date
    """
    
    try:
        rows, columns = database.execute_query(query, (portfolio_name, start_date, end_date))
        df = pd.DataFrame(rows, columns=columns)
        
        # Converti date in stringhe per Google Sheets
        if not df.empty and 'date' in df.columns:
            df['date'] = df['date'].astype(str)
        
        return df
        
    except Exception as e:
        logger.error(f"Errore caricamento snapshots: {e}")
        # Ritorna DataFrame vuoto con colonne corrette
        return pd.DataFrame(columns=["date", "total_value", "cash_balance", "positions_count",
                                   "total_return_pct", "max_drawdown_pct", "volatility_pct", 
                                   "sharpe_ratio", "win_rate_pct"])


def _write_to_google_sheet(all_signals: dict, portfolio_df: pd.DataFrame) -> str:
    """Scrive tutti i dati nel Google Sheet configurato."""
    from scripts import google_services, config
    
    logger.info("Apertura Google Sheet...")
    client = google_services.get_gsheet_client()
    
    # Apri sheet configurato
    spreadsheet = client.open_by_key(config.WEEKLY_REPORTS_SHEET_ID)
    logger.info(f"Aperto sheet: {spreadsheet.title}")
    
    # CANCELLA TUTTI I FOGLI ESISTENTI
    worksheets = spreadsheet.worksheets()
    for ws in worksheets:
        try:
            spreadsheet.del_worksheet(ws)
            logger.info(f"Cancellato foglio: {ws.title}")
        except Exception as e:
            logger.warning(f"Errore cancellando foglio {ws.title}: {e}")
    
    # CREA FOGLIO PORTFOLIO SNAPSHOTS
    logger.info("Creazione foglio Portfolio_Snapshots...")
    portfolio_ws = spreadsheet.add_worksheet(title="Portfolio_Snapshots", rows=50, cols=15)
    
    if not portfolio_df.empty:
        # Scrivi intestazioni + dati
        data_to_write = [portfolio_df.columns.tolist()] + portfolio_df.values.tolist()
        portfolio_ws.update(data_to_write)
        logger.info(f"Scritti {len(portfolio_df)} snapshots portfolio")
    else:
        portfolio_ws.update([["Nessun dato disponibile"]])
        logger.warning("Nessun snapshot portfolio disponibile")
    
    # CREA FOGLIO PER OGNI STRATEGIA
    for strategy_name, signals_df in all_signals.items():
        logger.info(f"Creazione foglio: {strategy_name}")
        
        # Crea worksheet
        ws = spreadsheet.add_worksheet(title=strategy_name, rows=100, cols=10)
        
        if not signals_df.empty:
            # Scrivi intestazioni + dati
            data_to_write = [signals_df.columns.tolist()] + signals_df.values.tolist()
            ws.update(data_to_write)
            logger.info(f"Scritti {len(signals_df)} segnali per {strategy_name}")
        else:
            ws.update([["Nessun segnale generato"]])
            logger.warning(f"Nessun segnale per strategia {strategy_name}")
    
    logger.info(f"✅ Google Sheet aggiornato: {len(all_signals)} strategie + 1 portfolio")
    return spreadsheet.url


if __name__ == "__main__":
    main()