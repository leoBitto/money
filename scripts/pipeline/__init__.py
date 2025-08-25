# scripts/pipeline/__init__.py  
"""
Pipeline Package

Moduli:
- update_db: Aggiornamento quotidiano database
"""

from .update_db import update_daily_prices

__all__ = ['update_daily_prices']