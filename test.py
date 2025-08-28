# test_portfolio.py
"""
Script di Test per il Sistema Portfolio
======================================

Testa tutte le funzionalità del modulo portfolio.py:
1. Creazione tabelle DB
2. Creazione portfolio vuoto
3. Creazione portfolio con posizioni iniziali  
4. Operazioni BUY/SELL
5. Lettura dati e verifiche

PREREQUISITI:
- Database PostgreSQL configurato
- Tabella 'universe' con dati storici (per prezzi)
- Credenziali Google Cloud configurate

UTILIZZO:
python test_portfolio.py
"""

import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal
import pandas as pd

# Aggiungi la root del progetto al path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scripts.portfolio import (
    create_portfolio_tables,
    create_portfolio, 
    add_operation,
    get_portfolio_snapshot,
    get_portfolio_positions,
    get_portfolio_snapshots_bulk
)
from scripts.database import get_available_tickers, execute_query

# Configurazione test
TEST_PORTFOLIO_NAME = "test_demo"
INITIAL_CASH = 10000.0
TEST_DATE = "2025-08-28"

def test_1_create_tables():
    """Test 1: Creazione tabelle portfolio"""
    print("\n" + "="*60)
    print("🧪 TEST 1: Creazione Tabelle DB")
    print("="*60)
    
    try:
        execute_query("DROP TABLE IF EXISTS portfolio_positions CASCADE", fetch=False)
        execute_query("DROP TABLE IF EXISTS portfolio_snapshots CASCADE", fetch=False)
        create_portfolio_tables()
        print("✅ Test 1 PASSATO: Tabelle create con successo")
        return True
    except Exception as e:
        print(f"❌ Test 1 FALLITO: {e}")
        return False

def test_2_empty_portfolio():
    """Test 2: Creazione portfolio vuoto"""
    print("\n" + "="*60)
    print("🧪 TEST 2: Portfolio Vuoto")
    print("="*60)
    
    try:
        # Crea portfolio vuoto
        create_portfolio(
            name=TEST_PORTFOLIO_NAME + "_empty",
            initial_cash=INITIAL_CASH,
            date=TEST_DATE,
            overwrite=True
        )
        
        # Verifica snapshot
        snapshot = get_portfolio_snapshot(TEST_DATE, TEST_PORTFOLIO_NAME + "_empty")
        assert snapshot is not None, "Snapshot non trovato"
        assert snapshot['total_value'] == INITIAL_CASH, f"Valore totale errato: {snapshot['total_value']}"
        assert snapshot['cash_balance'] == INITIAL_CASH, f"Cash balance errato: {snapshot['cash_balance']}"
        assert snapshot['positions_count'] == 0, f"Numero posizioni errato: {snapshot['positions_count']}"
        
        print(f"✅ Portfolio vuoto creato: ${snapshot['total_value']:,.2f}")
        print("✅ Test 2 PASSATO: Portfolio vuoto funziona")
        return True
        
    except Exception as e:
        print(f"❌ Test 2 FALLITO: {e}")
        return False

