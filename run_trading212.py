"""Trading 212 runner. Defaults to DEMO + DRY RUN.

Examples:
  python run_trading212.py
      # demo account, read + plan only

  python run_trading212.py --execute-demo
      # sends DEMO orders

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
from execution.planner import build_rebalance_orders
from execution.engine import execute_orders


ROOT = Path(__file__).resolve().parent

load_dotenv(ROOT / ".env")

SETTINGS = load_settings()


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
    Get a recent GBP/USD market rate from Yahoo Finance.

    Yahoo ticker:
        GBPUSD=X

    Example:
        GBPUSD = 1.35

    Means:
        £1 = $1.35

    Therefore:
        $1 = £(1 / 1.35)

    Returns:
        USD -> GBP conversion rate.
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

    # yfinance may return either a Series or
    # a one-column DataFrame depending on version.
    if isinstance(close, pd.DataFrame):
        gbp_usd = float(close.iloc[-1, 0])
    else:
        gbp_usd = float(close.iloc[-1])

    if gbp_usd <= 0:
        raise RuntimeError(
            f"Invalid GBP/USD FX rate: {gbp_usd}"
        )

    usd_to_gbp = 1.0 / gbp_usd

    # Sanity guard against accidentally inverted/bad FX data.
    if not 0.50 < usd_to_gbp < 1.20:
        raise RuntimeError(
            f"Suspicious USD->GBP rate: {usd_to_gbp:.6f}"
        )

    return usd_to_gbp


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

    args = parser.parse_args()

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
    # Build GainZ rebalance
    # --------------------------------------------------------

    orders = build_rebalance_orders(
        target_weights=weights,
        positions=positions,
        cash=cash,
        prices=prices,
        min_order_value=1.0,
        usd_to_gbp=usd_to_gbp,
    )

    # --------------------------------------------------------
    # Execute
    #
    # WITHOUT --execute-demo:
    #     DRY RUN ONLY
    #
    # WITH --execute-demo:
    #     Trading 212 Practice orders
    # --------------------------------------------------------

    results = execute_orders(
        broker,
        orders,
        dry_run=not args.execute_demo,
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