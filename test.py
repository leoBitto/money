# ~/money/test.py

from scripts.trading.generate_signals import generate_signals, generate_all_strategies_signals
from scripts.trading import strategies
from scripts.reports.generate_weekly_signals_report import generate_weekly_signals_report
import pandas as pd
from datetime import datetime, timedelta


def test_weekly_report():
    """
    Test the weekly signals report generation.
    """
    print("\n" + "=" * 50)
    print("📄 TESTING WEEKLY REPORT")
    print("=" * 50)
    
    try:
        test_date = '2025-08-23'
        print(f"Generating weekly report for date: {test_date}")
        
        results = generate_weekly_signals_report(test_date)
        
        successful = sum(1 for url in results.values() if url)
        total = len(results)
        
        print(f"✅ Report settimanale completato!")
        print(f"📊 Successo: {successful}/{total} report generati")
        
        if results:
            print(f"\n📋 Dettaglio report:")
            for strategy, url in results.items():
                if url:
                    print(f"   ✅ {strategy}")
                    print(f"      🔗 {url}")
                else:
                    print(f"   ❌ {strategy}: Errore o nessun dato")
        
        return successful > 0
        
    except Exception as e:
        print(f"❌ Errore nel generare il report settimanale: {e}")
        return False

def test_weekly_report_dry_run():
    """
    Test "dry run" - verifica che tutto funzioni senza creare report reali
    """
    print("\n" + "=" * 50)
    print("🧪 TESTING WEEKLY REPORT DRY RUN")
    print("=" * 50)
    
    try:
        # Import delle funzioni necessarie
        from scripts.reports.generate_weekly_signals_report import (
            setup_google_client, 
            get_strategy_functions
        )
        
        # Test connessione Google
        print("🔗 Testando connessione Google Sheets...")
        gc = setup_google_client()
        print("✅ Connessione Google Sheets OK")
        
        # Test recupero strategie
        print("📈 Recuperando strategie...")
        strategies_list = get_strategy_functions()
        print(f"✅ Trovate {len(strategies_list)} strategie")
        for name, func in strategies_list:
            print(f"   - {name}")
        
        # Test generazione segnali (senza creare Google Sheets)
        print(f"\n🧮 Testando generazione segnali...")
        test_date = '2025-08-23'
        
        default_params = {
            'moving_average_crossover': {'short_window': 3, 'long_window': 5},
            'rsi_strategy': {'period': 14, 'overbought': 70, 'oversold': 30},
            'breakout_strategy': {'lookback': 20}
        }
        
        all_good = True
        for strategy_name, strategy_func in strategies_list:
            try:
                params = default_params.get(strategy_name, {})
                df_signals = generate_signals(strategy_func, test_date, **params)
                
                if not df_signals.empty:
                    signal_counts = df_signals['signal'].value_counts()
                    print(f"   ✅ {strategy_name}: {len(df_signals)} ticker, "
                          f"Buy: {signal_counts.get(1, 0)}, "
                          f"Hold: {signal_counts.get(0, 0)}, " 
                          f"Sell: {signal_counts.get(-1, 0)}")
                else:
                    print(f"   ⚠️  {strategy_name}: Nessun dato disponibile")
                    
            except Exception as e:
                print(f"   ❌ {strategy_name}: {e}")
                all_good = False
        
        if all_good:
            print(f"\n✅ Dry run completato con successo!")
            print(f"🚀 Tutto pronto per generare i report reali.")
        else:
            print(f"\n⚠️  Dry run completato con alcuni errori.")
            
        return all_good
        
    except Exception as e:
        print(f"❌ Errore nel dry run: {e}")
        return False

def test_weekly_report_with_custom_date():
    """
    Test del report con date personalizzate
    """
    print("\n" + "=" * 50)
    print("📅 TESTING WEEKLY REPORT - CUSTOM DATES")
    print("=" * 50)
    
    test_dates = [
        '2025-08-20',
        '2025-08-21',
        '2025-08-22',
        '2025-08-23'
    ]
    
    for test_date in test_dates:
        print(f"\n📅 Testando data: {test_date}")
        try:
            results = generate_weekly_signals_report(test_date)
            successful = sum(1 for url in results.values() if url)
            print(f"   📊 Risultato: {successful}/{len(results)} report generati")
            
        except Exception as e:
            print(f"   ❌ Errore per data {test_date}: {e}")

if __name__ == "__main__":

    print("=" * 60)

    
    # === TESTS REPORT ===
    # Test dry run (CONSIGLIATO per iniziare - non crea report reali)
    test_weekly_report_dry_run()
    
    # Test report settimanale con date diverse
    test_weekly_report_with_custom_date()
    
    # Test report settimanale completo (ATTENZIONE: crea report reali su Google Drive!)
    test_weekly_report()
    
    print(f"\n🎉 TESTS COMPLETED!")
    print(f"\n💡 SUGGERIMENTI:")
    print(f"   - Per i primi test usa 'test_report_dry_run()'")
    print(f"   - I test report creano files reali su Google Drive!")
    print(f"   - Decommenta gradualmente i test che ti servono")