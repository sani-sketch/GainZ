import pandas as pd
import numpy as np

from backtesting.adaptive_core import adaptive_walk_forward_validate
from backtesting.walk_forward import WalkForwardConfig
from backtesting.regime_multifactor_research import Variant
from risk_management.dynamic_risk import RiskConfig


def _frame(seed: int, n: int = 900, drift: float = 0.0004):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n)
    r = rng.normal(drift, 0.01, n)
    close = 100 * np.cumprod(1 + r)
    volume = rng.integers(1_000_000, 5_000_000, n)
    return pd.DataFrame({"Date": dates, "Close": close, "Volume": volume})


def test_adaptive_returns_only_known_modes():
    stocks = {f"S{i}": _frame(i, drift=0.0003 + i * 0.00002) for i in range(12)}
    spy = _frame(100, drift=0.00035)
    variant = Variant("test", 5, 63, 126, 0.6, 0.6, 0.3, 0.1, 0.0, "none")
    risk = RiskConfig(name="test", target_volatility=None)
    folds, oos, summary = adaptive_walk_forward_validate(
        stocks, spy, variants=[variant], risk_configs=[risk],
        config=WalkForwardConfig(train_days=252, test_days=126, step_days=126),
    )
    assert not folds.empty
    assert set(folds["allocation_mode"]).issubset({"GAINZ", "BENCHMARK"})
    assert not oos.empty
    assert summary["folds"] == len(folds)


def test_adaptive_oos_has_no_duplicate_dates():
    stocks = {f"S{i}": _frame(i + 20) for i in range(12)}
    spy = _frame(200)
    variant = Variant("test", 5, 63, 126, 0.6, 0.6, 0.3, 0.1, 0.0, "none")
    risk = RiskConfig(name="test", target_volatility=None)
    _, oos, _ = adaptive_walk_forward_validate(
        stocks, spy, variants=[variant], risk_configs=[risk],
        config=WalkForwardConfig(train_days=252, test_days=126, step_days=126),
    )
    assert not oos["Date"].duplicated().any()
