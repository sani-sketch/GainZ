"""Trading 212 runner. Defaults to DEMO + DRY RUN.

Examples:
  python run_trading212.py
      # demo account, read + plan only
      # Telegram signals are sent

  python run_trading212.py --execute-demo
      # sends DEMO orders
      # Telegram signals are sent

  python run_trading212.py --investment-amount 500
      # Practice-only new-cash GainZ preview

Live mode is intentionally not exposed as a CLI switch.
"""

from pathlib import Path
import argparse
import json

import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

from config.settings import load_settings
from live.signal import adaptive_target
from broker.trading212 import Trading212Broker
from execution.planner import PlannedOrder, build_rebalance_orders
from execution.engine import execute_orders
from notifications.telegram import send_telegram_message
from portfolio.realized_pnl import (
    calculate_realized_pnl,
    get_today_realized_pnl,
)


ROOT = Path(__file__).resolve().parent

load_dotenv(ROOT / ".env")

SETTINGS = load_settings()

MAX_POSITION_WEIGHT = 0.15
MAX_ORDER_WEIGHT = 0.10
MAX_EXPOSURE_WEIGHT = 0.90

# Engineering safety threshold for testing.
# This is configurable and is not an investment recommendation.
MAX_DAILY_LOSS_WEIGHT = 0.02


# ============================================================
# PRICE DATA
# ============================================================

def load_prices(ticker):
    path = ROOT / "data" / f"{ticker}_daily.csv"

    return (
        pd.read_csv(
            path,
            skiprows=[1, 2],
            names=[
                "Date",
                "Adj Close",
                "Close",
                "High",
                "Low",
                "Open",
                "Volume",
            ],
            header=0,
            parse_dates=["Date"],
        )[["Date", "Close", "Volume"]]
        .dropna()
        .sort_values("Date")
    )


# ============================================================
# FX
# ============================================================

def get_usd_to_gbp_rate() -> float:
    """
    Get a recent GBP/USD market rate from Yahoo Finance and convert
    it to USD -> GBP.
    """

    fx = yf.download(
        "GBPUSD=X",
        period="5d",
        interval="1d",
        auto_adjust=False,
        progress=False,
    )

    if fx.empty:
        raise RuntimeError(
            "Unable to retrieve GBP/USD FX rate."
        )

    close = fx["Close"].dropna()

    if close.empty:
        raise RuntimeError(
            "GBP/USD FX data contains no closing price."
        )

    if isinstance(close, pd.DataFrame):
        gbp_usd = float(close.iloc[-1, 0])
    else:
        gbp_usd = float(close.iloc[-1])

    if gbp_usd <= 0:
        raise RuntimeError(
            f"Invalid GBP/USD FX rate: {gbp_usd}"
        )

    usd_to_gbp = 1.0 / gbp_usd

    if not 0.50 < usd_to_gbp < 1.20:
        raise RuntimeError(
            f"Suspicious USD->GBP rate: {usd_to_gbp:.6f}"
        )

    return usd_to_gbp


# ============================================================
# TELEGRAM SIGNALS
# ============================================================

def send_order_plan_to_telegram(
    orders,
    execute_demo: bool,
):
    """
    Send the GainZ order plan to Telegram.

    Notification only. This function never executes trades.
    """

    if not orders:
        send_telegram_message(
            "⚪ GAINZ UPDATE\n\n"
            "No BUY or SELL signals today.\n"
            "Portfolio already matches the current GainZ plan."
        )
        return

    mode = (
        "PRACTICE EXECUTION"
        if execute_demo
        else "SIGNAL ONLY"
    )

    lines = [
        "📊 GAINZ ALPHA",
        "",
        f"Mode: {mode}",
        "",
    ]

    sells = []
    buys = []

    for order in orders:
        quantity = float(
            getattr(order, "quantity", 0.0)
        )

        symbol = str(
            getattr(
                order,
                "ticker",
                getattr(order, "symbol", "UNKNOWN"),
            )
        )

        if quantity < 0:
            sells.append(
                (
                    symbol,
                    abs(quantity),
                )
            )

        elif quantity > 0:
            buys.append(
                (
                    symbol,
                    quantity,
                )
            )

    if sells:
        lines.append("🔴 SELL")

        for symbol, quantity in sells:
            lines.append(
                f"{symbol}: {quantity:.6f} shares"
            )

        lines.append("")

    if buys:
        lines.append("🟢 BUY")

        for symbol, quantity in buys:
            lines.append(
                f"{symbol}: {quantity:.6f} shares"
            )

        lines.append("")

    lines.extend(
        [
            f"Total signals: {len(orders)}",
            "",
            (
                "Review in Trading 212 before "
                "placing any manual trade."
            ),
        ]
    )

    send_telegram_message(
        "\n".join(lines)
    )


