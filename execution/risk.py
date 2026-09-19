from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str


def check_max_position_size(
    order,
    positions,
    equity: float,
    max_position_weight: float = 0.15,
) -> RiskDecision:
    if equity <= 0:
        return RiskDecision(
            False,
            "RISK: Account equity must be greater than zero.",
        )

    if str(order.side).upper() == "SELL":
        return RiskDecision(
            True,
            "RISK APPROVED: SELL does not increase position size.",
        )

    current_market_value = 0.0

    for position in positions:
        if str(position.symbol).upper() == str(order.symbol).upper():
            current_market_value += max(
                float(position.market_value),
                0.0,
            )

    proposed_market_value = (
        current_market_value
        + max(float(order.estimated_value), 0.0)
    )

    proposed_weight = proposed_market_value / float(equity)

    if proposed_weight > float(max_position_weight):
        return RiskDecision(
            False,
            (
                f"RISK: {order.symbol} position would become "
                f"{proposed_weight * 100:.1f}% of equity, above the "
                f"{max_position_weight * 100:.1f}% limit."
            ),
        )

    return RiskDecision(
        True,
        (
            f"RISK APPROVED: {order.symbol} proposed position "
            f"{proposed_weight * 100:.1f}% of equity."
        ),
    )


def check_max_order_value(
    order,
    equity: float,
    max_order_weight: float = 0.10,
) -> RiskDecision:
    if equity <= 0:
        return RiskDecision(
            False,
            "RISK: Account equity must be greater than zero.",
        )

    if str(order.side).upper() == "SELL":
        return RiskDecision(
            True,
            "RISK APPROVED: SELL does not increase order exposure.",
        )

    order_value = max(
        float(order.estimated_value),
        0.0,
    )

    order_weight = order_value / float(equity)

    if order_weight > float(max_order_weight):
        return RiskDecision(
            False,
            (
                f"RISK: Order value is {order_weight * 100:.1f}% of equity, "
                f"above the {max_order_weight * 100:.1f}% limit."
            ),
        )

    return RiskDecision(
        True,
        (
            f"RISK APPROVED: Order value is "
            f"{order_weight * 100:.1f}% of equity."
        ),
    )


def check_max_portfolio_exposure(
    order,
    positions,
    equity: float,
    max_exposure_weight: float = 0.90,
    approved_buy_value: float = 0.0,
) -> RiskDecision:
    if equity <= 0:
        return RiskDecision(
            False,
            "RISK: Account equity must be greater than zero.",
        )

    if str(order.side).upper() == "SELL":
        return RiskDecision(
            True,
            "RISK APPROVED: SELL does not increase portfolio exposure.",
        )

    invested_value = sum(
        max(float(position.market_value), 0.0)
        for position in positions
    )

    proposed_invested_value = (
        invested_value
        + max(float(approved_buy_value), 0.0)
        + max(float(order.estimated_value), 0.0)
    )

    proposed_exposure = (
        proposed_invested_value
        / float(equity)
    )

    if proposed_exposure > float(max_exposure_weight):
        return RiskDecision(
            False,
            (
                f"RISK: Portfolio exposure would become "
                f"{proposed_exposure * 100:.1f}%, above the "
                f"{max_exposure_weight * 100:.1f}% limit."
            ),
        )

    return RiskDecision(
        True,
        (
            f"RISK APPROVED: Proposed portfolio exposure "
            f"{proposed_exposure * 100:.1f}%."
        ),
    )


