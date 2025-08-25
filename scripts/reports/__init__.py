# scripts/reports/__init__.py
"""
Reports Package

Moduli:
- generate_weekly_signals_report: Report settimanale completo
"""

from .generate_weekly_signals_report import generate_weekly_report

__all__ = ['generate_weekly_report']