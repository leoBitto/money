# ~/money/test.py

from scripts.trading.generate_signals import generate_signals, generate_all_strategies_signals
from scripts.trading import strategies
import pandas as pd
from datetime import datetime, timedelta

def test_single_strategy():
    """
    Test function to generate signals for a single strategy on a given date.
    """
    print("=" * 50)
    print("🔍 TESTING SINGLE STRATEGY - Moving Average Crossover")
    print("=" * 50)
    
    try:
        # Test con parametri di default
        df = generate_signals(
            strategy_func=strategies.moving_average_crossover, 
            date='2025-08-23'
        )
        print(f"✅ Segnali generati per {len(df)} ticker")
        print(f"📊 Distribuzione segnali:")
        print(df['signal'].value_counts())
        print(f"\n📋 Prime 10 righe:")
        print(df.head(10))
        
        # Test con parametri personalizzati
        print(f"\n🔧 Test con parametri personalizzati (MA 10-30)...")
        df_custom = generate_signals(
            strategy_func=strategies.moving_average_crossover, 
            date='2025-08-23',
            short_window=10,
            long_window=30
        )
        print(f"✅ Segnali generati: {len(df_custom)} ticker")
        print(f"📊 Distribuzione segnali personalizzati:")
        print(df_custom['signal'].value_counts())
        
    except Exception as e:
        print(f"❌ Errore nel test singola strategia: {e}")

def test_single_strategy_specific_tickers():
    """
    Test con ticker specifici
    """
    print("\n" + "=" * 50)
    print("🎯 TESTING STRATEGY CON TICKER SPECIFICI - rsi strategy")
    print("=" * 50)
    
    # Lista di ticker di esempio (modifica secondo i tuoi dati)
    test_tickers = ["AAPL", "GOOGL", "MSFT", "TSLA", "AMZN"]
    
    try:
        df = generate_signals(
            strategy_func=strategies.rsi_strategy,
            date='2025-08-23',
            tickers=test_tickers,
            period=14,
            overbought=70,
            oversold=30
        )
        print(f"✅ Segnali RSI per {len(df)} ticker specifici")
        print(f"📊 Distribuzione segnali:")
        print(df['signal'].value_counts())
        print(f"\n📋 Risultati completi:")
        print(df)
        
    except Exception as e:
        print(f"❌ Errore nel test ticker specifici: {e}")

def test_manual_strategies():
    """
    Test manuale delle singole strategie con controllo più dettagliato
    """
    print("\n" + "=" * 50)
    print("🔧 TESTING MANUAL STRATEGIES")
    print("=" * 50)
    
    strategies_to_test = [
        {
            'name': 'Moving Average Crossover',
            'func': strategies.moving_average_crossover,
            'params': {'short_window': 5, 'long_window': 15}
        },
        {
            'name': 'RSI Strategy', 
            'func': strategies.rsi_strategy,
            'params': {'period': 14, 'overbought': 75, 'oversold': 25}
        },
        {
            'name': 'Breakout Strategy',
            'func': strategies.breakout_strategy,
            'params': {'lookback': 20}
        }
    ]

    for strategy_info in strategies_to_test:
        print(f"\n📈 Testing {strategy_info['name']}...")
        try:
            df = generate_signals(
                strategy_func=strategy_info['func'],
                date='2025-08-23',
                **strategy_info['params']
            )
            
            print(f"   ✅ Ticker processati: {len(df)}")
            signal_dist = df['signal'].value_counts()
            total_signals = len(df)
            
            for signal_val in [-1, 0, 1]:
                count = signal_dist.get(signal_val, 0)
                percentage = (count / total_signals * 100) if total_signals > 0 else 0
                signal_name = {-1: 'Sell', 0: 'Hold', 1: 'Buy'}[signal_val]
                print(f"   {signal_name}: {count} ({percentage:.1f}%)")
                
        except Exception as e:
            print(f"   ❌ Errore: {e}")

def test_date_range():
    """
    Test con diverse date per vedere l'evoluzione dei segnali
    """
    print("\n" + "=" * 50)
    print("📅 TESTING DATE RANGE")
    print("=" * 50)
    
    # Test con diverse date
    test_dates = [
        '2025-08-20',
        '2025-08-21', 
        '2025-08-22',
        '2025-08-23'
    ]
    
    for test_date in test_dates:
        print(f"\n📅 Data: {test_date}")
        try:
            df = generate_signals(
                strategy_func=strategies.moving_average_crossover,
                date=test_date,
                short_window=3,
                long_window=5
            )
            
            if not df.empty:
                signal_counts = df['signal'].value_counts()
                print(f"   Ticker: {len(df)}, "
                      f"Buy: {signal_counts.get(1, 0)}, "
                      f"Hold: {signal_counts.get(0, 0)}, "
                      f"Sell: {signal_counts.get(-1, 0)}")
            else:
                print("   ❌ Nessun dato disponibile")
                
        except Exception as e:
            print(f"   ❌ Errore: {e}")


if __name__ == "__main__":
    print("🚀 STARTING TRADING SIGNALS TESTS")
    print("=" * 60)
    
    # Commenta/decommenta quello che vuoi testare
    
    # Test base
    test_single_strategy()
    
    # Test con ticker specifici
    test_single_strategy_specific_tickers()
    
    # Test manuale dettagliato
    test_manual_strategies()
    
    # Test con diverse date
    test_date_range()
    
    print(f"\n🎉 TESTS COMPLETED!")