# run_backtest.py
"""
Script per Esecuzione Backtest di Strategie di Trading
======================================================

Questo script esegue backtest delle strategie con logica realistica:
- Calcolo segnali: ogni VENERDÌ usando dati disponibili fino a quel giorno
- Esecuzione trade: ogni LUNEDÌ ai prezzi di apertura  
- Portfolio: equal-weighted (stesso importo $ per ogni posizione BUY)

LIMITAZIONI IMPORTANTI DA CONSIDERARE:
-------------------------------------
1. EQUAL WEIGHT: Non considera volatilità, correlazioni o momentum
2. MARKET IMPACT: Assume esecuzione istantanea senza impatto sul prezzo
3. LIQUIDITY: Non considera problemi di liquidità o spread bid-ask
4. SLIPPAGE: Assume esecuzione esatta al prezzo di apertura
5. TRANSACTION COSTS: Solo commissioni fisse, no costi di finanziamento
6. REGIME CHANGES: Non adatta la strategia a cambi di regime di mercato
7. OVERFITTING: Rischio di over-ottimizzazione sui dati storici

DATI DI OUTPUT:
--------------
Tutti i risultati vengono salvati in formato CSV nella cartella 'backtest_results/':
- portfolio_[strategia]_[timestamp].csv: evoluzione valore portfolio 
- trades_[strategia]_[timestamp].csv: storico completo trade eseguiti
- signals_[strategia]_[timestamp].csv: storico segnali generati  
- summary_[strategia]_[timestamp].csv: metriche aggregate di performance

ESEMPI DI UTILIZZO:
------------------
# Testa tutte le strategie disponibili
python run_backtest.py

# Testa strategia specifica con parametri custom  
python run_backtest.py --strategy moving_average_crossover --capital 50000

# Backtest su periodo specifico
python run_backtest.py --start-date 2023-01-01 --end-date 2024-01-01

# Solo alcuni ticker
python run_backtest.py --tickers AAPL TSLA MSFT --save-to-db

# Confronta tutte le strategie
python run_backtest.py --compare-all
"""

import argparse
import logging
import os
import sys
import inspect
from datetime import datetime
import pandas as pd

from scripts import config
from scripts.backtest import run_backtest
from scripts.trading import strategies
from scripts.database import get_available_tickers, execute_query

# Setup logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename="logs/run_backtest.log", 
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

def get_available_strategies():
    """
    Recupera tutte le strategie disponibili dal modulo strategies.
    
    Returns:
        List[Tuple[str, Callable]]: Lista di tuple (nome_strategia, funzione_strategia)
    """
    strategy_functions = []
    for name, func in inspect.getmembers(strategies, inspect.isfunction):
        sig = inspect.signature(func)
        # Euristica: le strategie dovrebbero avere 'df' come primo parametro
        if 'df' in sig.parameters:
            strategy_functions.append((name, func))
    return strategy_functions


