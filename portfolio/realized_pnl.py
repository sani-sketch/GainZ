from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return default


def _date_from_timestamp(value: str) -> str:
    """
    Convert an ISO timestamp to a YYYY-MM-DD date.

    Trading 212 timestamps are normally UTC. If parsing fails,
    fall back to the first 10 characters so malformed historical
    records do not crash dashboard reporting.
    """

    value = str(value or "").strip()

    if not value:
        return ""

    try:
        return datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        ).date().isoformat()

    except ValueError:
        return value[:10]


def calculate_realized_pnl(historical_orders: list) -> dict:
    """
    Calculate realised trading P/L using Trading 212's own
    broker-reported realisedProfitLoss value.

    We intentionally do NOT reconstruct realised P/L using FIFO.
    Trading 212 already provides the authoritative realised P/L
    for each filled SELL transaction.
    """

    realized_trades = []

    for record in historical_orders or []:

        if not isinstance(record, dict):
            continue

        order = record.get("order", {}) or {}
        fill = record.get("fill", {}) or {}

        # Only completed orders.
        if str(order.get("status", "")).upper() != "FILLED":
            continue

        # Realised P/L only exists when something is sold.
        if str(order.get("side", "")).upper() != "SELL":
            continue

        wallet = fill.get("walletImpact", {}) or {}

        # Skip records where Trading 212 did not provide
        # realised P/L.
        if "realisedProfitLoss" not in wallet:
            continue

        ticker = str(
            order.get("ticker")
            or (order.get("instrument", {}) or {}).get("ticker")
            or ""
        )

        quantity = abs(
            _float(
                fill.get(
                    "quantity",
                    order.get(
                        "filledQuantity",
                        order.get("quantity", 0),
                    ),
                )
            )
        )

        realised_pnl = _float(
            wallet.get("realisedProfitLoss")
        )

        filled_at = (
            fill.get("filledAt")
            or order.get("createdAt")
            or ""
        )

        currency = str(
            wallet.get("currency")
            or order.get("currency")
            or ""
        )

        net_value = abs(
            _float(wallet.get("netValue"))
        )

        price = _float(fill.get("price"))

        fees = 0.0

        for tax in wallet.get("taxes", []) or []:
            if not isinstance(tax, dict):
                continue

            fees += abs(
                _float(tax.get("quantity"))
            )

        if not ticker or not filled_at:
            continue

        date = _date_from_timestamp(filled_at)

        if not date:
            continue

        realized_trades.append(
            {
                "date": date,
                "filled_at": filled_at,
                "ticker": ticker,
                "quantity": round(quantity, 6),
                "price": round(price, 6),
                "proceeds": round(net_value, 2),
                "realized_pnl": round(
                    realised_pnl,
                    2,
                ),
                "fees": round(fees, 2),
                "currency": currency,
            }
        )

    # Sort chronologically.
    realized_trades.sort(
        key=lambda trade: trade["filled_at"]
    )

    # ---------------------------------------------------------
    # DAILY REALISED P/L
    # ---------------------------------------------------------

    daily_totals = defaultdict(float)

    for trade in realized_trades:
        daily_totals[trade["date"]] += (
            trade["realized_pnl"]
        )

    daily = [
        {
            "date": date,
            "realized_pnl": round(value, 2),
        }
        for date, value in sorted(
            daily_totals.items()
        )
    ]

    # ---------------------------------------------------------
    # TOTAL REALISED P/L
    # ---------------------------------------------------------

    total_realized_pnl = round(
        sum(
            trade["realized_pnl"]
            for trade in realized_trades
        ),
        2,
    )

    # ---------------------------------------------------------
    # SUMMARY
    # ---------------------------------------------------------

    winning_trades = sum(
        1
        for trade in realized_trades
        if trade["realized_pnl"] > 0
    )

    losing_trades = sum(
        1
        for trade in realized_trades
        if trade["realized_pnl"] < 0
    )

    flat_trades = sum(
        1
        for trade in realized_trades
        if trade["realized_pnl"] == 0
    )

    return {
        "trades": realized_trades,
        "daily": daily,
        "total_realized_pnl": total_realized_pnl,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "flat_trades": flat_trades,
    }


def get_realized_pnl_for_date(
    realized_analysis: dict,
    date: str,
) -> float:
    """
    Return broker-reported realised P/L for one YYYY-MM-DD date.

    If there are no realised trades for that date, return 0.0.
    """

    target_date = str(date or "").strip()

    if not target_date:
        return 0.0

    for row in realized_analysis.get("daily", []) or []:
        if str(row.get("date", "")) == target_date:
            return round(
                _float(row.get("realized_pnl")),
                2,
            )

    return 0.0


def get_today_realized_pnl(
    realized_analysis: dict,
    now: datetime | None = None,
) -> float:
    """
    Return today's broker-reported realised P/L.

    Default day boundary is UTC because Trading 212 fill timestamps
    are returned as UTC timestamps. A timezone-aware datetime can
    be supplied explicitly in tests.
    """

    if now is None:
        now = datetime.now(timezone.utc)

    return get_realized_pnl_for_date(
        realized_analysis=realized_analysis,
        date=now.date().isoformat(),
    )