def test_3_portfolio_with_positions():
    """Test 3: Portfolio con posizioni iniziali"""
    print("\n" + "="*60)
    print("🧪 TEST 3: Portfolio con Posizioni Iniziali")
    print("="*60)
    
    try:
        # Ottieni alcuni ticker disponibili
        available_tickers = get_available_tickers()
        if len(available_tickers) < 2:
            print("⚠️ Test 3 SALTATO: Servono almeno 2 ticker nel DB")
            return True
            
        test_tickers = available_tickers[:2]
        print(f"📊 Usando ticker: {test_tickers}")
        
        # Definisci posizioni iniziali
        initial_positions = {
            test_tickers[0]: {"shares": 10, "avg_cost": 150.0},
            test_tickers[1]: {"shares": 5, "avg_cost": 300.0}
        }
        
        # Crea portfolio
        create_portfolio(
            name=TEST_PORTFOLIO_NAME + "_positions",
            initial_cash=5000.0,
            positions=initial_positions,
            date=TEST_DATE,
            overwrite=True
        )
        
        # Verifica snapshot
        snapshot = get_portfolio_snapshot(TEST_DATE, TEST_PORTFOLIO_NAME + "_positions")
        assert snapshot is not None, "Snapshot non trovato"
        assert snapshot['positions_count'] == 2, f"Numero posizioni errato: {snapshot['positions_count']}"
        assert snapshot['total_value'] > 5000.0, "Valore totale dovrebbe essere > cash iniziale"
        
        # Verifica posizioni
        positions = get_portfolio_positions(TEST_DATE, TEST_PORTFOLIO_NAME + "_positions")
        assert len(positions) == 2, f"Numero posizioni DataFrame errato: {len(positions)}"
        
        print(f"✅ Portfolio con posizioni creato:")
        print(f"   💰 Valore totale: ${snapshot['total_value']:,.2f}")
        print(f"   💵 Cash: ${snapshot['cash_balance']:,.2f}")
        print(f"   📊 Posizioni: {snapshot['positions_count']}")
        print("✅ Test 3 PASSATO: Portfolio con posizioni funziona")
        return True
        
    except Exception as e:
        print(f"❌ Test 3 FALLITO: {e}")
        return False

def test_4_buy_operation():
    """Test 4: Operazione di acquisto"""
    print("\n" + "="*60)
    print("🧪 TEST 4: Operazione BUY")
    print("="*60)
    
    try:
        # Usa il portfolio vuoto creato nel test 2
        portfolio_name = TEST_PORTFOLIO_NAME + "_empty"
        
        # Ottieni ticker disponibile
        available_tickers = get_available_tickers()
        if not available_tickers:
            print("⚠️ Test 4 SALTATO: Nessun ticker disponibile nel DB")
            return True
            
        test_ticker = available_tickers[0]
        print(f"📊 Comprando: {test_ticker}")
        
        # Esegui operazione BUY
        add_operation(
            portfolio_name=portfolio_name,
            action="BUY",
            ticker=test_ticker,
            shares=10,
            price=155.50,
            date=TEST_DATE
        )
        
        # Verifica risultati
        snapshot = get_portfolio_snapshot(TEST_DATE, portfolio_name)
        positions = get_portfolio_positions(TEST_DATE, portfolio_name)
        
        assert snapshot is not None, "Snapshot non trovato dopo BUY"
        assert snapshot['positions_count'] == 1, f"Dovrebbe esserci 1 posizione, trovate: {snapshot['positions_count']}"
        assert len(positions) == 1, f"DataFrame posizioni dovrebbe avere 1 riga, ha: {len(positions)}"
        assert positions.iloc[0]['ticker'] == test_ticker, "Ticker posizione errato"
        assert positions.iloc[0]['shares'] == 10, "Numero shares errato"
        
        expected_cost = 10 * 155.50
        expected_cash = INITIAL_CASH - expected_cost
        assert abs(snapshot['cash_balance'] - expected_cash) < 0.01, f"Cash balance errato: {snapshot['cash_balance']}"
        
        print(f"✅ Operazione BUY completata:")
        print(f"   📊 {test_ticker}: 10 shares @ $155.50")
        print(f"   💵 Cash rimanente: ${snapshot['cash_balance']:,.2f}")
        print("✅ Test 4 PASSATO: Operazione BUY funziona")
        return True
        
    except Exception as e:
        print(f"❌ Test 4 FALLITO: {e}")
        return False

