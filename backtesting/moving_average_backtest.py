"""Simple long-only moving-average backtest for historical research."""

from dataclasses import dataclass

import pandas as pd


@dataclass
class BacktestResult:
    """The portfolio history and summary values produced by the backtest."""

    history: pd.DataFrame
    final_portfolio_value: float
    total_return: float
    buy_and_hold_return: float
    maximum_drawdown: float
    number_of_position_changes: int
    strategy_metrics: dict[str, float]
    buy_and_hold_metrics: dict[str, float]


def calculate_portfolio_metrics(
    dates: pd.Series,
    portfolio_values: pd.Series,
    daily_returns: pd.Series,
    initial_capital: float,
    invested: pd.Series | None = None,
) -> dict[str, float]:
    """Calculate common performance metrics for one portfolio history."""
    years = (dates.iloc[-1] - dates.iloc[0]).days / 365.25
    total_return = portfolio_values.iloc[-1] / initial_capital - 1
    cagr = (portfolio_values.iloc[-1] / initial_capital) ** (1 / years) - 1
    volatility = daily_returns.std() * 252**0.5
    sharpe_ratio = daily_returns.mean() / daily_returns.std() * 252**0.5
    running_peak = portfolio_values.cummax()
    maximum_drawdown = (portfolio_values / running_peak - 1).min()

    metrics = {
        "cagr": float(cagr),
        "annualized_volatility": float(volatility),
        "sharpe_ratio": float(sharpe_ratio),
        "maximum_drawdown": float(maximum_drawdown),
        "total_return": float(total_return),
    }
    if invested is not None:
        metrics["percentage_invested"] = float(invested.mean())
    return metrics


def make_buy_and_hold_history(
    prices: pd.DataFrame,
    initial_capital: float = 10_000.0,
    column_name: str = "Buy and hold portfolio",
) -> pd.DataFrame:
    """Create a portfolio history for holding one asset throughout."""
    history = prices[["Date", "Close"]].copy().sort_values("Date").reset_index(drop=True)
    history[column_name] = initial_capital * history["Close"] / history["Close"].iloc[0]
    history["Daily return"] = history["Close"].pct_change().fillna(0.0)
    return history


def run_moving_average_backtest(
    prices: pd.DataFrame,
    initial_capital: float = 10_000.0,
    transaction_cost_rate: float = 0.0,
) -> BacktestResult:
    """Backtest a long-only 50/200-day moving-average strategy.

    A signal uses a day's closing price, so it is shifted by one day before
    affecting the portfolio. This prevents today's close from influencing
    today's return in the backtest.
    """
    if len(prices) < 201:
        raise ValueError("At least 201 daily prices are needed for this backtest.")
    if initial_capital <= 0:
        raise ValueError("Initial capital must be greater than zero.")
    if transaction_cost_rate < 0:
        raise ValueError("Transaction costs cannot be negative.")

    history = prices[["Date", "Close"]].copy().sort_values("Date").reset_index(drop=True)
    history["50-day average"] = history["Close"].rolling(window=50).mean()
    history["200-day average"] = history["Close"].rolling(window=200).mean()

    # A signal is known after the close. It can only change the next day's position.
    signal = history["50-day average"] > history["200-day average"]
    history["Invested"] = signal.shift(1, fill_value=False).astype(int)
    history["Daily return"] = history["Close"].pct_change().fillna(0.0)
    position_change = history["Invested"].diff().abs()
    position_change.iloc[0] = 0.0
    history["Position change"] = position_change
    history["Trading cost"] = history["Position change"] * transaction_cost_rate
    history["Strategy return"] = (
        history["Invested"] * history["Daily return"] - history["Trading cost"]
    )
    history["Strategy portfolio"] = initial_capital * (
        1 + history["Strategy return"]
    ).cumprod()
    history["Buy and hold portfolio"] = initial_capital * (
        history["Close"] / history["Close"].iloc[0]
    )

    running_peak = history["Strategy portfolio"].cummax()
    drawdown = history["Strategy portfolio"] / running_peak - 1
    history["Strategy drawdown"] = drawdown
    strategy_metrics = calculate_portfolio_metrics(
        history["Date"],
        history["Strategy portfolio"],
        history["Strategy return"],
        initial_capital,
        history["Invested"],
    )
    buy_and_hold_metrics = calculate_portfolio_metrics(
        history["Date"],
        history["Buy and hold portfolio"],
        history["Daily return"],
        initial_capital,
    )

    return BacktestResult(
        history=history,
        final_portfolio_value=float(history["Strategy portfolio"].iloc[-1]),
        total_return=float(history["Strategy portfolio"].iloc[-1] / initial_capital - 1),
        buy_and_hold_return=float(history["Close"].iloc[-1] / history["Close"].iloc[0] - 1),
        maximum_drawdown=float(drawdown.min()),
        number_of_position_changes=int(history["Position change"].sum()),
        strategy_metrics=strategy_metrics,
        buy_and_hold_metrics=buy_and_hold_metrics,
    )
