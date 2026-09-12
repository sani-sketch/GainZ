from pathlib import Path
import pandas as pd

from backtesting.walk_forward import WalkForwardConfig, walk_forward_validate
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

    folds, oos, summary = walk_forward_validate(
        price_data,
        spy,
        config=WalkForwardConfig(train_days=252, test_days=126, step_days=126),
    )

    folds.to_csv(ROOT / "outputs" / "walk_forward_folds.csv", index=False)
    oos.to_csv(ROOT / "outputs" / "walk_forward_oos_history.csv", index=False)

    with open(ROOT / "outputs" / "walk_forward_summary.md", "w", encoding="utf-8") as f:
        f.write("# GainZ Walk-Forward Validation\n\n")
        f.write("Rolling 252-trading-day training windows followed by 126-trading-day test windows.\n")
        f.write("Each fold selects a strategy/risk combination using training data only.\n\n")
        f.write("## Combined out-of-sample result\n\n")
        f.write(f"- Folds: {int(summary['folds'])}\n")
        f.write(f"- Folds beating SPY on total return: {int(summary['folds_beating_spy'])}/{int(summary['folds'])}\n")
        f.write(f"- GainZ OOS CAGR: {summary['strategy_cagr']:.2%}\n")
        f.write(f"- SPY OOS CAGR: {summary['spy_cagr']:.2%}\n")
        f.write(f"- GainZ OOS Sharpe: {summary['strategy_sharpe']:.2f}\n")
        f.write(f"- SPY OOS Sharpe: {summary['spy_sharpe']:.2f}\n")
        f.write(f"- GainZ OOS max drawdown: {summary['strategy_max_drawdown']:.2%}\n")
        f.write(f"- SPY OOS max drawdown: {summary['spy_max_drawdown']:.2%}\n\n")
        f.write("## Important limitation\n\n")
        f.write("This is temporal walk-forward validation, but the stock universe is still based on current constituents, so survivorship bias remains. Also, the strategy family itself was designed after inspecting this dataset, so this is not equivalent to a completely untouched future test.\n\n")
        f.write("## Fold details\n\n")
        f.write(folds.to_markdown(index=False))
        f.write("\n")

    print("\nCombined walk-forward OOS result")
    print(f"Folds: {int(summary['folds'])}; beat SPY in {int(summary['folds_beating_spy'])}")
    print(f"GainZ CAGR: {summary['strategy_cagr']:.2%} | SPY CAGR: {summary['spy_cagr']:.2%}")
    print(f"GainZ Sharpe: {summary['strategy_sharpe']:.2f} | SPY Sharpe: {summary['spy_sharpe']:.2f}")
    print(f"GainZ max DD: {summary['strategy_max_drawdown']:.2%} | SPY max DD: {summary['spy_max_drawdown']:.2%}")
    print("\nFold selections")
    print(folds[["fold", "train_start", "train_end", "test_start", "test_end", "variant", "risk_config", "test_cagr", "spy_test_cagr", "beat_spy_return"]].to_string(index=False))


if __name__ == "__main__":
    main()
