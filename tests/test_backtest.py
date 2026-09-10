"""Tests for the simple moving-average backtest."""

import pandas as pd

from backtesting.moving_average_backtest import run_moving_average_backtest


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
