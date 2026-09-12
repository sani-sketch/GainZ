import numpy as np
import pandas as pd

from risk_management.dynamic_risk import RiskConfig, apply_dynamic_risk_overlay


def test_exposure_is_bounded_and_no_leverage():
    idx = pd.date_range("2024-01-01", periods=100, freq="B")
    r = pd.Series(np.sin(np.arange(100)) * 0.03, index=idx)
    out = apply_dynamic_risk_overlay(r)
    assert (out["exposure"] >= 0).all()
    assert (out["exposure"] <= 1).all()


def test_volatility_target_reduces_exposure_after_high_volatility():
    idx = pd.date_range("2024-01-01", periods=80, freq="B")
    r = pd.Series([0.04, -0.04] * 40, index=idx)
    cfg = RiskConfig(target_volatility=0.10, vol_lookback=10)
    out = apply_dynamic_risk_overlay(r, cfg)
    assert out["exposure"].iloc[-1] < 1.0


def test_today_return_does_not_change_today_exposure():
    idx = pd.date_range("2024-01-01", periods=50, freq="B")
    base = pd.Series(0.001, index=idx)
    shock = base.copy()
    shock.iloc[-1] = -0.30
    a = apply_dynamic_risk_overlay(base)
    b = apply_dynamic_risk_overlay(shock)
    assert a["exposure"].iloc[-1] == b["exposure"].iloc[-1]
