"""A small Streamlit dashboard for viewing downloaded price data."""

from pathlib import Path
import sys

import pandas as pd
import plotly.express as px
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIRECTORY = PROJECT_ROOT / "data"
TRADING_DAYS_PER_YEAR = 252

# Streamlit runs this file from the dashboard folder. Add the project root so
# sibling packages such as backtesting can be imported reliably.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtesting.moving_average_backtest import (
    BacktestResult,
    calculate_portfolio_metrics,
    make_buy_and_hold_history,
    run_moving_average_backtest,
)
from backtesting.multi_stock_backtest import (
    MOMENTUM_STRATEGY,
    TREND_MOMENTUM_STRATEGY,
    TREND_STRATEGY,
    run_multi_stock_research,
)
from config.settings import load_settings


SETTINGS = load_settings()
RESEARCH_TICKERS = SETTINGS["universe"]["symbols"]
BENCHMARK = SETTINGS["universe"]["benchmark"]


@st.cache_data(show_spinner=False)
def load_price_data(symbol: str) -> pd.DataFrame:
    """Read one Yahoo Finance CSV and return Date and Close columns."""
    file_path = DATA_DIRECTORY / f"{symbol}_daily.csv"

    if not file_path.exists():
        raise FileNotFoundError(
            f"{file_path.name} is missing. Run data/download_prices.py first."
        )

    # yfinance writes a three-row header for a one-symbol DataFrame.
    prices = pd.read_csv(
        file_path,
        skiprows=[1, 2],
        names=["Date", "Adj Close", "Close", "High", "Low", "Open", "Volume"],
        header=0,
        parse_dates=["Date"],
    )
    prices = prices[["Date", "Close"]].dropna().sort_values("Date")
    return prices


@st.cache_data(show_spinner=False)
def make_price_chart(prices: pd.DataFrame, symbol: str):
    """Create an interactive Plotly line chart for one symbol."""
    line_color = "#d85b43" if symbol == "AAPL" else "#1f6f78"
    return px.line(
        prices,
        x="Date",
        y="Close",
        title=f"{symbol} closing price",
        labels={"Date": "Date", "Close": "Price (USD)"},
        render_mode="svg",
        template="plotly_white",
    ).update_traces(line={"color": line_color, "width": 2.5}).update_layout(
        hovermode="x unified",
        paper_bgcolor="#0d1217",
        plot_bgcolor="#0d1217",
        font={"color": "#e8eef0"},
        margin={"l": 20, "r": 20, "t": 55, "b": 20},
        xaxis={"showgrid": False, "linecolor": "#42515a", "tickfont": {"color": "#aab8bd"}},
        yaxis={"gridcolor": "#27343b", "zeroline": False, "tickfont": {"color": "#aab8bd"}},
    )


@st.cache_data(show_spinner=False)
def make_cumulative_return_chart(aapl: pd.DataFrame, spy: pd.DataFrame):
    """Create a chart comparing growth from the same starting value."""
    combined = aapl.merge(spy, on="Date", suffixes=("_AAPL", "_SPY"))
    comparison = combined[["Date", "Close_AAPL", "Close_SPY"]].copy()
    comparison["AAPL"] = comparison["Close_AAPL"] / comparison["Close_AAPL"].iloc[0] * 100
    comparison["SPY"] = comparison["Close_SPY"] / comparison["Close_SPY"].iloc[0] * 100
    comparison = comparison[["Date", "AAPL", "SPY"]].melt(
        id_vars="Date", var_name="Symbol", value_name="Growth"
    )

    chart = px.line(
        comparison,
        x="Date",
        y="Growth",
        color="Symbol",
        title="Cumulative price growth (start = 100)",
        labels={"Date": "Date", "Growth": "Value", "Symbol": ""},
        color_discrete_map={"AAPL": "#d85b43", "SPY": "#1f6f78"},
        render_mode="svg",
    )
    return chart.update_layout(
        hovermode="x unified",
        paper_bgcolor="#0d1217",
        plot_bgcolor="#0d1217",
        font={"color": "#e8eef0"},
        margin={"l": 20, "r": 20, "t": 55, "b": 20},
        legend={"orientation": "h", "y": 1.08, "x": 0},
        xaxis={"showgrid": False, "linecolor": "#42515a", "tickfont": {"color": "#aab8bd"}},
        yaxis={"gridcolor": "#27343b", "zeroline": False, "tickfont": {"color": "#aab8bd"}},
    )


