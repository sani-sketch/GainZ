"""Research-only backtest combining trend, momentum, and point-in-time fundamentals."""

from __future__ import annotations

import pandas as pd

from backtesting.moving_average_backtest import (
    BacktestResult,
)

from backtesting.momentum_backtest import (
    MOMENTUM_LOOKBACK_DAYS,
    _run_signal_backtest,
)

from fundamentals.history import (
    load_growth_history,
    historical_growth_score_from_data,
)


FUNDAMENTAL_GROWTH_THRESHOLD = 50.0


# ============================================================
# FUNDAMENTAL HISTORY
# ============================================================

def build_fundamental_growth_history(
    symbol: str,
    dates: pd.Series,
) -> pd.DataFrame:
    """
    Build point-in-time fundamental growth scores.

    We do NOT call SEC for every trading day.

    Instead, evaluate the score only when necessary and cache
    each calendar date result.
    """

    symbol = symbol.strip().upper()
    fundamental_data = load_growth_history(symbol)

    rows = []
    cache: dict[str, dict] = {}

    unique_dates = (
        pd.to_datetime(dates)
        .dropna()
        .drop_duplicates()
        .sort_values()
    )

    for date in unique_dates:

        date_string = date.strftime(
            "%Y-%m-%d"
        )

        if date_string not in cache:

            result = historical_growth_score_from_data(
            fundamental_data,
            date_string,
        )       

            cache[date_string] = result

        result = cache[
            date_string
        ]

        rows.append(
            {
                "Date": date,
                "Fundamental growth score":
                    result.get(
                        "growth_score"
                    ),

                "Latest fundamental filing":
                    result.get(
                        "latest_available_filing"
                    ),
            }
        )

    return pd.DataFrame(
        rows
    )


# ============================================================
# BACKTEST
# ============================================================

def run_trend_momentum_fundamental_backtest(
    prices: pd.DataFrame,
    symbol: str,
    initial_capital: float = 10_000.0,
    transaction_cost_rate: float = 0.0,
    fundamental_threshold: float = FUNDAMENTAL_GROWTH_THRESHOLD,
) -> BacktestResult:
    """
    Research-only strategy requiring:

    1. 50-day MA > 200-day MA
    2. 12-month momentum > 0
    3. Point-in-time fundamental growth score >= threshold

    The final signal is shifted one trading day by
    _run_signal_backtest before returns are applied.
    """

    if len(prices) < MOMENTUM_LOOKBACK_DAYS + 1:

        raise ValueError(
            "At least 253 daily prices are needed "
            "for the fundamental backtest."
        )

    if initial_capital <= 0:

        raise ValueError(
            "Initial capital must be greater than zero."
        )

    if transaction_cost_rate < 0:

        raise ValueError(
            "Transaction costs cannot be negative."
        )

    if not 0 <= fundamental_threshold <= 100:

        raise ValueError(
            "Fundamental threshold must be between 0 and 100."
        )

    symbol = (
        symbol
        .strip()
        .upper()
    )

    history = (
        prices[
            [
                "Date",
                "Close",
            ]
        ]
        .copy()
        .sort_values(
            "Date"
        )
        .reset_index(
            drop=True
        )
    )

    history[
        "Date"
    ] = pd.to_datetime(
        history["Date"]
    )

    # --------------------------------------------------------
    # PRICE SIGNALS
    # --------------------------------------------------------

    history[
        "50-day average"
    ] = (
        history["Close"]
        .rolling(
            window=50
        )
        .mean()
    )

    history[
        "200-day average"
    ] = (
        history["Close"]
        .rolling(
            window=200
        )
        .mean()
    )

    history[
        "12-month momentum"
    ] = (
        history["Close"]
        / history["Close"].shift(
            MOMENTUM_LOOKBACK_DAYS
        )
        - 1
    )

    # --------------------------------------------------------
    # POINT-IN-TIME FUNDAMENTALS
    # --------------------------------------------------------

    fundamental_history = (
        build_fundamental_growth_history(
            symbol,
            history["Date"],
        )
    )

    history = history.merge(
        fundamental_history,
        on="Date",
        how="left",
    )

    # --------------------------------------------------------
    # SIGNAL COMPONENTS
    # --------------------------------------------------------

    history[
        "Trend signal"
    ] = (
        history[
            "50-day average"
        ]
        > history[
            "200-day average"
        ]
    )

    history[
        "Momentum signal"
    ] = (
        history[
            "12-month momentum"
        ]
        > 0
    )

    history[
        "Fundamental signal"
    ] = (
        history[
            "Fundamental growth score"
        ]
        >= fundamental_threshold
    )

    # Missing fundamental data does NOT pass the filter.

    history[
        "Fundamental signal"
    ] = (
        history[
            "Fundamental signal"
        ]
        .fillna(
            False
        )
    )

    # --------------------------------------------------------
    # COMBINED SIGNAL
    # --------------------------------------------------------

    signal = (
        history[
            "Trend signal"
        ]
        & history[
            "Momentum signal"
        ]
        & history[
            "Fundamental signal"
        ]
    )

    # --------------------------------------------------------
    # BACKTEST
    # --------------------------------------------------------

    result = (
        _run_signal_backtest(
            history,
            signal,
            initial_capital,
            transaction_cost_rate,
        )
    )

    # --------------------------------------------------------
    # ADD RESEARCH COLUMNS BACK TO RESULT
    # --------------------------------------------------------

    research_columns = [
        "50-day average",
        "200-day average",
        "12-month momentum",
        "Fundamental growth score",
        "Latest fundamental filing",
        "Trend signal",
        "Momentum signal",
        "Fundamental signal",
    ]

    for column in research_columns:

        result.history[
            column
        ] = history[
            column
        ].values

    return result