def save_results_to_database(backtest_results: Dict[str, any]) -> bool:
    """
    Salva i risultati del backtest nel database PostgreSQL.
    
    Crea tabelle se non esistono:
    - backtest_runs: metadati e metriche aggregate dei backtest
    - backtest_trades: dettaglio di tutti i trade eseguiti
    - backtest_portfolio: evoluzione del valore del portfolio
    
    Args:
        backtest_results (Dict): Risultati del backtest da salvare
        
    Returns:
        bool: True se salvataggio riuscito, False altrimenti
    """
    try:
        # Crea tabelle se non esistono
        create_tables_sql = """
        CREATE TABLE IF NOT EXISTS backtest_runs (
            id SERIAL PRIMARY KEY,
            strategy_name VARCHAR(100) NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            initial_capital DECIMAL(12,2) NOT NULL,
            final_capital DECIMAL(12,2) NOT NULL,
            total_return DECIMAL(8,4),
            annualized_return DECIMAL(8,4),
            volatility DECIMAL(8,4), 
            sharpe_ratio DECIMAL(8,4),
            max_drawdown DECIMAL(8,4),
            num_trades INTEGER,
            win_rate DECIMAL(6,2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS backtest_trades (
            id SERIAL PRIMARY KEY,
            backtest_run_id INTEGER REFERENCES backtest_runs(id),
            trade_date DATE NOT NULL,
            ticker VARCHAR(20) NOT NULL,
            action VARCHAR(10) NOT NULL,
            shares INTEGER NOT NULL,
            price DECIMAL(10,4) NOT NULL,
            gross_amount DECIMAL(12,2) NOT NULL,
            commission DECIMAL(8,2) NOT NULL,
            net_amount DECIMAL(12,2) NOT NULL,
            pnl DECIMAL(12,2)
        );
        
        CREATE TABLE IF NOT EXISTS backtest_portfolio (
            id SERIAL PRIMARY KEY,
            backtest_run_id INTEGER REFERENCES backtest_runs(id),
            portfolio_date DATE NOT NULL,
            cash DECIMAL(12,2) NOT NULL,
            positions_value DECIMAL(12,2) NOT NULL,
            total_value DECIMAL(12,2) NOT NULL,
            num_positions INTEGER NOT NULL
        );
        """
        
        execute_query(create_tables_sql, fetch=False)
        
        # Inserisci run principale
        run_sql = """
        INSERT INTO backtest_runs 
        (strategy_name, start_date, end_date, initial_capital, final_capital,
         total_return, annualized_return, volatility, sharpe_ratio, max_drawdown,
         num_trades, win_rate)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """
        
        pm = backtest_results['portfolio_metrics']
        tm = backtest_results['trade_metrics']
        
        result = execute_query(run_sql, (
            backtest_results['strategy_name'],
            backtest_results['start_date'],
            backtest_results['end_date'], 
            backtest_results['initial_capital'],
            backtest_results['final_capital'],
            pm.get('total_return'),
            pm.get('annualized_return'),
            pm.get('volatility'),
            pm.get('sharpe_ratio'),
            pm.get('max_drawdown'),
            tm.get('num_trades'),
            tm.get('win_rate')
        ))
        
        backtest_run_id = result[0][0]
        
        # Inserisci trade
        trades_df = backtest_results['trades_history']
        if not trades_df.empty:
            trades_data = []
            for _, trade in trades_df.iterrows():
                trades_data.append((
                    backtest_run_id,
                    trade['date'],
                    trade['ticker'], 
                    trade['action'],
                    trade['shares'],
                    trade['price'],
                    trade['gross_amount'],
                    trade['commission'],
                    trade['net_amount'],
                    trade.get('pnl', None)
                ))
            
            trades_sql = """
            INSERT INTO backtest_trades 
            (backtest_run_id, trade_date, ticker, action, shares, price,
             gross_amount, commission, net_amount, pnl)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            from scripts.database import execute_many
            execute_many(trades_sql, trades_data)
        
        # Inserisci portfolio history
        portfolio_df = backtest_results['portfolio_history']
        if not portfolio_df.empty:
            portfolio_data = []
            for _, row in portfolio_df.iterrows():
                portfolio_data.append((
                    backtest_run_id,
                    row['date'],
                    row['cash'],
                    row['positions_value'],
                    row['total_value'],
                    row['num_positions']
                ))
            
            portfolio_sql = """
            INSERT INTO backtest_portfolio
            (backtest_run_id, portfolio_date, cash, positions_value, total_value, num_positions)
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            
            execute_many(portfolio_sql, portfolio_data)
        
        print(f"✅ Risultati salvati nel database (run_id: {backtest_run_id})")
        return True
        
    except Exception as e:
        print(f"❌ Errore salvataggio database: {e}")
        logging.exception("Error saving backtest results to database")
        return False


def print_backtest_summary(results: Dict[str, any]) -> None:
    """
    Stampa un riassunto dei risultati del backtest in formato leggibile.
    
    Args:
        results (Dict): Risultati del backtest da stampare
    """
    pm = results['portfolio_metrics']
    tm = results['trade_metrics']
    
    print(f"\n{'='*80}")
    print(f"📊 RISULTATI BACKTEST: {results['strategy_name'].upper()}")
    print(f"{'='*80}")
    print(f"📅 Periodo: {results['start_date']} → {results['end_date']}")
    print(f"💰 Capitale: ${results['initial_capital']:,.2f} → ${results['final_capital']:,.2f}")
    print(f"\n📈 PERFORMANCE:")
    print(f"   Rendimento Totale:     {pm.get('total_return', 0):>8.2f}%")
    print(f"   Rendimento Annualiz.:  {pm.get('annualized_return', 0):>8.2f}%")
    print(f"   Volatilità:            {pm.get('volatility', 0):>8.2f}%")
    print(f"   Sharpe Ratio:          {pm.get('sharpe_ratio', 0):>8.2f}")
    print(f"   Max Drawdown:          {pm.get('max_drawdown', 0):>8.2f}%")
    print(f"   Calmar Ratio:          {pm.get('calmar_ratio', 0):>8.2f}")
    
    print(f"\n💼 TRADING:")
    print(f"   Numero Trade:          {tm.get('num_trades', 0):>8}")
    print(f"   Trade Profittevoli:    {tm.get('profitable_trades', 0):>8}")
    print(f"   Win Rate:              {tm.get('win_rate', 0):>8.2f}%")
    print(f"   Profitto Medio:        ${tm.get('avg_profit', 0):>7.2f}")
    print(f"   Profit Factor:         {tm.get('profit_factor', 0):>8.2f}")
    
    print(f"\n📁 FILE GENERATI:")
    for file_path in results.get('output_files', []):
        print(f"   • {os.path.basename(file_path)}")