@st.cache_data(show_spinner=False)
def make_moving_average_chart(prices: pd.DataFrame, symbol: str = "AAPL"):
    """Create a price chart with 50-day and 200-day averages."""
    prices = prices.copy()
    prices["50-day average"] = prices["Close"].rolling(window=50).mean()
    prices["200-day average"] = prices["Close"].rolling(window=200).mean()
    price_label = f"{symbol} price"
    chart_data = prices.rename(columns={"Close": price_label}).melt(
        id_vars="Date",
        value_vars=[price_label, "50-day average", "200-day average"],
        var_name="Series",
        value_name="Price",
    )

    chart = px.line(
        chart_data,
        x="Date",
        y="Price",
        color="Series",
        title=f"{symbol} price with moving averages",
        labels={"Date": "Date", "Price": "Price (USD)", "Series": ""},
        color_discrete_map={
            price_label: "#e8eef0",
            "50-day average": "#d85b43",
            "200-day average": "#1f6f78",
        },
        render_mode="svg",
    )
    return chart.update_layout(
        hovermode="x unified",
        paper_bgcolor="#0d1217",
        plot_bgcolor="#0d1217",
        font={"color": "#e8eef0"},
        margin={"l": 20, "r": 20, "t": 55, "b": 20},
        legend={"orientation": "h", "y": 1.08, "x": 0},
        xaxis={"showgrid": False, "linecolor": "#42515a", "tickfont": {"color": "#aab8bd"}},
        yaxis={"gridcolor": "#27343b", "zeroline": False, "tickfont": {"color": "#aab8bd"}},
    )


@st.cache_data(show_spinner=False)
def make_backtest_chart(result: BacktestResult, symbol: str = "AAPL"):
    """Create a chart comparing the strategy with buy-and-hold for one symbol."""
    chart_data = result.history[
        ["Date", "Strategy portfolio", "Buy and hold portfolio"]
    ].melt(id_vars="Date", var_name="Portfolio", value_name="Value")
    chart = px.line(
        chart_data,
        x="Date",
        y="Value",
        color="Portfolio",
        title=f"{symbol} backtest portfolio value",
        labels={"Date": "Date", "Value": "Portfolio value (USD)", "Portfolio": ""},
        color_discrete_map={
            "Strategy portfolio": "#d85b43",
            "Buy and hold portfolio": "#1f6f78",
        },
        render_mode="svg",
    )
    return chart.update_layout(
        hovermode="x unified",
        paper_bgcolor="#0d1217",
        plot_bgcolor="#0d1217",
        font={"color": "#e8eef0"},
        margin={"l": 20, "r": 20, "t": 55, "b": 20},
        legend={"orientation": "h", "y": 1.08, "x": 0},
        xaxis={"showgrid": False, "linecolor": "#42515a", "tickfont": {"color": "#aab8bd"}},
        yaxis={"gridcolor": "#27343b", "zeroline": False, "tickfont": {"color": "#aab8bd"}},
    )


@st.cache_data(show_spinner=False)
def make_equity_curve_chart(
    result: BacktestResult,
    aapl_buy_and_hold: pd.DataFrame,
    spy_buy_and_hold: pd.DataFrame,
):
    """Create an equity curve comparing the strategy with both benchmarks."""
    chart_data = result.history[["Date", "Strategy portfolio"]].rename(
        columns={"Strategy portfolio": "GainZ Alpha Strategy"}
    )
    chart_data = chart_data.merge(
        aapl_buy_and_hold[["Date", "AAPL Buy & Hold"]], on="Date"
    ).merge(spy_buy_and_hold[["Date", "SPY Buy & Hold"]], on="Date")
    chart_data = chart_data.melt(
        id_vars="Date", var_name="Portfolio", value_name="Value"
    )
    chart = px.line(
        chart_data,
        x="Date",
        y="Value",
        color="Portfolio",
        title="Equity curves (starting value = $10,000)",
        labels={"Date": "Date", "Value": "Portfolio value (USD)", "Portfolio": ""},
        color_discrete_map={
            "GainZ Alpha Strategy": "#d85b43",
            "AAPL Buy & Hold": "#e8eef0",
            "SPY Buy & Hold": "#1f6f78",
        },
        render_mode="svg",
    )
    return chart.update_layout(
        hovermode="x unified",
        paper_bgcolor="#0d1217",
        plot_bgcolor="#0d1217",
        font={"color": "#e8eef0"},
        margin={"l": 20, "r": 20, "t": 55, "b": 20},
        legend={"orientation": "h", "y": 1.08, "x": 0},
        xaxis={"showgrid": False, "linecolor": "#42515a", "tickfont": {"color": "#aab8bd"}},
        yaxis={"gridcolor": "#27343b", "zeroline": False, "tickfont": {"color": "#aab8bd"}},
    )


