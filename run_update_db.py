# run_update_db.py (SCRIPT MASTER)
"""
Script master per aggiornare il db
"""
from scripts.pipeline.update_db import update_daily_prices
import sys
from datetime import datetime

def main():

    print("🚀 AVVIO UPDATE DB")
    print("=" * 50)
    
    try:

        update_daily_prices()
        print()
        
        print("🎉 OPERAZIONE COMPLETATA CON SUCCESSO!")
        print(f"⏰ Completato alle: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
    except Exception as e:
        print(f"❌ ERRORE DURANTE L'ESECUZIONE: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
