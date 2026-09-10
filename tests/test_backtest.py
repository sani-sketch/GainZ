"""Tests for the simple moving-average backtest."""

import pandas as pd
import pytest

from backtesting.moving_average_backtest import (
    calculate_portfolio_metrics,
    run_moving_average_backtest,
)
from backtesting.multi_stock_backtest import run_multi_stock_research
from backtesting.multi_stock_backtest import (
    MOMENTUM_STRATEGY,
    TREND_MOMENTUM_STRATEGY,
)
from backtesting.momentum_backtest import (
    run_momentum_backtest,
    run_trend_momentum_backtest,
)
from backtesting.momentum_portfolio import (
    audit_portfolio_result,
    run_momentum_portfolio_backtest,
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


def test_multi_stock_research_uses_shared_dates_and_excess_cagr() -> None:
    dates = pd.date_range("2020-01-01", periods=230, freq="D")
    rising = pd.DataFrame({"Date": dates, "Close": range(100, 330)})
    falling = pd.DataFrame({"Date": dates, "Close": range(330, 100, -1)})
    too_short = pd.DataFrame({"Date": dates[:200], "Close": range(100, 300)})

    result = run_multi_stock_research(
        {"RISE": rising, "FALL": falling, "SHORT": too_short}
    )

    assert set(result.metrics["Ticker"]) == {"RISE", "FALL"}
    assert result.start_date == dates[0]
    assert result.end_date == dates[-1]
    assert "fewer than 201 daily prices" in result.skipped["SHORT"]
    rise = result.metrics.set_index("Ticker").loc["RISE"]
    assert rise["Excess CAGR"] == pytest.approx(
        rise["Strategy CAGR"] - rise["Buy & Hold CAGR"]
    )


def test_multi_stock_research_skips_malformed_ticker() -> None:
    result = run_multi_stock_research({"BROKEN": pd.DataFrame({"Close": [1, 2]})})

    assert result.metrics.empty
    assert "missing required columns" in result.skipped["BROKEN"]


def test_momentum_signal_changes_position_on_the_next_day() -> None:
    dates = pd.date_range("2020-01-01", periods=260, freq="D")
    prices = pd.DataFrame(
        {"Date": dates, "Close": [100.0] * 252 + list(range(101, 109))}
    )

    result = run_momentum_backtest(prices)

    assert result.history.loc[252, "Invested"] == 0
    assert result.history.loc[253, "Invested"] == 1
    assert result.history["Invested"].isin([0, 1]).all()


def test_multi_stock_research_runs_momentum_strategy() -> None:
    dates = pd.date_range("2020-01-01", periods=260, freq="D")
    prices = pd.DataFrame({"Date": dates, "Close": range(100, 360)})

    result = run_multi_stock_research(
        {"RISE": prices}, strategy=MOMENTUM_STRATEGY
    )

    assert list(result.metrics["Ticker"]) == ["RISE"]
    assert result.backtests["RISE"].history["12-month momentum"].iloc[252] > 0


def test_trend_momentum_requires_both_conditions_and_shifts_signal() -> None:
    dates = pd.date_range("2020-01-01", periods=260, freq="D")
    prices = pd.DataFrame({"Date": dates, "Close": [100.0] * 252 + list(range(101, 109))})

    result = run_trend_momentum_backtest(prices)

    assert result.history.loc[252, "Invested"] == 0
    assert result.history.loc[253, "Invested"] == 1
    assert result.history["Invested"].isin([0, 1]).all()


def test_multi_stock_research_runs_trend_momentum_strategy() -> None:
    dates = pd.date_range("2020-01-01", periods=260, freq="D")
    prices = pd.DataFrame({"Date": dates, "Close": range(100, 360)})

    result = run_multi_stock_research(
        {"RISE": prices}, strategy=TREND_MOMENTUM_STRATEGY
    )

    assert list(result.metrics["Ticker"]) == ["RISE"]
    assert result.backtests["RISE"].history["Invested"].isin([0, 1]).all()


def test_momentum_portfolio_selects_top_five_and_rebalances_next_day() -> None:
    dates = pd.date_range("2020-01-01", periods=520, freq="D")
    price_data = {
        f"S{index}": pd.DataFrame({"Date": dates, "Close": [100.0] * 252 + list(range(101 + index, 369 + index))})
        for index in range(6)
    }
    spy = pd.DataFrame({"Date": dates, "Close": range(100, 620)})

    result = run_momentum_portfolio_backtest(price_data, spy)

    assert result.metrics["number_of_rebalances"] > 0
    assert result.monthly_holdings["Stocks Held"].max() == 5
    assert (result.monthly_holdings["Invested"] <= 1.0).all()
    first_rebalance = result.monthly_holdings.iloc[0]
    assert first_rebalance["Effective Date"] > first_rebalance["Rebalance Date"]
    assert len(result.latest_ranking) == 6
    assert len(result.latest_allocation) == 5


def test_momentum_portfolio_ranking_uses_rebalance_close_only() -> None:
    dates = pd.date_range("2020-01-01", periods=520, freq="D")
    price_data = {
        f"S{index}": pd.DataFrame({"Date": dates, "Close": [100.0] * 252 + list(range(101 + index, 369 + index))})
        for index in range(6)
    }
    spy = pd.DataFrame({"Date": dates, "Close": range(100, 620)})
    original = run_momentum_portfolio_backtest(price_data, spy)

    changed_data = {
        ticker: prices.copy() for ticker, prices in price_data.items()
    }
    first_rebalance = original.monthly_holdings.iloc[0]["Rebalance Date"]
    changed_data["S0"].loc[changed_data["S0"]["Date"] > first_rebalance, "Close"] *= 10
    changed = run_momentum_portfolio_backtest(changed_data, spy)

    original_scores = original.monthly_rankings[
        original.monthly_rankings["Rebalance Date"] == first_rebalance
    ][["Ticker", "Momentum"]].reset_index(drop=True)
    changed_scores = changed.monthly_rankings[
        changed.monthly_rankings["Rebalance Date"] == first_rebalance
    ][["Ticker", "Momentum"]].reset_index(drop=True)
    pd.testing.assert_frame_equal(original_scores, changed_scores)
    assert original.monthly_holdings.iloc[0]["Effective Date"] > first_rebalance


def test_momentum_portfolio_costs_reduce_results_and_are_audited() -> None:
    dates = pd.date_range("2020-01-01", periods=520, freq="D")
    price_data = {
        f"S{index}": pd.DataFrame({"Date": dates, "Close": [100.0] * 252 + list(range(101 + index, 369 + index))})
        for index in range(6)
    }
    spy = pd.DataFrame({"Date": dates, "Close": range(100, 620)})
    before = run_momentum_portfolio_backtest(price_data, spy)
    after = run_momentum_portfolio_backtest(
        price_data, spy, transaction_cost_rate=0.001, slippage_rate=0.0005
    )

    assert after.metrics["total_trading_cost"] > 0
    assert after.metrics["final_portfolio_value"] < before.metrics["final_portfolio_value"]
    assert {"Trades Required", "Turnover", "Transaction Cost", "Slippage"}.issubset(
        after.monthly_holdings.columns
    )


def test_momentum_portfolio_audit_checks_pass() -> None:
    dates = pd.date_range("2020-01-01", periods=520, freq="D")
    price_data = {
        f"S{index}": pd.DataFrame({"Date": dates, "Close": [100.0] * 252 + list(range(101 + index, 369 + index))})
        for index in range(6)
    }
    spy = pd.DataFrame({"Date": dates, "Close": range(100, 620)})
    result = run_momentum_portfolio_backtest(
        price_data,
        spy,
        transaction_cost_rate=0.001,
        slippage_rate=0.0005,
    )

    audit = audit_portfolio_result(price_data, spy, result, 0.001, 0.0005)

    assert (audit["Status"] == "PASS").all()