def check_daily_realized_loss(
    order,
    today_realized_pnl: float,
    equity: float,
    max_daily_loss_weight: float = 0.02,
) -> RiskDecision:
    if equity <= 0:
        return RiskDecision(
            False,
            "RISK: Account equity must be greater than zero.",
        )

    if str(order.side).upper() == "SELL":
        return RiskDecision(
            True,
            "RISK APPROVED: SELL remains allowed after daily losses.",
        )

    if max_daily_loss_weight <= 0:
        return RiskDecision(
            False,
            "RISK: Daily realised-loss limit must be greater than zero.",
        )

    loss_limit = (
        float(equity)
        * float(max_daily_loss_weight)
    )

    if float(today_realized_pnl) <= -loss_limit:
        return RiskDecision(
            False,
            (
                f"RISK: Today's realised P/L is "
                f"£{float(today_realized_pnl):.2f}. "
                f"The daily realised-loss limit is "
                f"£{loss_limit:.2f} "
                f"({max_daily_loss_weight * 100:.1f}% of equity). "
                f"New BUY orders are blocked."
            ),
        )

    return RiskDecision(
        True,
        (
            f"RISK APPROVED: Today's realised P/L is "
            f"£{float(today_realized_pnl):.2f}; "
            f"daily loss limit is £{loss_limit:.2f}."
        ),
    )


def _pending_symbol(pending_order: dict) -> str:
    """
    Extract a broker ticker/symbol from a Trading 212 pending-order payload.

    Trading 212 payloads may expose the ticker directly or inside
    the nested instrument object.
    """

    if not isinstance(pending_order, dict):
        return ""

    direct = (
        pending_order.get("ticker")
        or pending_order.get("symbol")
    )

    if direct:
        return str(direct).upper()

    instrument = pending_order.get("instrument")

    if isinstance(instrument, dict):
        nested = (
            instrument.get("ticker")
            or instrument.get("symbol")
        )

        if nested:
            value = str(nested).strip().upper()
            return value.split("_")[0] if "_" in value else value

    # Some endpoints/wrappers may return an order envelope.
    nested_order = pending_order.get("order")

    if isinstance(nested_order, dict):
        direct = (
            nested_order.get("ticker")
            or nested_order.get("symbol")
        )

        if direct:
            value = str(direct).strip().upper()
            return value.split("_")[0] if "_" in value else value

        instrument = nested_order.get("instrument")

        if isinstance(instrument, dict):
            nested = (
                instrument.get("ticker")
                or instrument.get("symbol")
            )

            if nested:
                return str(nested).upper()

    return ""


def check_duplicate_order(
    order,
    pending_orders,
) -> RiskDecision:
    """
    Block ANY new order for a ticker that already has a pending broker order.

    This is intentionally stricter than the earlier same-direction rule.

    Examples:
        pending AMD BUY + new AMD BUY  -> BLOCKED
        pending AMD BUY + new AMD SELL -> BLOCKED
        pending AMD SELL + new AMD BUY -> BLOCKED
        pending AMD SELL + new AMD SELL -> BLOCKED

    The existing pending order must resolve/cancel before GainZ can approve
    another order for that ticker.
    """

    order_symbol = str(order.symbol).upper()

    for pending_order in pending_orders:
        pending_symbol = _pending_symbol(
            pending_order
        )

        if not pending_symbol:
            continue

        if pending_symbol == order_symbol:
            return RiskDecision(
                False,
                (
                    f"RISK: {order.symbol} already has a pending "
                    f"Trading 212 order. New {str(order.side).upper()} "
                    f"is blocked until the existing order resolves."
                ),
            )

    return RiskDecision(
        True,
        (
            f"RISK APPROVED: No pending Trading 212 order "
            f"for {order.symbol}."
        ),
    )


def check_same_run_duplicate(
    order,
    seen_orders,
) -> RiskDecision:
    """
    Prevent the same symbol + direction from being processed twice
    during one execution run.

    Opposite directions remain distinct here because broker-level
    pending-order conflict protection is handled separately.
    """

    key = (
        str(order.symbol).upper(),
        str(order.side).upper(),
    )

    if key in seen_orders:
        return RiskDecision(
            False,
            (
                f"RISK: Duplicate {key[1]} order for "
                f"{key[0]} in the same execution run."
            ),
        )

    return RiskDecision(
        True,
        (
            f"RISK APPROVED: No same-run duplicate "
            f"for {key[0]} {key[1]}."
        ),
    )
