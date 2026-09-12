"""Adaptive GainZ-vs-benchmark walk-forward model.

Professional-style fallback rule:
1. On each training window, choose the best GainZ strategy/risk combination using training data only.
2. Compare that candidate's training Sharpe ratio with the benchmark's training Sharpe.
3. In the next unseen test window, run GainZ only if its training Sharpe was higher; otherwise hold the benchmark.

This is a research model. It reduces the need to force GainZ to trade when its recent evidence is weak,
but it does not remove survivorship bias from the current-stock universe.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backtesting.regime_multifactor_research import Variant, run_variant
from backtesting.walk_forward import (
    WalkForwardConfig,
    _folds,
    _metrics,
    _selection_score,
    candidate_variants,
)
from risk_management.dynamic_risk import RiskConfig, apply_dynamic_risk_overlay, standard_risk_configs


def adaptive_walk_forward_validate(
    price_data,
    benchmark_prices,
    variants: list[Variant] | None = None,
    risk_configs: list[RiskConfig] | None = None,
    config: WalkForwardConfig = WalkForwardConfig(),
    initial_capital: float = 10_000.0,
    sharpe_margin: float = 0.0,
):
    """Walk-forward GainZ with a training-only benchmark fallback.

    `sharpe_margin=0.0` means GainZ must have a higher training Sharpe than the
    benchmark to be used in the following unseen test window.
    """
    variants = variants or candidate_variants()
    risk_configs = risk_configs or standard_risk_configs()

    combo_returns: dict[tuple[str, str], pd.Series] = {}
    benchmark: pd.Series | None = None

    for variant in variants:
        raw, bench, _ = run_variant(price_data, benchmark_prices, variant, initial_capital=initial_capital)
        if benchmark is None:
            benchmark = bench
        for risk_cfg in risk_configs:
            combo_returns[(variant.name, risk_cfg.name)] = apply_dynamic_risk_overlay(raw, risk_cfg)["protected_return"]

    if benchmark is None or not combo_returns:
        raise ValueError("No adaptive candidates generated")

    common_index = benchmark.index
    for r in combo_returns.values():
        common_index = common_index.intersection(r.index)
    common_index = common_index.sort_values()
    benchmark = benchmark.reindex(common_index).fillna(0.0)
    combo_returns = {k: v.reindex(common_index).fillna(0.0) for k, v in combo_returns.items()}

    folds = _folds(common_index, config)
    if not folds:
        raise ValueError("Not enough history for adaptive walk-forward validation")

    fold_rows: list[dict[str, object]] = []
    oos_parts: list[pd.DataFrame] = []

    for fold_no, (train_idx, test_idx) in enumerate(folds, start=1):
        best_key = None
        best_score = -np.inf
        best_metrics: dict[str, float] = {}

        for key, returns in combo_returns.items():
            tm = _metrics(returns.loc[train_idx], initial_capital)
            score = _selection_score(tm)
            if score > best_score:
                best_score = score
                best_key = key
                best_metrics = tm

        if best_key is None:
            continue

        benchmark_train = _metrics(benchmark.loc[train_idx], initial_capital)
        gainz_train_sharpe = best_metrics.get("sharpe", -np.inf)
        benchmark_train_sharpe = benchmark_train.get("sharpe", np.inf)
        use_gainz = gainz_train_sharpe > benchmark_train_sharpe + sharpe_margin

        test_strategy = combo_returns[best_key].loc[test_idx]
        bench_test = benchmark.loc[test_idx]
        chosen = test_strategy if use_gainz else bench_test

        chosen_metrics = _metrics(chosen, initial_capital)
        bench_metrics = _metrics(bench_test, initial_capital)

        fold_rows.append({
            "fold": fold_no,
            "train_start": train_idx[0],
            "train_end": train_idx[-1],
            "test_start": test_idx[0],
            "test_end": test_idx[-1],
            "selected_variant": best_key[0],
            "selected_risk_config": best_key[1],
            "gainz_train_sharpe": gainz_train_sharpe,
            "benchmark_train_sharpe": benchmark_train_sharpe,
            "allocation_mode": "GAINZ" if use_gainz else "BENCHMARK",
            "test_cagr": chosen_metrics.get("cagr", np.nan),
            "test_sharpe": chosen_metrics.get("sharpe", np.nan),
            "test_max_drawdown": chosen_metrics.get("max_drawdown", np.nan),
            "spy_test_cagr": bench_metrics.get("cagr", np.nan),
            "spy_test_sharpe": bench_metrics.get("sharpe", np.nan),
            "spy_test_max_drawdown": bench_metrics.get("max_drawdown", np.nan),
            "beat_spy_return": chosen_metrics.get("total_return", -np.inf) > bench_metrics.get("total_return", np.inf),
        })

        oos_parts.append(pd.DataFrame({
            "Date": test_idx,
            "adaptive_return": chosen.values,
            "gainz_candidate_return": test_strategy.values,
            "spy_return": bench_test.values,
            "fold": fold_no,
            "allocation_mode": "GAINZ" if use_gainz else "BENCHMARK",
            "variant": best_key[0],
            "risk_config": best_key[1],
        }))

    folds_df = pd.DataFrame(fold_rows)
    oos = pd.concat(oos_parts, ignore_index=True).drop_duplicates("Date", keep="first").sort_values("Date").set_index("Date")

    adaptive_metrics = _metrics(oos["adaptive_return"], initial_capital)
    spy_metrics = _metrics(oos["spy_return"], initial_capital)

    summary = {
        "folds": int(len(folds_df)),
        "gainz_folds": int((folds_df["allocation_mode"] == "GAINZ").sum()),
        "benchmark_folds": int((folds_df["allocation_mode"] == "BENCHMARK").sum()),
        "folds_beating_spy": int(folds_df["beat_spy_return"].sum()),
        "adaptive_cagr": adaptive_metrics["cagr"],
        "adaptive_sharpe": adaptive_metrics["sharpe"],
        "adaptive_max_drawdown": adaptive_metrics["max_drawdown"],
        "adaptive_total_return": adaptive_metrics["total_return"],
        "spy_cagr": spy_metrics["cagr"],
        "spy_sharpe": spy_metrics["sharpe"],
        "spy_max_drawdown": spy_metrics["max_drawdown"],
        "spy_total_return": spy_metrics["total_return"],
    }
    return folds_df, oos.reset_index(), summary
