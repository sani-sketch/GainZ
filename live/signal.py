"""Generate today's target portfolio using training-only adaptive selection."""
from __future__ import annotations
import numpy as np
import pandas as pd
from backtesting.regime_multifactor_research import run_variant
from backtesting.walk_forward import candidate_variants, _metrics, _selection_score
from risk_management.dynamic_risk import standard_risk_configs, apply_dynamic_risk_overlay
from backtesting.regime_multifactor_portfolio import _build_matrices, _cross_sectional_zscore


def _latest_weights(price_data, variant, exposure: float) -> dict[str, float]:
    closes, volumes, _ = _build_matrices(price_data, next(iter(price_data.values())))
    fast = closes.pct_change(variant.momentum_fast, fill_method=None)
    slow = closes.pct_change(variant.momentum_slow, fill_method=None)
    momentum = variant.momentum_slow_weight * slow + (1 - variant.momentum_slow_weight) * fast
    trend = closes / closes.rolling(200).mean() - 1
    vol = closes.pct_change(fill_method=None).rolling(63).std() * np.sqrt(252)
    volume = volumes / volumes.rolling(20).mean() - 1
    scores = (variant.weight_momentum * _cross_sectional_zscore(momentum)
              + variant.weight_trend * _cross_sectional_zscore(trend)
              + variant.weight_low_vol * _cross_sectional_zscore(-vol)
              + variant.weight_volume * _cross_sectional_zscore(volume))
    latest = scores.iloc[-1].dropna().sort_values(ascending=False).head(variant.top_n)
    if latest.empty:
        return {}
    return {str(s): float(exposure / len(latest)) for s in latest.index}


def adaptive_target(price_data, benchmark_prices, train_days: int = 252, sharpe_margin: float = 0.0):
    variants = candidate_variants()
    risks = standard_risk_configs()
    best = None
    best_score = -np.inf
    benchmark_returns = None
    for v in variants:
        raw, bench, _ = run_variant(price_data, benchmark_prices, v)
        benchmark_returns = bench
        for rc in risks:
            protected = apply_dynamic_risk_overlay(raw, rc)
            r = protected["protected_return"].tail(train_days)
            m = _metrics(r)
            score = _selection_score(m)
            if score > best_score:
                best_score, best = score, (v, rc, raw, protected, m)
    if best is None or benchmark_returns is None:
        raise ValueError("Could not select adaptive target")
    v, rc, raw, protected, gm = best
    bm = _metrics(benchmark_returns.tail(train_days))
    use_gainz = gm.get("sharpe", -np.inf) > bm.get("sharpe", np.inf) + sharpe_margin
    if not use_gainz:
        return {"SPY": 1.0}, {"mode": "BENCHMARK", "variant": v.name, "risk": rc.name, "gainz_sharpe": gm.get("sharpe"), "benchmark_sharpe": bm.get("sharpe")}
    exposure = float(protected["exposure"].iloc[-1])
    weights = _latest_weights(price_data, v, exposure)
    return weights, {"mode": "GAINZ", "variant": v.name, "risk": rc.name, "exposure": exposure, "gainz_sharpe": gm.get("sharpe"), "benchmark_sharpe": bm.get("sharpe")}
