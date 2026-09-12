"""Dynamic portfolio risk overlay for GainZ.

The overlay is intentionally simple and transparent. It uses only information
available before each trading day:
- trailing realised volatility (shifted by one day)
- the protected portfolio's drawdown as of the prior close

It never increases exposure above 100% and places unused capital in cash.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RiskConfig:
    name: str = "balanced"
    target_volatility: float | None = 0.15
    vol_lookback: int = 20
    max_exposure: float = 1.0
    dd_level_1: float = -0.10
    dd_exposure_1: float = 0.75
    dd_level_2: float = -0.15
    dd_exposure_2: float = 0.50
    dd_level_3: float = -0.20
    dd_exposure_3: float = 0.25


def _validate(config: RiskConfig) -> None:
    if config.vol_lookback < 2:
        raise ValueError("vol_lookback must be at least 2")
    if config.target_volatility is not None and config.target_volatility <= 0:
        raise ValueError("target_volatility must be positive or None")
    if not 0 <= config.max_exposure <= 1:
        raise ValueError("max_exposure must be between 0 and 1")
    for x in (config.dd_exposure_1, config.dd_exposure_2, config.dd_exposure_3):
        if not 0 <= x <= 1:
            raise ValueError("drawdown exposures must be between 0 and 1")
    if not (config.dd_level_3 < config.dd_level_2 < config.dd_level_1 < 0):
        raise ValueError("drawdown levels must satisfy level_3 < level_2 < level_1 < 0")


def apply_dynamic_risk_overlay(
    strategy_returns: pd.Series,
    config: RiskConfig = RiskConfig(),
) -> pd.DataFrame:
    """Apply volatility targeting and drawdown de-risking without look-ahead.

    Returns a DataFrame with raw/protected returns, exposure and drawdown.
    Cash is assumed to earn 0% in this research model.
    """
    _validate(config)
    raw = pd.Series(strategy_returns, dtype=float).fillna(0.0).copy()
    if raw.empty:
        raise ValueError("strategy_returns cannot be empty")

    # Shift one day so today's position size never uses today's return.
    realised_vol = (
        raw.rolling(config.vol_lookback, min_periods=config.vol_lookback)
        .std(ddof=0)
        .mul(np.sqrt(252))
        .shift(1)
    )

    exposure = pd.Series(index=raw.index, dtype=float)
    protected = pd.Series(index=raw.index, dtype=float)
    equity = 1.0
    peak = 1.0

    for i, dt in enumerate(raw.index):
        prior_dd = equity / peak - 1.0

        vol_cap = config.max_exposure
        rv = realised_vol.loc[dt]
        if config.target_volatility is not None and pd.notna(rv) and rv > 0:
            vol_cap = min(vol_cap, config.target_volatility / float(rv))

        dd_cap = config.max_exposure
        if prior_dd <= config.dd_level_3:
            dd_cap = config.dd_exposure_3
        elif prior_dd <= config.dd_level_2:
            dd_cap = config.dd_exposure_2
        elif prior_dd <= config.dd_level_1:
            dd_cap = config.dd_exposure_1

        e = float(np.clip(min(vol_cap, dd_cap), 0.0, config.max_exposure))
        r = e * float(raw.loc[dt])
        equity *= 1.0 + r
        peak = max(peak, equity)

        exposure.loc[dt] = e
        protected.loc[dt] = r

    protected_equity = (1.0 + protected).cumprod()
    drawdown = protected_equity / protected_equity.cummax() - 1.0

    return pd.DataFrame({
        "raw_return": raw,
        "protected_return": protected,
        "exposure": exposure,
        "cash": 1.0 - exposure,
        "realised_volatility": realised_vol,
        "protected_equity": protected_equity,
        "protected_drawdown": drawdown,
    })


def standard_risk_configs() -> list[RiskConfig]:
    """Small, pre-defined sensitivity set; not a brute-force optimiser."""
    return [
        RiskConfig(
            name="drawdown_only",
            target_volatility=None,
            dd_level_1=-0.10, dd_exposure_1=0.75,
            dd_level_2=-0.15, dd_exposure_2=0.50,
            dd_level_3=-0.20, dd_exposure_3=0.25,
        ),
        RiskConfig(
            name="vol18_balanced",
            target_volatility=0.18,
            dd_level_1=-0.10, dd_exposure_1=0.75,
            dd_level_2=-0.15, dd_exposure_2=0.50,
            dd_level_3=-0.20, dd_exposure_3=0.25,
        ),
        RiskConfig(
            name="vol15_balanced",
            target_volatility=0.15,
            dd_level_1=-0.10, dd_exposure_1=0.75,
            dd_level_2=-0.15, dd_exposure_2=0.50,
            dd_level_3=-0.20, dd_exposure_3=0.25,
        ),
        RiskConfig(
            name="vol12_defensive",
            target_volatility=0.12,
            dd_level_1=-0.08, dd_exposure_1=0.70,
            dd_level_2=-0.12, dd_exposure_2=0.45,
            dd_level_3=-0.16, dd_exposure_3=0.20,
        ),
    ]