@st.cache_data(show_spinner=False)
def make_drawdown_chart(result: BacktestResult, symbol: str = "AAPL"):
    """Create a chart showing a strategy's falls from previous peaks."""
    chart = px.line(
        result.history,
        x="Date",
        y="Strategy drawdown",
        title=f"{symbol} GainZ Alpha strategy drawdown",
        labels={"Date": "Date", "Strategy drawdown": "Drawdown"},
        render_mode="svg",
    )
    return chart.update_traces(
        line={"color": "#d85b43"},
        fill="tozeroy",
        fillcolor="rgba(216, 91, 67, 0.25)",
    ).update_layout(
        hovermode="x unified",
        paper_bgcolor="#0d1217",
        plot_bgcolor="#0d1217",
        font={"color": "#e8eef0"},
        margin={"l": 20, "r": 20, "t": 55, "b": 20},
        xaxis={"showgrid": False, "linecolor": "#42515a", "tickfont": {"color": "#aab8bd"}},
        yaxis={"gridcolor": "#27343b", "zeroline": False, "tickformat": ".0%", "tickfont": {"color": "#aab8bd"}},
    )


@st.cache_data(show_spinner=False)
def calculate_insights(aapl: pd.DataFrame, spy: pd.DataFrame) -> dict[str, float | str]:
    """Calculate simple historical statistics from the two price series."""
    combined = aapl.merge(spy, on="Date", suffixes=("_AAPL", "_SPY"))
    prices = combined.set_index("Date")
    daily_returns = prices.pct_change(fill_method=None).dropna()
    aapl_50_day_average = prices["Close_AAPL"].rolling(window=50).mean().iloc[-1]
    aapl_200_day_average = prices["Close_AAPL"].rolling(window=200).mean().iloc[-1]

    insights = {
        "aapl_50_day_average": aapl_50_day_average,
        "aapl_200_day_average": aapl_200_day_average,
        "aapl_1d_return": prices["Close_AAPL"].iloc[-1] / prices["Close_AAPL"].iloc[-2] - 1,
        "spy_1d_return": prices["Close_SPY"].iloc[-1] / prices["Close_SPY"].iloc[-2] - 1,
        "aapl_1m_return": prices["Close_AAPL"].iloc[-1] / prices["Close_AAPL"].iloc[-22] - 1,
        "spy_1m_return": prices["Close_SPY"].iloc[-1] / prices["Close_SPY"].iloc[-22] - 1,
        "aapl_1y_return": prices["Close_AAPL"].iloc[-1] / prices["Close_AAPL"].iloc[-253] - 1,
        "spy_1y_return": prices["Close_SPY"].iloc[-1] / prices["Close_SPY"].iloc[-253] - 1,
        "aapl_return": prices["Close_AAPL"].iloc[-1] / prices["Close_AAPL"].iloc[0] - 1,
        "spy_return": prices["Close_SPY"].iloc[-1] / prices["Close_SPY"].iloc[0] - 1,
        "aapl_volatility": daily_returns["Close_AAPL"].std() * TRADING_DAYS_PER_YEAR ** 0.5,
        "spy_volatility": daily_returns["Close_SPY"].std() * TRADING_DAYS_PER_YEAR ** 0.5,
        "aapl_earlier_volatility": daily_returns["Close_AAPL"].std() * len(daily_returns) ** 0.5,
        "spy_earlier_volatility": daily_returns["Close_SPY"].std() * len(daily_returns) ** 0.5,
        "aapl_best_day": daily_returns["Close_AAPL"].max(),
        "aapl_worst_day": daily_returns["Close_AAPL"].min(),
        "spy_best_day": daily_returns["Close_SPY"].max(),
        "spy_worst_day": daily_returns["Close_SPY"].min(),
        "correlation": daily_returns["Close_AAPL"].corr(daily_returns["Close_SPY"]),
    }
    insights["aapl_trend_status"] = (
        "Uptrend" if aapl_50_day_average > aapl_200_day_average else "Downtrend"
    )

    for symbol in ["AAPL", "SPY"]:
        close_prices = prices[f"Close_{symbol}"]
        drawdown = close_prices / close_prices.cummax() - 1
        insights[f"{symbol.lower()}_drawdown"] = drawdown.min()

    return insights


