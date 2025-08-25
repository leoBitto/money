# generate_weekly_report.py (SCRIPT MASTER)
"""
Script master per generare il report settimanale completo
"""
from scripts.reports.generate_weekly_signals_report import generate_weekly_report
from scripts.pipeline.update_db import update_daily_prices
import sys
from datetime import datetime

def main():
    """
    Orchestrazione completa:
    1. Aggiorna i prezzi nel DB
    2. Genera il report settimanale
    """
    print("🚀 AVVIO GENERAZIONE REPORT SETTIMANALE")
    print("=" * 50)
    
    try:

        generate_weekly_report()
        print()
        
        print("🎉 OPERAZIONE COMPLETATA CON SUCCESSO!")
        print(f"⏰ Completato alle: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
    except Exception as e:
        print(f"❌ ERRORE DURANTE L'ESECUZIONE: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
