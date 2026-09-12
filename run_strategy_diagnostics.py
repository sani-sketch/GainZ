from pathlib import Path
import pandas as pd

from backtesting.regime_multifactor_research import evaluate_variants
from config.settings import load_settings

ROOT = Path(__file__).resolve().parent
SETTINGS = load_settings()


def load_prices(ticker: str) -> pd.DataFrame:
    path = ROOT / "data" / f"{ticker}_daily.csv"
    return pd.read_csv(
        path,
        skiprows=[1, 2],
        names=["Date", "Adj Close", "Close", "High", "Low", "Open", "Volume"],
        header=0,
        parse_dates=["Date"],
    )[["Date", "Close", "Volume"]].dropna().sort_values("Date")


def main():
    tickers = SETTINGS["universe"].get("broad_symbols", SETTINGS["universe"]["symbols"])
    benchmark = SETTINGS["universe"]["benchmark"]
    price_data = {ticker: load_prices(ticker) for ticker in tickers}
    spy = load_prices(benchmark)
    results = evaluate_variants(price_data, spy)
    out = ROOT / "outputs" / "strategy_diagnostics.csv"
    results.to_csv(out, index=False)
    cols = ["name", "full_cagr", "full_sharpe", "full_max_drawdown", "val_cagr", "val_sharpe", "val_max_drawdown", "val_spy_cagr", "val_spy_sharpe", "validation_score"]
    print(results[cols].head(15).to_string(index=False))
    print(f"\nSaved {len(results)} variants to {out}")


if __name__ == "__main__":
    main()
