# ~/money/test.py

from scripts import config
from scripts import database as db


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 CREATE PORTFOLIO TABLES ")
    print("=" * 60)
    query = f"""
ALTER TABLE portfolio_snapshots
    ADD COLUMN portfolio_name VARCHAR(50) DEFAULT 'default';

ALTER TABLE portfolio_positions
    ADD COLUMN portfolio_name VARCHAR(50) DEFAULT 'default';

ALTER TABLE portfolio_positions
    DROP CONSTRAINT portfolio_positions_pkey,
    ADD PRIMARY KEY (date, ticker, portfolio_name);

    """
    db.execute_query(query, fetch=False)
    