# simple_backtest_runner.py
"""
Script semplificato per eseguire backtest.
Fa UNA cosa: esegue backtest e mostra risultati.
"""

import argparse
import sys
from datetime import datetime

from scripts.backtest import run_backtest
from scripts import strategies
from scripts import config

def get_strategy_function(strategy_name: str):
    """Recupera la funzione strategia dal nome."""
    if not hasattr(strategies, strategy_name):
        available = [name for name in dir(strategies) if not name.startswith('_')]
        raise ValueError(f"Strategia '{strategy_name}' non trovata. "
                        f"Disponibili: {available}")
    return getattr(strategies, strategy_name)

def print_results(df_results):
    """Stampa risultati in formato semplice."""
    if df_results.empty:
        print("❌ Nessun risultato generato")
        return
    
    # Calcoli base
    initial_value = df_results.iloc[0]['total_value']
    final_value = df_results.iloc[-1]['total_value']
    total_return = ((final_value - initial_value) / initial_value) * 100
    
    print(f"\n📊 RISULTATI BACKTEST")
    print(f"{'='*50}")
    print(f"Valore iniziale: €{initial_value:,.2f}")
    print(f"Valore finale:   €{final_value:,.2f}")
    print(f"Rendimento:      {total_return:+.2f}%")
    print(f"Numero giorni:   {len(df_results)}")
    
    # Salva CSV semplice
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"backtest_results_{timestamp}.csv"
    df_results.to_csv(filename, index=False)
    print(f"💾 Salvato: {filename}")

def main():
    parser = argparse.ArgumentParser(description="Esegui backtest semplice")
    parser.add_argument('strategy', help='Nome strategia (es: moving_average_crossover)')
    parser.add_argument('--start-date', default=config.BACKTEST_START_DATE,
                       help='Data inizio (YYYY-MM-DD)')
    parser.add_argument('--end-date', default='2024-12-31',
                       help='Data fine (YYYY-MM-DD)')
    parser.add_argument('--capital', type=float, default=10000.0,
                       help='Capitale iniziale')
    
    args = parser.parse_args()
    
    try:
        # Recupera strategia
        strategy_fn = get_strategy_function(args.strategy)
        print(f"🚀 Avvio backtest: {args.strategy}")
        print(f"📅 Periodo: {args.start_date} → {args.end_date}")
        print(f"💰 Capitale: €{args.capital:,.2f}")
        
        # Esegui backtest
        results = run_backtest(
            strategy_fn=strategy_fn,
            start_date=args.start_date, 
            end_date=args.end_date,
            initial_cash=args.capital
        )
        
        # Mostra risultati
        print_results(results)
        
    except Exception as e:
        print(f"❌ Errore: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()