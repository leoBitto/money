```markdown
# Progetto Money – Documentazione Operativa

## 1. Scopo del progetto
Il progetto **Money** è una pipeline finanziaria che:
- Legge una lista di ticker da un Google Sheet.
- Scarica i prezzi di chiusura storici tramite `yfinance`.
- Inserisce/aggiorna i dati in un database PostgreSQL.
- Automatizza l’aggiornamento serale tramite un servizio systemd e un timer.

Questa documentazione serve come guida operativa per comprendere, deployare e manutenere il progetto.

---

## 2. Struttura del repository

```

money/
├── check\_db.py            # Script per verificare lo stato del DB
├── get\_history.py         # Script per scaricare dati storici da yfinance
├── init\_db.py             # Script di inizializzazione DB
├── update\_db.py           # Script principale per aggiornare prezzi giornalieri
├── logs/                  # Log delle esecuzioni
│   └── .gitkeep
├── scripts/               # Cartella con script di supporto
├── docs/                  # Documentazione
│   └── readme.md
├── requirements.txt       # Dipendenze Python
├── env/                   # Virtualenv (non versionato)
└── .gitignore

````

---

## 3. Requisiti

- Python 3.10+
- PostgreSQL accessibile
- VM Linux con accesso SSH
- Google Cloud Service Account per leggere i Google Sheets
- Pacchetti Python come indicato in `requirements.txt`:
  - `psycopg2-binary`
  - `pandas`
  - `numpy`
  - `yfinance`
  - `google-cloud-secret-manager`
  - `requests`
  - `python-dotenv`

---

## 4. Configurazione ambiente

### 4.1 Virtualenv
Creare l’ambiente virtuale nella root del progetto:

```bash
cd ~/money
python3 -m venv env
source env/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
deactivate
````

### 4.2 Secrets

I secrets gestiscono credenziali per:

* DB PostgreSQL (`DB_HOST`, `DB_USER`, ecc.)
* Google Service Account (`service_account.json`)
* VM SSH (per CI/CD)

Su GitHub, questi vengono configurati nelle **Actions Secrets**.

---

## 5. Aggiornamento dati

### 5.1 Script principale

`update_db.py`:

* Legge la lista dei ticker da Google Sheet.
* Ottiene i prezzi storici con `yfinance`.
* Inserisce/aggiorna i dati nella tabella `universe` del DB.
* Logga output e errori in `logs/update_db.log`.

### 5.2 Cronologia storica

Per popolare dati passati si utilizza `get_history.py`.
Evita blocchi di yfinance e duplicazioni nel DB.

---

## 6. Automazione con systemd

### 6.1 Service

`/etc/systemd/system/update_db.service`:

```ini
[Unit]
Description=Aggiorna database universe da Google Sheets
After=network.target

[Service]
Type=oneshot
User=leonardo_bitto1
WorkingDirectory=/home/leonardo_bitto1/money
ExecStart=/home/leonardo_bitto1/money/env/bin/python /home/leonardo_bitto1/money/scripts/pipeline/update_db.py
StandardOutput=append:/home/leonardo_bitto1/money/logs/update_db.log
StandardError=append:/home/leonardo_bitto1/money/logs/update_db.log
```

### 6.2 Timer

`/etc/systemd/system/update_db.timer`:

```ini
[Unit]
Description=Timer giornaliero per update_db

[Timer]
OnCalendar=*-*-* 23:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Abilitare e avviare il timer:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now update_db.timer
systemctl list-timers
```

---

## 7. CI/CD con GitHub Actions

* L’action fa `git pull` sulla VM dopo ogni push su `main`.
* Riavvia il service con:

```bash
sudo systemctl restart update_db.service
```

* I secrets necessari:

  * `SSH_PRIVATE_KEY`
  * `SERVER_USER`
  * `SERVER_HOST`
  * `SERVER_PATH` (es. `/home/leonardo_bitto1/money`)
  * `SERVICE_NAME` (es. `update_db.service`)

---

## 8. Debug e log

* Log delle esecuzioni: `logs/update_db.log`
* Controllare status service/timer:

```bash
systemctl status update_db.service
systemctl status update_db.timer
```

* Visualizzare log in tempo reale:

```bash
tail -f ~/money/logs/update_db.log
```

---

## 9. Prossimi passi

1. Popolare storico maggiore di ticker per backtest.
2. Costruire modulo portfolio e analisi.
3. Implementare strategie di trading e backtest.
4. Aggiornare documentazione in caso di cambiamenti in CI/CD o servizi.

---

## 10. Strategia di trading e generazione segnali

### 10.1 Modulo `strategies.py`
- Contiene tutte le strategie implementate.
- Ogni strategia è una funzione che riceve in input un DataFrame con dati storici:
  ```text
  Columns: date, ticker, open, high, low, close, volume
````

* Restituisce un **segnale** (`BUY`, `SELL`, `HOLD`) o un codice numerico.
* Documentazione interna:

  * Docstring in Google-style con parametri e output.
  * Spiegazione tecnica e logica della strategia:

    * Perché funziona.
    * Quando è più efficace.
* Strategie attualmente implementate:

  * `moving_average_crossover`
  * `rsi_strategy`
  * `momentum_breakout`
  * Altre possono essere aggiunte seguendo lo stesso schema.

### 10.2 Funzione `generate_signals`

* Input:

  1. `strategy_func` → funzione strategia dal modulo `strategies.py`.
  2. `tickers` → lista di ticker da analizzare.
  3. `date` → data di riferimento.
* Output:

  * DataFrame con colonne: `ticker`, `signal`.
* Funzionamento:

  1. Recupera i dati storici dal DB `universe`.
  2. Applica la strategia a ciascun ticker.
  3. Costruisce un DataFrame dei segnali generati.
* Uso tipico:

  ```python
  df_signals = generate_signals(strategy_func=strategies.moving_average_crossover, tickers=['SPY','AAPL'], date='2025-08-23')
  ```

### 10.3 Generazione report settimanale

* Script: `create_weekly_signals_report.py`
* Funzioni principali:

  1. Recupera la lista dei ticker dal DB.
  2. Cicla su tutte le strategie definite in `strategies.py`.
  3. Genera segnali per ciascuna strategia.
  4. Crea un Google Sheet nella cartella Drive:

     ```
     Reports/Weekly
     ```

     con nome:

     ```
     <strategy_name>_<data>
     ```
* Questo report permette di consultare i segnali il weekend e programmare i trigger nel broker.

### 10.4 Test dei segnali

* Script: `test.py`
* Permette di:

  * Generare segnali per una singola strategia.
  * Generare segnali per tutte le strategie.
  * Testare la creazione del report settimanale.
* Serve per debug e sviluppo senza eseguire cron/systemd.

### 10.5 Pipeline completa strategie → report

1. Scrivere/aggiornare strategie in `strategies.py`.
2. Recuperare dati storici dal DB `universe`.
3. Chiamare `generate_signals` con ticker e data.
4. Salvare i segnali in un DataFrame.
5. Generare report settimanale con `create_weekly_signals_report.py` (Drive `Reports/Weekly`).

---

## 11. Note operative

* Tutti gli script devono essere eseguiti nell’ambiente virtuale `env`.
* Gli import devono essere coerenti:

  ```python
  from scripts.trading import strategies
  from scripts.trading.generate_signals import generate_signals
  ```
* I report settimanali vengono generati automaticamente tramite systemd / timer (opzionale per test manuali).

```

