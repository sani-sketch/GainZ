"""Fast browser view for the Multi-Stock Research section."""

import pandas as pd
import streamlit as st

from dashboard.app import (
    RESEARCH_TICKERS,
    load_price_data,
    make_backtest_chart,
    make_drawdown_chart,
    make_moving_average_chart,
    run_cached_multi_stock_research,
)
from backtesting.multi_stock_backtest import (
    MOMENTUM_STRATEGY,
    TREND_MOMENTUM_STRATEGY,
    TREND_STRATEGY,
)


INITIAL_CAPITAL = 10_000.0


@st.cache_data(show_spinner=False)
def load_research_prices() -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    """Load the research universe once and retain per-ticker errors."""
    prices: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}
    for ticker in RESEARCH_TICKERS:
        try:
            prices[ticker] = load_price_data(ticker)
        except Exception as error:
            errors[ticker] = str(error)
    return prices, errors


def main() -> None:
    """Render only the focused multi-stock research experience."""
    st.set_page_config(page_title="GainZ Multi-Stock Research", layout="wide")
    st.title("Multi-Stock Research")
    st.caption("Fast research view. Historical results are descriptive research statistics only.")

    price_data, load_errors = load_research_prices()
    if load_errors:
        st.warning("Unavailable tickers: " + ", ".join(sorted(load_errors)))

    runs = {
        strategy: run_cached_multi_stock_research(
            price_data,
            INITIAL_CAPITAL,
            strategy,
        )
        for strategy in [TREND_STRATEGY, MOMENTUM_STRATEGY, TREND_MOMENTUM_STRATEGY]
    }
    selected_strategy = st.selectbox(
        "Strategy",
        [TREND_STRATEGY, MOMENTUM_STRATEGY, TREND_MOMENTUM_STRATEGY],
    )
    selected_run = runs[selected_strategy]
    metrics = selected_run.metrics

    if metrics.empty:
        st.info("No ticker has enough valid data for this strategy.")
        return

    cagr_beats = metrics["Strategy CAGR"] > metrics["Buy & Hold CAGR"]
    sharpe_beats = metrics["Strategy Sharpe"] > metrics["Buy & Hold Sharpe"]
    summary = st.columns(7)
    summary[0].metric("Stocks tested", len(metrics))
    summary[1].metric("CAGR beats", int(cagr_beats.sum()))
    summary[2].metric("CAGR beat rate", f"{cagr_beats.mean():.1%}")
    summary[3].metric("Sharpe beats", int(sharpe_beats.sum()))
    summary[4].metric("Average CAGR", f"{metrics['Strategy CAGR'].mean():.1%}")
    summary[5].metric("Average buy & hold CAGR", f"{metrics['Buy & Hold CAGR'].mean():.1%}")
    summary[6].metric("Average excess CAGR", f"{metrics['Excess CAGR'].mean():+.1%}")

    table_columns = [
        "Ticker", "Strategy CAGR", "Buy & Hold CAGR", "Excess CAGR",
        "Strategy Sharpe", "Buy & Hold Sharpe", "Strategy Max DD",
        "Buy & Hold Max DD", "Time Invested", "Position Changes",
    ]
    table = metrics[table_columns].style.format(
        {
            "Strategy CAGR": "{:.1%}", "Buy & Hold CAGR": "{:.1%}",
            "Excess CAGR": "{:+.1%}", "Strategy Sharpe": "{:.2f}",
            "Buy & Hold Sharpe": "{:.2f}", "Strategy Max DD": "{:.1%}",
            "Buy & Hold Max DD": "{:.1%}", "Time Invested": "{:.1%}",
            "Position Changes": "{:.0f}",
        }
    )
    st.dataframe(table, width="stretch", hide_index=True)

    st.subheader("Strategy Comparison")
    comparison_rows = []
    for strategy, result in runs.items():
        strategy_metrics = result.metrics
        if strategy_metrics.empty:
            continue
        comparison_rows.append(
            {
                "Strategy": strategy,
                "Average CAGR": strategy_metrics["Strategy CAGR"].mean(),
                "Average Excess CAGR": strategy_metrics["Excess CAGR"].mean(),
                "Average Sharpe": strategy_metrics["Strategy Sharpe"].mean(),
                "Average Max Drawdown": strategy_metrics["Strategy Max DD"].mean(),
                "CAGR beats Buy & Hold": (
                    strategy_metrics["Strategy CAGR"] > strategy_metrics["Buy & Hold CAGR"]
                ).mean(),
                "Sharpe beats Buy & Hold": (
                    strategy_metrics["Strategy Sharpe"] > strategy_metrics["Buy & Hold Sharpe"]
                ).mean(),
                "Average Time Invested": strategy_metrics["Time Invested"].mean(),
            }
        )
    st.dataframe(
        pd.DataFrame(comparison_rows).style.format(
            {
                "Average CAGR": "{:.1%}", "Average Excess CAGR": "{:+.1%}",
                "Average Sharpe": "{:.2f}", "Average Max Drawdown": "{:.1%}",
                "CAGR beats Buy & Hold": "{:.1%}",
                "Sharpe beats Buy & Hold": "{:.1%}",
                "Average Time Invested": "{:.1%}",
            }
        ),
        width="stretch",
        hide_index=True,
    )

    ticker = st.selectbox("Inspect a ticker", list(metrics["Ticker"]))
    result = selected_run.backtests[ticker]
    prices = result.history[["Date", "Close"]]
    st.plotly_chart(make_moving_average_chart(prices, ticker), width="stretch")
    st.plotly_chart(make_backtest_chart(result, ticker), width="stretch")
    st.plotly_chart(make_drawdown_chart(result, ticker), width="stretch")

    selected_metrics = pd.DataFrame(
        {
            "Selected Strategy": result.strategy_metrics,
            "Buy & Hold": result.buy_and_hold_metrics,
        }
    )
    st.dataframe(selected_metrics, width="stretch")


if __name__ == "__main__":
    main()