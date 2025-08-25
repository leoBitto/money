# scripts/utils/db/__init__.py
"""
Database Utilities Package

Moduli:
- db_utils: DatabaseManager e operazioni database
- init_db: Inizializzazione schema database (standalone)
- check_db: Controllo e visualizzazione dati (standalone)  
- get_history: Download storico iniziale (standalone)
"""

from .db_utils import DatabaseManager

__all__ = ['DatabaseManager']
