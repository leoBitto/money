# ~/money/test.py

from scripts.trading.generate_signals import generate_signals, generate_all_strategies_signals
from scripts.trading import strategies
from scripts.reports.generate_weekly_signals_report import generate_weekly_signals_report
import pandas as pd
from datetime import datetime, timedelta


def test_simplified_weekly_report():
    """
    Test the simplified weekly signals report generation.
    """
    print("\n" + "=" * 50)
    print("📄 TESTING SIMPLIFIED WEEKLY REPORT")
    print("=" * 50)
    
    try:
        test_date = '2025-08-23'
        print(f"Generating simplified weekly report for date: {test_date}")
        
        results = generate_weekly_signals_report(test_date)
        
        successful = sum(1 for url in results.values() if url)
        total = len(results)
        
        print(f"✅ Report settimanale semplificato completato!")
        print(f"📊 Successo: {successful}/{total} Google Sheets generati")
        
        if results:
            print(f"\n📋 Dettaglio Google Sheets creati:")
            for strategy, url in results.items():
                if url:
                    # Formatta il nome del file come sarà visualizzato
                    date_obj = datetime.strptime(test_date, "%Y-%m-%d")
                    formatted_date = date_obj.strftime("%d_%m_%Y")
                    sheet_name = f"{strategy}_{formatted_date}"
                    
                    print(f"   ✅ {sheet_name}")
                    print(f"      📊 2 colonne: Ticker | Signal")
                    print(f"      🔗 {url}")
                else:
                    print(f"   ❌ {strategy}: Errore o nessun dato")
        
        return successful > 0
        
    except Exception as e:
        print(f"❌ Errore nel generare il report settimanale: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_simplified_report_dry_run():
    """
    Test "dry run" - verifica che tutto funzioni senza creare Google Sheets reali
    """
    print("\n" + "=" * 50)
    print("🧪 TESTING SIMPLIFIED REPORT DRY RUN")
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
        print(f"\n🧮 Testando generazione segnali per formato semplificato...")
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
                    # Simula la trasformazione che farà la funzione semplificata
                    signal_map = {-1: 'SELL', 0: 'HOLD', 1: 'BUY'}
                    df_simple = df_signals[['ticker', 'signal']].copy()
                    df_simple['signal_text'] = df_simple['signal'].map(signal_map)
                    
                    signal_counts = df_simple['signal_text'].value_counts()
                    
                    # Formatta nome file come sarà creato
                    date_obj = datetime.strptime(test_date, "%Y-%m-%d")
                    formatted_date = date_obj.strftime("%d_%m_%Y")
                    future_sheet_name = f"{strategy_name}_{formatted_date}"
                    
                    print(f"   ✅ {future_sheet_name}")
                    print(f"      📊 {len(df_simple)} righe | "
                          f"BUY: {signal_counts.get('BUY', 0)}, "
                          f"HOLD: {signal_counts.get('HOLD', 0)}, "
                          f"SELL: {signal_counts.get('SELL', 0)}")
                    print(f"      📋 Esempio dati: {df_simple.head(2).to_dict('records')}")
                    
                else:
                    print(f"   ⚠️  {strategy_name}: Nessun dato disponibile")
                    
            except Exception as e:
                print(f"   ❌ {strategy_name}: {e}")
                all_good = False
        
        if all_good:
            print(f"\n✅ Dry run completato con successo!")
            print(f"🚀 I Google Sheets saranno creati con formato:")
            print(f"   📊 Colonne: Ticker | Signal")
            print(f"   📁 Nomi: strategia_dd_mm_yyyy")
            print(f"   🎨 Header colorato, resto semplice")
        else:
            print(f"\n⚠️  Dry run completato con alcuni errori.")
            
        return all_good
        
    except Exception as e:
        print(f"❌ Errore nel dry run: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_simplified_report_single_strategy():
    """
    Test di una singola strategia per debug
    """
    print("\n" + "=" * 50)
    print("🎯 TESTING SINGLE STRATEGY - SIMPLIFIED")
    print("=" * 50)
    
    try:
        from scripts.reports.generate_weekly_signals_report import (
            setup_google_client, 
            get_strategy_functions,
            generate_strategy_sheet
        )
        
        # Setup
        gc = setup_google_client()
        strategies_list = get_strategy_functions()
        
        if not strategies_list:
            print("❌ Nessuna strategia trovata")
            return False
        
        # Testa solo la prima strategia
        strategy_name, strategy_func = strategies_list[0]
        test_date = '2025-08-23'
        
        print(f"🎯 Testando strategia: {strategy_name}")
        print(f"📅 Data: {test_date}")
        
        # Parametri default
        default_params = {
            'moving_average_crossover': {'short_window': 3, 'long_window': 5},
            'rsi_strategy': {'period': 14, 'overbought': 70, 'oversold': 30},
            'breakout_strategy': {'lookback': 20}
        }
        
        params = default_params.get(strategy_name, {})
        url = generate_strategy_sheet(strategy_name, strategy_func, test_date, gc, params)
        
        if url:
            date_obj = datetime.strptime(test_date, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%d_%m_%Y")
            sheet_name = f"{strategy_name}_{formatted_date}"
            
            print(f"✅ Google Sheet creato con successo!")
            print(f"📊 Nome: {sheet_name}")
            print(f"🔗 URL: {url}")
            print(f"📋 Struttura: 2 colonne (Ticker | Signal)")
            return True
        else:
            print(f"❌ Errore nella creazione del Google Sheet")
            return False
        
    except Exception as e:
        print(f"❌ Errore nel test singola strategia: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_simplified_report_with_custom_dates():
    """
    Test del report semplificato con date personalizzate
    """
    print("\n" + "=" * 50)
    print("📅 TESTING SIMPLIFIED REPORT - CUSTOM DATES")
    print("=" * 50)
    
    test_dates = [
        '2025-08-20',
        '2025-08-21',
        '2025-08-22',
        '2025-08-23'
    ]
    
    all_results = {}
    
    for test_date in test_dates:
        print(f"\n📅 Testando data: {test_date}")
        try:
            results = generate_weekly_signals_report(test_date)
            successful = sum(1 for url in results.values() if url)
            all_results[test_date] = {'successful': successful, 'total': len(results), 'urls': results}
            
            print(f"   📊 Risultato: {successful}/{len(results)} Google Sheets generati")
            
            if successful > 0:
                date_obj = datetime.strptime(test_date, "%Y-%m-%d")
                formatted_date = date_obj.strftime("%d_%m_%Y")
                print(f"   📁 Sheets creati con suffisso: _{formatted_date}")
            
        except Exception as e:
            print(f"   ❌ Errore per data {test_date}: {e}")
            all_results[test_date] = {'successful': 0, 'total': 0, 'urls': {}}
    
    # Riepilogo finale
    print(f"\n📋 RIEPILOGO MULTI-DATE:")
    for date, result in all_results.items():
        print(f"   {date}: {result['successful']}/{result['total']} sheets")
    
    return all_results


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 TESTING SIMPLIFIED WEEKLY REPORT SYSTEM")
    print("=" * 60)
    
    # === TESTS REPORT SEMPLIFICATI ===
    
    # 1. Test dry run (CONSIGLIATO per iniziare - non crea Google Sheets reali)
    print("\n🔍 FASE 1: DRY RUN (nessun file creato)")
    test_simplified_report_dry_run()
    
    # 2. Test strategia singola (crea UN solo Google Sheet per test)
    print("\n🎯 FASE 2: TEST SINGOLA STRATEGIA")
    # Decommentare per testare creazione di UN singolo Google Sheet
    # test_simplified_report_single_strategy()
    
    # 3. Test report completo per una data (crea Google Sheets reali!)
    print("\n📊 FASE 3: TEST REPORT COMPLETO")
    # Decommentare per creare tutti i Google Sheets
    # test_simplified_weekly_report()
    
    # 4. Test con date multiple (crea MOLTI Google Sheets!)
    print("\n📅 FASE 4: TEST DATE MULTIPLE")
    # Decommentare per test con date diverse (ATTENZIONE: crea molti files!)
    # test_simplified_report_with_custom_dates()
    
    print(f"\n🎉 TESTS COMPLETED!")
    print(f"\n💡 SUGGERIMENTI:")
    print(f"   ✅ Fase 1 (dry run) è sempre sicura")
    print(f"   🎯 Fase 2 crea 1 solo Google Sheet per test")
    print(f"   📊 Fase 3 crea tutti i Google Sheets per 1 data")
    print(f"   📅 Fase 4 crea MOLTI Google Sheets (4 date x strategie)")
    print(f"   💡 Decommenta gradualmente le fasi che vuoi testare")
    print(f"   🗂️ I Google Sheets vengono creati in: WEEKLY_FOLDER_ID")