# ============================================================
# NEW-CASH BUY-ONLY PLAN
# ============================================================

def build_new_cash_orders(
    weights: dict,
    deployment_cash: float,
    prices: dict,
    usd_to_gbp: float,
) -> list[PlannedOrder]:
    """
    Deploy only the requested new cash using the raw GainZ target
    weights.

    Existing holdings are not sold or rebalanced in this mode.
    Raw weights are deliberately not normalised to 100%, so GainZ's
    intended residual cash allocation is preserved.
    """

    orders: list[PlannedOrder] = []

    for symbol, target_weight in sorted(
        weights.items(),
        key=lambda item: item[0],
    ):
        target_weight = float(
            target_weight or 0.0
        )

        if target_weight <= 0:
            continue

        price_usd = float(
            prices.get(symbol, 0.0) or 0.0
        )

        if price_usd <= 0:
            continue

        price_gbp = price_usd * usd_to_gbp

        if price_gbp <= 0:
            continue

        allocation_gbp = (
            float(deployment_cash)
            * target_weight
        )

        if allocation_gbp < 1.0:
            continue

        quantity = allocation_gbp / price_gbp

        orders.append(
            PlannedOrder(
                symbol=symbol,
                side="BUY",
                quantity=quantity,
                reference_price=price_gbp,
                estimated_value=allocation_gbp,
            )
        )

    return orders


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--execute-demo",
        action="store_true",
        help="Actually submit orders to Trading 212 DEMO",
    )

    parser.add_argument(
        "--investment-amount",
        type=float,
        default=None,
        help=(
            "Optional GBP amount to deploy using GainZ target weights. "
            "When omitted, the existing full-portfolio rebalance is used."
        ),
    )

    args = parser.parse_args()

    if (
        args.investment_amount is not None
        and args.investment_amount <= 0
    ):
        parser.error(
            "--investment-amount must be greater than zero"
        )

    # --------------------------------------------------------
    # GainZ universe
    # --------------------------------------------------------

    tickers = SETTINGS["universe"].get(
        "broad_symbols",
        SETTINGS["universe"]["symbols"],
    )

    benchmark = SETTINGS["universe"]["benchmark"]

    # --------------------------------------------------------
    # Historical market data
    # --------------------------------------------------------

    data = {
        ticker: load_prices(ticker)
        for ticker in tickers
    }

    spy = load_prices(benchmark)

    # --------------------------------------------------------
    # Generate GainZ target portfolio
    # --------------------------------------------------------

    weights, decision = adaptive_target(
        data,
        spy,
    )

    # --------------------------------------------------------
    # Latest USD stock prices
    # --------------------------------------------------------

    prices = {
        ticker: float(df["Close"].iloc[-1])
        for ticker, df in data.items()
    }

    prices[benchmark] = float(
        spy["Close"].iloc[-1]
    )

    # --------------------------------------------------------
    # USD -> GBP conversion
    # --------------------------------------------------------

    usd_to_gbp = get_usd_to_gbp_rate()

    print(
        f"USD -> GBP FX rate: "
        f"{usd_to_gbp:.6f}"
    )

    # --------------------------------------------------------
    # Trading 212 Practice
    # --------------------------------------------------------

    broker = Trading212Broker(
        environment="demo"
    )

    account = broker.account_summary()
    positions = broker.positions()

    # --------------------------------------------------------
    # Available GBP cash
    # --------------------------------------------------------

    cash_data = account.get(
        "cash",
        {},
    )

    if isinstance(cash_data, dict):
        cash = float(
            cash_data.get(
                "availableToTrade",
                0.0,
            )
        )
    else:
        cash = float(
            cash_data or 0.0
        )

    # --------------------------------------------------------
    # Build GainZ plan
    # --------------------------------------------------------

    deployment_cash = cash

    if args.investment_amount is not None:
        if args.investment_amount > cash:
            raise RuntimeError(
                f"Requested Practice investment "
                f"£{args.investment_amount:.2f} exceeds "
                f"available cash £{cash:.2f}."
            )

        deployment_cash = float(
            args.investment_amount
        )

        print(
            f"GainZ Practice deployment amount: "
            f"£{deployment_cash:.2f}"
        )

    if args.investment_amount is None:
        # Normal mode: whole Practice portfolio rebalance.
        orders = build_rebalance_orders(
            target_weights=weights,
            positions=positions,
            cash=deployment_cash,
            prices=prices,
            min_order_value=1.0,
            usd_to_gbp=usd_to_gbp,
        )

    else:
        # New-cash mode: BUY only. No existing position is sold.
        orders = build_new_cash_orders(
            weights=weights,
            deployment_cash=deployment_cash,
            prices=prices,
            usd_to_gbp=usd_to_gbp,
        )

        planned_deployment = sum(
            float(order.estimated_value)
            for order in orders
        )

        print(
            f"GainZ new-cash mode: {len(orders)} BUY orders, "
            f"planned deployment £{planned_deployment:.2f}, "
            f"cash reserve "
            f"£{deployment_cash - planned_deployment:.2f}"
        )

    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    send_order_plan_to_telegram(
        orders,
        execute_demo=args.execute_demo,
    )

    # --------------------------------------------------------
    # Risk-engine inputs
    # --------------------------------------------------------

    pending_orders = broker.orders()

    invested_value = sum(
        float(position.market_value)
        for position in positions
    )

    # Do not add deployment_cash here. It is already part of cash.
    equity = float(cash) + invested_value

    # Broker history is now a mandatory risk input.
    # If this request fails, the runner fails closed before execution.
    historical_orders = broker.historical_orders()

    realized_analysis = calculate_realized_pnl(
        historical_orders
    )

    today_realized_pnl = get_today_realized_pnl(
        realized_analysis
    )

    print(
        f"Risk engine: equity=£{equity:.2f}, "
        f"pending_orders={len(pending_orders)}, "
        f"today_realised_pnl=£{today_realized_pnl:.2f}"
    )

    # --------------------------------------------------------
    # Execute / dry-run through ALL safeguards
    # --------------------------------------------------------

    results = execute_orders(
        broker=broker,
        orders=orders,
        dry_run=not args.execute_demo,
        positions=positions,
        equity=equity,
        pending_orders=pending_orders,
        max_position_weight=MAX_POSITION_WEIGHT,
        max_order_weight=MAX_ORDER_WEIGHT,
        max_exposure_weight=MAX_EXPOSURE_WEIGHT,
        today_realized_pnl=today_realized_pnl,
        max_daily_loss_weight=MAX_DAILY_LOSS_WEIGHT,
    )

    # --------------------------------------------------------
    # Report
    # --------------------------------------------------------

    report = {
        "environment": "demo",

        "executed": bool(
            args.execute_demo
        ),

        "decision": decision,

        "target_weights": weights,

        "cash_available_gbp": cash,

        "requested_investment_amount_gbp": (
            float(args.investment_amount)
            if args.investment_amount is not None
            else None
        ),

        "deployment_cash_gbp": deployment_cash,

        "portfolio_equity_gbp": equity,

        "today_realized_pnl_gbp": (
            today_realized_pnl
        ),

        "pending_order_count": len(
            pending_orders
        ),

        "risk_limits": {
            "max_position_weight": (
                MAX_POSITION_WEIGHT
            ),
            "max_order_weight": (
                MAX_ORDER_WEIGHT
            ),
            "max_exposure_weight": (
                MAX_EXPOSURE_WEIGHT
            ),
            "max_daily_loss_weight": (
                MAX_DAILY_LOSS_WEIGHT
            ),
        },

        "usd_to_gbp": usd_to_gbp,

        "planned_order_count": len(
            orders
        ),

        "orders": [
            result.__dict__
            for result in results
        ],
    }

    # --------------------------------------------------------
    # Save report
    # --------------------------------------------------------

    output_path = (
        ROOT
        / "outputs"
        / "trading212_demo_report.json"
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(
            report,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            report,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
