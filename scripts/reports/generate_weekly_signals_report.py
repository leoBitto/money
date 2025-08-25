# scripts/reports/generate_weekly_signals_report.py (REFACTORED)
from datetime import datetime
from typing import Dict
import pandas as pd
from gspread_dataframe import set_with_dataframe

# Import utilities
from ..utils.gcp_utils import GoogleSheetsManager
from ..utils.trading_utils import (
    get_strategy_functions, 
    format_signals_column, 
    calculate_signal_distribution,
    create_signals_summary
)
from ..trading.generate_signals import generate_signals
from ..trading import strategies

# Configurazioni
WEEKLY_FOLDER_ID = "1pGSxyPjc8rotTFZp-HA-Xrl7yZHjDWDh"
TEST_SHEET_ID = "1fGTT6O197auwyHGnEBKwvHm3oZwwWz9r8Nm4hz76jKM"

def generate_weekly_report():
    """
    Genera il report settimanale con tutti i segnali delle strategie
    """
    print("📈 Inizio generazione report settimanale...")
    
    # Setup
    sheets_manager = GoogleSheetsManager()
    today = datetime.today().strftime('%Y-%m-%d')
    
    # Recupera tutte le strategie disponibili
    strategy_functions = get_strategy_functions(strategies)
    print(f"🔍 Trovate {len(strategy_functions)} strategie: {[name for name, _ in strategy_functions]}")
    
    if not strategy_functions:
        print("❌ Nessuna strategia trovata!")
        return
    
    # Apri il foglio esistente
    try:
        spreadsheet = sheets_manager.get_sheet_by_id(TEST_SHEET_ID)
        print("✅ Foglio Google Sheets aperto")
    except Exception as e:
        print(f"❌ Errore apertura foglio: {e}")
        return
    
    # Prepara i metadati
    metadata_row = {"Date": today}
    all_signals = {}
    
    # --- 1. Genera segnali per ogni strategia ---
    for strategy_name, strategy_func in strategy_functions:
        print(f"🔄 Processando strategia: {strategy_name}")
        
        try:
            # Genera segnali (usa parametri di default delle strategie)
            df_signals = generate_signals(strategy_func, today)
            
            if df_signals.empty:
                print(f"⚠️  Nessun segnale generato per {strategy_name}")
                continue
            
            # Converti segnali in formato testo per il report
            df_signals_formatted = format_signals_column(df_signals.copy())
            all_signals[strategy_name] = df_signals_formatted
            
            # Calcola statistiche per metadati
            distribution = calculate_signal_distribution(df_signals_formatted)
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
            # Controlla se esiste già un worksheet con quel nome
            try:
                worksheet = spreadsheet.worksheet(strategy_name)
                worksheet.clear()  # pulisci prima di scrivere
                print(f"🔄 Aggiornamento foglio esistente: {strategy_name}")
            except:
                worksheet = spreadsheet.add_worksheet(
                    title=strategy_name,
                    rows=str(len(df_signals) + 10),  # margine extra
                    cols=str(len(df_signals.columns) + 2)
                )
                print(f"📄 Creato nuovo foglio: {strategy_name}")
            
            # Scrivi il DataFrame
            set_with_dataframe(worksheet, df_signals)
            print(f"✅ Foglio '{strategy_name}' aggiornato con {len(df_signals)} segnali")
            
        except Exception as e:
            print(f"❌ Errore scrittura foglio {strategy_name}: {e}")
    
    # --- 3. Crea foglio riassuntivo ---
    try:
        summary_df = create_signals_summary(all_signals)
        
        try:
            summary_ws = spreadsheet.worksheet("Summary")
            summary_ws.clear()
        except:
            summary_ws = spreadsheet.add_worksheet(
                title="Summary",
                rows=str(len(summary_df) + 5),
                cols=str(len(summary_df.columns) + 2)
            )
        
        set_with_dataframe(summary_ws, summary_df)
        print("✅ Foglio 'Summary' creato/aggiornato")
        
    except Exception as e:
        print(f"❌ Errore creazione summary: {e}")
    
    # --- 4. Aggiorna foglio Metadata ---
    try:
        try:
            meta_ws = spreadsheet.worksheet("Metadata")
        except:
            # Crea il foglio se non esiste
            meta_ws = spreadsheet.add_worksheet(
                title="Metadata",
                rows="100",
                cols="20"
            )
            # Scrivi intestazioni
            headers = list(metadata_row.keys())
            meta_ws.append_row(headers)
            print("📄 Creato foglio Metadata")
        
        # Prendi intestazioni correnti
        existing_headers = meta_ws.row_values(1)
        
        # Se ci sono nuove colonne (strategie), aggiorna intestazioni
        new_headers = list(metadata_row.keys())
        if existing_headers != new_headers:
            meta_ws.clear()
            meta_ws.append_row(new_headers)
            print("🔄 Aggiornate intestazioni Metadata")
        
        # Aggiungi nuova riga con i dati
        row_values = [metadata_row.get(h, "") for h in new_headers]
        meta_ws.append_row(row_values)
        
        print(f"✅ Metadata aggiornato con i dati del {today}")
        
    except Exception as e:
        print(f"❌ Errore aggiornamento metadata: {e}")
    
    print("🎉 Report settimanale generato con successo!")
    print(f"📊 Statistiche finali:")
    for strategy_name in all_signals.keys():
        distribution = calculate_signal_distribution(all_signals[strategy_name])
        total = sum(distribution.values())
        print(f"   • {strategy_name}: {distribution.get('BUY', 0)} BUY, {distribution.get('HOLD', 0)} HOLD, {distribution.get('SELL', 0)} SELL (tot: {total})")

if __name__ == "__main__":
    generate_weekly_report()