def test_5_sell_operation():
    """Test 5: Operazione di vendita"""
    print("\n" + "="*60)
    print("🧪 TEST 5: Operazione SELL")
    print("="*60)
    
    try:
        # Usa il portfolio del test 4
        portfolio_name = TEST_PORTFOLIO_NAME + "_empty"
        
        # Ottieni posizione corrente
        positions = get_portfolio_positions(TEST_DATE, portfolio_name)
        if positions.empty:
            print("⚠️ Test 5 SALTATO: Nessuna posizione da vendere")
            return True
            
        test_ticker = positions.iloc[0]['ticker']
        current_shares = positions.iloc[0]['shares']
        
        # Vendi metà posizione
        sell_shares = 5
        sell_price = 160.00
        
        print(f"📊 Vendendo: {sell_shares} shares di {test_ticker} @ ${sell_price}")
        
        # Esegui operazione SELL
        add_operation(
            portfolio_name=portfolio_name,
            action="SELL",
            ticker=test_ticker,
            shares=sell_shares,
            price=sell_price,
            date=TEST_DATE
        )
        
        # Verifica risultati
        snapshot = get_portfolio_snapshot(TEST_DATE, portfolio_name)
        positions_after = get_portfolio_positions(TEST_DATE, portfolio_name)
        
        assert snapshot is not None, "Snapshot non trovato dopo SELL"
        
        if len(positions_after) > 0:
            # Dovrebbe rimanere una posizione ridotta
            assert positions_after.iloc[0]['shares'] == (current_shares - sell_shares), "Shares rimanenti errate"
            print(f"✅ Posizione ridotta: {positions_after.iloc[0]['shares']} shares rimanenti")
        else:
            print("✅ Posizione completamente venduta")
        
        print(f"   💵 Nuovo cash balance: ${snapshot['cash_balance']:,.2f}")
        print("✅ Test 5 PASSATO: Operazione SELL funziona")
        return True
        
    except Exception as e:
        print(f"❌ Test 5 FALLITO: {e}")
        return False

def test_6_bulk_read():
    """Test 6: Lettura bulk per backtest"""
    print("\n" + "="*60)
    print("🧪 TEST 6: Lettura Bulk Snapshots")
    print("="*60)
    
    try:
        # Crea alcuni snapshots per diverse date
        portfolio_name = TEST_PORTFOLIO_NAME + "_bulk"
        
        test_dates = [
            "2025-08-26",
            "2025-08-27", 
            "2025-08-28"
        ]
        
        for i, date in enumerate(test_dates):
            create_portfolio(
                name=portfolio_name,
                initial_cash=10000.0 + (i * 100),  # Varia leggermente il capitale
                date=date,
                overwrite=True
            )
        
        # Test lettura bulk
        snapshots = get_portfolio_snapshots_bulk(
            start_date="2025-08-25",
            end_date="2025-08-29", 
            portfolio_name=portfolio_name
        )
        
        assert len(snapshots) == 3, f"Dovrebbero esserci 3 snapshots, trovati: {len(snapshots)}"
        
        for date in test_dates:
            assert date in snapshots, f"Snapshot per data {date} non trovato"
            
        print(f"✅ Lettura bulk completata: {len(snapshots)} snapshots")
        for date, data in snapshots.items():
            print(f"   📅 {date}: ${data['total_value']:,.2f}")
            
        print("✅ Test 6 PASSATO: Lettura bulk funziona")
        return True
        
    except Exception as e:
        print(f"❌ Test 6 FALLITO: {e}")
        return False

