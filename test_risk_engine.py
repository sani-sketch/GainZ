from execution.engine import execute_orders
from execution.planner import PlannedOrder
from broker.base import OrderResult


class FakeBroker:
    def market_order(self, symbol, quantity):
        print(f"BROKER CALLED: BUY {symbol} quantity={quantity}")
        return OrderResult(
            symbol,
            quantity,
            "SUBMITTED",
            message="Fake broker accepted order.",
        )


order = PlannedOrder(
    symbol="AMD",
    quantity=5,
    reference_price=100,
    estimated_value=600,
    side="BUY",
)

results = execute_orders(
    broker=FakeBroker(),
    orders=[order],
    dry_run=False,
    positions=[],
    equity=5000,
    max_position_weight=0.15,
    max_order_weight=0.10,
)

for result in results:
    print(result)
