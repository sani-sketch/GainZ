"""Download daily historical prices for the first GainZ Alpha universe."""

from pathlib import Path
import sys

import yfinance as yf

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import load_settings


DATA_DIRECTORY = PROJECT_ROOT / "data"
settings = load_settings()
SYMBOLS = (
    settings["universe"]["symbols"]
    + settings["universe"]["broad_symbols"]
    + [settings["universe"]["benchmark"]]
)


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
    """Download data for every research ticker, continuing after failures."""
    DATA_DIRECTORY.mkdir(exist_ok=True)

    failed_symbols: dict[str, str] = {}
    for symbol in dict.fromkeys(SYMBOLS):
        try:
            download_symbol_data(symbol)
        except Exception as error:
            failed_symbols[symbol] = str(error)
            print(f"Could not download {symbol}: {error}")

    if failed_symbols:
        print(f"Completed with {len(failed_symbols)} failed download(s).")


if __name__ == "__main__":
    main()