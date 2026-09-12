"""Trading 212 runner. Defaults to DEMO + DRY RUN.

Examples:
  python run_trading212.py
      # demo account, read + plan only

  python run_trading212.py --execute-demo
      # sends DEMO orders

Live mode is intentionally not exposed as a CLI switch.

Before real-money use:
- review the code and tests
- set GAINZ_ENABLE_LIVE=YES
- explicitly change the broker environment in source/config
"""

from pathlib import Path
import argparse
import json

import pandas as pd

from config.settings import load_settings
from live.signal import adaptive_target
from broker.trading212 import Trading212Broker
from execution.planner import build_rebalance_orders
from execution.engine import execute_orders


ROOT = Path(__file__).resolve().parent
SETTINGS = load_settings()


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


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--execute-demo",
        action="store_true",
        help="Actually submit orders to Trading 212 DEMO",
    )

    args = parser.parse_args()

    tickers = SETTINGS["universe"].get(
        "broad_symbols",
        SETTINGS["universe"]["symbols"],
    )

    benchmark = SETTINGS["universe"]["benchmark"]

    # -----------------------------
    # Load historical market data
    # -----------------------------
    data = {
        ticker: load_prices(ticker)
        for ticker in tickers
    }

    spy = load_prices(benchmark)

    # -----------------------------
    # Generate GainZ target weights
    # -----------------------------
    weights, decision = adaptive_target(
        data,
        spy,
    )

    # -----------------------------
    # Latest prices
    # -----------------------------
    prices = {
        ticker: float(df["Close"].iloc[-1])
        for ticker, df in data.items()
    }

    prices[benchmark] = float(
        spy["Close"].iloc[-1]
    )

    # -----------------------------
    # Trading 212 DEMO broker
    # -----------------------------
    broker = Trading212Broker(
        environment="demo"
    )

    # -----------------------------
    # Read account state
    # -----------------------------
    account = broker.account_summary()
    positions = broker.positions()

    # Trading 212 currently returns:
    #
    # "cash": {
    #     "availableToTrade": ...,
    #     ...
    # }
    #
    cash_data = account.get("cash", {})

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

    # -----------------------------
    # Create rebalance orders
    # -----------------------------
    orders = build_rebalance_orders(
    target_weights=weights,
    positions=positions,
    cash=cash,
    prices=prices,
    min_order_value=1.0,
)

    # -----------------------------
    # Execute
    #
    # Default:
    #   dry_run=True
    #
    # --execute-demo:
    #   dry_run=False
    # -----------------------------
    results = execute_orders(
        broker,
        orders,
        dry_run=not args.execute_demo,
    )

    # -----------------------------
    # Save report
    # -----------------------------
    report = {
        "environment": "demo",
        "executed": bool(
            args.execute_demo
        ),
        "decision": decision,
        "target_weights": weights,
        "cash_available": cash,
        "orders": [
            result.__dict__
            for result in results
        ],
    }

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