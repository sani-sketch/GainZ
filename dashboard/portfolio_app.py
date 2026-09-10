"""Streamlit page for the monthly top-five momentum portfolio."""

from pathlib import Path
import sys

import pandas as pd
import plotly.express as px
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtesting.momentum_portfolio import run_momentum_portfolio_backtest
from config.settings import load_settings


SETTINGS = load_settings()
RESEARCH_TICKERS = SETTINGS["universe"]["symbols"]
BENCHMARK = SETTINGS["universe"]["benchmark"]
INITIAL_CAPITAL = 10_000.0


@st.cache_data(show_spinner=False)
def load_prices(ticker: str) -> pd.DataFrame:
    """Load one downloaded Yahoo Finance CSV."""
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
def run_cached_portfolio(price_data: dict[str, pd.DataFrame], spy: pd.DataFrame):
    """Cache the portfolio calculation for the downloaded research files."""
    return run_momentum_portfolio_backtest(
        price_data,
        spy,
        initial_capital=INITIAL_CAPITAL,
    )


def make_growth_chart(result) -> object:
    chart_data = result.history[
        ["Date", "Portfolio value", "SPY Buy & Hold"]
    ].melt(id_vars="Date", var_name="Portfolio", value_name="Value")
    return px.line(
        chart_data,
        x="Date",
        y="Value",
        color="Portfolio",
        title="Momentum portfolio growth vs SPY",
        labels={"Value": "Portfolio value (USD)", "Portfolio": ""},
        render_mode="svg",
    ).update_layout(hovermode="x unified")


def make_drawdown_chart(result) -> object:
    chart_data = result.history[
        ["Date", "Portfolio drawdown", "SPY drawdown"]
    ].melt(id_vars="Date", var_name="Portfolio", value_name="Drawdown")
    return px.line(
        chart_data,
        x="Date",
        y="Drawdown",
        color="Portfolio",
        title="Drawdown comparison",
        labels={"Drawdown": "Drawdown", "Portfolio": ""},
        render_mode="svg",
    ).update_layout(hovermode="x unified", yaxis_tickformat=".0%")


def main() -> None:
    """Render the portfolio research page."""
    st.set_page_config(page_title="GainZ Momentum Portfolio", layout="wide")
    st.title("Momentum Portfolio")
    st.caption(
        "Monthly research portfolio: top five stocks with positive trailing 12-month momentum, equally weighted."
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
        result = run_cached_portfolio(price_data, spy)
    except ValueError as error:
        st.error(str(error))
        return

    metrics = result.metrics
    summary = st.columns(6)
    summary[0].metric("CAGR", f"{metrics['cagr']:.1%}")
    summary[1].metric("Total return", f"{metrics['total_return']:.1%}")
    summary[2].metric("Annualized volatility", f"{metrics['annualized_volatility']:.1%}")
    summary[3].metric("Sharpe ratio", f"{metrics['sharpe_ratio']:.2f}")
    summary[4].metric("Maximum drawdown", f"{metrics['maximum_drawdown']:.1%}")
    summary[5].metric("Final value", f"${metrics['final_portfolio_value']:,.0f}")

    st.plotly_chart(make_growth_chart(result), width="stretch")
    comparison = pd.DataFrame(
        {
            "Momentum Portfolio": [
                metrics["cagr"], metrics["total_return"], metrics["annualized_volatility"],
                metrics["sharpe_ratio"], metrics["maximum_drawdown"], metrics["final_portfolio_value"],
            ],
            "SPY Buy & Hold": [
                metrics["spy_cagr"], metrics["spy_total_return"], metrics["spy_annualized_volatility"],
                metrics["spy_sharpe_ratio"], metrics["spy_maximum_drawdown"], metrics["spy_final_portfolio_value"],
            ],
        },
        index=["CAGR", "Total return", "Annualized volatility", "Sharpe ratio", "Maximum drawdown", "Final portfolio value"],
    )
    st.dataframe(
        comparison.style.format(
            {"Momentum Portfolio": "{:.1%}", "SPY Buy & Hold": "{:.1%}"},
            subset=pd.IndexSlice[["CAGR", "Total return", "Annualized volatility", "Maximum drawdown"], :],
        ).format(
            {"Momentum Portfolio": "{:.2f}", "SPY Buy & Hold": "{:.2f}"},
            subset=pd.IndexSlice[["Sharpe ratio"], :],
        ).format(
            {"Momentum Portfolio": "${:,.0f}", "SPY Buy & Hold": "${:,.0f}"},
            subset=pd.IndexSlice[["Final portfolio value"], :],
        ),
        width="stretch",
    )
    st.plotly_chart(make_drawdown_chart(result), width="stretch")

    detail = st.columns(3)
    detail[0].metric("Average stocks held", f"{metrics['average_stocks_held']:.2f}")
    detail[1].metric("Number of rebalances", f"{metrics['number_of_rebalances']:.0f}")
    detail[2].metric("Time in cash", f"{metrics['percentage_cash']:.1%}")

    st.subheader("Monthly portfolio holdings")
    st.dataframe(result.monthly_holdings, width="stretch", hide_index=True)

    st.subheader("Latest momentum ranking")
    ranking = result.latest_ranking.copy()
    ranking["Momentum"] = ranking["Momentum"].map(lambda value: f"{value:.1%}")
    ranking["Allocation"] = ranking["Allocation"].map(lambda value: f"{value:.1%}")
    st.dataframe(
        ranking[["Rank", "Ticker", "Momentum", "Allocation"]],
        width="stretch",
        hide_index=True,
    )

    st.subheader("Latest portfolio allocation")
    allocation = result.latest_allocation.copy()
    allocation["Momentum"] = allocation["Momentum"].map(lambda value: f"{value:.1%}")
    allocation["Allocation"] = allocation["Allocation"].map(lambda value: f"{value:.1%}")
    st.dataframe(allocation, width="stretch", hide_index=True)
    st.caption(
        f"Shared research window: {result.start_date.date()} to {result.end_date.date()}. "
        "A month-end ranking is applied from the next trading day; results are historical research only."
    )


if __name__ == "__main__":
    main()