def show_heading(title: str, explanation: str) -> None:
    """Show a section heading with a beginner-friendly information button."""
    heading, info = st.columns([0.94, 0.06])
    heading.subheader(title)
    with info.popover("ⓘ"):
        st.write(explanation)


def apply_dashboard_style() -> None:
    """Add a light visual system while keeping Streamlit's existing font."""
    st.markdown(
        """
        <style>
            .stApp {
                background: #080b0f;
            }
            [data-testid="stAppViewContainer"] {
                background: #080b0f;
            }
            [data-testid="stHeader"] {
                background: #080b0f;
            }
            .block-container {
                max-width: 1120px;
                padding-top: 2.5rem;
                padding-bottom: 3rem;
            }
            [data-testid="stSidebar"] {
                background: #0d1217;
                border-right: 1px solid #2b3a43;
            }
            [data-testid="stSidebar"] h2 {
                color: #f4f7f7 !important;
                font-size: 1.05rem;
            }
            [data-testid="stSidebar"] p,
            [data-testid="stSidebar"] a {
                color: #c2cdd0 !important;
            }
            h1 {
                color: #f4f7f7 !important;
                letter-spacing: 0;
                font-weight: 700;
            }
            h3 {
                color: #f4f7f7 !important;
                letter-spacing: 0;
                margin-top: 1.6rem;
            }
            [data-testid="stMarkdownContainer"] p {
                color: #c2cdd0;
            }
            .hero-panel {
                border: 1px solid #30414a;
                border-radius: 12px;
                padding: 1.2rem 1.4rem;
                margin: 0.2rem 0 1.4rem;
                background: linear-gradient(115deg, #111820 0%, #152a2e 100%);
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.24);
            }
            .hero-kicker {
                color: #d85b43;
                font-size: 0.75rem;
                font-weight: 700;
                letter-spacing: 0.12em;
                text-transform: uppercase;
            }
            .hero-copy {
                color: #c2cdd0;
                font-size: 1rem;
                margin: 0.35rem 0 0;
            }
            [data-testid="stMetric"] {
                background: #11181e;
                border: 1px solid #2b3a43;
                border-radius: 10px;
                padding: 0.8rem 1rem;
                box-shadow: 0 4px 14px rgba(0, 0, 0, 0.2);
            }
            [data-testid="stMetricLabel"] {
                color: #aab8bd !important;
            }
            [data-testid="stMetricValue"] {
                color: #f4f7f7 !important;
            }
            div[data-testid="stPlotlyChart"] {
                border: 1px solid #2b3a43;
                border-radius: 10px;
                padding: 0.4rem;
                background: #0d1217;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def run_cached_backtest(prices: pd.DataFrame, initial_capital: float) -> BacktestResult:
    """Cache the historical backtest so reruns do not recalculate it."""
    return run_moving_average_backtest(prices, initial_capital=initial_capital)


@st.cache_data(show_spinner=False)
def run_cached_multi_stock_research(
    price_data: dict[str, pd.DataFrame],
    initial_capital: float,
    strategy: str,
):
    """Cache one independent multi-stock strategy run."""
    return run_multi_stock_research(
        price_data,
        initial_capital=initial_capital,
        strategy=strategy,
    )


def main() -> None:
    """Build the dashboard page."""
    st.set_page_config(page_title="GainZ Alpha", page_icon="📈", layout="wide")
    apply_dashboard_style()

    with st.sidebar:
        st.header("On this page")
        st.markdown(
            """
            [Latest prices](#latest-prices)  
            [Recent returns](#recent-returns)  
            [Dataset coverage](#dataset-coverage)  
            [Historical comparison](#historical-comparison)  
            [Daily risk](#daily-risk)  
            [Historical prices](#historical-prices)  
            [AAPL moving averages](#aapl-moving-averages)  
            [Backtest](#backtest)  
            [Multi-Stock Research](#multi-stock-research)
            [Cumulative comparison](#cumulative-comparison)
            """
        )
        st.divider()
        st.caption("GainZ Alpha is a research dashboard. It does not provide investment advice or place trades.")

    st.title("GainZ Alpha")
    st.markdown(
        """
        <div class="hero-panel">
            <div class="hero-kicker">Research dashboard · V1</div>
            <p class="hero-copy">A clear view of daily price history for AAPL and SPY. Research only, with no trading or broker connection.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    try:
        aapl = load_price_data("AAPL")
        spy = load_price_data("SPY")
    except FileNotFoundError as error:
        st.error(str(error))
        st.stop()

    insights = calculate_insights(aapl, spy)

    show_heading(
        "Latest prices",
        "The most recent closing price in the downloaded file. It shows where the price ended on the latest trading day.",
    )
    aapl_metric, spy_metric = st.columns(2)
    aapl_metric.metric(
        "AAPL",
        f"${aapl.iloc[-1]['Close']:.2f}",
        help="The latest closing price in the downloaded daily data.",
    )
    spy_metric.metric(
        "SPY",
        f"${spy.iloc[-1]['Close']:.2f}",
        help="The latest closing price in the downloaded daily data.",
    )

    show_heading(
        "Recent returns",
        "A return measures how much the price changed over a period. Positive means the price rose; negative means it fell. One month uses about 21 trading days and one year uses about 252 trading days.",
    )
    st.caption("These are price changes only. They do not include dividends or fees.")

    aapl_returns, spy_returns = st.columns(2)
    with aapl_returns:
        st.markdown("**AAPL**")
        st.metric(
            "1-day return",
            f"{insights['aapl_1d_return']:.2%}",
            help="The percentage change from the previous trading day's close.",
        )
        st.metric(
            "1-month return",
            f"{insights['aapl_1m_return']:.2%}",
            help="The percentage change over roughly 21 trading days.",
        )
        st.metric(
            "1-year return",
            f"{insights['aapl_1y_return']:.2%}",
            help="The percentage change over roughly 252 trading days.",
        )
    with spy_returns:
        st.markdown("**SPY**")
        st.metric(
            "1-day return",
            f"{insights['spy_1d_return']:.2%}",
            help="The percentage change from the previous trading day's close.",
        )
        st.metric(
            "1-month return",
            f"{insights['spy_1m_return']:.2%}",
            help="The percentage change over roughly 21 trading days.",
        )
        st.metric(
            "1-year return",
            f"{insights['spy_1y_return']:.2%}",
            help="The percentage change over roughly 252 trading days.",
        )

    show_heading(
        "Dataset coverage",
        "The number of trading days in each file. Weekends and market holidays are not trading days.",
    )
    aapl_days, spy_days = st.columns(2)
    aapl_days.metric("AAPL trading days", f"{len(aapl):,}")
    spy_days.metric("SPY trading days", f"{len(spy):,}")

    show_heading(
        "Historical comparison",
        "This compares how AAPL and SPY behaved during the period in the files. It describes the past and does not predict the future.",
    )
    st.caption("Price returns exclude dividends. Volatility and drawdown describe historical risk, not future risk.")

    aapl_return, spy_return, correlation = st.columns(3)
    aapl_return.metric("AAPL price return", f"{insights['aapl_return']:.1%}")
    spy_return.metric("SPY price return", f"{insights['spy_return']:.1%}")
    correlation.metric("AAPL/SPY correlation", f"{insights['correlation']:.2f}")

    aapl_risk, spy_risk = st.columns(2)
    aapl_risk.metric(
        "AAPL annualized volatility",
        f"{insights['aapl_volatility']:.1%}",
        help="An estimate based on daily closing-price changes, annualized using 252 trading days.",
    )
    spy_risk.metric(
        "SPY annualized volatility",
        f"{insights['spy_volatility']:.1%}",
        help="An estimate based on daily closing-price changes, annualized using 252 trading days.",
    )

    st.caption(
        "The earlier volatility estimates from the written summary are shown below for reference. "
        "They are scaled by the full sample length, so they are not standard annualized volatility."
    )
    earlier_aapl, earlier_spy = st.columns(2)
    earlier_aapl.metric(
        "AAPL earlier volatility estimate",
        f"{insights['aapl_earlier_volatility']:.1%}",
    )
    earlier_spy.metric(
        "SPY earlier volatility estimate",
        f"{insights['spy_earlier_volatility']:.1%}",
    )

    show_heading(
        "Daily risk",
        "The best and worst single trading days. A large range means prices can move significantly in one day.",
    )
    aapl_daily, spy_daily = st.columns(2)
    aapl_daily.metric(
        "AAPL best / worst day",
        f"+{insights['aapl_best_day']:.1%} / {insights['aapl_worst_day']:.1%}",
    )
    spy_daily.metric(
        "SPY best / worst day",
        f"+{insights['spy_best_day']:.1%} / {insights['spy_worst_day']:.1%}",
    )

    aapl_drawdown, spy_drawdown = st.columns(2)
    aapl_drawdown.metric("AAPL maximum drawdown", f"{insights['aapl_drawdown']:.1%}")
    spy_drawdown.metric("SPY maximum drawdown", f"{insights['spy_drawdown']:.1%}")

    show_heading(
        "Historical prices",
        "The charts show each closing price over time. Hover over the lines, zoom in, or pan across the dates to inspect the data.",
    )
    st.plotly_chart(make_price_chart(aapl, "AAPL"), width="stretch")
    st.plotly_chart(make_price_chart(spy, "SPY"), width="stretch")

    show_heading(
        "AAPL moving averages",
        "A moving average smooths daily prices so it is easier to see the general direction. The 50-day average reacts more quickly; the 200-day average shows a longer-term view.",
    )
    st.caption(
        "Calculation: for each day, add the closing prices in the chosen window and divide by the number of days. "
        "The trend status compares the latest 50-day and 200-day averages."
    )
    aapl_50_average, aapl_200_average, trend_status = st.columns(3)
    aapl_50_average.metric(
        "AAPL 50-day average",
        f"${insights['aapl_50_day_average']:.2f}",
        help="The average AAPL closing price across the most recent 50 trading days.",
    )
    trend_status.metric(
        "Educational trend status",
        insights["aapl_trend_status"],
        help="Uptrend means the 50-day average is above the 200-day average. Downtrend means it is below.",
    )
    aapl_200_average.metric(
        "AAPL 200-day average",
        f"${insights['aapl_200_day_average']:.2f}",
        help="The average AAPL closing price across the most recent 200 trading days.",
    )
    st.plotly_chart(make_moving_average_chart(aapl), width="stretch")
    st.caption("This status is for education and research only. It is not a buy or sell recommendation.")

    initial_capital = 10_000.0
    aligned_prices = aapl.merge(spy, on="Date", suffixes=("_AAPL", "_SPY"))
    aligned_aapl = aligned_prices[["Date", "Close_AAPL"]].rename(
        columns={"Close_AAPL": "Close"}
    )
    aligned_spy = aligned_prices[["Date", "Close_SPY"]].rename(
        columns={"Close_SPY": "Close"}
    )
    backtest = run_cached_backtest(aligned_aapl, initial_capital)
    aapl_buy_and_hold = make_buy_and_hold_history(
        aligned_aapl, initial_capital, "AAPL Buy & Hold"
    )
    spy_buy_and_hold = make_buy_and_hold_history(
        aligned_spy, initial_capital, "SPY Buy & Hold"
    )
    spy_metrics = calculate_portfolio_metrics(
        spy_buy_and_hold["Date"],
        spy_buy_and_hold["SPY Buy & Hold"],
        spy_buy_and_hold["Daily return"],
        initial_capital,
        invested=pd.Series(1, index=spy_buy_and_hold.index),
    )
    show_heading(
        "Backtest",
        "This is a historical simulation of the AAPL moving-average rule. When the 50-day average is above the 200-day average, the simulated portfolio holds AAPL; otherwise it holds cash.",
    )
    st.caption(
        "The signal is shifted by one trading day: a signal calculated from today's close can only affect tomorrow's position. "
        "Trading costs are set to 0% for this first version, but the backtest code has a cost parameter for later use."
    )
    st.caption(
        "CAGR is the average yearly growth rate. Volatility measures how much daily returns vary. "
        "Sharpe compares return with volatility using a 0% risk-free rate. Drawdown is the fall from a previous peak."
    )
    strategy_metrics = backtest.strategy_metrics
    aapl_metrics = backtest.buy_and_hold_metrics
    comparison_table = pd.DataFrame(
        {
            "GainZ Alpha Strategy": [
                f"{strategy_metrics['cagr']:.1%}",
                f"{strategy_metrics['annualized_volatility']:.1%}",
                f"{strategy_metrics['sharpe_ratio']:.2f}",
                f"{strategy_metrics['maximum_drawdown']:.1%}",
                f"{strategy_metrics['percentage_invested']:.1%}",
                f"{strategy_metrics['number_of_position_changes']:.0f}",
            ],
            "AAPL Buy & Hold": [
                f"{aapl_metrics['cagr']:.1%}",
                f"{aapl_metrics['annualized_volatility']:.1%}",
                f"{aapl_metrics['sharpe_ratio']:.2f}",
                f"{aapl_metrics['maximum_drawdown']:.1%}",
                "100.0%",
                "0",
            ],
            "SPY Buy & Hold": [
                f"{spy_metrics['cagr']:.1%}",
                f"{spy_metrics['annualized_volatility']:.1%}",
                f"{spy_metrics['sharpe_ratio']:.2f}",
                f"{spy_metrics['maximum_drawdown']:.1%}",
                "100.0%",
                "0",
            ],
        },
        index=[
            "Annualized return (CAGR)",
            "Annualized volatility",
            "Sharpe ratio (0% risk-free rate)",
            "Maximum drawdown",
            "Trading days invested",
            "Number of position changes",
        ],
    )
    st.dataframe(comparison_table, width="stretch")
    st.caption(
        f"Final strategy value: ${backtest.final_portfolio_value:,.2f}. "
        f"The strategy changed between invested and cash {backtest.number_of_position_changes} times."
    )
    st.plotly_chart(
        make_equity_curve_chart(backtest, aapl_buy_and_hold, spy_buy_and_hold),
        width="stretch",
    )
    st.plotly_chart(make_drawdown_chart(backtest), width="stretch")
    st.caption("Educational research only. This backtest is not a prediction or a buy/sell recommendation.")

    show_heading(
        "Multi-Stock Research",
        "This applies one selected long-only research strategy independently to each configured ticker over the shared date window available in the downloaded files. These are research statistics, not evidence that a strategy works.",
    )
    st.caption(
        "The research sample is a diversified set of stocks selected for comparison only. "
        "SPY remains the market benchmark in the legacy dashboard sections."
    )
    research_prices: dict[str, pd.DataFrame] = {}
    research_load_errors: dict[str, str] = {}
    for ticker in RESEARCH_TICKERS:
        try:
            research_prices[ticker] = load_price_data(ticker)
        except Exception as error:
            research_load_errors[ticker] = str(error)

    research = run_multi_stock_research(research_prices, initial_capital)
    if research_load_errors:
        st.warning(
            "Some research tickers were unavailable and were skipped: "
            + ", ".join(sorted(research_load_errors))
            + ". Run data/download_prices.py to download or update the universe."
        )
    strategy_choice = st.selectbox(
        "Strategy",
        options=[TREND_STRATEGY, MOMENTUM_STRATEGY, TREND_MOMENTUM_STRATEGY],
        help="Run either the existing 50/200 trend rule or the independent 12-month momentum rule.",
    )
    research_runs = {
        strategy: run_cached_multi_stock_research(
            research_prices,
            initial_capital,
            strategy,
        )
        for strategy in [TREND_STRATEGY, MOMENTUM_STRATEGY, TREND_MOMENTUM_STRATEGY]
    }
    research = research_runs[strategy_choice]
    if research.skipped:
        st.caption("Skipped ticker details: " + "; ".join(
            f"{ticker}: {reason}" for ticker, reason in research.skipped.items()
        ))

    metrics = research.metrics
    if metrics.empty:
        st.info("No research ticker has enough valid daily data for this strategy yet.")
    else:
        strategy_cagr_beats = metrics["Strategy CAGR"] > metrics["Buy & Hold CAGR"]
        strategy_sharpe_beats = metrics["Strategy Sharpe"] > metrics["Buy & Hold Sharpe"]
        summary_columns = st.columns(7)
        summary_columns[0].metric("Stocks tested", f"{len(metrics)}")
        summary_columns[1].metric("Strategy CAGR beat", f"{strategy_cagr_beats.sum()}")
        summary_columns[2].metric("Beat percentage", f"{strategy_cagr_beats.mean():.1%}")
        summary_columns[3].metric("Strategy Sharpe beat", f"{strategy_sharpe_beats.sum()}")
        summary_columns[4].metric("Average strategy CAGR", f"{metrics['Strategy CAGR'].mean():.1%}")
        summary_columns[5].metric("Average buy & hold CAGR", f"{metrics['Buy & Hold CAGR'].mean():.1%}")
        summary_columns[6].metric("Average excess CAGR", f"{metrics['Excess CAGR'].mean():+.1%}")

        table_columns = [
            "Ticker",
            "Strategy CAGR",
            "Buy & Hold CAGR",
            "Excess CAGR",
            "Strategy Sharpe",
            "Buy & Hold Sharpe",
            "Strategy Max DD",
            "Buy & Hold Max DD",
            "Time Invested",
            "Position Changes",
        ]
        percentage_columns = {
            column: "{:.1%}"
            for column in table_columns
            if column not in {"Ticker", "Strategy Sharpe", "Buy & Hold Sharpe", "Position Changes"}
        }
        st.dataframe(
            metrics[table_columns].style.format(percentage_columns).format(
                {"Strategy Sharpe": "{:.2f}", "Buy & Hold Sharpe": "{:.2f}", "Position Changes": "{:.0f}"}
            ),
            width="stretch",
            hide_index=True,
        )

        show_heading(
            "Strategy Comparison",
            "This compares the two independent strategies across the stocks that completed each backtest. The strategies are not combined or optimized.",
        )
        comparison_rows = []
        for strategy, strategy_result in research_runs.items():
            strategy_metrics = strategy_result.metrics
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
                    "Average CAGR": "{:.1%}",
                    "Average Excess CAGR": "{:+.1%}",
                    "Average Sharpe": "{:.2f}",
                    "Average Max Drawdown": "{:.1%}",
                    "CAGR beats Buy & Hold": "{:.1%}",
                    "Sharpe beats Buy & Hold": "{:.1%}",
                    "Average Time Invested": "{:.1%}",
                }
            ),
            width="stretch",
            hide_index=True,
        )

        selected_ticker = st.selectbox(
            "Inspect a ticker",
            options=list(metrics["Ticker"]),
            help="Select one successfully tested ticker to inspect its price, equity, drawdown, and metrics.",
        )
        selected_result = research.backtests[selected_ticker]
        selected_prices = selected_result.history[["Date", "Close"]]
        st.plotly_chart(
            make_moving_average_chart(selected_prices, selected_ticker),
            width="stretch",
            key="research-moving-average",
        )
        st.plotly_chart(
            make_backtest_chart(selected_result, selected_ticker),
            width="stretch",
            key="research-equity-curve",
        )
        st.plotly_chart(
            make_drawdown_chart(selected_result, selected_ticker),
            width="stretch",
            key="research-drawdown",
        )
        selected_strategy = selected_result.strategy_metrics
        selected_buy_and_hold = selected_result.buy_and_hold_metrics
        inspection_table = pd.DataFrame(
            {
                "Selected Strategy": selected_strategy,
                "Buy & Hold": selected_buy_and_hold,
            }
        ).rename(
            index={
                "cagr": "CAGR",
                "annualized_volatility": "Annualized volatility",
                "sharpe_ratio": "Sharpe ratio",
                "maximum_drawdown": "Maximum drawdown",
                "percentage_invested": "Time invested",
                "number_of_position_changes": "Position changes",
            }
        )
        st.dataframe(
            inspection_table.style.format(
                {
                    "Selected Strategy": "{:.1%}",
                    "Buy & Hold": "{:.1%}",
                },
                subset=pd.IndexSlice[
                    ["CAGR", "Annualized volatility", "Maximum drawdown", "Time invested"],
                    :,
                ],
            ).format(
                {"Selected Strategy": "{:.2f}", "Buy & Hold": "{:.2f}"},
                subset=pd.IndexSlice[["Sharpe ratio"], :],
            ).format(
                {"Selected Strategy": "{:.0f}", "Buy & Hold": "{:.0f}"},
                subset=pd.IndexSlice[["Position changes"], :],
            ),
            width="stretch",
        )
        st.caption(
            f"{strategy_choice} research window: {research.start_date.date()} to {research.end_date.date()}. "
            "Historical results are descriptive and do not establish future performance."
        )

    show_heading(
        "Cumulative comparison",
        "Both lines start at 100 so you can compare growth from the same starting point. A line at 120 means the price grew by about 20% from the start.",
    )
    st.plotly_chart(make_cumulative_return_chart(aapl, spy), width="stretch")


if __name__ == "__main__":
    main()