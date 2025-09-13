# scripts/portfolio.py
"""
Modulo semplificato Portfolio / Position / Trade
================================================

- Portfolio: gestisce cash, posizioni, trade e snapshot
- Position: singola posizione con logica stop/profit
- Trade: singolo trade eseguito

Uso tipico:

>>> portfolio = Portfolio("demo", "2025-09-01", 10000)
>>> portfolio.execute_trade("AAPL", "BUY", 10, price=150.0, stop_loss=140, profit_target=180)
>>> portfolio.get_positions_count()
>>> portfolio.get_cash_balance()
>>> portfolio._trades  # lista dei trade eseguiti
"""

from typing import Dict, List, Optional
from datetime import datetime

# ================================
# POSITION
# ================================

class Position:
    def __init__(self, ticker: str, shares: int, avg_cost: float,
                 stop_loss: Optional[float] = None,
                 profit_target: Optional[float] = None):
        self.ticker = ticker.upper()
        self.shares = shares
        self.avg_cost = avg_cost
        self.stop_loss = stop_loss
        self.profit_target = profit_target

    def get_current_value(self) -> float:
        return self.avg_cost * self.shares

    def get_unrealized_pnl(self, current_price: float) -> float:
        return (current_price - self.avg_cost) * self.shares

    def get_unrealized_pnl_pct(self, current_price: float) -> float:
        if self.avg_cost == 0:
            return 0.0
        return ((current_price - self.avg_cost) / self.avg_cost) * 100

    def is_stop_loss_hit(self, current_price: float) -> bool:
        return self.stop_loss is not None and current_price <= self.stop_loss

    def is_profit_target_hit(self, current_price: float) -> bool:
        return self.profit_target is not None and current_price >= self.profit_target

# ================================
# TRADE
# ================================

class Trade:
    def __init__(self, ticker: str, operation: str, quantity: int, price: float,
                 stop_loss: Optional[float] = None, profit_target: Optional[float] = None):
        self.ticker = ticker.upper()
        self.operation = operation.upper()  # BUY o SELL
        self.quantity = quantity
        self.price = price
        self.stop_loss = stop_loss
        self.profit_target = profit_target

    def get_value(self) -> float:
        return self.quantity * self.price

    def __repr__(self):
        return f"<Trade {self.operation} {self.quantity} {self.ticker} @ {self.price}>"

# ================================
# PORTFOLIO
# ================================

class Portfolio:
    def __init__(self, name: str, date: str, initial_cash: float = 10000.0):
        self.name = name
        self.date = date
        self._snapshot = {
            "cash_balance": initial_cash,
            "total_value": initial_cash,
            "positions_count": 0
        }
        self._positions: Dict[str, Position] = {}
        self._trades: List[Trade] = []

    # ----------------------------
    # Accessori
    # ----------------------------

    def get_cash_balance(self) -> float:
        return self._snapshot["cash_balance"]

    def get_positions_count(self) -> int:
        return len([p for p in self._positions.values() if p.shares > 0])

    def get_total_value(self) -> float:
        positions_value = sum(p.get_current_value() for p in self._positions.values())
        return self._snapshot["cash_balance"] + positions_value

    def get_position(self, ticker: str) -> Optional[Position]:
        return self._positions.get(ticker.upper())

    # ----------------------------
    # Trading
    # ----------------------------

    def execute_trade(self, ticker: str, operation: str, quantity: int,
                      price: float, stop_loss: Optional[float] = None,
                      profit_target: Optional[float] = None) -> None:
        operation = operation.upper()
        if operation not in ["BUY", "SELL"]:
            raise ValueError("Operazione deve essere BUY o SELL")

        ticker = ticker.upper()
        total_cost = price * quantity

        if operation == "BUY":
            if total_cost > self.get_cash_balance():
                raise ValueError(f"Cash insufficiente per comprare {quantity} {ticker}")
            self._snapshot["cash_balance"] -= total_cost
            self._add_or_update_position(ticker, quantity, price, stop_loss, profit_target)
        else:  # SELL
            pos = self.get_position(ticker)
            if not pos or pos.shares < quantity:
                raise ValueError(f"Azioni insufficienti per vendere {quantity} {ticker}")
            self._snapshot["cash_balance"] += total_cost
            pos.shares -= quantity
            if pos.shares == 0:
                pos.stop_loss = None
                pos.profit_target = None

        self._snapshot["positions_count"] = self.get_positions_count()
        self._trades.append(Trade(ticker, operation, quantity, price, stop_loss, profit_target))

    def _add_or_update_position(self, ticker: str, quantity: int, price: float,
                                stop_loss: Optional[float], profit_target: Optional[float]) -> None:
        pos = self.get_position(ticker)
        if pos:
            new_shares = pos.shares + quantity
            new_avg_cost = ((pos.shares * pos.avg_cost) + (quantity * price)) / new_shares
            pos.shares = new_shares
            pos.avg_cost = new_avg_cost
            if stop_loss is not None:
                pos.stop_loss = stop_loss
            if profit_target is not None:
                pos.profit_target = profit_target
        else:
            self._positions[ticker] = Position(ticker, quantity, price, stop_loss, profit_target)

    # ----------------------------
    # Helper
    # ----------------------------

    def list_trades(self) -> List[Trade]:
        return self._trades

    def snapshot(self) -> dict:
        return {
            "date": self.date,
            "cash_balance": self._snapshot["cash_balance"],
            "total_value": self.get_total_value(),
            "positions_count": self.get_positions_count(),
            "positions": {t: vars(p) for t, p in self._positions.items()},
            "trades": [vars(tr) for tr in self._trades]
        }
