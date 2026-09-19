from __future__ import annotations

from broker.base import Broker, OrderResult
from execution.planner import PlannedOrder
from execution.risk import (
    check_daily_realized_loss,
    check_duplicate_order,
    check_max_order_value,
    check_max_portfolio_exposure,
    check_max_position_size,
    check_same_run_duplicate,
)


def _blocked_result(
    order: PlannedOrder,
    message: str,
) -> OrderResult:
    return OrderResult(
        symbol=order.symbol,
        quantity=order.quantity,
        status="BLOCKED",
        message=message,
    )


def execute_orders(
    broker: Broker,
    orders: list[PlannedOrder],
    dry_run: bool = True,
    positions=None,
    equity: float | None = None,
    pending_orders: list[dict] | None = None,
    max_position_weight: float = 0.15,
    max_order_weight: float = 0.10,
    max_exposure_weight: float = 0.90,
    today_realized_pnl: float | None = None,
    max_daily_loss_weight: float = 0.02,
) -> list[OrderResult]:
    """
    Validate planned orders through the GainZ execution safety layer.

    Safety checks:
    1. Required risk data must be present.
    2. Existing Trading 212 pending-order duplicate check.
    3. Same-run duplicate check.
    4. Maximum position size.
    5. Maximum single-order value.
    6. Maximum total portfolio exposure.
    7. Daily realised-loss blocker.
    8. Only after every check passes may the broker be called.

    Daily-loss behaviour:
    - BUY orders are blocked once today's broker-reported realised P/L
      reaches the configured loss threshold.
    - SELL orders remain allowed so exposure can still be reduced.

    Fail-closed behaviour:
    - Missing positions, equity, pending orders, or today's realised P/L
      blocks the run rather than silently bypassing a safety check.

    dry_run=True never submits an order to the broker.
    """

    results: list[OrderResult] = []

    # ---------------------------------------------------------
    # FAIL-CLOSED INPUT VALIDATION
    # ---------------------------------------------------------

    if positions is None:
        return [
            _blocked_result(
                order,
                "RISK: Positions data is missing. Execution blocked.",
            )
            for order in orders
        ]

    if equity is None:
        return [
            _blocked_result(
                order,
                "RISK: Account equity is missing. Execution blocked.",
            )
            for order in orders
        ]

    try:
        equity_value = float(equity)
    except (TypeError, ValueError):
        equity_value = 0.0

    if equity_value <= 0:
        return [
            _blocked_result(
                order,
                "RISK: Account equity must be greater than zero. Execution blocked.",
            )
            for order in orders
        ]

    if pending_orders is None:
        return [
            _blocked_result(
                order,
                "RISK: Pending-order data is missing. Execution blocked.",
            )
            for order in orders
        ]

    if today_realized_pnl is None:
        return [
            _blocked_result(
                order,
                "RISK: Today's realised P/L is missing. Execution blocked.",
            )
            for order in orders
        ]

    try:
        today_realized_pnl_value = float(today_realized_pnl)
    except (TypeError, ValueError):
        return [
            _blocked_result(
                order,
                "RISK: Today's realised P/L is invalid. Execution blocked.",
            )
            for order in orders
        ]

    # ---------------------------------------------------------
    # RUN-LEVEL STATE
    # ---------------------------------------------------------

    seen_orders: set[tuple[str, str]] = set()

    # Cumulative estimated value of BUY orders already approved
    # during this execution run. This prevents several individually
    # acceptable BUYs from collectively breaching the exposure cap.
    approved_buy_value = 0.0

    # ---------------------------------------------------------
    # ORDER-BY-ORDER SAFETY CHECKS
    # ---------------------------------------------------------

    for order in orders:

        # 1. Existing broker pending-order duplicate.
        decision = check_duplicate_order(
            order=order,
            pending_orders=pending_orders,
        )

        if not decision.allowed:
            results.append(
                _blocked_result(
                    order,
                    decision.reason,
                )
            )
            continue

        # 2. Duplicate within this execution run.
        decision = check_same_run_duplicate(
            order=order,
            seen_orders=seen_orders,
        )

        if not decision.allowed:
            results.append(
                _blocked_result(
                    order,
                    decision.reason,
                )
            )
            continue

        # 3. Maximum position size.
        decision = check_max_position_size(
            order=order,
            positions=positions,
            equity=equity_value,
            max_position_weight=max_position_weight,
        )

        if not decision.allowed:
            results.append(
                _blocked_result(
                    order,
                    decision.reason,
                )
            )
            continue

        # 4. Maximum single-order value.
        decision = check_max_order_value(
            order=order,
            equity=equity_value,
            max_order_weight=max_order_weight,
        )

        if not decision.allowed:
            results.append(
                _blocked_result(
                    order,
                    decision.reason,
                )
            )
            continue

        # 5. Maximum total portfolio exposure.
        decision = check_max_portfolio_exposure(
            order=order,
            positions=positions,
            equity=equity_value,
            max_exposure_weight=max_exposure_weight,
            approved_buy_value=approved_buy_value,
        )

        if not decision.allowed:
            results.append(
                _blocked_result(
                    order,
                    decision.reason,
                )
            )
            continue

        # 6. Daily realised-loss emergency brake.
        decision = check_daily_realized_loss(
            order=order,
            today_realized_pnl=today_realized_pnl_value,
            equity=equity_value,
            max_daily_loss_weight=max_daily_loss_weight,
        )

        if not decision.allowed:
            results.append(
                _blocked_result(
                    order,
                    decision.reason,
                )
            )
            continue

        # The order has passed every safety rule. Record it now so
        # another identical order in this same run can be blocked.
        seen_orders.add(
            (
                str(order.symbol).upper(),
                str(order.side).upper(),
            )
        )

        # Track approved BUY exposure cumulatively.
        if str(order.side).upper() == "BUY":
            approved_buy_value += max(
                float(order.estimated_value),
                0.0,
            )

        # -----------------------------------------------------
        # DRY RUN
        # -----------------------------------------------------

        if dry_run:
            results.append(
                OrderResult(
                    symbol=order.symbol,
                    quantity=order.quantity,
                    status="DRY_RUN_APPROVED",
                    message=(
                        f"RISK APPROVED: {str(order.side).upper()} "
                        f"est {float(order.estimated_value):.2f}"
                    ),
                )
            )
            continue

        # -----------------------------------------------------
        # BROKER SUBMISSION
        # -----------------------------------------------------

        if broker is None:
            results.append(
                _blocked_result(
                    order,
                    "RISK: Broker is missing. Execution blocked.",
                )
            )
            break

        result = broker.market_order(
            symbol=order.symbol,
            quantity=order.quantity,
        )

        results.append(result)

        # Stop the run immediately if the broker rejects/fails/errors.
        if str(result.status).upper() in {
            "REJECTED",
            "FAILED",
            "ERROR",
        }:
            break

    return results
