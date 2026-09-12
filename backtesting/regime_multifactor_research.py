"""Research harness for testing robust regime-aware multi-factor variants.

This module intentionally keeps the search space small. It is for sensitivity
analysis, not brute-force optimisation.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Mapping

import numpy as np
import pandas as pd

from backtesting.moving_average_backtest import calculate_portfolio_metrics
from backtesting.regime_multifactor_portfolio import _build_matrices, _cross_sectional_zscore


@dataclass(frozen=True)
class Variant:
    name: str
    top_n: int
    momentum_fast: int
    momentum_slow: int
    momentum_slow_weight: float
    weight_momentum: float
    weight_trend: float
    weight_low_vol: float
    weight_volume: float
    regime: str


def _regime_signal(spy: pd.Series, mode: str) -> pd.Series:
    ma50 = spy.rolling(50).mean()
    ma100 = spy.rolling(100).mean()
    ma200 = spy.rolling(200).mean()
    if mode == "strict_50_200":
        return (spy > ma200) & (ma50 > ma200)
    if mode == "price_above_200":
        return spy > ma200
    if mode == "price_above_100":
        return spy > ma100
    if mode == "none":
        return pd.Series(True, index=spy.index)
    raise ValueError(f"Unknown regime mode: {mode}")


def _metrics_for_period(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    initial_capital: float,
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
) -> dict[str, float]:
    mask = pd.Series(True, index=returns.index)
    if start is not None:
        mask &= returns.index >= pd.Timestamp(start)
    if end is not None:
        mask &= returns.index <= pd.Timestamp(end)
    r = returns.loc[mask]
    b = benchmark_returns.loc[mask]
    if len(r) < 30:
        return {}
    values = initial_capital * (1 + r).cumprod()
    bvalues = initial_capital * (1 + b).cumprod()
    m = calculate_portfolio_metrics(
        pd.Series(r.index), values.reset_index(drop=True), r.reset_index(drop=True), initial_capital
    )
    bm = calculate_portfolio_metrics(
        pd.Series(b.index), bvalues.reset_index(drop=True), b.reset_index(drop=True), initial_capital
    )
    return {
        "cagr": float(m["cagr"]),
        "total_return": float(m["total_return"]),
        "sharpe": float(m["sharpe_ratio"]),
        "max_drawdown": float(m["maximum_drawdown"]),
        "spy_cagr": float(bm["cagr"]),
        "spy_sharpe": float(bm["sharpe_ratio"]),
        "spy_max_drawdown": float(bm["maximum_drawdown"]),
    }


def run_variant(
    price_data: Mapping[str, pd.DataFrame],
    benchmark_prices: pd.DataFrame,
    variant: Variant,
    initial_capital: float = 10_000.0,
    transaction_cost_rate: float = 0.0005,
    slippage_rate: float = 0.0005,
) -> tuple[pd.Series, pd.Series, pd.DataFrame]:
    closes, volumes, spy = _build_matrices(price_data, benchmark_prices)
    dates = closes.index

    fast = closes.pct_change(variant.momentum_fast, fill_method=None)
    slow = closes.pct_change(variant.momentum_slow, fill_method=None)
    momentum = variant.momentum_slow_weight * slow + (1 - variant.momentum_slow_weight) * fast
    trend = closes / closes.rolling(200).mean() - 1
    vol = closes.pct_change(fill_method=None).rolling(63).std() * np.sqrt(252)
    volume = volumes / volumes.rolling(20).mean() - 1

    scores = (
        variant.weight_momentum * _cross_sectional_zscore(momentum)
        + variant.weight_trend * _cross_sectional_zscore(trend)
        + variant.weight_low_vol * _cross_sectional_zscore(-vol)
        + variant.weight_volume * _cross_sectional_zscore(volume)
    )
    risk_on = _regime_signal(spy, variant.regime)

    warmup = max(200, variant.momentum_slow)
    weights = pd.DataFrame(0.0, index=dates, columns=closes.columns)
    active = pd.Series(0.0, index=closes.columns)
    changes: dict[pd.Timestamp, pd.Series] = {}
    costs: dict[pd.Timestamp, float] = {}
    rows: list[dict[str, object]] = []

    for i in range(warmup, len(dates) - 1):
        signal_date, effective_date = dates[i], dates[i + 1]
        if effective_date.month == signal_date.month:
            continue
        s = scores.loc[signal_date].dropna().sort_values(ascending=False)
        allocation = pd.Series(0.0, index=closes.columns)
        selected = s.head(variant.top_n) if bool(risk_on.loc[signal_date]) else s.iloc[0:0]
        if len(selected):
            allocation.loc[selected.index] = 1 / len(selected)
        turnover = float((allocation - active).abs().sum())
        costs[effective_date] = turnover * (transaction_cost_rate + slippage_rate)
        changes[effective_date] = allocation
        rows.append({
            "signal_date": signal_date,
            "effective_date": effective_date,
            "regime": "RISK_ON" if bool(risk_on.loc[signal_date]) else "RISK_OFF",
            "turnover": turnover,
            "stocks": ", ".join(selected.index),
        })
        active = allocation

    for i in range(1, len(dates)):
        weights.iloc[i] = weights.iloc[i - 1]
        execution_date = dates[i - 1]
        if execution_date in changes:
            weights.iloc[i] = changes[execution_date]

    holdings = pd.DataFrame(rows)
    if holdings.empty:
        raise ValueError("No rebalances generated")
    start = pd.Timestamp(holdings["effective_date"].iloc[0])
    mask = dates >= start
    daily = closes.pct_change(fill_method=None).fillna(0)
    trading_costs = pd.Series(costs, index=dates, dtype=float).fillna(0)
    strat = (weights * daily).sum(axis=1) - trading_costs
    bench = spy.pct_change(fill_method=None).fillna(0)
    return strat.loc[mask], bench.loc[mask], holdings


def default_variants() -> list[Variant]:
    factor_sets = {
        "baseline": (0.40, 0.30, 0.20, 0.10),
        "no_volume": (0.45, 0.35, 0.20, 0.00),
        "momentum_heavy": (0.55, 0.25, 0.20, 0.00),
        "momentum_trend": (0.60, 0.30, 0.10, 0.00),
    }
    momentum_sets = {
        "3m6m": (63, 126, 0.60),
    }
    out = []
    for top_n, (fname, fw), (mname, mw), regime in product(
        [5, 10, 15, 20], factor_sets.items(), momentum_sets.items(),
        ["strict_50_200", "price_above_200", "price_above_100", "none"]
    ):
        out.append(Variant(
            name=f"N{top_n}_{fname}_{mname}_{regime}",
            top_n=top_n,
            momentum_fast=mw[0], momentum_slow=mw[1], momentum_slow_weight=mw[2],
            weight_momentum=fw[0], weight_trend=fw[1], weight_low_vol=fw[2], weight_volume=fw[3],
            regime=regime,
        ))
    return out


def evaluate_variants(
    price_data: Mapping[str, pd.DataFrame],
    benchmark_prices: pd.DataFrame,
    variants: list[Variant] | None = None,
    initial_capital: float = 10_000.0,
    validation_start: str = "2025-01-01",
) -> pd.DataFrame:
    variants = variants or default_variants()
    rows = []
    for v in variants:
        r, b, holdings = run_variant(price_data, benchmark_prices, v, initial_capital=initial_capital)
        full = _metrics_for_period(r, b, initial_capital)
        dev = _metrics_for_period(r, b, initial_capital, end=pd.Timestamp(validation_start) - pd.Timedelta(days=1))
        val = _metrics_for_period(r, b, initial_capital, start=pd.Timestamp(validation_start))
        if not full or not val:
            continue
        row = {
            "name": v.name,
            "top_n": v.top_n,
            "momentum_fast": v.momentum_fast,
            "momentum_slow": v.momentum_slow,
            "factor_momentum": v.weight_momentum,
            "factor_trend": v.weight_trend,
            "factor_low_vol": v.weight_low_vol,
            "factor_volume": v.weight_volume,
            "regime": v.regime,
            "rebalances": len(holdings),
        }
        for prefix, metrics in [("full", full), ("dev", dev), ("val", val)]:
            for k, value in metrics.items():
                row[f"{prefix}_{k}"] = value
        # Robustness score: reward validation excess return/Sharpe, penalise deeper DD.
        row["validation_score"] = (
            2.0 * (row["val_cagr"] - row["val_spy_cagr"])
            + 0.5 * (row["val_sharpe"] - row["val_spy_sharpe"])
            + 0.5 * (row["val_max_drawdown"] - row["val_spy_max_drawdown"])
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values("validation_score", ascending=False).reset_index(drop=True)
