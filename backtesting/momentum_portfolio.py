"""Monthly top-five 12-month momentum portfolio backtest."""

from dataclasses import dataclass
from typing import Mapping

import pandas as pd

from backtesting.moving_average_backtest import calculate_portfolio_metrics


MOMENTUM_LOOKBACK_DAYS = 252
TOP_N_STOCKS = 5


@dataclass
class MomentumPortfolioResult:
    """Portfolio history, holdings, rankings, and summary statistics."""

    history: pd.DataFrame
    metrics: dict[str, float]
    monthly_holdings: pd.DataFrame
    monthly_rankings: pd.DataFrame
    latest_ranking: pd.DataFrame
    latest_allocation: pd.DataFrame
    data_audit: pd.DataFrame
    weights: pd.DataFrame
    start_date: pd.Timestamp
    end_date: pd.Timestamp


def _make_price_matrix(price_data: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """Align all ticker closes to dates shared by the complete universe."""
    series = []
    for ticker, prices in price_data.items():
        required = {"Date", "Close"}
        if not required.issubset(prices.columns):
            raise ValueError(f"{ticker} is missing Date or Close columns")
        cleaned = prices[["Date", "Close"]].copy()
        cleaned["Date"] = pd.to_datetime(cleaned["Date"], errors="coerce")
        cleaned["Close"] = pd.to_numeric(cleaned["Close"], errors="coerce")
        cleaned = cleaned.dropna().drop_duplicates("Date").set_index("Date")
        if (cleaned["Close"] <= 0).any():
            raise ValueError(f"{ticker} contains non-positive closing prices")
        series.append(cleaned["Close"].rename(ticker))

    if not series:
        raise ValueError("At least one price series is required")
    matrix = pd.concat(series, axis=1, join="inner").sort_index().dropna()
    if len(matrix) < MOMENTUM_LOOKBACK_DAYS + 2:
        raise ValueError("At least 254 shared daily prices are needed")
    return matrix


def audit_price_data(
    price_data: Mapping[str, pd.DataFrame],
    benchmark_prices: pd.DataFrame,
) -> pd.DataFrame:
    """Summarize coverage and missing values before shared-date alignment."""
    all_prices = dict(price_data)
    all_prices["SPY"] = benchmark_prices
    cleaned_series: dict[str, pd.Series] = {}
    rows: list[dict[str, object]] = []
    for ticker, prices in all_prices.items():
        if not {"Date", "Close"}.issubset(prices.columns):
            rows.append({"Ticker": ticker, "Status": "Missing Date or Close columns"})
            continue
        dates = pd.to_datetime(prices["Date"], errors="coerce")
        closes = pd.to_numeric(prices["Close"], errors="coerce")
        valid = pd.DataFrame({"Date": dates, "Close": closes}).dropna()
        valid = valid[valid["Close"] > 0].drop_duplicates("Date").sort_values("Date")
        cleaned_series[ticker] = valid.set_index("Date")["Close"]
        rows.append(
            {
                "Ticker": ticker,
                "Status": "OK",
                "Raw rows": len(prices),
                "Valid rows": len(valid),
                "Missing/invalid rows": len(prices) - len(valid),
                "Duplicate dates": int(dates.duplicated().sum()),
                "First valid date": valid["Date"].iloc[0] if not valid.empty else pd.NaT,
                "Last valid date": valid["Date"].iloc[-1] if not valid.empty else pd.NaT,
                "Has 252-day history": len(valid) >= MOMENTUM_LOOKBACK_DAYS + 1,
            }
        )

    if cleaned_series:
        shared_dates = pd.concat(cleaned_series.values(), axis=1, join="inner").index
        shared_start = shared_dates.min() if len(shared_dates) else pd.NaT
        shared_end = shared_dates.max() if len(shared_dates) else pd.NaT
        for row in rows:
            if row["Status"] != "OK":
                continue
            series = cleaned_series[row["Ticker"]]
            row["Rows before shared start"] = int((series.index < shared_start).sum())
            row["Shared date range"] = f"{shared_start.date()} to {shared_end.date()}"
    return pd.DataFrame(rows)


def run_momentum_portfolio_backtest(
    price_data: Mapping[str, pd.DataFrame],
    benchmark_prices: pd.DataFrame,
    initial_capital: float = 10_000.0,
    transaction_cost_rate: float = 0.0,
    slippage_rate: float = 0.0,
) -> MomentumPortfolioResult:
    """Backtest monthly rebalanced, equal-weighted top-five momentum holdings.

    Scores and rankings use each month-end close. The target allocation is
    applied on the next shared trading day, avoiding look-ahead bias.
    """
    if initial_capital <= 0:
        raise ValueError("Initial capital must be greater than zero.")
    if transaction_cost_rate < 0 or slippage_rate < 0:
        raise ValueError("Transaction costs and slippage cannot be negative.")

    all_prices = dict(price_data)
    all_prices["SPY"] = benchmark_prices
    price_matrix = _make_price_matrix(all_prices)
    stock_prices = price_matrix.drop(columns="SPY")
    benchmark = price_matrix["SPY"]
    dates = price_matrix.index
    momentum = stock_prices / stock_prices.shift(MOMENTUM_LOOKBACK_DAYS) - 1

    weights = pd.DataFrame(0.0, index=dates, columns=stock_prices.columns)
    monthly_holdings_rows: list[dict[str, object]] = []
    monthly_ranking_rows: list[dict[str, object]] = []
    rebalance_dates: list[pd.Timestamp] = []
    target_allocations: dict[pd.Timestamp, pd.Series] = {}
    costs_by_effective_date: dict[pd.Timestamp, float] = {}
    active_allocation = pd.Series(0.0, index=stock_prices.columns)

    for index in range(MOMENTUM_LOOKBACK_DAYS, len(dates) - 1):
        date = dates[index]
        next_date = dates[index + 1]
        if next_date.month == date.month:
            continue

        scores = momentum.loc[date].dropna().sort_values(ascending=False)
        positive_scores = scores[scores > 0]
        selected = positive_scores.head(TOP_N_STOCKS)
        allocation = pd.Series(0.0, index=stock_prices.columns)
        if not selected.empty:
            allocation.loc[selected.index] = 1.0 / TOP_N_STOCKS
        turnover = float((allocation - active_allocation).abs().sum())
        transaction_cost = turnover * transaction_cost_rate
        slippage = turnover * slippage_rate
        costs_by_effective_date[next_date] = transaction_cost + slippage
        target_allocations[date] = allocation
        rebalance_dates.append(date)

        trade_labels = []
        for ticker in stock_prices.columns:
            change = allocation[ticker] - active_allocation[ticker]
            if change > 0:
                trade_labels.append(f"BUY {ticker} {change:.1%}")
            elif change < 0:
                trade_labels.append(f"SELL {ticker} {-change:.1%}")

        for rank, (ticker, score) in enumerate(scores.items(), start=1):
            monthly_ranking_rows.append(
                {"Rebalance Date": date, "Rank": rank, "Ticker": ticker, "Momentum": score}
            )
        monthly_holdings_rows.append(
            {
                "Rebalance Date": date,
                "Effective Date": next_date,
                "Selected Stocks": ", ".join(selected.index),
                "Stocks Held": float((allocation > 0).sum()),
                "Invested": float(allocation.sum()),
                "Cash": float(1 - allocation.sum()),
                "Trades Required": "; ".join(trade_labels) or "None",
                "Turnover": turnover,
                "Transaction Cost": transaction_cost,
                "Slippage": slippage,
                "Total Trading Cost": transaction_cost + slippage,
            }
        )
        active_allocation = allocation

    for index in range(1, len(dates)):
        weights.iloc[index] = weights.iloc[index - 1]
        rebalance_date = dates[index - 1]
        if rebalance_date in target_allocations:
            weights.iloc[index] = target_allocations[rebalance_date]

    daily_stock_returns = stock_prices.pct_change().fillna(0.0)
    daily_benchmark_returns = benchmark.pct_change().fillna(0.0)
    trading_costs = pd.Series(costs_by_effective_date, index=dates).fillna(0.0)
    portfolio_returns = (weights * daily_stock_returns).sum(axis=1) - trading_costs
    portfolio_values = initial_capital * (1 + portfolio_returns).cumprod()
    benchmark_values = initial_capital * benchmark / benchmark.iloc[0]
    strategy_drawdown = portfolio_values / portfolio_values.cummax() - 1
    benchmark_drawdown = benchmark_values / benchmark_values.cummax() - 1

    strategy_metrics = calculate_portfolio_metrics(
        pd.Series(dates), portfolio_values.reset_index(drop=True),
        portfolio_returns.reset_index(drop=True), initial_capital,
    )
    benchmark_metrics = calculate_portfolio_metrics(
        pd.Series(dates), benchmark_values.reset_index(drop=True),
        daily_benchmark_returns.reset_index(drop=True), initial_capital,
    )
    history = pd.DataFrame(
        {
            "Date": dates,
            "Portfolio value": portfolio_values.to_numpy(),
            "SPY Buy & Hold": benchmark_values.to_numpy(),
            "Portfolio return": portfolio_returns.to_numpy(),
            "SPY return": daily_benchmark_returns.to_numpy(),
            "Portfolio drawdown": strategy_drawdown.to_numpy(),
            "SPY drawdown": benchmark_drawdown.to_numpy(),
            "Stocks held": (weights > 0).sum(axis=1).to_numpy(),
            "Cash": (1 - weights.sum(axis=1)).to_numpy(),
            "Trading costs": trading_costs.to_numpy(),
        }
    )

    monthly_holdings = pd.DataFrame(monthly_holdings_rows)
    monthly_rankings = pd.DataFrame(monthly_ranking_rows)
    latest_ranking = monthly_rankings[
        monthly_rankings["Rebalance Date"] == monthly_rankings["Rebalance Date"].max()
    ].reset_index(drop=True)
    latest_ranking["Allocation"] = latest_ranking["Ticker"].map(
        target_allocations[rebalance_dates[-1]]
    ).fillna(0.0)
    latest_allocation = latest_ranking[latest_ranking["Allocation"] > 0][
        ["Ticker", "Momentum", "Allocation"]
    ].reset_index(drop=True)

    metrics = {
        "cagr": strategy_metrics["cagr"],
        "total_return": strategy_metrics["total_return"],
        "annualized_volatility": strategy_metrics["annualized_volatility"],
        "sharpe_ratio": strategy_metrics["sharpe_ratio"],
        "maximum_drawdown": strategy_metrics["maximum_drawdown"],
        "final_portfolio_value": float(portfolio_values.iloc[-1]),
        "average_stocks_held": float((weights > 0).sum(axis=1).mean()),
        "number_of_rebalances": float(len(rebalance_dates)),
        "percentage_cash": float((1 - weights.sum(axis=1)).mean()),
        "total_trading_cost": float(trading_costs.sum()),
        "spy_cagr": benchmark_metrics["cagr"],
        "spy_total_return": benchmark_metrics["total_return"],
        "spy_annualized_volatility": benchmark_metrics["annualized_volatility"],
        "spy_sharpe_ratio": benchmark_metrics["sharpe_ratio"],
        "spy_maximum_drawdown": benchmark_metrics["maximum_drawdown"],
        "spy_final_portfolio_value": float(benchmark_values.iloc[-1]),
    }
    return MomentumPortfolioResult(
        history=history,
        metrics=metrics,
        monthly_holdings=monthly_holdings,
        monthly_rankings=monthly_rankings,
        latest_ranking=latest_ranking,
        latest_allocation=latest_allocation,
        data_audit=audit_price_data(price_data, benchmark_prices),
        weights=weights,
        start_date=dates[0],
        end_date=dates[-1],
    )


def audit_portfolio_result(
    price_data: Mapping[str, pd.DataFrame],
    benchmark_prices: pd.DataFrame,
    result: MomentumPortfolioResult,
    transaction_cost_rate: float,
    slippage_rate: float,
) -> pd.DataFrame:
    """Run invariant checks for timing, ranking, holdings, costs, and dates."""
    matrix = _make_price_matrix({**price_data, "SPY": benchmark_prices})
    stock_prices = matrix.drop(columns="SPY")
    expected_momentum = stock_prices / stock_prices.shift(MOMENTUM_LOOKBACK_DAYS) - 1
    checks: list[dict[str, str]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"Check": name, "Status": "PASS" if passed else "FAIL", "Details": detail})

    ranking_error = 0.0
    ranking_rows_ok = True
    for date, group in result.monthly_rankings.groupby("Rebalance Date"):
        for row in group.itertuples():
            expected = expected_momentum.loc[date, row.Ticker]
            ranking_error = max(ranking_error, abs(float(expected) - float(row.Momentum)))
            ranking_rows_ok &= pd.notna(expected)
    add(
        "Momentum uses only prior 252 trading closes",
        ranking_rows_ok and ranking_error < 1e-12,
        f"Maximum ranking-score reconstruction error: {ranking_error:.3g}",
    )

    lag_ok = True
    dates = pd.DatetimeIndex(result.history["Date"])
    for _, row in result.monthly_holdings.iterrows():
        index = dates.get_loc(row["Rebalance Date"])
        lag_ok &= row["Effective Date"] == dates[index + 1]
        lag_ok &= row["Effective Date"] > row["Rebalance Date"]
    add("Trades occur on the next trading day", lag_ok, "Every effective date is the next shared trading date.")

    expected_returns = (result.weights * stock_prices.pct_change().fillna(0.0)).sum(axis=1)
    expected_returns = expected_returns - result.history["Trading costs"].to_numpy()
    return_error = (expected_returns.to_numpy() - result.history["Portfolio return"].to_numpy()).__abs__().max()
    add(
        "Portfolio returns use actual held weights",
        return_error < 1e-12,
        f"Maximum return reconstruction error: {return_error:.3g}",
    )

    eligible_ok = True
    for _, row in result.monthly_holdings.iterrows():
        selected = [ticker for ticker in row["Selected Stocks"].split(", ") if ticker]
        scores = result.monthly_rankings[
            result.monthly_rankings["Rebalance Date"] == row["Rebalance Date"]
        ].set_index("Ticker")["Momentum"]
        eligible_ok &= all(ticker in scores.index and scores[ticker] > 0 for ticker in selected)
    add("Stocks are eligible only after 252 observations", eligible_ok, "Selections are made from non-NaN positive momentum scores.")

    cost_expected = result.monthly_holdings["Turnover"].sum() * (
        transaction_cost_rate + slippage_rate
    )
    cost_error = abs(cost_expected - result.metrics["total_trading_cost"])
    add(
        "Transaction costs match turnover",
        cost_error < 1e-12,
        f"Expected total cost {cost_expected:.6f}; recorded {result.metrics['total_trading_cost']:.6f}.",
    )

    chronological = dates.is_monotonic_increasing and dates.is_unique
    add("Trading dates are chronological and unique", chronological, "Shared price matrix dates are sorted and unique.")
    audit = result.data_audit
    data_clean = (
        audit["Status"].eq("OK").all()
        and audit["Missing/invalid rows"].eq(0).all()
        and audit["Duplicate dates"].eq(0).all()
    )
    add("No duplicate, NaN, or invalid price rows", data_clean, "Raw downloaded files were checked before alignment.")
    return pd.DataFrame(checks)