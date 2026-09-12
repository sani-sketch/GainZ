"""Compare the fixed Momentum Portfolio across the original and broad universes."""

from pathlib import Path
import sys

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtesting.momentum_portfolio import (
    audit_portfolio_result,
    run_momentum_portfolio_backtest,
)
from config.settings import load_settings
from dashboard.validation_app import apply_funky_style, period_metrics


SETTINGS = load_settings()
ORIGINAL_TICKERS = SETTINGS["universe"]["symbols"]
BROAD_TICKERS = SETTINGS["universe"]["broad_symbols"]
BENCHMARK = SETTINGS["universe"]["benchmark"]
INITIAL_CAPITAL = 10_000.0
TRANSACTION_COST = 0.001
SLIPPAGE = 0.0005


@st.cache_data(show_spinner=False)
def load_prices(ticker: str) -> pd.DataFrame:
    """Load one local Yahoo Finance daily close file."""
    path = PROJECT_ROOT / "data" / f"{ticker}_daily.csv"
    if not path.exists():
        raise FileNotFoundError(path.name)
    return pd.read_csv(
        path,
        skiprows=[1, 2],
        names=["Date", "Adj Close", "Close", "High", "Low", "Open", "Volume"],
        header=0,
        parse_dates=["Date"],
    )[["Date", "Close"]].dropna().sort_values("Date")


@st.cache_data(show_spinner=False)
def run_cached(price_data: dict[str, pd.DataFrame], spy: pd.DataFrame, cost: float, slippage: float):
    """Cache one fixed-strategy universe run."""
    return run_momentum_portfolio_backtest(
        price_data,
        spy,
        initial_capital=INITIAL_CAPITAL,
        transaction_cost_rate=cost,
        slippage_rate=slippage,
    )