def compare_strategies_results(all_results: List[Dict[str, any]]) -> None:
    """
    Crea una tabella di confronto tra i risultati di più strategie.
    
    Args:
        all_results (List[Dict]): Lista dei risultati di backtest da confrontare
    """
    if len(all_results) < 2:
        return
    
    print(f"\n{'='*120}")
    print("🏆 CONFRONTO STRATEGIE")
    print(f"{'='*120}")
    
    comparison_data = []
    for result in all_results:
        if result is None:
            continue
            
        pm = result['portfolio_metrics']
        tm = result['trade_metrics']
        
        comparison_data.append({
            'Strategy': result['strategy_name'],
            'Total Return (%)': f"{pm.get('total_return', 0):7.2f}",
            'Annual Return (%)': f"{pm.get('annualized_return', 0):7.2f}", 
            'Volatility (%)': f"{pm.get('volatility', 0):7.2f}",
            'Sharpe': f"{pm.get('sharpe_ratio', 0):6.2f}",
            'Max DD (%)': f"{pm.get('max_drawdown', 0):7.2f}",
            'Trades': f"{tm.get('num_trades', 0):6}",
            'Win Rate (%)': f"{tm.get('win_rate', 0):6.2f}",
            'Profit Factor': f"{tm.get('profit_factor', 0):6.2f}"
        })
    
    if comparison_data:
        df_comparison = pd.DataFrame(comparison_data)
        print(df_comparison.to_string(index=False))
        
        # Salva confronto
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        comparison_file = f"backtest_results/comparison_{timestamp}.csv"
        os.makedirs("backtest_results", exist_ok=True)
        df_comparison.to_csv(comparison_file, index=False)
        print(f"\n💾 Confronto salvato: {comparison_file}")


def run_single_strategy_backtest(strategy_name: str, strategy_fn: callable, args: argparse.Namespace) -> Dict[str, any]:
    """
    Esegue il backtest per una singola strategia.
    
    Args:
        strategy_name (str): Nome della strategia
        strategy_fn (callable): Funzione della strategia
        args (argparse.Namespace): Argomenti della command line
        
    Returns:
        Dict[str, any]: Risultati del backtest o None se errore
    """
    print(f"\n🔄 Avvio backtest strategia: {strategy_name}")
    logging.info(f"Starting backtest for strategy: {strategy_name}")
    
    try:
        # Usa parametri di default se disponibili
        strategy_params = config.DEFAULT_STRATEGY_PARAMS.get(strategy_name, {})
        
        result = run_backtest(
            strategy_fn=strategy_fn,
            start_date=args.start_date,
            end_date=args.end_date,
            tickers=args.tickers,
            initial_capital=args.capital,
            commission_rate=args.commission,
            output_dir=args.output_dir,
            **strategy_params
        )
        
        # Mostra summary
        print_backtest_summary(result)
        
        # Salva nel database se richiesto
        if args.save_to_db:
            save_results_to_database(result)
        
        logging.info(f"Backtest completed for {strategy_name}: "
                    f"Return={result['portfolio_metrics'].get('total_return', 0):.2f}%")
        
        return result
        
    except Exception as e:
        print(f"❌ Errore nel backtest di {strategy_name}: {e}")
        logging.exception(f"Error in backtest for {strategy_name}")
        return None


