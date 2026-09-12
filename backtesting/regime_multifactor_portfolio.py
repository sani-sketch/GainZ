"""Monthly regime-aware multi-factor rotation portfolio backtest.

Signals are formed at month-end using only information available through that close.
Target weights become effective on the next shared trading day.
"""

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd

from backtesting.moving_average_backtest import calculate_portfolio_metrics


TOP_N_STOCKS = 10


@dataclass
class RegimeMultifactorPortfolioResult:
    history: pd.DataFrame
    metrics: dict[str, float]
    monthly_holdings: pd.DataFrame
    monthly_rankings: pd.DataFrame
    latest_ranking: pd.DataFrame
    latest_allocation: pd.DataFrame
    weights: pd.DataFrame
    start_date: pd.Timestamp
    end_date: pd.Timestamp


def _clean_ohlcv(prices: pd.DataFrame, ticker: str) -> pd.DataFrame:
    required = {"Date", "Close", "Volume"}
    if not required.issubset(prices.columns):
        missing = ", ".join(sorted(required - set(prices.columns)))
        raise ValueError(f"{ticker} is missing required columns: {missing}")
    out = prices[["Date", "Close", "Volume"]].copy()
    out["Date"] = pd.to_datetime(out["Date"], errors="coerce")
    out["Close"] = pd.to_numeric(out["Close"], errors="coerce")
    out["Volume"] = pd.to_numeric(out["Volume"], errors="coerce")
    out = out.dropna().drop_duplicates("Date").sort_values("Date")
    out = out[(out["Close"] > 0) & (out["Volume"] >= 0)]
    return out.set_index("Date")


