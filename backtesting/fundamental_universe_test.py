"""Compare GainZ baseline vs point-in-time fundamental growth filter."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from backtesting.fundamental_growth_backtest import (
    compare_with_baseline,
)


UNIVERSE = [
    "AMD",
    "MU",
    "MPC",
    "PANW",
    "FTNT",
    "PSX",
    "INTC",
    "STT",
    "CRM",
    "MRK",
    "BAC",
    "TMO",
    "MS",
    "ADP",
    "UNH",
]

DATA_DIRECTORY = Path("data")


# ============================================================
# PRICE LOADER
# ============================================================

def load_price_data(
    symbol: str,
) -> pd.DataFrame:
    """
    Load the existing GainZ yfinance-style CSV.

    Handles the extra Ticker / Date header rows automatically.
    """

    path = (
        DATA_DIRECTORY
        / f"{symbol}_daily.csv"
    )

    if not path.exists():
        raise FileNotFoundError(
            f"Price file not found: {path}"
        )

    dataframe = pd.read_csv(
        path,
        skiprows=2,
        names=[
            "Date",
            "Adj Close",
            "Close",
            "High",
            "Low",
            "Open",
            "Volume",
        ],
    )

    dataframe["Date"] = pd.to_datetime(
        dataframe["Date"],
        errors="coerce",
    )

    dataframe["Close"] = pd.to_numeric(
        dataframe["Close"],
        errors="coerce",
    )

    dataframe = (
        dataframe
        .dropna(
            subset=[
                "Date",
                "Close",
            ]
        )
        .sort_values("Date")
        .drop_duplicates("Date")
        .reset_index(drop=True)
    )

    if dataframe.empty:
        raise ValueError(
            f"No usable price data for {symbol}"
        )

    return dataframe


# ============================================================
# SINGLE TICKER COMPARISON
# ============================================================

def test_symbol(
    symbol: str,
) -> dict:

    prices = load_price_data(
        symbol
    )

    comparison = (
        compare_with_baseline(
            prices,
            symbol=symbol,
        )
    )

    baseline = comparison.iloc[0]
    fundamental = comparison.iloc[1]

    return {
        "Ticker":
            symbol,

        "Baseline CAGR":
            baseline["CAGR"],

        "Fundamental CAGR":
            fundamental["CAGR"],

        "CAGR Change":
            (
                fundamental["CAGR"]
                - baseline["CAGR"]
            ),

        "Baseline Sharpe":
            baseline["Sharpe"],

        "Fundamental Sharpe":
            fundamental["Sharpe"],

        "Sharpe Change":
            (
                fundamental["Sharpe"]
                - baseline["Sharpe"]
            ),

        "Baseline Volatility":
            baseline["Volatility"],

        "Fundamental Volatility":
            fundamental["Volatility"],

        "Volatility Change":
            (
                fundamental["Volatility"]
                - baseline["Volatility"]
            ),

        "Baseline Max DD":
            baseline["Max Drawdown"],

        "Fundamental Max DD":
            fundamental["Max Drawdown"],

        "Max DD Change":
            (
                fundamental["Max Drawdown"]
                - baseline["Max Drawdown"]
            ),

        "Baseline Invested":
            baseline["Time Invested"],

        "Fundamental Invested":
            fundamental["Time Invested"],

        "Baseline Trades":
            baseline["Position Changes"],

        "Fundamental Trades":
            fundamental["Position Changes"],

        "Baseline Final":
            baseline["Final Value"],

        "Fundamental Final":
            fundamental["Final Value"],
    }


# ============================================================
# UNIVERSE TEST
# ============================================================

def run_universe_test() -> tuple[
    pd.DataFrame,
    dict[str, str],
]:

    results = []
    skipped = {}

    for symbol in UNIVERSE:

        print(
            f"Testing {symbol}..."
        )

        try:

            result = test_symbol(
                symbol
            )

            results.append(
                result
            )

        except Exception as error:

            skipped[symbol] = str(
                error
            )

            print(
                f"SKIPPED {symbol}: "
                f"{error}"
            )

    return (
        pd.DataFrame(results),
        skipped,
    )


# ============================================================
# SUMMARY
# ============================================================

def print_summary(
    results: pd.DataFrame,
    skipped: dict[str, str],
) -> None:

    if results.empty:

        print(
            "\nNo successful backtests."
        )

        return

    display = results[
        [
            "Ticker",
            "Baseline CAGR",
            "Fundamental CAGR",
            "CAGR Change",
            "Baseline Sharpe",
            "Fundamental Sharpe",
            "Sharpe Change",
            "Baseline Max DD",
            "Fundamental Max DD",
        ]
    ].copy()

    percent_columns = [
        "Baseline CAGR",
        "Fundamental CAGR",
        "CAGR Change",
        "Baseline Max DD",
        "Fundamental Max DD",
    ]

    for column in percent_columns:

        display[column] = (
            display[column]
            * 100
        ).map(
            lambda value:
                f"{value:+.1f}%"
        )

    for column in [
        "Baseline Sharpe",
        "Fundamental Sharpe",
        "Sharpe Change",
    ]:

        display[column] = (
            display[column]
            .map(
                lambda value:
                    f"{value:+.2f}"
            )
        )

    print()

    print(
        "=" * 120
    )

    print(
        "GAINZ FUNDAMENTAL GROWTH "
        "UNIVERSE TEST"
    )

    print(
        "=" * 120
    )

    print(
        display.to_string(
            index=False
        )
    )

    successful = len(
        results
    )

    cagr_improved = int(
        (
            results[
                "CAGR Change"
            ]
            > 0
        ).sum()
    )

    sharpe_improved = int(
        (
            results[
                "Sharpe Change"
            ]
            > 0
        ).sum()
    )

    volatility_reduced = int(
        (
            results[
                "Volatility Change"
            ]
            < 0
        ).sum()
    )

    drawdown_improved = int(
        (
            results[
                "Max DD Change"
            ]
            > 0
        ).sum()
    )

    print()

    print(
        "-" * 120
    )

    print(
        "SUMMARY"
    )

    print(
        "-" * 120
    )

    print(
        f"Successful backtests: "
        f"{successful}"
    )

    print(
        f"CAGR improved: "
        f"{cagr_improved}/{successful}"
    )

    print(
        f"Sharpe improved: "
        f"{sharpe_improved}/{successful}"
    )

    print(
        f"Volatility reduced: "
        f"{volatility_reduced}/{successful}"
    )

    print(
        f"Max drawdown improved: "
        f"{drawdown_improved}/{successful}"
    )

    print(
        f"Average CAGR change: "
        f"{results['CAGR Change'].mean() * 100:+.2f} pp"
    )

    print(
        f"Average Sharpe change: "
        f"{results['Sharpe Change'].mean():+.3f}"
    )

    print(
        f"Average invested-time change: "
        f"{(
            results['Fundamental Invested'].mean()
            - results['Baseline Invested'].mean()
        ) * 100:+.2f} pp"
    )

    print(
        f"Average trade-count change: "
        f"{(
            results['Fundamental Trades'].mean()
            - results['Baseline Trades'].mean()
        ):+.2f}"
    )

    if skipped:

        print()

        print(
            "SKIPPED"
        )

        for symbol, reason in skipped.items():

            print(
                f"{symbol}: {reason}"
            )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    results, skipped = (
        run_universe_test()
    )

    print_summary(
        results,
        skipped,
    )