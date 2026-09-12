import pandas as pd
import pytest

from backtesting.walk_forward import WalkForwardConfig, _folds, _selection_score


def test_folds_keep_training_before_test():
    idx = pd.date_range("2020-01-01", periods=800, freq="B")
    folds = _folds(idx, WalkForwardConfig(train_days=252, test_days=126, step_days=126))
    assert len(folds) >= 3
    for train, test in folds:
        assert train[-1] < test[0]
        assert len(train) == 252
        assert 30 <= len(test) <= 126


def test_invalid_short_training_window_is_rejected():
    idx = pd.date_range("2020-01-01", periods=500, freq="B")
    with pytest.raises(ValueError):
        _folds(idx, WalkForwardConfig(train_days=100, min_train_days=200))


def test_selection_score_rewards_better_sharpe_and_drawdown():
    strong = {"cagr": 0.15, "sharpe": 1.2, "max_drawdown": -0.10}
    weak = {"cagr": 0.15, "sharpe": 0.6, "max_drawdown": -0.25}
    assert _selection_score(strong) > _selection_score(weak)