def load_universe(tickers: list[str]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    prices: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    for ticker in tickers:
        try:
            prices[ticker] = load_prices(ticker)
        except (FileNotFoundError, ValueError):
            missing.append(ticker)
    return prices, missing


def comparison_table(results: dict[tuple[str, str], object]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (universe, scenario), result in results.items():
        split = int(len(result.history) * 0.70)
        periods = {
            "Full period": (0, len(result.history)),
            "Development period (70%)": (0, split),
            "Out-of-sample period (30%)": (split, len(result.history)),
        }
        for period_name, (start, end) in periods.items():
            metrics = period_metrics(result, start, end)
            rows.append(
                {
                    "Universe": universe,
                    "Cost scenario": scenario,
                    "Period": period_name,
                    "CAGR": metrics["CAGR"],
                    "Total return": metrics["Total return"],
                    "Volatility": metrics["Volatility"],
                    "Sharpe": metrics["Sharpe"],
                    "Maximum drawdown": metrics["Maximum drawdown"],
                    "SPY CAGR": metrics["SPY CAGR"],
                    "SPY Sharpe": metrics["SPY Sharpe"],
                    "Portfolio turnover": result.monthly_holdings["Turnover"].sum(),
                    "Rebalances": len(result.monthly_holdings),
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    """Render robust-universe validation without changing the portfolio rules."""
    st.set_page_config(page_title="GainZ Robust Universe Testing", layout="wide")
    apply_funky_style()
    st.markdown('<div class="validation-kicker">GainZ Alpha · Wider lens</div>', unsafe_allow_html=True)
    st.title("Robust Universe Testing")
    st.caption(
        "The unchanged monthly top-five momentum portfolio tested on the original 15-stock sample and a broader sector-diversified sample."
    )
    st.warning(
        "Survivorship and selection bias remains: the broader universe uses current constituents selected today, not a point-in-time historical membership database."
    )

    original_prices, original_missing = load_universe(ORIGINAL_TICKERS)
    broad_prices, broad_missing = load_universe(BROAD_TICKERS)
    try:
        spy = load_prices(BENCHMARK)
    except FileNotFoundError:
        st.error("SPY_daily.csv is missing. Run data/download_prices.py first.")
        return

    status = st.columns(3)
    status[0].metric("Original universe", f"{len(original_prices)}/{len(ORIGINAL_TICKERS)}")
    status[1].metric("Broad universe", f"{len(broad_prices)}/{len(BROAD_TICKERS)}")
    status[2].metric("Benchmark", BENCHMARK)
    if original_missing:
        st.warning("Missing original files: " + ", ".join(original_missing))
    if broad_missing:
        st.error(
            f"The broad-universe comparison is incomplete: {len(broad_missing)} files are missing. "
            "Run `python data/download_prices.py` to download the configured broad sample."
        )
        st.caption("Missing broad tickers: " + ", ".join(broad_missing))
        return

    results: dict[tuple[str, str], object] = {}
    for universe, prices in [("Original 15-stock", original_prices), ("Broad universe", broad_prices)]:
        results[(universe, "Before costs")] = run_cached(prices, spy, 0.0, 0.0)
        results[(universe, "After costs")] = run_cached(
            prices, spy, TRANSACTION_COST, SLIPPAGE
        )

    st.subheader("Original 15-stock universe vs broader universe vs SPY")
    table = comparison_table(results)
    st.dataframe(
        table.style.format(
            {
                "CAGR": "{:.1%}", "Total return": "{:.1%}", "Volatility": "{:.1%}",
                "Sharpe": "{:.2f}", "Maximum drawdown": "{:.1%}", "SPY CAGR": "{:.1%}",
                "SPY Sharpe": "{:.2f}", "Portfolio turnover": "{:.1%}",
                "Rebalances": "{:.0f}",
            }
        ),
        width="stretch",
        hide_index=True,
    )
    st.caption(
        "After-cost results use 0.10% transaction cost plus 0.05% slippage. "
        "Portfolio turnover is cumulative gross weight turnover (so 24.6 equals 2,460%), not annualized turnover. "
        "No parameter, universe, or strategy optimization was performed."
    )

    broad_after = results[("Broad universe", "After costs")]
    audit_results = audit_portfolio_result(
        broad_prices,
        spy,
        broad_after,
        TRANSACTION_COST,
        SLIPPAGE,
    )
    split = int(len(broad_after.history) * 0.70)
    dates = pd.DatetimeIndex(broad_after.history["Date"])
    split_ok = (
        dates.is_monotonic_increasing
        and 0 < split < len(dates)
        and dates[split - 1] < dates[split]
    )
    audit_results = pd.concat(
        [
            audit_results,
            pd.DataFrame(
                [
                    {
                        "Check": "70/30 split is chronological",
                        "Status": "PASS" if split_ok else "FAIL",
                        "Details": f"Development ends {dates[split - 1].date()}; OOS starts {dates[split].date()}.",
                    },
                    {
                        "Check": "Current-universe survivorship/selection bias",
                        "Status": "WARNING",
                        "Details": "The broad sample uses today's constituents, not point-in-time membership.",
                    },
                    {
                        "Check": "Broad universe selection basis",
                        "Status": "WARNING",
                        "Details": "Stocks were selected for current size/liquidity and sector coverage, not historical returns.",
                    },
                ]
            ),
        ],
        ignore_index=True,
    )
    st.subheader("Audit Results")
    st.dataframe(audit_results, width="stretch", hide_index=True)
    st.caption(
        "A PASS means the implementation invariant was verified. WARNINGS are structural limitations that this backtest does not correct."
    )

    st.subheader("Latest broad-universe data audit")
    st.dataframe(
        broad_after.data_audit,
        width="stretch",
        hide_index=True,
    )
    st.subheader("Broad-universe rebalance audit")
    st.dataframe(
        broad_after.monthly_holdings.style.format(
            {
                "Invested": "{:.1%}", "Cash": "{:.1%}", "Turnover": "{:.1%}",
                "Transaction Cost": "{:.2%}", "Slippage": "{:.2%}",
                "Total Trading Cost": "{:.2%}", "Stocks Held": "{:.0f}",
            }
        ),
        width="stretch",
        hide_index=True,
    )


if __name__ == "__main__":
    main()