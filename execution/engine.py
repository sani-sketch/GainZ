from __future__ import annotations
from broker.base import Broker, OrderResult
from execution.planner import PlannedOrder


def execute_orders(broker: Broker, orders: list[PlannedOrder], dry_run: bool = True) -> list[OrderResult]:
    """Execute sell-first order plan. dry_run=True never sends an order."""
    if dry_run:
        return [OrderResult(o.symbol, o.quantity, "DRY_RUN", message=f"{o.side} est {o.estimated_value:.2f}") for o in orders]
    results = []
    for order in orders:
        result = broker.market_order(order.symbol, order.quantity)
        results.append(result)
        if result.status.upper() in {"REJECTED", "FAILED", "ERROR"}:
            break
    return results
