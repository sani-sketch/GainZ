from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: float
    price: float
    market_value: float

@dataclass(frozen=True)
class OrderResult:
    symbol: str
    quantity: float
    status: str
    order_id: str | None = None
    message: str = ""

class Broker(Protocol):
    def account_summary(self) -> dict: ...
    def positions(self) -> list[Position]: ...
    def market_order(self, symbol: str, quantity: float) -> OrderResult: ...
