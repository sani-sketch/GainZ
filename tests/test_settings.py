"""Smoke tests for the initial project configuration."""

from config.settings import load_settings


def test_settings_load_with_v1_scope() -> None:
    settings = load_settings()

    assert settings["project"]["name"] == "GainZ Alpha"
    assert settings["project"]["frequency"] == "daily"
    assert settings["universe"]["benchmark"] == "SPY"
    assert len(settings["universe"]["broad_symbols"]) >= 100
    assert len(settings["universe"]["broad_symbols"]) == len(
        set(settings["universe"]["broad_symbols"])
    )
    assert settings["universe"]["symbols"] == [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "JPM", "V",
        "WMT", "COST", "XOM", "JNJ", "PG", "HD", "KO",
    ]
    assert settings["backtest"]["initial_capital"] > 0
    assert settings["risk"]["max_position_weight"] <= 1
