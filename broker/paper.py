from __future__ import annotations
import uuid
from broker.base import Position, OrderResult

class PaperBroker:
    """Deterministic local paper broker used before any external API is enabled."""
    def __init__(self, cash: float, prices: dict[str, float]):
        self.cash = float(cash)
        self.prices = {k.upper(): float(v) for k, v in prices.items()}
        self._qty: dict[str, float] = {}

    def account_summary(self) -> dict:
        invested = sum(q * self.prices[s] for s, q in self._qty.items())
        return {"cash": self.cash, "invested": invested, "total_value": self.cash + invested, "currency": "GBP"}

    def positions(self) -> list[Position]:
        return [Position(s, q, self.prices[s], q * self.prices[s]) for s, q in sorted(self._qty.items()) if abs(q) > 1e-10]

    def market_order(self, symbol: str, quantity: float) -> OrderResult:
        symbol = symbol.upper()
        if symbol not in self.prices:
            return OrderResult(symbol, quantity, "REJECTED", message="Missing price")
        price = self.prices[symbol]
        current = self._qty.get(symbol, 0.0)
        if current + quantity < -1e-9:
            return OrderResult(symbol, quantity, "REJECTED", message="Cannot sell more than held")
        cost = quantity * price
        if cost > self.cash + 1e-9:
            return OrderResult(symbol, quantity, "REJECTED", message="Insufficient cash")
        self.cash -= cost
        self._qty[symbol] = current + quantity
        return OrderResult(symbol, quantity, "FILLED", order_id=str(uuid.uuid4()))