# ============================================================
# LOOK-AHEAD VALIDATION
# ============================================================

def validate_no_lookahead(
    history: pd.DataFrame,
) -> None:
    """
    Confirm that no fundamental filing used by the strategy
    occurs after the corresponding trading date.
    """

    if (
        "Latest fundamental filing"
        not in history.columns
    ):

        raise ValueError(
            "Fundamental filing column missing."
        )

    check = history[
        [
            "Date",
            "Latest fundamental filing",
        ]
    ].copy()

    check[
        "Latest fundamental filing"
    ] = pd.to_datetime(
        check[
            "Latest fundamental filing"
        ],
        errors="coerce",
    )

    invalid = check[
        (
            check[
                "Latest fundamental filing"
            ].notna()
        )
        & (
            check[
                "Latest fundamental filing"
            ]
            > check[
                "Date"
            ]
        )
    ]

    if not invalid.empty:

        raise RuntimeError(
            "LOOK-AHEAD BIAS DETECTED: "
            "a fundamental filing was used "
            "before its filing date."
        )


# ============================================================
# SIMPLE COMPARISON
# ============================================================

def compare_with_baseline(
    prices: pd.DataFrame,
    symbol: str,
    initial_capital: float = 10_000.0,
    transaction_cost_rate: float = 0.0,
    fundamental_threshold: float = FUNDAMENTAL_GROWTH_THRESHOLD,
) -> pd.DataFrame:
    """
    Compare:

    A. Existing Trend + Momentum
    B. Trend + Momentum + Fundamental Growth
    """

    from backtesting.momentum_backtest import (
        run_trend_momentum_backtest,
    )

    baseline = (
        run_trend_momentum_backtest(
            prices,
            initial_capital=
                initial_capital,
            transaction_cost_rate=
                transaction_cost_rate,
        )
    )

    fundamental = (
        run_trend_momentum_fundamental_backtest(
            prices,
            symbol=symbol,
            initial_capital=
                initial_capital,
            transaction_cost_rate=
                transaction_cost_rate,
            fundamental_threshold=
                fundamental_threshold,
        )
    )

    validate_no_lookahead(
        fundamental.history
    )

    baseline_metrics = (
        baseline.strategy_metrics
    )

    fundamental_metrics = (
        fundamental.strategy_metrics
    )

    rows = [
        {
            "Strategy":
                "Trend + Momentum",

            "CAGR":
                baseline_metrics[
                    "cagr"
                ],

            "Volatility":
                baseline_metrics[
                    "annualized_volatility"
                ],

            "Sharpe":
                baseline_metrics[
                    "sharpe_ratio"
                ],

            "Max Drawdown":
                baseline_metrics[
                    "maximum_drawdown"
                ],

            "Time Invested":
                baseline_metrics[
                    "percentage_invested"
                ],

            "Position Changes":
                baseline_metrics[
                    "number_of_position_changes"
                ],

            "Final Value":
                baseline.final_portfolio_value,
        },

        {
            "Strategy":
                (
                    "Trend + Momentum "
                    "+ Fundamental Growth"
                ),

            "CAGR":
                fundamental_metrics[
                    "cagr"
                ],

            "Volatility":
                fundamental_metrics[
                    "annualized_volatility"
                ],

            "Sharpe":
                fundamental_metrics[
                    "sharpe_ratio"
                ],

            "Max Drawdown":
                fundamental_metrics[
                    "maximum_drawdown"
                ],

            "Time Invested":
                fundamental_metrics[
                    "percentage_invested"
                ],

            "Position Changes":
                fundamental_metrics[
                    "number_of_position_changes"
                ],

            "Final Value":
                fundamental.final_portfolio_value,
        },
    ]

    return pd.DataFrame(
        rows
    )