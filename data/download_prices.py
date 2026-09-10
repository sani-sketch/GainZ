"""Download daily historical prices for the first GainZ Alpha universe."""

from pathlib import Path

import yfinance as yf


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIRECTORY = PROJECT_ROOT / "data"
SYMBOLS = ["AAPL", "SPY"]


def download_symbol_data(symbol: str) -> None:
    """Download five years of daily data for one symbol and save it as CSV."""
    print(f"Downloading {symbol}...")

    # Yahoo Finance returns a pandas DataFrame containing the daily price history.
    prices = yf.download(
        symbol,
        period="5y",
        interval="1d",
        auto_adjust=False,
        progress=False,
    )

    if prices.empty:
        raise ValueError(f"Yahoo Finance returned no data for {symbol}.")

    output_path = DATA_DIRECTORY / f"{symbol}_daily.csv"
    prices.to_csv(output_path)

    print(f"Saved {len(prices)} rows to {output_path}")
    print("First 5 rows:")
    print(prices.head())
    print("Last 5 rows:")
    print(prices.tail())
    print()


def main() -> None:
    """Download data for each symbol in the small starter universe."""
    DATA_DIRECTORY.mkdir(exist_ok=True)

    for symbol in SYMBOLS:
        download_symbol_data(symbol)


if __name__ == "__main__":
    main()