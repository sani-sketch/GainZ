"""Run the fixed moving-average strategy across a research universe."""

from dataclasses import dataclass
from typing import Mapping

import pandas as pd

from backtesting.moving_average_backtest import BacktestResult, run_moving_average_backtest
from backtesting.momentum_backtest import (
    run_momentum_backtest,
    run_trend_momentum_backtest,
)


TREND_STRATEGY = "50/200 Trend"
MOMENTUM_STRATEGY = "12-Month Momentum"
TREND_MOMENTUM_STRATEGY = "Trend + Momentum"
STRATEGIES = (TREND_STRATEGY, MOMENTUM_STRATEGY, TREND_MOMENTUM_STRATEGY)


@dataclass
class MultiStockResearchResult:
    """Backtests, comparable summary metrics, and skipped-ticker diagnostics."""

    metrics: pd.DataFrame
    backtests: dict[str, BacktestResult]
    skipped: dict[str, str]
    start_date: pd.Timestamp | None
    end_date: pd.Timestamp | None


def _clean_prices(prices: pd.DataFrame) -> pd.DataFrame:
    """Return valid, ordered Date and Close columns."""
    required_columns = {"Date", "Close"}
    if not required_columns.issubset(prices.columns):
        missing = ", ".join(sorted(required_columns - set(prices.columns)))
        raise ValueError(f"missing required columns: {missing}")

    cleaned = prices[["Date", "Close"]].copy()
    cleaned["Date"] = pd.to_datetime(cleaned["Date"], errors="coerce")
    cleaned["Close"] = pd.to_numeric(cleaned["Close"], errors="coerce")
    cleaned = cleaned.dropna().drop_duplicates("Date").sort_values("Date")
    if (cleaned["Close"] <= 0).any():
        raise ValueError("contains non-positive closing prices")
    return cleaned.reset_index(drop=True)


def run_multi_stock_research(
    price_data: Mapping[str, pd.DataFrame],
    initial_capital: float = 10_000.0,
    strategy: str = TREND_STRATEGY,
) -> MultiStockResearchResult:
    """Run one independent strategy over a shared date window.

    Each ticker is backtested independently. A ticker with malformed, missing,
    or too-short data is recorded in ``skipped`` rather than aborting the run.
    """
    if strategy not in STRATEGIES:
        raise ValueError(f"Unknown strategy: {strategy}")

    minimum_prices = 201 if strategy == TREND_STRATEGY else 253
    backtest_functions = {
        TREND_STRATEGY: run_moving_average_backtest,
        MOMENTUM_STRATEGY: run_momentum_backtest,
        TREND_MOMENTUM_STRATEGY: run_trend_momentum_backtest,
    }
    backtest_function = backtest_functions[strategy]
    cleaned_data: dict[str, pd.DataFrame] = {}
    skipped: dict[str, str] = {}
    for ticker, prices in price_data.items():
        try:
            cleaned = _clean_prices(prices)
            if len(cleaned) < minimum_prices:
                raise ValueError(f"fewer than {minimum_prices} daily prices")
            cleaned_data[ticker] = cleaned
        except (AttributeError, TypeError, ValueError) as error:
            skipped[ticker] = str(error)

    if not cleaned_data:
        return MultiStockResearchResult(pd.DataFrame(), {}, skipped, None, None)

    start_date = max(prices["Date"].iloc[0] for prices in cleaned_data.values())
    end_date = min(prices["Date"].iloc[-1] for prices in cleaned_data.values())
    if start_date > end_date:
        for ticker in cleaned_data:
            skipped[ticker] = "no shared date window with the other tickers"
        return MultiStockResearchResult(pd.DataFrame(), {}, skipped, None, None)

    backtests: dict[str, BacktestResult] = {}
    rows: list[dict[str, float | str]] = []
    for ticker, prices in cleaned_data.items():
        comparable_prices = prices[prices["Date"].between(start_date, end_date)].reset_index(drop=True)
        if len(comparable_prices) < minimum_prices:
            skipped[ticker] = f"fewer than {minimum_prices} prices in the shared date window"
            continue
        try:
            result = backtest_function(
                comparable_prices,
                initial_capital=initial_capital,
            )
        except (ValueError, TypeError) as error:
            skipped[ticker] = str(error)
            continue

        backtests[ticker] = result
        strategy = result.strategy_metrics
        buy_and_hold = result.buy_and_hold_metrics
        rows.append(
            {
                "Ticker": ticker,
                "Strategy CAGR": strategy["cagr"],
                "Buy & Hold CAGR": buy_and_hold["cagr"],
                "Excess CAGR": strategy["cagr"] - buy_and_hold["cagr"],
                "Strategy Volatility": strategy["annualized_volatility"],
                "Buy & Hold Volatility": buy_and_hold["annualized_volatility"],
                "Strategy Sharpe": strategy["sharpe_ratio"],
                "Buy & Hold Sharpe": buy_and_hold["sharpe_ratio"],
                "Strategy Max DD": strategy["maximum_drawdown"],
                "Buy & Hold Max DD": buy_and_hold["maximum_drawdown"],
                "Time Invested": strategy["percentage_invested"],
                "Position Changes": strategy["number_of_position_changes"],
            }
        )

    return MultiStockResearchResult(
        metrics=pd.DataFrame(rows),
        backtests=backtests,
        skipped=skipped,
        start_date=start_date,
        end_date=end_date,
    )