def main():
    """Funzione principale dello script."""
    parser = argparse.ArgumentParser(
        description="Esegui backtest di strategie di trading",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi di utilizzo:
  python run_backtest.py                                    # Testa tutte le strategie
  python run_backtest.py --strategy moving_average_crossover  # Strategia specifica  
  python run_backtest.py --start-date 2023-01-01 --end-date 2024-01-01  # Periodo custom
  python run_backtest.py --tickers AAPL TSLA --capital 50000  # Ticker e capitale custom
  python run_backtest.py --compare-all --save-to-db         # Confronta tutto e salva in DB
        """
    )
    
    parser.add_argument('--strategy', type=str, 
                       help='Strategia specifica da testare')
    parser.add_argument('--start-date', type=str, default=config.BACKTEST_START_DATE,
                       help='Data inizio backtest (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, default=datetime.now().strftime("%Y-%m-%d"),
                       help='Data fine backtest (YYYY-MM-DD)')
    parser.add_argument('--tickers', nargs='+', 
                       help='Lista ticker specifici da testare')
    parser.add_argument('--capital', type=float, default=config.BACKTEST_INITIAL_CAPITAL,
                       help='Capitale iniziale')
    parser.add_argument('--commission', type=float, default=config.BACKTEST_COMMISSION,
                       help='Tasso commissioni (es. 0.001 = 0.1%)')
    parser.add_argument('--output-dir', type=str, default="backtest_results",
                       help='Directory per salvare i risultati')
    parser.add_argument('--save-to-db', action='store_true',
                       help='Salva risultati nel database PostgreSQL')
    parser.add_argument('--compare-all', action='store_true',
                       help='Confronta tutte le strategie disponibili')
    
    args = parser.parse_args()
    
    print("🚀 Avvio sistema di backtesting...")
    print(f"📅 Periodo: {args.start_date} → {args.end_date}")
    print(f"💰 Capitale iniziale: ${args.capital:,.2f}")
    print(f"💸 Commissioni: {args.commission:.1%}")
    
    logging.info(f"Backtest started - Period: {args.start_date} to {args.end_date}")
    
    # Ottieni ticker disponibili
    if not args.tickers:
        print("🔍 Recupero ticker disponibili dal database...")
        try:
            args.tickers = get_available_tickers()
            print(f"✅ Trovati {len(args.tickers)} ticker")
            if len(args.tickers) > 10:
                print(f"   Primi 10: {', '.join(args.tickers[:10])}")
            else:
                print(f"   Ticker: {', '.join(args.tickers)}")
        except Exception as e:
            print(f"❌ Errore recupero ticker: {e}")
            sys.exit(1)
    else:
        print(f"📈 Usando ticker specificati: {args.tickers}")
    
    # Ottieni strategie disponibili
    available_strategies = get_available_strategies()
    if not available_strategies:
        print("❌ Nessuna strategia trovata nel modulo strategies!")
        sys.exit(1)
    
    print(f"🧠 Strategie disponibili ({len(available_strategies)}): "
          f"{[name for name, _ in available_strategies]}")
    
    # Esegui backtest
    results = []
    
    if args.strategy:
        # Test singola strategia
        strategy_found = False
        for strategy_name, strategy_fn in available_strategies:
            if strategy_name == args.strategy:
                result = run_single_strategy_backtest(strategy_name, strategy_fn, args)
                if result:
                    results.append(result)
                strategy_found = True
                break
        
        if not strategy_found:
            print(f"❌ Strategia '{args.strategy}' non trovata!")
            print(f"Strategie disponibili: {[name for name, _ in available_strategies]}")
            sys.exit(1)
            
    else:
        # Test tutte le strategie (o confronto se richiesto)
        if args.compare_all:
            print(f"\n🏁 Avvio confronto completo di {len(available_strategies)} strategie...")
        else:
            print(f"\n🔄 Test di tutte le {len(available_strategies)} strategie...")
        
        for i, (strategy_name, strategy_fn) in enumerate(available_strategies, 1):
            print(f"\n[{i}/{len(available_strategies)}] Processando: {strategy_name}")
            result = run_single_strategy_backtest(strategy_name, strategy_fn, args)
            if result:
                results.append(result)
    
    # Mostra confronto finale se multiple strategie
    if len(results) > 1 or args.compare_all:
        compare_strategies_results(results)
    
    # Summary finale
    print(f"\n{'='*60}")
    print(f"✅ BACKTEST COMPLETATO")
    print(f"{'='*60}")
    print(f"📊 Strategie testate: {len(results)}")
    print(f"📁 Risultati salvati in: {args.output_dir}/")
    if args.save_to_db:
        print(f"💾 Risultati salvati anche nel database PostgreSQL")
    
    # Trova migliore strategia
    if len(results) > 1:
        best_strategy = max(results, key=lambda x: x['portfolio_metrics'].get('sharpe_ratio', -999))
        print(f"🏆 Migliore strategia (Sharpe): {best_strategy['strategy_name']} "
              f"({best_strategy['portfolio_metrics'].get('sharpe_ratio', 0):.2f})")
    
    logging.info(f"Backtest execution completed - {len(results)} strategies tested")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  Backtest interrotto dall'utente")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Errore imprevisto: {e}")
        logging.exception("Unexpected error in backtest execution")
        sys.exit(1)