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
    usd_to_gbp: float | None = None,
) -> list[PlannedOrder]:

    """
    Translate GainZ target weights into Trading 212 orders.

    Portfolio/account values are GBP.

    Existing positions:
        GBP/share is derived from Trading 212 market_value.

    New US positions:
        Yahoo USD/share is converted to GBP/share using usd_to_gbp.

    Rebalance threshold:
        Ignore small adjustments below the greater of:
        - min_order_value
        - 0.5% of total portfolio equity

    Full exits are always allowed.

    Orders are returned SELL first, BUY second.
    """

    # ---------------------------------------------------------
    # Validate target weights
    # ---------------------------------------------------------

    if any(weight < 0 for weight in target_weights.values()):
        raise ValueError(
            "Long-only target weights cannot be negative."
        )

    if sum(target_weights.values()) > 1.000001:
        raise ValueError(
            "Long-only target weights must sum to <= 1."
        )

    # ---------------------------------------------------------
    # Current portfolio
    # ---------------------------------------------------------

    current = {
        position.symbol.upper(): position
        for position in positions
    }

    current_invested_value = sum(
        float(position.market_value)
        for position in positions
    )

    equity = float(cash) + current_invested_value

    investable = equity * (1.0 - cash_buffer)

    # ---------------------------------------------------------
    # Dynamic rebalance threshold
    # ---------------------------------------------------------

    dynamic_min_order_value = max(
        float(min_order_value),
        equity * 0.005,
    )

    # ---------------------------------------------------------
    # Symbols requiring rebalance
    # ---------------------------------------------------------

    symbols = (
        set(current)
        | {
            symbol.upper()
            for symbol in target_weights
        }
    )

    orders: list[PlannedOrder] = []

    # ---------------------------------------------------------
    # Build orders
    # ---------------------------------------------------------

    for symbol in symbols:

        position = current.get(symbol)

        current_qty = (
            float(position.quantity)
            if position
            else 0.0
        )

        current_value = (
            float(position.market_value)
            if position
            else 0.0
        )

        target_weight = float(
            target_weights.get(symbol, 0.0)
        )

        target_value = (
            investable * target_weight
        )

        # -----------------------------------------------------
        # Existing position
        # -----------------------------------------------------

        if (
            position is not None
            and current_qty > 0
            and current_value > 0
        ):

            account_price_per_share = (
                current_value / current_qty
            )

        # -----------------------------------------------------
        # New position
        # -----------------------------------------------------

        elif target_weight > 0:

            market_price_usd = prices.get(symbol)

            if market_price_usd is None:
                raise ValueError(
                    f"Missing market price for {symbol}."
                )

            if usd_to_gbp is None:
                raise ValueError(
                    f"USD/GBP FX rate required to size "
                    f"new position {symbol}."
                )

            if usd_to_gbp <= 0:
                raise ValueError(
                    "usd_to_gbp must be greater than zero."
                )

            account_price_per_share = (
                float(market_price_usd)
                * float(usd_to_gbp)
            )

        else:
            continue

        # -----------------------------------------------------
        # Target quantity
        # -----------------------------------------------------

        target_qty = (
            target_value
            / account_price_per_share
        )

        delta_qty = (
            target_qty - current_qty
        )

        estimated_value = abs(
            delta_qty * account_price_per_share
        )

        # -----------------------------------------------------
        # Full exit detection
        # -----------------------------------------------------

        is_full_exit = (
            position is not None
            and current_qty > 0
            and target_weight == 0
        )

        # -----------------------------------------------------
        # Ignore insignificant rebalances
        #
        # Full exits bypass the threshold so GainZ does not
        # leave unwanted residual positions behind.
        # -----------------------------------------------------

        if (
            not is_full_exit
            and estimated_value < dynamic_min_order_value
        ):
            continue

        # -----------------------------------------------------
        # BUY / SELL
        # -----------------------------------------------------

        side = (
            "BUY"
            if delta_qty > 0
            else "SELL"
        )

        orders.append(
            PlannedOrder(
                symbol=symbol,
                quantity=delta_qty,
                reference_price=account_price_per_share,
                estimated_value=estimated_value,
                side=side,
            )
        )

    # ---------------------------------------------------------
    # Sell before buying
    # ---------------------------------------------------------

    return sorted(
        orders,
        key=lambda order: (
            0 if order.side == "SELL" else 1,
            order.symbol,
        ),
    )