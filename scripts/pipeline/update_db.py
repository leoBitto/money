# scripts/pipeline/update_db.py (REFACTORED)
from datetime import datetime

# Import delle utilities
from ..utils.gcp_utils import GoogleSheetsManager
from ..utils.data_utils import download_yfinance_data, prepare_db_batch
from ..utils.db_utils import DatabaseManager

# Configurazioni
SPREADSHEET_ID = '1Uh3S3YCyvupZ5yZh2uDi0XYGaZIkEkupxsYed6xRxgA'

def update_daily_prices():
    """
    Aggiorna i prezzi giornalieri nel database con i dati più recenti
    """
    print("🔄 Inizio aggiornamento prezzi giornalieri...")
    
    # --- 1. Setup Google Sheets e recupero ticker ---
    print("📊 Recupero ticker da Google Sheets...")
    sheets_manager = GoogleSheetsManager()
    tickers = sheets_manager.get_tickers_from_sheet(SPREADSHEET_ID)
    print(f"✅ Trovati {len(tickers)} ticker nello Sheet.")
    
    if not tickers:
        print("❌ Nessun ticker trovato. Operazione interrotta.")
        return
    
    # --- 2. Download dati da yfinance ---
    print("📈 Download dati odierni da yfinance...")
    try:
        df_prices = download_yfinance_data(tickers, period="1d", interval="1d")
        print(f"✅ Righe pronte da inserire: {len(df_prices)}")
        
        if df_prices.empty:
            print("❌ Nessun dato scaricato. Operazione interrotta.")
            return
            
    except Exception as e:
        print(f"❌ Errore nel download dati: {e}")
        return
    
    # --- 3. Preparazione dati per DB ---
    print("🔧 Preparazione dati per inserimento...")
    batch_data = prepare_db_batch(df_prices)
    
    if not batch_data:
        print("❌ Nessun dato valido da inserire.")
        return
    
    # --- 4. Inserimento in database ---
    print("💾 Inserimento dati nel database...")
    try:
        db_manager = DatabaseManager()
        
        # Usa DO UPDATE per aggiornare dati esistenti (prezzi possono cambiare durante il giorno)
        conflict_resolution = """DO UPDATE 
        SET open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume"""
        
        rows_processed = db_manager.insert_batch_universe(batch_data, conflict_resolution)
        print(f"✅ {rows_processed} righe inserite/aggiornate su PostgreSQL")
        
    except Exception as e:
        print(f"❌ Errore nell'inserimento database: {e}")
        return
    
    print("🎉 Aggiornamento completato con successo!")

if __name__ == "__main__":
    update_daily_prices()