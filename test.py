# ~/money/test.py

from scripts import config
from scripts import database as db


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 CREATE PORTFOLIO TABLES ")
    print("=" * 60)
    query = f"""
    CREATE TABLE portfolio_snapshots (
    date DATE PRIMARY KEY,
    
    -- Valori base portafoglio
    total_value DECIMAL(12,2) NOT NULL,           -- valore totale portafoglio (posizioni + cash)
    cash_balance DECIMAL(12,2) NOT NULL,          -- cash disponibile
    positions_count INTEGER DEFAULT 0,            -- numero posizioni aperte
    
    -- Metriche di performance
    daily_return_pct DECIMAL(8,4),                -- rendimento giornaliero %
    portfolio_volatility DECIMAL(8,4),            -- volatilità rolling 30 giorni
    portfolio_sharpe DECIMAL(8,4),                -- sharpe ratio rolling 30 giorni
    
    -- Metriche di rischio
    max_drawdown_pct DECIMAL(8,4),               -- max drawdown storico %
    current_drawdown_pct DECIMAL(8,4),           -- drawdown corrente da picco %
    peak_value DECIMAL(12,2),                    -- valore picco storico
    consecutive_loss_days INTEGER DEFAULT 0,      -- giorni perdita consecutiva
    
    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indici per performance
CREATE INDEX idx_portfolio_snapshots_date ON portfolio_snapshots(date);

    """
    db.execute_query(query, fetch=FALSE)
    