from __future__ import annotations
from dataclasses import dataclass
from broker.base import Position

@dataclass(frozen=True)
class PlannedOrder:
    symbol: str
    quantity: float
    reference_price: float
    estimated_value: float
    side: str


def build_rebalance_orders(
    target_weights: dict[str, float],
    positions: list[Position],
    cash: float,
    prices: dict[str, float],
    min_order_value: float = 1.0,
    cash_buffer: float = 0.02,
) -> list[PlannedOrder]:
    """Translate target weights into sell-first/buy-second fractional-share orders."""
    if any(w < 0 for w in target_weights.values()) or sum(target_weights.values()) > 1.000001:
        raise ValueError("Long-only target weights must be non-negative and sum to <= 1")
    current = {p.symbol.upper(): p for p in positions}
    equity = float(cash) + sum(p.market_value for p in positions)
    investable = equity * (1.0 - cash_buffer)
    symbols = set(current) | {s.upper() for s in target_weights}
    orders = []
    for symbol in symbols:
        price = float(prices.get(symbol, current.get(symbol).price if symbol in current else 0.0))
        if price <= 0:
            raise ValueError(f"Missing positive price for {symbol}")
        current_qty = current.get(symbol).quantity if symbol in current else 0.0
        target_value = investable * float(target_weights.get(symbol, 0.0))
        target_qty = target_value / price
        delta = target_qty - current_qty
        value = abs(delta * price)
        if value >= min_order_value:
            orders.append(PlannedOrder(symbol, delta, price, value, "BUY" if delta > 0 else "SELL"))
    return sorted(orders, key=lambda o: (0 if o.side == "SELL" else 1, o.symbol))