def _build_matrices(
    price_data: Mapping[str, pd.DataFrame],
    benchmark_prices: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    cleaned = {ticker: _clean_ohlcv(frame, ticker) for ticker, frame in price_data.items()}
    spy = _clean_ohlcv(benchmark_prices, "SPY")

    closes = pd.concat({ticker: frame["Close"] for ticker, frame in cleaned.items()}, axis=1)
    volumes = pd.concat({ticker: frame["Volume"] for ticker, frame in cleaned.items()}, axis=1)
    benchmark = spy["Close"].rename("SPY")

    # Use dates shared by the benchmark and all stocks. The bundled dataset is downloaded
    # over one common window, so this prevents accidental stale-price forward filling.
    combined = pd.concat([closes, volumes.add_prefix("VOL_"), benchmark], axis=1, join="inner").dropna()
    if len(combined) < 202:
        raise ValueError("At least 202 shared daily observations are required.")

    stock_cols = list(closes.columns)
    return (
        combined[stock_cols].astype(float),
        combined[[f"VOL_{ticker}" for ticker in stock_cols]].rename(columns=lambda x: x[4:]).astype(float),
        combined["SPY"].astype(float),
    )


def _cross_sectional_zscore(frame: pd.DataFrame) -> pd.DataFrame:
    mean = frame.mean(axis=1)
    std = frame.std(axis=1, ddof=0).replace(0, np.nan)
    return frame.sub(mean, axis=0).div(std, axis=0).fillna(0.0)


def run_regime_multifactor_backtest(
    price_data: Mapping[str, pd.DataFrame],
    benchmark_prices: pd.DataFrame,
    initial_capital: float = 10_000.0,
    top_n: int = TOP_N_STOCKS,
    transaction_cost_rate: float = 0.0005,
    slippage_rate: float = 0.0005,
) -> RegimeMultifactorPortfolioResult:
    """Backtest monthly top-N factor rotation with an SPY 50/200 regime filter."""
    if initial_capital <= 0:
        raise ValueError("Initial capital must be greater than zero.")
    if top_n <= 0:
        raise ValueError("top_n must be greater than zero.")
    if transaction_cost_rate < 0 or slippage_rate < 0:
        raise ValueError("Trading costs cannot be negative.")

    closes, volumes, spy = _build_matrices(price_data, benchmark_prices)
    dates = closes.index

    momentum_6m = closes.pct_change(126, fill_method=None)
    momentum_3m = closes.pct_change(63, fill_method=None)
    momentum = 0.6 * momentum_6m + 0.4 * momentum_3m
    ma_200 = closes.rolling(200).mean()
    trend = closes / ma_200 - 1.0
    volatility = closes.pct_change(fill_method=None).rolling(63).std() * np.sqrt(252)
    volume_strength = volumes / volumes.rolling(20).mean() - 1.0

    momentum_z = _cross_sectional_zscore(momentum)
    trend_z = _cross_sectional_zscore(trend)
    low_vol_z = _cross_sectional_zscore(-volatility)
    volume_z = _cross_sectional_zscore(volume_strength)
    factor_scores = 0.40 * momentum_z + 0.30 * trend_z + 0.20 * low_vol_z + 0.10 * volume_z

    spy_ma50 = spy.rolling(50).mean()
    spy_ma200 = spy.rolling(200).mean()
    risk_on = (spy > spy_ma200) & (spy_ma50 > spy_ma200)

    weights = pd.DataFrame(0.0, index=dates, columns=closes.columns)
    execution_allocations: dict[pd.Timestamp, pd.Series] = {}
    costs_by_date: dict[pd.Timestamp, float] = {}
    holdings_rows: list[dict[str, object]] = []
    ranking_rows: list[dict[str, object]] = []
    active = pd.Series(0.0, index=closes.columns)

    for idx in range(200, len(dates) - 1):
        signal_date = dates[idx]
        effective_date = dates[idx + 1]
        if effective_date.month == signal_date.month:
            continue

        scores = factor_scores.loc[signal_date].dropna().sort_values(ascending=False)
        allocation = pd.Series(0.0, index=closes.columns)
        selected = scores.head(min(top_n, len(scores))) if bool(risk_on.loc[signal_date]) else scores.iloc[0:0]
        if not selected.empty:
            allocation.loc[selected.index] = 1.0 / len(selected)

        turnover = float((allocation - active).abs().sum())
        total_cost = turnover * (transaction_cost_rate + slippage_rate)
        costs_by_date[effective_date] = total_cost
        execution_allocations[effective_date] = allocation

        for rank, (ticker, score) in enumerate(scores.items(), start=1):
            ranking_rows.append({
                "Rebalance Date": signal_date,
                "Rank": rank,
                "Ticker": ticker,
                "Factor Score": float(score),
                "Momentum Z": float(momentum_z.loc[signal_date, ticker]),
                "Trend Z": float(trend_z.loc[signal_date, ticker]),
                "Low Volatility Z": float(low_vol_z.loc[signal_date, ticker]),
                "Volume Z": float(volume_z.loc[signal_date, ticker]),
            })

        holdings_rows.append({
            "Rebalance Date": signal_date,
            "Effective Date": effective_date,
            "Regime": "RISK_ON" if bool(risk_on.loc[signal_date]) else "RISK_OFF",
            "Selected Stocks": ", ".join(selected.index),
            "Stocks Held": int(len(selected)),
            "Invested": float(allocation.sum()),
            "Cash": float(1.0 - allocation.sum()),
            "Turnover": turnover,
            "Trading Cost": total_cost,
        })
        active = allocation

    for idx in range(1, len(dates)):
        weights.iloc[idx] = weights.iloc[idx - 1]
        # A signal formed at close on day t is executed at the close of day t+1.
        # The new holdings therefore earn close-to-close returns starting on day t+2.
        execution_date = dates[idx - 1]
        if execution_date in execution_allocations:
            weights.iloc[idx] = execution_allocations[execution_date]

    daily_returns = closes.pct_change(fill_method=None).fillna(0.0)
    spy_returns = spy.pct_change(fill_method=None).fillna(0.0)
    trading_costs = pd.Series(costs_by_date, index=dates, dtype=float).fillna(0.0)
    portfolio_returns = (weights * daily_returns).sum(axis=1) - trading_costs
    portfolio_values = initial_capital * (1.0 + portfolio_returns).cumprod()
    holdings = pd.DataFrame(holdings_rows)
    if holdings.empty:
        raise ValueError("No rebalance dates were generated.")
    active_start = pd.Timestamp(holdings["Effective Date"].iloc[0])
    active_mask = dates >= active_start
    active_dates = dates[active_mask]
    active_returns = portfolio_returns.loc[active_dates]
    active_values = initial_capital * (1.0 + active_returns).cumprod()
    active_spy = spy.loc[active_dates]
    active_spy_returns = active_spy.pct_change(fill_method=None).fillna(0.0)
    benchmark_values = initial_capital * active_spy / active_spy.iloc[0]

    portfolio_dd = active_values / active_values.cummax() - 1.0
    spy_dd = benchmark_values / benchmark_values.cummax() - 1.0

    strat_metrics = calculate_portfolio_metrics(
        pd.Series(active_dates), active_values.reset_index(drop=True), active_returns.reset_index(drop=True), initial_capital
    )
    bench_metrics = calculate_portfolio_metrics(
        pd.Series(active_dates), benchmark_values.reset_index(drop=True), active_spy_returns.reset_index(drop=True), initial_capital
    )

    rankings = pd.DataFrame(ranking_rows)
    latest_date = holdings["Rebalance Date"].max()
    latest_ranking = rankings[rankings["Rebalance Date"] == latest_date].copy().reset_index(drop=True)
    latest_execution_date = pd.Timestamp(holdings.loc[holdings["Rebalance Date"] == latest_date, "Effective Date"].iloc[0])
    latest_target = execution_allocations[latest_execution_date]
    latest_ranking["Allocation"] = latest_ranking["Ticker"].map(latest_target).fillna(0.0)
    latest_allocation = latest_ranking[latest_ranking["Allocation"] > 0][
        ["Ticker", "Factor Score", "Allocation"]
    ].reset_index(drop=True)

    active_weights = weights.loc[active_dates]
    history = pd.DataFrame({
        "Date": active_dates,
        "Portfolio value": active_values.to_numpy(),
        "SPY Buy & Hold": benchmark_values.to_numpy(),
        "Portfolio return": active_returns.to_numpy(),
        "SPY return": active_spy_returns.to_numpy(),
        "Portfolio drawdown": portfolio_dd.to_numpy(),
        "SPY drawdown": spy_dd.to_numpy(),
        "Stocks held": (active_weights > 0).sum(axis=1).to_numpy(),
        "Cash": (1.0 - active_weights.sum(axis=1)).to_numpy(),
        "Trading costs": trading_costs.loc[active_dates].to_numpy(),
    })

    metrics = {
        "cagr": strat_metrics["cagr"],
        "total_return": strat_metrics["total_return"],
        "annualized_volatility": strat_metrics["annualized_volatility"],
        "sharpe_ratio": strat_metrics["sharpe_ratio"],
        "maximum_drawdown": strat_metrics["maximum_drawdown"],
        "final_portfolio_value": float(active_values.iloc[-1]),
        "number_of_rebalances": float(len(holdings)),
        "risk_on_rebalances": float((holdings["Regime"] == "RISK_ON").sum()),
        "risk_off_rebalances": float((holdings["Regime"] == "RISK_OFF").sum()),
        "percentage_cash": float((1.0 - active_weights.sum(axis=1)).mean()),
        "total_trading_cost": float(trading_costs.loc[active_dates].sum()),
        "spy_cagr": bench_metrics["cagr"],
        "spy_total_return": bench_metrics["total_return"],
        "spy_annualized_volatility": bench_metrics["annualized_volatility"],
        "spy_sharpe_ratio": bench_metrics["sharpe_ratio"],
        "spy_maximum_drawdown": bench_metrics["maximum_drawdown"],
        "spy_final_portfolio_value": float(benchmark_values.iloc[-1]),
    }

    return RegimeMultifactorPortfolioResult(
        history=history,
        metrics=metrics,
        monthly_holdings=holdings,
        monthly_rankings=rankings,
        latest_ranking=latest_ranking,
        latest_allocation=latest_allocation,
        weights=active_weights,
        start_date=active_dates[0],
        end_date=dates[-1],
    )
