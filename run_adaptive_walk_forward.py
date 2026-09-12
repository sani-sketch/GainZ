from pathlib import Path
import pandas as pd

from backtesting.adaptive_core import adaptive_walk_forward_validate
from backtesting.walk_forward import WalkForwardConfig
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


def main() -> None:
    tickers = SETTINGS["universe"].get("broad_symbols", SETTINGS["universe"]["symbols"])
    benchmark = SETTINGS["universe"]["benchmark"]
    price_data = {ticker: load_prices(ticker) for ticker in tickers}
    spy = load_prices(benchmark)

    folds, oos, summary = adaptive_walk_forward_validate(
        price_data,
        spy,
        config=WalkForwardConfig(train_days=252, test_days=126, step_days=126),
        sharpe_margin=0.0,
    )

    folds.to_csv(ROOT / "outputs" / "adaptive_walk_forward_folds.csv", index=False)
    oos.to_csv(ROOT / "outputs" / "adaptive_walk_forward_oos_history.csv", index=False)

    with open(ROOT / "outputs" / "adaptive_walk_forward_summary.md", "w", encoding="utf-8") as f:
        f.write("# GainZ Adaptive Walk-Forward Validation\n\n")
        f.write("GainZ is used in an unseen test fold only when its selected candidate had a higher Sharpe ratio than SPY in the preceding training fold. Otherwise the model falls back to SPY.\n\n")
        f.write(f"- Folds: {summary['folds']}\n")
        f.write(f"- GainZ folds: {summary['gainz_folds']}\n")
        f.write(f"- Benchmark fallback folds: {summary['benchmark_folds']}\n")
        f.write(f"- Adaptive OOS CAGR: {summary['adaptive_cagr']:.2%}\n")
        f.write(f"- SPY OOS CAGR: {summary['spy_cagr']:.2%}\n")
        f.write(f"- Adaptive OOS Sharpe: {summary['adaptive_sharpe']:.2f}\n")
        f.write(f"- SPY OOS Sharpe: {summary['spy_sharpe']:.2f}\n")
        f.write(f"- Adaptive max drawdown: {summary['adaptive_max_drawdown']:.2%}\n")
        f.write(f"- SPY max drawdown: {summary['spy_max_drawdown']:.2%}\n")
        f.write(f"- Adaptive total return: {summary['adaptive_total_return']:.2%}\n")
        f.write(f"- SPY total return: {summary['spy_total_return']:.2%}\n\n")
        f.write("## Important limitations\n\n")
        f.write("The stock universe is based on current constituents, so survivorship bias remains. The strategy family was also developed after inspecting this dataset. These results are research evidence, not a forecast or guarantee.\n\n")
        f.write(folds.to_markdown(index=False))
        f.write("\n")

    print("\nAdaptive GainZ walk-forward")
    print(f"GainZ used in {summary['gainz_folds']}/{summary['folds']} folds; benchmark fallback in {summary['benchmark_folds']}/{summary['folds']}")
    print(f"Adaptive CAGR: {summary['adaptive_cagr']:.2%} | SPY: {summary['spy_cagr']:.2%}")
    print(f"Adaptive Sharpe: {summary['adaptive_sharpe']:.2f} | SPY: {summary['spy_sharpe']:.2f}")
    print(f"Adaptive max DD: {summary['adaptive_max_drawdown']:.2%} | SPY: {summary['spy_max_drawdown']:.2%}")
    print(f"Adaptive total return: {summary['adaptive_total_return']:.2%} | SPY: {summary['spy_total_return']:.2%}")
    print("\nFold choices")
    print(folds[["fold", "allocation_mode", "gainz_train_sharpe", "benchmark_train_sharpe", "selected_variant", "selected_risk_config"]].to_string(index=False))


if __name__ == "__main__":
    main()
