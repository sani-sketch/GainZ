"""Simple long-only 12-month momentum backtest for historical research."""

import pandas as pd

from backtesting.moving_average_backtest import (
    BacktestResult,
    calculate_portfolio_metrics,
)


MOMENTUM_LOOKBACK_DAYS = 252


def _run_signal_backtest(
    prices: pd.DataFrame,
    signal: pd.Series,
    initial_capital: float,
    transaction_cost_rate: float,
) -> BacktestResult:
    """Apply a shifted long-only signal and calculate the shared metrics."""
    history = prices[["Date", "Close"]].copy().sort_values("Date").reset_index(drop=True)
    history["Invested"] = signal.reset_index(drop=True).shift(1, fill_value=False).astype(int)
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
        history["Date"], history["Strategy portfolio"], history["Strategy return"],
        initial_capital, history["Invested"], history["Position change"],
    )
    buy_and_hold_metrics = calculate_portfolio_metrics(
        history["Date"], history["Buy and hold portfolio"], history["Daily return"],
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


def run_momentum_backtest(
    prices: pd.DataFrame,
    initial_capital: float = 10_000.0,
    transaction_cost_rate: float = 0.0,
) -> BacktestResult:
    """Backtest a long-only strategy using positive 12-month momentum.

    The return over the previous 252 trading days is calculated after each
    close. That signal is shifted by one trading day before it affects returns.
    """
    if len(prices) < MOMENTUM_LOOKBACK_DAYS + 1:
        raise ValueError(
            "At least 253 daily prices are needed for the momentum backtest."
        )
    if initial_capital <= 0:
        raise ValueError("Initial capital must be greater than zero.")
    if transaction_cost_rate < 0:
        raise ValueError("Transaction costs cannot be negative.")

    history = prices[["Date", "Close"]].copy().sort_values("Date").reset_index(drop=True)
    history["12-month momentum"] = (
        history["Close"] / history["Close"].shift(MOMENTUM_LOOKBACK_DAYS) - 1
    )
    result = _run_signal_backtest(
        history,
        history["12-month momentum"] > 0,
        initial_capital,
        transaction_cost_rate,
    )
    result.history["12-month momentum"] = history["12-month momentum"]
    return result


def run_trend_momentum_backtest(
    prices: pd.DataFrame,
    initial_capital: float = 10_000.0,
    transaction_cost_rate: float = 0.0,
) -> BacktestResult:
    """Backtest the long-only strategy requiring trend and momentum together."""
    if len(prices) < MOMENTUM_LOOKBACK_DAYS + 1:
        raise ValueError(
            "At least 253 daily prices are needed for the trend and momentum backtest."
        )
    if initial_capital <= 0:
        raise ValueError("Initial capital must be greater than zero.")
    if transaction_cost_rate < 0:
        raise ValueError("Transaction costs cannot be negative.")

    history = prices[["Date", "Close"]].copy().sort_values("Date").reset_index(drop=True)
    history["50-day average"] = history["Close"].rolling(window=50).mean()
    history["200-day average"] = history["Close"].rolling(window=200).mean()
    history["12-month momentum"] = (
        history["Close"] / history["Close"].shift(MOMENTUM_LOOKBACK_DAYS) - 1
    )
    signal = (
        (history["50-day average"] > history["200-day average"])
        & (history["12-month momentum"] > 0)
    )
    result = _run_signal_backtest(
        history,
        signal,
        initial_capital,
        transaction_cost_rate,
    )
    for column in ["50-day average", "200-day average", "12-month momentum"]:
        result.history[column] = history[column]
    return result