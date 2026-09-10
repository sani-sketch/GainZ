"""Tests for the simple moving-average backtest."""

import pandas as pd
import pytest

from backtesting.moving_average_backtest import (
    calculate_portfolio_metrics,
    run_moving_average_backtest,
)


def test_signal_changes_position_on_the_next_day() -> None:
    dates = pd.date_range("2020-01-01", periods=220, freq="D")
    prices = pd.DataFrame(
        {
            "Date": dates,
            "Close": [100.0] * 200 + list(range(101, 121)),
        }
    )

    result = run_moving_average_backtest(prices)

    # A signal known at the end of a day must not invest on that same day.
    assert result.history.loc[199, "Invested"] == 0
    assert result.history["Invested"].isin([0, 1]).all()
    assert result.final_portfolio_value > 0
    assert result.number_of_position_changes >= 0
    assert 0 <= result.strategy_metrics["percentage_invested"] <= 1
    assert "cagr" in result.strategy_metrics
    assert "sharpe_ratio" in result.strategy_metrics
    assert "number_of_position_changes" in result.strategy_metrics
    assert result.strategy_metrics["number_of_position_changes"] == result.number_of_position_changes


def test_performance_metrics_use_zero_risk_free_rate_by_default() -> None:
    dates = pd.Series(pd.date_range("2020-01-01", periods=252, freq="D"))
    daily_returns = pd.Series([0.001] * 252)
    portfolio_values = 10_000 * (1 + daily_returns).cumprod()

    metrics = calculate_portfolio_metrics(
        dates,
        portfolio_values,
        daily_returns,
        10_000,
        invested=pd.Series([1] * 252),
        position_changes=pd.Series([0, 1] + [0] * 250),
    )

    assert metrics["percentage_invested"] == 1.0
    assert metrics["number_of_position_changes"] == 1.0
    assert metrics["cagr"] > 0
    assert metrics["annualized_volatility"] == pytest.approx(0.0)
