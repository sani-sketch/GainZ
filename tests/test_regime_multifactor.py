import pandas as pd
import numpy as np

from strategies.regime_multifactor import (
    detect_market_regime,
    calculate_factor_score,
    latest_stock_score,
)


def make_sample_data(rows=300):
    np.random.seed(42)

    dates = pd.date_range("2024-01-01", periods=rows, freq="B")

    price = 100 + np.cumsum(np.random.normal(0.15, 1, rows))
    volume = np.random.randint(1_000_000, 5_000_000, rows)

    return pd.DataFrame(
        {
            "Close": price,
            "Volume": volume,
        },
        index=dates,
    )


def test_market_regime_runs():
    df = make_sample_data()

    regime = detect_market_regime(df)

    assert len(regime) == len(df)
    assert regime.iloc[-1] in ["RISK_ON", "RISK_OFF"]


def test_factor_score_runs():
    df = make_sample_data()

    scored = calculate_factor_score(df)

    assert "factor_score" in scored.columns
    assert scored["factor_score"].dropna().shape[0] > 0


def test_latest_stock_score_returns_number():
    df = make_sample_data()

    score = latest_stock_score(df)

    assert isinstance(score, float)

def test_rank_stock_universe_orders_and_weights_factors():
    from strategies.regime_multifactor import rank_stock_universe

    a = make_sample_data()
    b = make_sample_data()
    b["Close"] = b["Close"] * np.linspace(1.0, 1.5, len(b))
    ranked = rank_stock_universe({"AAA": a, "BBB": b})

    assert list(ranked["rank"]) == [1, 2]
    assert ranked["factor_score"].is_monotonic_decreasing
    assert set(ranked["ticker"]) == {"AAA", "BBB"}


def test_select_portfolio_respects_risk_off():
    from strategies.regime_multifactor import select_portfolio

    stock = make_sample_data()
    market = make_sample_data()
    market["Close"] = np.linspace(200, 50, len(market))
    selected = select_portfolio({"AAA": stock}, market, top_n=1)
    assert selected.empty


def test_select_portfolio_equal_weights_when_risk_on():
    from strategies.regime_multifactor import select_portfolio

    a = make_sample_data()
    b = make_sample_data()
    market = make_sample_data()
    market["Close"] = np.linspace(100, 250, len(market))
    selected = select_portfolio({"AAA": a, "BBB": b}, market, top_n=2)
    assert len(selected) == 2
    assert np.isclose(selected["target_weight"].sum(), 1.0)
