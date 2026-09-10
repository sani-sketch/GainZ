"""Smoke tests for the initial project configuration."""

from config.settings import load_settings


def test_settings_load_with_v1_scope() -> None:
    settings = load_settings()

    assert settings["project"]["name"] == "GainZ Alpha"
    assert settings["project"]["frequency"] == "daily"
    assert settings["universe"]["benchmark"] == "SPY"
    assert settings["backtest"]["initial_capital"] > 0
    assert settings["risk"]["max_position_weight"] <= 1
