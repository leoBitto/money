# run_weekly_report.py
"""
Entry Point: Report Settimanale Portfolio
=========================================

Genera report settimanale completo usando il RiskManager refactored.
Schedulato per esecuzione automatica ogni venerdì.

NUOVO WORKFLOW:
1. Carica portfolio "demo" 
2. Genera segnali da tutte le strategie (moving_average, rsi, breakout)
3. Valida segnali con risk manager (position sizing, cash limits, concentration)
4. Scrive Google Sheets organizzati:
   - Portfolio_Overview: Metriche aggregate + storico
   - Active_Positions: Dettaglio posizioni correnti  
   - Strategy_*: Segnali per ogni strategia con validazione
   - Execution_Summary: Dashboard per decisioni weekend

OUTPUT: Google Sheet aggiornato pronto per review weekend
"""

import logging
import os
import sys
from datetime import datetime

# Assicura che la cartella logs/ esista
os.makedirs("logs", exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/run_weekly_report.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)  # Aggiungi anche output console
    ]
)

logger = logging.getLogger(__name__)


def main():
    """Entry point principale per generazione report settimanale."""
    pass
    #start_time = datetime.now()
    #logger.info("=" * 60)
    #logger.info("🚀 AVVIO GENERAZIONE REPORT SETTIMANALE")
    #logger.info("=" * 60)
    #logger.info(f"Timestamp: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    #
    #try:
    #    # Import dopo setup logging per catturare eventuali errori di import
    #    from scripts.reports import generate_weekly_report
    #    
    #    # Genera report per portfolio demo
    #    result = generate_weekly_report(
    #        portfolio_name="demo",
    #        date=None  # Usa data corrente
    #    )
    #    
    #    if result['success']:
    #        # SUCCESS
    #        duration = datetime.now() - start_time
    #        logger.info("=" * 60)
    #        logger.info("✅ REPORT GENERATO CON SUCCESSO!")
    #        logger.info("=" * 60)
    #        logger.info(f"Portfolio: {result['portfolio_name']}")
    #        logger.info(f"Data: {result['date']}")
    #        logger.info(f"Fogli scritti: {', '.join(result['sheets_written'])}")
    #        logger.info(f"Segnali totali: {result['total_signals']}")
    #        logger.info(f"Ordini approvati: {result['approved_orders']}")
    #        logger.info(f"Valore portfolio: €{result['portfolio_summary']['Total_Value']:,.2f}")
    #        logger.info(f"Cash disponibile: €{result['portfolio_summary']['Cash_Balance']:,.2f}")
    #        logger.info(f"Posizioni attive: {result['portfolio_summary']['Positions_Count']}")
    #        logger.info(f"Durata esecuzione: {duration.total_seconds():.1f} secondi")
    #        logger.info("=" * 60)
    #        logger.info("📊 REPORT PRONTO PER REVIEW WEEKEND")
    #        logger.info("=" * 60)
    #        
    #    else:
    #        # ERROR
    #        logger.error("=" * 60) 
    #        logger.error("❌ ERRORE NELLA GENERAZIONE DEL REPORT")
    #        logger.error("=" * 60)
    #        logger.error(f"Errore: {result.get('error', 'Errore sconosciuto')}")
    #        logger.error("=" * 60)
    #        raise Exception(f"Report generation failed: {result.get('error')}")
#
    #except ImportError as e:
    #    logger.error(f"❌ Errore import moduli: {e}")
    #    logger.error("Verificare che tutti i moduli siano disponibili")
    #    raise
    #    
    #except Exception as e:
    #    logger.exception(f"❌ Errore critico durante la generazione del report: {e}")
    #    raise
#

if __name__ == "__main__":
    main()