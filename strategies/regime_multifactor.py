import pandas as pd
import numpy as np


def detect_market_regime(
    market_df: pd.DataFrame,
    short_window: int = 50,
    long_window: int = 200,
) -> pd.Series:
    """
    Classify the market as RISK_ON or RISK_OFF.

    Expected columns:
    - Close
    """

    df = market_df.copy()

    df["ma_short"] = df["Close"].rolling(short_window).mean()
    df["ma_long"] = df["Close"].rolling(long_window).mean()

    risk_on = (
        (df["Close"] > df["ma_long"])
        & (df["ma_short"] > df["ma_long"])
    )

    return pd.Series(
        np.where(risk_on, "RISK_ON", "RISK_OFF"),
        index=df.index,
        name="market_regime",
    )


def calculate_factor_score(stock_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate the first GainZ multi-factor score.

    Factors:
    - 6-month momentum
    - 3-month momentum
    - trend strength
    - volatility
    - volume confirmation

    Expected columns:
    - Close
    - Volume
    """

    df = stock_df.copy()

    # -------------------------
    # MOMENTUM
    # -------------------------
    df["momentum_6m"] = df["Close"].pct_change(126)
    df["momentum_3m"] = df["Close"].pct_change(63)

    # -------------------------
    # TREND
    # -------------------------
    df["ma_50"] = df["Close"].rolling(50).mean()
    df["ma_200"] = df["Close"].rolling(200).mean()

    df["trend_strength"] = (
        df["Close"] / df["ma_200"] - 1
    )

    # -------------------------
    # VOLATILITY
    # Lower volatility receives a better score
    # -------------------------
    daily_returns = df["Close"].pct_change()

    df["volatility"] = (
        daily_returns
        .rolling(63)
        .std()
        * np.sqrt(252)
    )

    # -------------------------
    # VOLUME CONFIRMATION
    # -------------------------
    df["avg_volume_20"] = df["Volume"].rolling(20).mean()

    df["volume_strength"] = (
        df["Volume"] / df["avg_volume_20"]
    )

    # -------------------------
    # NORMALISED FACTORS
    # -------------------------
    df["momentum_score"] = (
        0.6 * df["momentum_6m"]
        + 0.4 * df["momentum_3m"]
    )

    df["trend_score"] = df["trend_strength"]

    df["volatility_score"] = -df["volatility"]

    df["volume_score"] = (
        df["volume_strength"] - 1
    )

    # -------------------------
    # FINAL SCORE
    # -------------------------
    df["factor_score"] = (
        0.40 * df["momentum_score"]
        + 0.30 * df["trend_score"]
        + 0.20 * df["volatility_score"]
        + 0.10 * df["volume_score"]
    )

    return df


def latest_stock_score(stock_df: pd.DataFrame) -> float:
    """
    Return the latest valid GainZ factor score.
    """

    scored = calculate_factor_score(stock_df)

    valid_scores = scored["factor_score"].dropna()

    if valid_scores.empty:
        return np.nan

    return float(valid_scores.iloc[-1])

def _zscore(series: pd.Series) -> pd.Series:
    """Cross-sectional z-score; constant factors contribute zero."""
    std = series.std(ddof=0)
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=series.index)
    return (series - series.mean()) / std


def rank_stock_universe(stock_data: dict[str, pd.DataFrame], top_n: int | None = None) -> pd.DataFrame:
    """Rank a stock universe using cross-sectionally normalised factor values.

    Each mapping value is a point-in-time price history ending on the ranking date.
    This function never reads future rows beyond the supplied frame.
    """
    rows = []
    for ticker, frame in stock_data.items():
        scored = calculate_factor_score(frame)
        valid = scored.dropna(subset=["momentum_score", "trend_score", "volatility", "volume_score"])
        if valid.empty:
            continue
        last = valid.iloc[-1]
        rows.append({
            "ticker": ticker,
            "momentum": float(last["momentum_score"]),
            "trend": float(last["trend_score"]),
            "volatility": float(last["volatility"]),
            "volume": float(last["volume_score"]),
        })

    if not rows:
        return pd.DataFrame(columns=["ticker", "momentum", "trend", "volatility", "volume", "factor_score", "rank"])

    ranked = pd.DataFrame(rows).set_index("ticker")
    ranked["momentum_z"] = _zscore(ranked["momentum"])
    ranked["trend_z"] = _zscore(ranked["trend"])
    ranked["low_volatility_z"] = _zscore(-ranked["volatility"])
    ranked["volume_z"] = _zscore(ranked["volume"])
    ranked["factor_score"] = (
        0.40 * ranked["momentum_z"]
        + 0.30 * ranked["trend_z"]
        + 0.20 * ranked["low_volatility_z"]
        + 0.10 * ranked["volume_z"]
    )
    ranked = ranked.sort_values("factor_score", ascending=False)
    ranked["rank"] = np.arange(1, len(ranked) + 1)
    ranked = ranked.reset_index()
    return ranked.head(top_n).copy() if top_n is not None else ranked


def select_portfolio(
    stock_data: dict[str, pd.DataFrame],
    market_df: pd.DataFrame,
    top_n: int = 10,
) -> pd.DataFrame:
    """Return top-ranked stocks only when the latest market regime is RISK_ON."""
    regime = detect_market_regime(market_df)
    if regime.empty or regime.iloc[-1] != "RISK_ON":
        return pd.DataFrame(columns=["ticker", "factor_score", "rank", "target_weight"])
    selected = rank_stock_universe(stock_data, top_n=top_n)
    if selected.empty:
        selected["target_weight"] = pd.Series(dtype=float)
        return selected
    selected["target_weight"] = 1.0 / len(selected)
    return selected