def test_7_error_handling():
    """Test 7: Gestione errori"""
    print("\n" + "="*60)
    print("🧪 TEST 7: Gestione Errori")
    print("="*60)
    
    try:
        portfolio_name = TEST_PORTFOLIO_NAME + "_errors"
        
        # Test 1: Portfolio inesistente
        snapshot = get_portfolio_snapshot("2025-01-01", "portfolio_inesistente")
        assert snapshot is None, "Dovrebbe restituire None per portfolio inesistente"
        print("✅ Portfolio inesistente gestito correttamente")
        
        # Test 2: Cash insufficiente
        create_portfolio(portfolio_name, 100.0, date=TEST_DATE, overwrite=True)
        
        try:
            add_operation(
                portfolio_name=portfolio_name,
                action="BUY",
                ticker="AAPL",
                shares=100,
                price=200.0,  # Costo totale: $20,000 > $100 disponibili
                date=TEST_DATE
            )
            print("❌ Dovrebbe aver sollevato errore per cash insufficiente")
            return False
        except ValueError as e:
            if "Cash insufficiente" in str(e):
                print("✅ Errore cash insufficiente gestito correttamente")
            else:
                print(f"❌ Errore imprevisto: {e}")
                return False
        
        # Test 3: Vendita di posizione inesistente
        try:
            add_operation(
                portfolio_name=portfolio_name,
                action="SELL",
                ticker="TICKER_INESISTENTE",
                shares=10,
                price=100.0,
                date=TEST_DATE
            )
            print("❌ Dovrebbe aver sollevato errore per ticker inesistente")
            return False
        except ValueError as e:
            if "posizione non esistente" in str(e):
                print("✅ Errore vendita posizione inesistente gestito correttamente")
            else:
                print(f"❌ Errore imprevisto: {e}")
                return False
        
        print("✅ Test 7 PASSATO: Gestione errori funziona")
        return True
        
    except Exception as e:
        print(f"❌ Test 7 FALLITO: {e}")
        return False

def cleanup_test_data():
    """Pulizia dati di test"""
    print("\n" + "="*60)
    print("🧹 CLEANUP: Rimozione Dati di Test")
    print("="*60)
    
    try:
        from scripts.database import execute_query
        
        # Lista portfolio di test da rimuovere
        test_portfolios = [
            TEST_PORTFOLIO_NAME + "_empty",
            TEST_PORTFOLIO_NAME + "_positions", 
            TEST_PORTFOLIO_NAME + "_bulk",
            TEST_PORTFOLIO_NAME + "_errors"
        ]
        
        for portfolio in test_portfolios:
            # Rimuovi posizioni
            execute_query(
                "DELETE FROM portfolio_positions WHERE portfolio_name = %s",
                (portfolio,),
                fetch=False
            )
            # Rimuovi snapshots
            execute_query(
                "DELETE FROM portfolio_snapshots WHERE portfolio_name = %s", 
                (portfolio,),
                fetch=False
            )
            
        print(f"✅ Rimossi {len(test_portfolios)} portfolio di test")
        
    except Exception as e:
        print(f"⚠️ Errore durante cleanup: {e}")

def main():
    """Esecuzione di tutti i test"""
    print("🚀 AVVIO TEST SISTEMA PORTFOLIO")
    print("="*80)
    
    tests = [
        ("Creazione Tabelle", test_1_create_tables),
        ("Portfolio Vuoto", test_2_empty_portfolio),
        ("Portfolio con Posizioni", test_3_portfolio_with_positions),
        ("Operazione BUY", test_4_buy_operation),
        ("Operazione SELL", test_5_sell_operation),
        ("Lettura Bulk", test_6_bulk_read),
        ("Gestione Errori", test_7_error_handling),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ ERRORE CRITICO in {test_name}: {e}")
            results.append((test_name, False))
    
    # Cleanup
    cleanup_test_data()
    
    # Risultati finali
    print("\n" + "="*80)
    print("📊 RISULTATI FINALI")
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSATO" if result else "❌ FALLITO"
        print(f"   {test_name:<25} {status}")
    
    print(f"\n🎯 RISULTATO: {passed}/{total} test passati")
    
    if passed == total:
        print("🎉 TUTTI I TEST SONO PASSATI! Sistema portfolio pronto per produzione.")
    else:
        print("⚠️ ALCUNI TEST SONO FALLITI. Controllare gli errori prima di procedere.")
    
    return passed == total

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️ Test interrotti dall'utente")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Errore critico: {e}")
        sys.exit(1)