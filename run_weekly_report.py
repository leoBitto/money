# run_weekly_report.py - Versione Semplificata
"""
Entry Point: Report Settimanale Portfolio (VERSIONE SEMPLIFICATA)
================================================================

Workflow semplice e diretto:
1. Genera segnali da tutte le strategie disponibili
2. Applica risk management per validare/raffinare i segnali  
3. Apre Google Sheet esistente nel drive
4. Pulisce e scrive N+1 fogli:
   - 1 foglio per strategia con segnali validati
   - 1 foglio con snapshot portfolio della settimana
5. Fine!

Niente classi complesse, solo funzioni dirette.
"""

import logging
import os
import sys
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
    """Entry point per generazione report settimanale semplificato."""
    start_time = datetime.now()
    today = start_time.strftime("%Y-%m-%d")
    
    logger.info("=" * 60)
    logger.info("🚀 AVVIO REPORT SETTIMANALE SEMPLIFICATO")
    logger.info("=" * 60)
    
    try:
        # Import dopo logging setup
        from scripts import database, portfolio, strategies, risk_manager, google_services
        from scripts import config
        
        # 1. CARICA PORTFOLIO
        logger.info("📊 Caricamento portfolio 'demo'...")
        pf = portfolio.Portfolio("demo", today)
        logger.info(f"Portfolio caricato: valore={pf.get_total_value():,.2f}€, cash={pf.get_cash_balance():,.2f}€")
        
        # 2. CARICA DATI UNIVERSE (ultima settimana)
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        logger.info(f"📈 Caricamento dati universe dal {week_ago} al {today}...")
        df = database.get_universe_data(start_date=week_ago, end_date=today)
        logger.info(f"Dati caricati: {len(df)} righe, {df['ticker'].nunique()} ticker")
        
        # 3. GENERA SEGNALI PER OGNI STRATEGIA
        strategies_list = [
            ("Moving_Average", strategies.moving_average_crossover),
            ("RSI_Strategy", strategies.rsi_strategy), 
            ("Breakout_Strategy", strategies.breakout_strategy)
        ]
        
        signals_data = {}
        for strategy_name, strategy_fn in strategies_list:
            logger.info(f"🎯 Generazione segnali: {strategy_name}")
            
            # Genera e raffina segnali
            signals = risk_manager.generate_signals(strategy_fn, df, today, pf)
            
            # Converti in DataFrame per Google Sheets
            signals_df = _convert_signals_to_dataframe(signals, strategy_name)
            signals_data[strategy_name] = signals_df
            
            buy_count = len(signals.get("BUY", {}))
            sell_count = len(signals.get("SELL", {})) 
            hold_count = len(signals.get("HOLD", {}))
            logger.info(f"Segnali {strategy_name}: BUY={buy_count}, SELL={sell_count}, HOLD={hold_count}")
        
        # 4. GENERA SNAPSHOT PORTFOLIO SETTIMANALE
        logger.info("📸 Generazione snapshot portfolio settimanale...")
        portfolio_df = _generate_portfolio_snapshots(pf, week_ago, today)
        
        # 5. SCRIVI GOOGLE SHEETS
        logger.info("📝 Scrittura Google Sheets...")
        sheet_url = _write_to_google_sheets(signals_data, portfolio_df, today)
        
        # SUCCESS
        duration = datetime.now() - start_time
        logger.info("=" * 60)
        logger.info("✅ REPORT GENERATO CON SUCCESSO!")
        logger.info("=" * 60)
        logger.info(f"Durata: {duration.total_seconds():.1f} secondi")
        logger.info(f"Google Sheet: {sheet_url}")
        logger.info("📊 REPORT PRONTO PER REVIEW!")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.exception(f"❌ Errore critico: {e}")
        raise


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
            "Notes": f"Size: {data.get('size', 0)} shares"
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
    
    return pd.DataFrame(rows)


def _generate_portfolio_snapshots(pf, start_date: str, end_date: str) -> pd.DataFrame:
    """Genera snapshots portfolio per la settimana."""
    from scripts import database
    
    # Query snapshot della settimana
    query = """
        SELECT date, total_value, cash_balance, positions_count,
               total_return_pct, max_drawdown_pct, volatility_pct, sharpe_ratio
        FROM portfolio_snapshots  
        WHERE portfolio_name = %s AND date BETWEEN %s AND %s
        ORDER BY date
    """
    
    rows, columns = database.execute_query(query, (pf.name, start_date, end_date))
    df = pd.DataFrame(rows, columns=columns)
    
    # Converti date in stringhe per Google Sheets
    if not df.empty and 'date' in df.columns:
        df['date'] = df['date'].astype(str)
    
    return df


def _write_to_google_sheets(signals_data: dict, portfolio_df: pd.DataFrame, date: str) -> str:
    """Scrive tutti i dati su Google Sheets e ritorna URL."""
    from scripts import google_services, config
    
    client = google_services.get_gsheet_client()
    
    # Apri/crea spreadsheet per la settimana
    sheet_name = f"Weekly_Report_{date}"
    
    try:
        # Prova ad aprire sheet esistente nella cartella
        # (questo richiede di implementare una funzione per cercare nella cartella)
        # Per ora creiamo sempre nuovo sheet
        spreadsheet = client.create(sheet_name)
        
        # Sposta nella cartella corretta se definita
        if hasattr(config, 'WEEKLY_REPORTS_FOLDER_ID'):
            # Codice per spostare il file nella cartella...
            pass
            
    except Exception as e:
        logger.warning(f"Creazione nuovo sheet fallita: {e}")
        # Fallback: usa sheet di test
        spreadsheet = client.open_by_key(config.TEST_SHEET_ID)
    
    # Pulisci tutti i worksheet esistenti (tranne il primo)
    worksheets = spreadsheet.worksheets()
    for ws in worksheets[1:]:  # Mantieni il primo
        spreadsheet.del_worksheet(ws)
    
    # Rinomina il primo worksheet
    main_ws = worksheets[0]
    main_ws.update_title("Portfolio_Snapshot")
    
    # Scrivi snapshot portfolio
    if not portfolio_df.empty:
        main_ws.update([portfolio_df.columns.tolist()] + portfolio_df.values.tolist())
    
    # Crea worksheet per ogni strategia
    for strategy_name, signals_df in signals_data.items():
        ws = spreadsheet.add_worksheet(title=strategy_name, rows=100, cols=10)
        if not signals_df.empty:
            ws.update([signals_df.columns.tolist()] + signals_df.values.tolist())
    
    logger.info(f"Google Sheet scritto: {spreadsheet.title}")
    return spreadsheet.url


if __name__ == "__main__":
    main()