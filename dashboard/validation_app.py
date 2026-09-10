"""Streamlit validation page for the existing Momentum Portfolio strategy."""

from pathlib import Path
import sys

import pandas as pd
import plotly.express as px
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtesting.moving_average_backtest import calculate_portfolio_metrics
from backtesting.momentum_portfolio import (
    audit_price_data,
    run_momentum_portfolio_backtest,
)
from config.settings import load_settings


SETTINGS = load_settings()
RESEARCH_TICKERS = SETTINGS["universe"]["symbols"]
BENCHMARK = SETTINGS["universe"]["benchmark"]
INITIAL_CAPITAL = 10_000.0
TRANSACTION_COST = 0.001
SLIPPAGE = 0.0005


@st.cache_data(show_spinner=False)
def load_prices(ticker: str) -> pd.DataFrame:
    """Load one downloaded daily close file."""
    path = PROJECT_ROOT / "data" / f"{ticker}_daily.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path.name} is missing. Run data/download_prices.py first.")
    return pd.read_csv(
        path,
        skiprows=[1, 2],
        names=["Date", "Adj Close", "Close", "High", "Low", "Open", "Volume"],
        header=0,
        parse_dates=["Date"],
    )[["Date", "Close"]].dropna().sort_values("Date")


@st.cache_data(show_spinner=False)
def run_cached_validation(
    price_data: dict[str, pd.DataFrame],
    spy: pd.DataFrame,
    transaction_cost: float,
    slippage: float,
):
    """Cache one unchanged strategy run for a cost scenario."""
    return run_momentum_portfolio_backtest(
        price_data,
        spy,
        initial_capital=INITIAL_CAPITAL,
        transaction_cost_rate=transaction_cost,
        slippage_rate=slippage,
    )


def period_metrics(result, start: int, end: int) -> dict[str, float]:
    """Calculate metrics for a chronological slice using its daily returns."""
    period = result.history.iloc[start:end].reset_index(drop=True)
    strategy_returns = period["Portfolio return"]
    spy_returns = period["SPY return"]
    strategy_values = INITIAL_CAPITAL * (1 + strategy_returns).cumprod()
    spy_values = INITIAL_CAPITAL * (1 + spy_returns).cumprod()
    strategy = calculate_portfolio_metrics(
        period["Date"], strategy_values, strategy_returns, INITIAL_CAPITAL
    )
    spy = calculate_portfolio_metrics(
        period["Date"], spy_values, spy_returns, INITIAL_CAPITAL
    )
    return {
        "CAGR": strategy["cagr"],
        "Total return": strategy["total_return"],
        "Volatility": strategy["annualized_volatility"],
        "Sharpe": strategy["sharpe_ratio"],
        "Maximum drawdown": strategy["maximum_drawdown"],
        "SPY CAGR": spy["cagr"],
        "SPY Total return": spy["total_return"],
        "SPY Volatility": spy["annualized_volatility"],
        "SPY Sharpe": spy["sharpe_ratio"],
        "SPY Maximum drawdown": spy["maximum_drawdown"],
    }


def make_validation_table(results: dict[str, object], split: int) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for scenario, result in results.items():
        length = len(result.history)
        periods = {
            "Full period": (0, length),
            "Development period (70%)": (0, split),
            "Out-of-sample period (30%)": (split, length),
        }
        for period_name, (start, end) in periods.items():
            values = period_metrics(result, start, end)
            rows.append(
                {
                    "Cost scenario": scenario,
                    "Period": period_name,
                    "CAGR": values["CAGR"],
                    "Total return": values["Total return"],
                    "Volatility": values["Volatility"],
                    "Sharpe": values["Sharpe"],
                    "Maximum drawdown": values["Maximum drawdown"],
                    "SPY CAGR": values["SPY CAGR"],
                    "SPY Total return": values["SPY Total return"],
                    "SPY Volatility": values["SPY Volatility"],
                    "SPY Sharpe": values["SPY Sharpe"],
                    "SPY Maximum drawdown": values["SPY Maximum drawdown"],
                }
            )
    return pd.DataFrame(rows)


