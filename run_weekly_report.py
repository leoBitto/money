# run_weekly_report.py
import logging
import os
from scripts.reports import generate_weekly_report

# Assicura che la cartella logs/ esista
os.makedirs("logs", exist_ok=True)

# Setup logging
logging.basicConfig(
    filename="logs/run_weekly_report.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

def main():
    logging.info("🚀 Avvio generazione report settimanale")

    try:
        generate_weekly_report()
        logging.info("✅ Report settimanale generato con successo")

    except Exception as e:
        logging.exception(f"❌ Errore durante la generazione del report: {e}")
        raise

if __name__ == "__main__":
    main()
