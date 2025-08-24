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
ExecStart=/home/leonardo_bitto1/money/env/bin/python /home/leonardo_bitto1/money/scripts/update_db.py
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

**Fine documento**

```