def apply_funky_style() -> None:
    """Add a lively visual layer while keeping research tables readable."""
    st.markdown(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Syne:wght@600;700;800&display=swap');

            :root {
                --ink: #f4f7ff;
                --muted: #aab4ce;
                --panel: rgba(20, 25, 43, 0.86);
                --line: rgba(142, 157, 204, 0.22);
                --cyan: #64f4e8;
                --pink: #ff6ea8;
                --yellow: #ffd166;
            }
            .stApp {
                background:
                    linear-gradient(135deg, rgba(100, 244, 232, 0.08), transparent 34%),
                    linear-gradient(315deg, rgba(255, 110, 168, 0.08), transparent 38%),
                    #0b0e17;
                color: var(--ink);
                font-family: 'Space Grotesk', sans-serif;
            }
            [data-testid="stAppViewContainer"] {
                background: transparent;
            }
            .block-container {
                max-width: 1440px;
                padding-top: 3.2rem;
                padding-bottom: 4rem;
            }
            h1, h2, h3 {
                font-family: 'Syne', sans-serif !important;
                letter-spacing: 0 !important;
                color: var(--ink) !important;
            }
            h1 {
                font-size: clamp(2.2rem, 5vw, 4.5rem) !important;
                line-height: 0.98 !important;
                background: linear-gradient(90deg, var(--cyan), var(--ink) 48%, var(--pink));
                -webkit-background-clip: text;
                background-clip: text;
                color: transparent !important;
                animation: titleIn 700ms cubic-bezier(.2,.8,.2,1) both;
            }
            h2, h3 {
                margin-top: 2rem !important;
            }
            p, [data-testid="stCaptionContainer"] {
                color: var(--muted) !important;
            }
            [data-testid="stMetric"] {
                min-height: 112px;
                padding: 1rem 1.05rem;
                border: 1px solid var(--line);
                border-radius: 16px;
                background: linear-gradient(145deg, rgba(28, 35, 58, .92), rgba(15, 19, 33, .9));
                box-shadow: 0 14px 34px rgba(0, 0, 0, .18);
                animation: cardIn 600ms cubic-bezier(.2,.8,.2,1) both;
            }
            [data-testid="stMetric"]:nth-child(odd) { border-color: rgba(100, 244, 232, .34); }
            [data-testid="stMetric"]:nth-child(even) { border-color: rgba(255, 110, 168, .28); }
            [data-testid="stMetricLabel"] { color: var(--muted) !important; }
            [data-testid="stMetricValue"] { color: var(--ink) !important; font-family: 'Syne', sans-serif; }
            [data-testid="stAlert"] {
                border: 1px solid rgba(255, 209, 102, .5);
                border-radius: 14px;
                background: rgba(80, 61, 23, .35);
                animation: cardIn 700ms 100ms both;
            }
            [data-testid="stDataFrame"] {
                border: 1px solid var(--line);
                border-radius: 14px;
                overflow: hidden;
                background: var(--panel);
                animation: cardIn 700ms 180ms both;
            }
            div[data-testid="stPlotlyChart"] {
                border: 1px solid var(--line);
                border-radius: 16px;
                padding: .45rem;
                background: rgba(15, 19, 33, .74);
                animation: chartIn 850ms cubic-bezier(.2,.8,.2,1) both;
            }
            .validation-kicker {
                display: inline-flex;
                align-items: center;
                gap: .55rem;
                margin: .2rem 0 1.1rem;
                color: var(--cyan);
                font-size: .76rem;
                font-weight: 700;
                letter-spacing: .16em;
                text-transform: uppercase;
            }
            .validation-kicker::before {
                content: '';
                width: 9px;
                height: 9px;
                border-radius: 50%;
                background: var(--pink);
                box-shadow: 0 0 18px var(--pink);
                animation: pulse 1.8s ease-in-out infinite;
            }
            @keyframes titleIn {
                from { opacity: 0; transform: translateY(14px); filter: blur(8px); }
                to { opacity: 1; transform: translateY(0); filter: blur(0); }
            }
            @keyframes cardIn {
                from { opacity: 0; transform: translateY(18px); }
                to { opacity: 1; transform: translateY(0); }
            }
            @keyframes chartIn {
                from { opacity: 0; transform: scale(.985); }
                to { opacity: 1; transform: scale(1); }
            }
            @keyframes pulse {
                0%, 100% { transform: scale(.8); opacity: .7; }
                50% { transform: scale(1.15); opacity: 1; }
            }
            @media (prefers-reduced-motion: reduce) {
                *, *::before, *::after { animation-duration: .01ms !important; animation-iteration-count: 1 !important; }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    """Render the V0.7 validation dashboard."""
    st.set_page_config(page_title="GainZ Strategy Validation", layout="wide")
    apply_funky_style()
    st.markdown('<div class="validation-kicker">GainZ Alpha · Reality check</div>', unsafe_allow_html=True)
    st.title("Strategy Validation")
    st.caption(
        "Validation of the existing monthly top-five 12-month momentum portfolio. "
        "No parameters or strategy rules are optimized here."
    )
    st.warning(
        "Survivorship and selection bias: this 15-stock universe consists of companies selected today. "
        "It is not a historical point-in-time universe, so results may be biased upward."
    )

    price_data: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    for ticker in RESEARCH_TICKERS:
        try:
            price_data[ticker] = load_prices(ticker)
        except (FileNotFoundError, ValueError):
            missing.append(ticker)
    try:
        spy = load_prices(BENCHMARK)
    except (FileNotFoundError, ValueError) as error:
        st.error(str(error))
        return
    if missing:
        st.error("Missing or invalid research data: " + ", ".join(missing))
        return

    try:
        before_costs = run_cached_validation(price_data, spy, 0.0, 0.0)
        after_costs = run_cached_validation(
            price_data, spy, TRANSACTION_COST, SLIPPAGE
        )
    except ValueError as error:
        st.error(str(error))
        return

    split = int(len(before_costs.history) * 0.70)
    results = {"Before costs": before_costs, "After costs": after_costs}
    validation_table = make_validation_table(results, split)
    percentage_columns = {
        "CAGR": "{:.1%}", "Total return": "{:.1%}", "Volatility": "{:.1%}",
        "Maximum drawdown": "{:.1%}", "SPY CAGR": "{:.1%}",
        "SPY Total return": "{:.1%}", "SPY Volatility": "{:.1%}",
        "SPY Maximum drawdown": "{:.1%}",
    }
    st.subheader("Performance validation")
    st.dataframe(
        validation_table.style.format(
            {**percentage_columns, "Sharpe": "{:.2f}", "SPY Sharpe": "{:.2f}"}
        ),
        width="stretch",
        hide_index=True,
    )
    st.caption(
        "After-cost scenario: 0.10% transaction cost plus 0.05% slippage applied to portfolio turnover at each effective rebalance."
    )

    after_history = after_costs.history[
        ["Date", "Portfolio value", "SPY Buy & Hold"]
    ].melt(id_vars="Date", var_name="Series", value_name="Value")
    st.plotly_chart(
        px.line(after_history, x="Date", y="Value", color="Series", title="After-cost portfolio growth vs SPY"),
        width="stretch",
    )
    after_drawdown = after_costs.history[
        ["Date", "Portfolio drawdown", "SPY drawdown"]
    ].melt(id_vars="Date", var_name="Series", value_name="Drawdown")
    st.plotly_chart(
        px.line(after_drawdown, x="Date", y="Drawdown", color="Series", title="After-cost drawdown comparison").update_layout(yaxis_tickformat=".0%"),
        width="stretch",
    )

    st.subheader("Data alignment audit")
    audit = audit_price_data(price_data, spy)
    st.dataframe(audit, width="stretch", hide_index=True)
    st.caption(
        "The backtest uses dates shared by all 15 stocks and SPY. Momentum scores are NaN until a stock has 252 prior trading observations, so it cannot be selected earlier."
    )

    st.subheader("Rebalance audit")
    st.dataframe(
        after_costs.monthly_holdings.style.format(
            {
                "Invested": "{:.1%}", "Cash": "{:.1%}", "Turnover": "{:.1%}",
                "Transaction Cost": "{:.2%}", "Slippage": "{:.2%}",
                "Total Trading Cost": "{:.2%}", "Stocks Held": "{:.0f}",
            }
        ),
        width="stretch",
        hide_index=True,
    )
    st.caption(
        "Each audit row ranks stocks using the rebalance-date close and applies the displayed trades on the following trading day."
    )


if __name__ == "__main__":
    main()