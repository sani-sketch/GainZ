import numpy as np
import pandas as pd

from backtesting.regime_multifactor_portfolio import run_regime_multifactor_backtest


def _sample(rows=520, drift=0.12, seed=1):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=rows, freq="B")
    close = 100 + np.cumsum(rng.normal(drift, 0.8, rows))
    return pd.DataFrame({"Date": dates, "Close": close, "Volume": rng.integers(1_000_000, 4_000_000, rows)})


def test_backtest_runs_and_has_no_same_day_execution():
    stocks = {"AAA": _sample(seed=1), "BBB": _sample(drift=0.2, seed=2), "CCC": _sample(drift=0.08, seed=3)}
    spy = _sample(drift=0.15, seed=4)
    result = run_regime_multifactor_backtest(stocks, spy, top_n=2)
    assert not result.history.empty
    assert (result.monthly_holdings["Effective Date"] > result.monthly_holdings["Rebalance Date"]).all()
    assert result.metrics["number_of_rebalances"] > 0


def test_risk_off_can_hold_cash():
    stocks = {"AAA": _sample(seed=1), "BBB": _sample(seed=2)}
    spy = _sample(drift=0.0, seed=4)
    spy["Close"] = np.linspace(250, 80, len(spy))
    result = run_regime_multifactor_backtest(stocks, spy, top_n=1)
    assert (result.monthly_holdings["Regime"] == "RISK_OFF").any()
    assert (result.monthly_holdings.loc[result.monthly_holdings["Regime"] == "RISK_OFF", "Cash"] == 1.0).all()
