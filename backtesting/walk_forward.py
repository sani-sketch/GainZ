"""Walk-forward validation for GainZ.

The module performs rolling train/test evaluation.  At each fold it chooses from a
small, pre-declared set of strategy/risk combinations using *training data only*,
then evaluates the chosen combination on the immediately following unseen test
window.

Important: this protects against temporal look-ahead in model selection, but it
does not fix survivorship bias in the current-stock research universe.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd

from backtesting.moving_average_backtest import calculate_portfolio_metrics
from backtesting.regime_multifactor_research import Variant, run_variant
from risk_management.dynamic_risk import RiskConfig, apply_dynamic_risk_overlay, standard_risk_configs


@dataclass(frozen=True)
class WalkForwardConfig:
    train_days: int = 252
    test_days: int = 126
    step_days: int = 126
    min_train_days: int = 200


def candidate_variants() -> list[Variant]:
    """Small robustness shortlist; deliberately not a large optimiser."""
    specs = [
        ("N10_momentum_trend_none", 10, 0.60, 0.30, 0.10, 0.00, "none"),
        ("N10_momentum_trend_strict", 10, 0.60, 0.30, 0.10, 0.00, "strict_50_200"),
        ("N10_no_volume_none", 10, 0.45, 0.35, 0.20, 0.00, "none"),
        ("N10_momentum_heavy_none", 10, 0.55, 0.25, 0.20, 0.00, "none"),
        ("N15_momentum_trend_none", 15, 0.60, 0.30, 0.10, 0.00, "none"),
        ("N5_momentum_trend_none", 5, 0.60, 0.30, 0.10, 0.00, "none"),
    ]
    return [
        Variant(
            name=name,
            top_n=top_n,
            momentum_fast=63,
            momentum_slow=126,
            momentum_slow_weight=0.60,
            weight_momentum=wm,
            weight_trend=wt,
            weight_low_vol=wv,
            weight_volume=wvol,
            regime=regime,
        )
        for name, top_n, wm, wt, wv, wvol, regime in specs
    ]


def _metrics(r: pd.Series, initial_capital: float = 10_000.0) -> dict[str, float]:
    r = pd.Series(r, dtype=float).dropna()
    if len(r) < 30:
        return {}
    values = initial_capital * (1.0 + r).cumprod()
    m = calculate_portfolio_metrics(
        pd.Series(r.index),
        values.reset_index(drop=True),
        r.reset_index(drop=True),
        initial_capital,
    )
    return {
        "cagr": float(m["cagr"]),
        "total_return": float(m["total_return"]),
        "sharpe": float(m["sharpe_ratio"]),
        "max_drawdown": float(m["maximum_drawdown"]),
        "final_value": float(values.iloc[-1]),
    }


def _selection_score(metrics: dict[str, float]) -> float:
    """Prefer risk-adjusted return while penalising deep drawdowns."""
    if not metrics:
        return -np.inf
    # Sharpe is the primary objective. CAGR contributes modestly and a deeper
    # drawdown reduces the score.  No benchmark/test information is used here.
    return metrics["sharpe"] + 0.50 * metrics["cagr"] + 0.50 * metrics["max_drawdown"]


def _folds(index: pd.DatetimeIndex, config: WalkForwardConfig) -> list[tuple[pd.DatetimeIndex, pd.DatetimeIndex]]:
    if config.train_days < config.min_train_days:
        raise ValueError("train_days must be >= min_train_days")
    if config.test_days < 1 or config.step_days < 1:
        raise ValueError("test_days and step_days must be positive")

    folds: list[tuple[pd.DatetimeIndex, pd.DatetimeIndex]] = []
    start = 0
    while start + config.train_days + 30 <= len(index):
        train = index[start : start + config.train_days]
        test_start = start + config.train_days
        test = index[test_start : min(test_start + config.test_days, len(index))]
        if len(test) < 30:
            break
        folds.append((train, test))
        start += config.step_days
    return folds


def walk_forward_validate(
    price_data: Mapping[str, pd.DataFrame],
    benchmark_prices: pd.DataFrame,
    variants: list[Variant] | None = None,
    risk_configs: list[RiskConfig] | None = None,
    config: WalkForwardConfig = WalkForwardConfig(),
    initial_capital: float = 10_000.0,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    """Run rolling walk-forward model selection and return fold/OOS results."""
    variants = variants or candidate_variants()
    risk_configs = risk_configs or standard_risk_configs()

    combo_returns: dict[tuple[str, str], pd.Series] = {}
    benchmark: pd.Series | None = None

    for variant in variants:
        raw, bench, _ = run_variant(
            price_data,
            benchmark_prices,
            variant,
            initial_capital=initial_capital,
        )
        if benchmark is None:
            benchmark = bench
        for risk_cfg in risk_configs:
            protected = apply_dynamic_risk_overlay(raw, risk_cfg)["protected_return"]
            combo_returns[(variant.name, risk_cfg.name)] = protected

    if benchmark is None or not combo_returns:
        raise ValueError("No walk-forward candidates generated")

    common_index = benchmark.index
    for r in combo_returns.values():
        common_index = common_index.intersection(r.index)
    common_index = common_index.sort_values()
    benchmark = benchmark.reindex(common_index).fillna(0.0)
    combo_returns = {k: v.reindex(common_index).fillna(0.0) for k, v in combo_returns.items()}

    folds = _folds(common_index, config)
    if not folds:
        raise ValueError("Not enough history for walk-forward validation")

    fold_rows: list[dict[str, object]] = []
    oos_parts: list[pd.DataFrame] = []

    for fold_no, (train_idx, test_idx) in enumerate(folds, start=1):
        best_key: tuple[str, str] | None = None
        best_score = -np.inf
        best_train_metrics: dict[str, float] = {}

        for key, returns in combo_returns.items():
            tm = _metrics(returns.loc[train_idx], initial_capital)
            score = _selection_score(tm)
            if score > best_score:
                best_score = score
                best_key = key
                best_train_metrics = tm

        if best_key is None:
            continue

        chosen = combo_returns[best_key].loc[test_idx]
        bench_test = benchmark.loc[test_idx]
        test_metrics = _metrics(chosen, initial_capital)
        bench_metrics = _metrics(bench_test, initial_capital)

        fold_rows.append({
            "fold": fold_no,
            "train_start": train_idx[0],
            "train_end": train_idx[-1],
            "test_start": test_idx[0],
            "test_end": test_idx[-1],
            "variant": best_key[0],
            "risk_config": best_key[1],
            "train_score": best_score,
            "train_cagr": best_train_metrics.get("cagr", np.nan),
            "train_sharpe": best_train_metrics.get("sharpe", np.nan),
            "train_max_drawdown": best_train_metrics.get("max_drawdown", np.nan),
            "test_cagr": test_metrics.get("cagr", np.nan),
            "test_sharpe": test_metrics.get("sharpe", np.nan),
            "test_max_drawdown": test_metrics.get("max_drawdown", np.nan),
            "spy_test_cagr": bench_metrics.get("cagr", np.nan),
            "spy_test_sharpe": bench_metrics.get("sharpe", np.nan),
            "spy_test_max_drawdown": bench_metrics.get("max_drawdown", np.nan),
            "beat_spy_return": test_metrics.get("total_return", -np.inf) > bench_metrics.get("total_return", np.inf),
        })

        oos_parts.append(pd.DataFrame({
            "Date": test_idx,
            "strategy_return": chosen.values,
            "spy_return": bench_test.values,
            "fold": fold_no,
            "variant": best_key[0],
            "risk_config": best_key[1],
        }))

    fold_results = pd.DataFrame(fold_rows)
    oos = pd.concat(oos_parts, ignore_index=True).drop_duplicates("Date", keep="first").sort_values("Date")
    oos = oos.set_index("Date")

    strategy_metrics = _metrics(oos["strategy_return"], initial_capital)
    spy_metrics = _metrics(oos["spy_return"], initial_capital)
    summary = {
        "folds": float(len(fold_results)),
        "folds_beating_spy": float(fold_results["beat_spy_return"].sum()),
        "strategy_cagr": strategy_metrics["cagr"],
        "strategy_sharpe": strategy_metrics["sharpe"],
        "strategy_max_drawdown": strategy_metrics["max_drawdown"],
        "strategy_total_return": strategy_metrics["total_return"],
        "spy_cagr": spy_metrics["cagr"],
        "spy_sharpe": spy_metrics["sharpe"],
        "spy_max_drawdown": spy_metrics["max_drawdown"],
        "spy_total_return": spy_metrics["total_return"],
    }
    return fold_results, oos.reset_index(), summary
