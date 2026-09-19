from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str


def _normalise_ticker(value: object) -> str:
    """
    Convert Trading 212 instrument tickers such as:

        ADP_US_EQ
        AMD_US_EQ

    into GainZ symbols:

        ADP
        AMD

    Also handles already-normalised symbols.
    """

    value = str(value or "").strip().upper()

    if not value:
        return ""

    # Trading 212 US equity instrument format.
    if value.endswith("_US_EQ"):
        return value[:-6]

    # Defensive fallback for other instrument suffixes.
    if "_" in value:
        return value.split("_")[0]

    return value


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

    symbol = _normalise_ticker(order.symbol)

    current_market_value = 0.0

    for position in positions or []:
        if _normalise_ticker(position.symbol) == symbol:
            current_market_value += max(
                float(position.market_value),
                0.0,
            )

    proposed_market_value = (
        current_market_value
        + max(float(order.estimated_value), 0.0)
    )

    proposed_weight = (
        proposed_market_value
        / float(equity)
    )

    if proposed_weight > float(max_position_weight):
        return RiskDecision(
            False,
            (
                f"RISK: {symbol} position would become "
                f"{proposed_weight:.1%} of equity, above the "
                f"{max_position_weight:.1%} limit."
            ),
        )

    return RiskDecision(
        True,
        (
            f"RISK APPROVED: {symbol} proposed position "
            f"{proposed_weight:.1%} of equity."
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

    order_weight = (
        order_value
        / float(equity)
    )

    if order_weight > float(max_order_weight):
        return RiskDecision(
            False,
            (
                f"RISK: Order value is {order_weight:.1%} of equity, "
                f"above the {max_order_weight:.1%} limit."
            ),
        )

    return RiskDecision(
        True,
        (
            f"RISK APPROVED: Order value is "
            f"{order_weight:.1%} of equity."
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
        for position in positions or []
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
                f"{proposed_exposure:.1%}, above the "
                f"{max_exposure_weight:.1%} limit."
            ),
        )

    return RiskDecision(
        True,
        (
            f"RISK APPROVED: Proposed portfolio exposure "
            f"{proposed_exposure:.1%}."
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

    realised_pnl = float(today_realized_pnl)

    if realised_pnl <= -loss_limit:
        return RiskDecision(
            False,
            (
                f"RISK: Today's realised P/L is "
                f"£{realised_pnl:.2f}. "
                f"The daily realised-loss limit is "
                f"£{loss_limit:.2f} "
                f"({max_daily_loss_weight:.1%} of equity). "
                f"New BUY orders are blocked."
            ),
        )

    return RiskDecision(
        True,
        (
            f"RISK APPROVED: Today's realised P/L is "
            f"£{realised_pnl:.2f}; daily loss limit is "
            f"£{loss_limit:.2f}."
        ),
    )


def _pending_symbol(pending_order: dict) -> str:
    """
    Extract and normalise the ticker from a Trading 212 pending-order
    payload.

    Example:

        ADP_US_EQ -> ADP
    """

    if not isinstance(pending_order, dict):
        return ""

    # Normal Trading 212 order response.
    direct = (
        pending_order.get("ticker")
        or pending_order.get("symbol")
    )

    if direct:
        return _normalise_ticker(direct)

    # Nested instrument response.
    instrument = pending_order.get("instrument")

    if isinstance(instrument, dict):
        nested = (
            instrument.get("ticker")
            or instrument.get("symbol")
        )

        if nested:
            return _normalise_ticker(nested)

    # Defensive support for an order envelope.
    nested_order = pending_order.get("order")

    if isinstance(nested_order, dict):

        direct = (
            nested_order.get("ticker")
            or nested_order.get("symbol")
        )

        if direct:
            return _normalise_ticker(direct)

        instrument = nested_order.get("instrument")

        if isinstance(instrument, dict):
            nested = (
                instrument.get("ticker")
                or instrument.get("symbol")
            )

            if nested:
                return _normalise_ticker(nested)

    return ""


def check_duplicate_order(
    order,
    pending_orders,
) -> RiskDecision:
    """
    Block ANY new order for a ticker that already has a pending
    Trading 212 order.

    Examples:

        pending AMD_US_EQ BUY + new AMD BUY
            -> BLOCKED

        pending AMD_US_EQ BUY + new AMD SELL
            -> BLOCKED

    This is deliberately stricter than checking only the direction.
    """

    order_symbol = _normalise_ticker(
        order.symbol
    )

    for pending_order in pending_orders or []:

        pending_symbol = _pending_symbol(
            pending_order
        )

        if not pending_symbol:
            continue

        if pending_symbol == order_symbol:

            return RiskDecision(
                False,
                (
                    f"RISK: {order_symbol} already has a "
                    f"pending Trading 212 order. New "
                    f"{str(order.side).upper()} is blocked "
                    f"until the existing order resolves."
                ),
            )

    return RiskDecision(
        True,
        (
            f"RISK APPROVED: No pending Trading 212 "
            f"order for {order_symbol}."
        ),
    )


def check_same_run_duplicate(
    order,
    seen_orders,
) -> RiskDecision:

    key = (
        _normalise_ticker(order.symbol),
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
