# run_weekly_report.py - Versione con argparse
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

Eseguito ogni venerdì tramite systemd.
"""

import logging
import os
import sys
import inspect
import argparse
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


def parse_args():
    """Parsa argomenti CLI."""
    parser = argparse.ArgumentParser(description="Generatore Report Settimanale")
    parser.add_argument(
        "--portfolio",
        required=True,
        help="Nome del portfolio da usare per generare il report"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=120,
        help="Numero di giorni di storico da caricare (default=120)"
    )
    return parser.parse_args()


def main():
    """Entry point per generazione report settimanale."""
    args = parse_args()
    portfolio_name = args.portfolio
    days_back = args.days

    start_time = datetime.now()
    today = start_time.strftime("%Y-%m-%d")
    
    logger.info("=" * 60)
    logger.info("🚀 AVVIO REPORT SETTIMANALE")
    logger.info("=" * 60)
    logger.info(f"Data: {today}")
    logger.info(f"Portfolio scelto: {portfolio_name}")
    logger.info(f"Giorni di storico: {days_back}")
    
    try:
        from scripts import database, portfolio, strategies, risk_manager, google_services, config
        
        # 1. SCOPRI STRATEGIE AUTOMATICAMENTE
        strategy_functions = _discover_strategy_functions()
        logger.info(f"🎯 Strategie scoperte: {list(strategy_functions.keys())}")
        
        # 2. CARICA PORTFOLIO
        logger.info(f"📊 Caricamento portfolio '{portfolio_name}'...")
        pf = portfolio.Portfolio(portfolio_name, today)
        logger.info(f"Portfolio {portfolio_name}: valore=€{pf.get_total_value():,.2f}, cash=€{pf.get_cash_balance():,.2f}")
        
        # 3. CARICA DATI UNIVERSE
        days_ago = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
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
        
        print("\n" + "="*60)
        print("📊 PORTFOLIO SNAPSHOTS SETTIMANA:")
        print("="*60)
        if not portfolio_df.empty:
            print(f"Righe: {len(portfolio_df)}")
            print(f"Colonne: {list(portfolio_df.columns)}")
            print("\nDati:")
            print(portfolio_df.to_string(index=False))
        else:
            print("❌ Nessun dato trovato!")
        print("="*60 + "\n")

        print("\n" + "="*80)
        print("🎯 TUTTI I SEGNALI GENERATI:")
        print("="*80)
        for strategy_name, signals_df in all_signals.items():
            print(f"\n📊 STRATEGIA: {strategy_name}")
            print("-" * 50)
            if not signals_df.empty:
                print(f"Segnali totali: {len(signals_df)}")
                print(signals_df.to_string(index=False))
            else:
                print("❌ Nessun segnale generato")
            print("-" * 50)
        print("="*80 + "\n")

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
    for name in dir(strategies):
        obj = getattr(strategies, name)
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
        return pd.DataFrame(columns=["Ticker", "Signal", "Strategy", "Size", "Price", 
                                   "Stop_Loss", "Risk_Amount", "Notes"])
    
    return pd.DataFrame(rows)


def _get_portfolio_snapshots_week(portfolio_name: str, today_str: str) -> pd.DataFrame:
    """Recupera snapshots portfolio da lunedì a venerdì (oggi è venerdì)."""
    from scripts import database
    
    today = datetime.strptime(today_str, "%Y-%m-%d")
    monday = today - timedelta(days=4)
    
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
        if not df.empty and 'date' in df.columns:
            df['date'] = df['date'].astype(str)
        return df
    except Exception as e:
        logger.error(f"Errore caricamento snapshots: {e}")
        return pd.DataFrame(columns=["date", "total_value", "cash_balance", "positions_count",
                                   "total_return_pct", "max_drawdown_pct", "volatility_pct", 
                                   "sharpe_ratio", "win_rate_pct"])


def _write_to_google_sheet(all_signals: dict, portfolio_df: pd.DataFrame) -> str:
    """Scrive tutti i dati nel Google Sheet configurato."""
    from scripts import google_services, config
    from decimal import Decimal
    
    def convert_for_sheets(value):
        """Converte un valore per essere sicuro con Google Sheets."""
        if isinstance(value, Decimal):
            return float(value)
        elif pd.isna(value):
            return ""
        else:
            return value
    
    def df_to_sheets_data(df):
        """Converte DataFrame in formato sicuro per Google Sheets."""
        if df.empty:
            return []
        
        # Headers
        headers = df.columns.tolist()
        
        # Dati - conversione riga per riga, cella per cella
        rows = []
        for _, row in df.iterrows():
            converted_row = [convert_for_sheets(value) for value in row]
            rows.append(converted_row)
        
        return [headers] + rows
    
    logger.info("Apertura Google Sheet...")
    client = google_services.get_gsheet_client()
    spreadsheet = client.open_by_key(config.WEEKLY_REPORTS_SHEET_ID)
    logger.info(f"Aperto sheet: {spreadsheet.title}")
    
    # Foglio portfolio
    try:
        # Prima PROVA a trovare il foglio esistente
        portfolio_ws = spreadsheet.worksheet("Portfolio_Snapshots")
        portfolio_ws.clear()  # Svuotalo
        logger.info("Trovato e svuotato foglio Portfolio_Snapshots esistente")
    except:
        # Solo se NON esiste, crealo
        portfolio_ws = spreadsheet.add_worksheet(title="Portfolio_Snapshots", rows=50, cols=15)
        logger.info("Creato nuovo foglio Portfolio_Snapshots")

    if not portfolio_df.empty:
        data_to_write = df_to_sheets_data(portfolio_df)
        portfolio_ws.update(data_to_write)
        logger.info(f"Scritto portfolio: {len(data_to_write)-1} righe di dati")
    else:
        portfolio_ws.update([["Nessun dato disponibile"]])
        logger.info("Portfolio vuoto")
    
    # Fogli strategie - trova o crea e svuota
    for strategy_name, signals_df in all_signals.items():
        try:
            ws = spreadsheet.worksheet(strategy_name)
            # Svuota il foglio esistente
            ws.clear()
            logger.info(f"Svuotato foglio {strategy_name} esistente")
        except:
            # Crea nuovo foglio se non esiste
            ws = spreadsheet.add_worksheet(title=strategy_name, rows=100, cols=10)
            logger.info(f"Creato nuovo foglio {strategy_name}")
        
        if not signals_df.empty:
            data_to_write = df_to_sheets_data(signals_df)
            ws.update(data_to_write)
            logger.info(f"Scritto {strategy_name}: {len(data_to_write)-1} righe di dati")
        else:
            ws.update([["Nessun segnale generato"]])
            logger.info(f"Strategia {strategy_name}: nessun segnale")
    
    logger.info(f"✅ Google Sheet completato: {len(all_signals)} strategie + portfolio")
    return spreadsheet.url


if __name__ == "__main__":
    main()
