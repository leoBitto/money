# ~/money/test.py

from scripts import config
from scripts import database as db


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 CREATE PORTFOLIO TABLES ")
    print("=" * 60)
    query = f"""
CREATE TABLE portfolio_positions (
    date DATE NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    
    -- Dati posizione base
    shares INTEGER NOT NULL,                      -- numero azioni possedute
    avg_cost DECIMAL(10,4) NOT NULL,             -- costo medio di acquisto
    current_price DECIMAL(10,4) NOT NULL,        -- prezzo corrente
    current_value DECIMAL(12,2) NOT NULL,        -- valore corrente (shares * current_price)
    
    -- Metriche posizione
    position_weight_pct DECIMAL(8,4),            -- peso % nel portafoglio totale
    position_pnl_pct DECIMAL(8,4),              -- P&L % dalla media acquisti
    position_volatility DECIMAL(8,4),            -- volatilità rolling 30 giorni della posizione
    position_sharpe DECIMAL(8,4),               -- sharpe ratio rolling 30 giorni della posizione
    
    -- Metriche di rischio posizione
    position_var_95 DECIMAL(12,2),              -- Value at Risk 95% (1 giorno)
    beta_vs_portfolio DECIMAL(6,4),             -- beta rispetto al portafoglio
    
    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    
    -- Chiavi
    PRIMARY KEY (date, ticker),
    FOREIGN KEY (date) REFERENCES portfolio_snapshots(date) ON DELETE CASCADE
);

-- Indici per performance  
CREATE INDEX idx_portfolio_positions_date ON portfolio_positions(date);
CREATE INDEX idx_portfolio_positions_ticker ON portfolio_positions(ticker);
CREATE INDEX idx_portfolio_positions_weight ON portfolio_positions(position_weight_pct DESC);

    """
    db.execute_query(query, fetch=False)
    