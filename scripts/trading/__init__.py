# scripts/trading/__init__.py
"""
Trading Package

Moduli:
- strategies: Funzioni strategia trading
- generate_signals: Generazione segnali per le strategie
"""

from .generate_signals import generate_signals, generate_all_strategies_signals
from . import strategies

__all__ = ['generate_signals', 'generate_all_strategies_signals', 'strategies']
