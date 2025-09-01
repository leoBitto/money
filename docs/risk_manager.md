# Risk Manager - Sistema di Gestione del Rischio

## Panoramica del Sistema

Il Risk Manager è il modulo centrale che trasforma i segnali di trading grezzi in decisioni operative concrete, applicando regole di gestione del rischio e position sizing.

### Architettura del Flusso

```
[SIGNALS] → [RISK MANAGER] → [PORTFOLIO EXECUTION]
    ↓             ↓                    ↓
HOLD/BUY/SELL  Analisi Risk     Ordini Eseguibili
 (semplici)   + Position Size   + Stop/Target
```

## Schema di Funzionamento

### 1. Input del Sistema
- **Segnali da Signals Module**: 
  - `HOLD` / `BUY` / `SELL` senza potenza dichiarata
  - Ticker, prezzo corrente, ATR
- **Dati Portfolio**:
  - Posizioni attuali, cash disponibile, performance

### 2. Gerarchia delle Decisioni

#### PRIORITÀ 1: SELL (Protezione Capitale)
```
IF posizione_esistente:
    ✓ Stop Loss raggiunto → SELL IMMEDIATO
    ✓ First Target raggiunto → SELL 50% + sposta stop a breakeven
    ✓ Breakeven dopo first target → SELL rimanente 50%
    ✓ Segnale strategia SELL → SELL (se non in 2-for-1)
```

#### PRIORITÀ 2: BUY (Crescita Capitale)
```
IF segnale BUY AND no_posizione_esistente:
    1. Verifica slots disponibili (max 5 posizioni)
    2. Calcola position size (2% risk)
    3. Imposta stop loss e targets (strategia 2-for-1)
    4. Esegui ordine
```

## Strategia 2-for-1 Dettagliata

### Meccanismo di Funzionamento

1. **Entry**: 
   - Position size basato su 2% di rischio del portfolio totale
   - Stop loss = Entry Price - (2 × ATR)
   - First Target = Entry Price + (2 × Risk per Share)

2. **Prima Fase**:
   - Quando prezzo raggiunge First Target → Vendi 50% delle shares
   - **Risultato**: Hai già incassato 2× il rischio iniziale su metà posizione
   - Sposta stop loss delle shares rimanenti a **breakeven** (prezzo di entrata)

3. **Seconda Fase**:
   - **Scenario A**: Prezzo continua a salire → Profitto "gratuito" illimitato
   - **Scenario B**: Prezzo scende a breakeven → Esci a pareggio
   - **Risultato Netto**: Nel peggiore dei casi hai guadagnato quanto avresti rischiato

### Esempio Pratico
```
Entry: €100, ATR: €2, Portfolio: €10.000
├─ Stop Loss: €96 (rischio €4/share)
├─ Position Size: 50 shares (€200 rischio = 2% di €10.000)
├─ First Target: €108 (+€8/share)
│
└─ Al First Target:
   ├─ Vendi 25 shares a €108 = +€200 (breakeven garantito)
   ├─ Stop rimanenti 25 shares → €100 (breakeven)
   └─ Upside illimitato su 25 shares residue
```

## Parametri di Configurazione

### Risk Management
- **Max Posizioni Simultanee**: 5
- **Risk per Trade**: 2% del portfolio totale
- **Stop Loss**: 2× ATR sotto entry price
- **Cash Buffer**: Mantieni 10% cash per sicurezza

### Position Sizing
```python
Risk per Trade = Portfolio Totale × 2%
Stop Distance = 2 × ATR
Shares = Risk per Trade ÷ Stop Distance
```

### Selezione Segnali Multipli
Quando ricevi più segnali BUY dello stesso momento:
1. Ordina alfabeticamente (per ora - implementazione semplice)
2. Calcola position size per ciascuno in ordine
3. Sottrai cash utilizzato dal budget disponibile
4. Continua fino a 5 posizioni massime o cash esaurito

## Struttura Database

### Tabelle Esistenti (Portfolio)
```sql
portfolio_snapshots: tracking performance generale
portfolio_positions: posizioni correnti con metriche
```

### Campi Aggiuntivi Necessari
```sql
-- Aggiungi a portfolio_positions:
stop_loss DECIMAL(10,4)           -- Stop loss corrente
first_target DECIMAL(10,4)        -- Target per prima metà
breakeven DECIMAL(10,4)           -- Prezzo breakeven  
first_half_sold BOOLEAN           -- Flag prima metà venduta
entry_atr DECIMAL(6,4)           -- ATR al momento dell'entry
```

## Flusso Operativo Dettagliato

### Morning Routine
1. **Portfolio Snapshot**: Calcola stato corrente
2. **Signal Processing**: Ricevi segnali da Signals module
3. **Risk Analysis**: Applica Risk Manager
4. **Order Generation**: Crea ordini eseguibili
5. **Execution**: Invia ordini al broker/simulatore

### Gestione Real-Time
- **Price Updates**: Monitora stop loss e target continuamente  
- **Position Updates**: Aggiorna database ad ogni modifica
- **Performance Tracking**: Traccia P&L e drawdown

## Vantaggi della Strategia

### Risk Management
- **Limited Downside**: Stop loss fisso al 2% per trade
- **Protected Capital**: Breakeven garantito dopo first target
- **Diversification**: Max 5 posizioni simultanee

### Profit Optimization  
- **Asymmetric Risk/Reward**: Rischi 1, puoi guadagnare 2+ infinito
- **Trend Following**: Lascia correre i vincenti
- **Quick Profit Taking**: Assicura guadagni su metà posizione

### Semplicità Operativa
- **Clear Rules**: Decisioni automatizzate senza emozioni
- **Scalable**: Funziona con qualsiasi capitale
- **Measurable**: Ogni parametro è quantificabile

## Metriche di Performance da Tracciare

### Per Trade
- P&L realizzato/non realizzato
- Durata holding
- % raggiungimento first target
- % trades chiusi a breakeven vs stop loss

### Portfolio
- Sharpe Ratio
- Maximum Drawdown
- Win Rate
- Profit Factor (Gross Profit / Gross Loss)

## Next Steps Implementation

1. **Fase 1**: Implementa funzioni base del Risk Manager
2. **Fase 2**: Aggiungi campi database per 2-for-1 tracking
3. **Fase 3**: Crea monitoring dashboard per performance
4. **Fase 4**: Backtesting completo della strategia

---

*Questo documento evolverà man mano che raffiniamo e testiamo il sistema.*