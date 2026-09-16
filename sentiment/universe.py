from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sentiment.scorer import score_ticker_news


# ============================================================
# SETTINGS
# ============================================================

GAINZ_UNIVERSE = [
    "AMD",
    "MU",
    "MPC",
    "PANW",
    "FTNT",
    "PSX",
    "INTC",
    "STT",
    "CRM",
    "MRK",
    "BAC",
    "TMO",
    "MS",
    "ADP",
    "UNH",
]

SENTIMENT_HISTORY_DIR = Path(
    "data/sentiment_history"
)


# ============================================================
# SCAN UNIVERSE
# ============================================================

def scan_sentiment_universe(
    symbols: list[str],
    days: int = 3,
    limit: int = 10,
) -> list[dict]:

    results = []

    for index, symbol in enumerate(
        symbols,
        start=1,
    ):

        print(
            f"Scanning {symbol} "
            f"({index}/{len(symbols)})..."
        )

        try:

            result = score_ticker_news(
                symbol=symbol,
                days=days,
                limit=limit,
            )

            results.append(result)

        except Exception as exc:

            print(
                f"WARNING: "
                f"{symbol} failed: {exc}"
            )

            results.append(
                {
                    "symbol": symbol,
                    "article_count": 0,
                    "sentiment_score": 0.0,
                    "sentiment_label": "ERROR",
                    "confidence_score": 0.0,
                    "confidence_label": "LOW",
                    "articles": [],
                    "error": str(exc),
                }
            )

    return results


# ============================================================
# SAVE HISTORICAL SNAPSHOT
# ============================================================

def save_sentiment_snapshot(
    results: list[dict],
) -> Path:
    """
    Save one point-in-time GainZ sentiment snapshot.

    This creates a historical dataset without affecting
    trading decisions.
    """

    SENTIMENT_HISTORY_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    now = datetime.now(
        timezone.utc
    )

    timestamp = now.isoformat()

    filename_timestamp = now.strftime(
        "%Y-%m-%dT%H%M%SZ"
    )

    stocks = {}

    for result in results:

        symbol = result.get(
            "symbol",
            "",
        )

        if not symbol:
            continue

        stocks[symbol] = {
            "sentiment_score": result.get(
                "sentiment_score",
                0.0,
            ),
            "sentiment_label": result.get(
                "sentiment_label",
                "NEUTRAL",
            ),
            "confidence_score": result.get(
                "confidence_score",
                0.0,
            ),
            "confidence_label": result.get(
                "confidence_label",
                "LOW",
            ),
            "article_count": result.get(
                "article_count",
                0,
            ),
            "coverage_score": result.get(
                "coverage_score",
                0.0,
            ),
            "average_relevance": result.get(
                "average_relevance",
                0.0,
            ),
            "average_recency": result.get(
                "average_recency",
                0.0,
            ),
        }

    snapshot = {
        "timestamp_utc": timestamp,
        "universe_size": len(results),
        "stocks": stocks,
    }

    output_path = (
        SENTIMENT_HISTORY_DIR
        / f"{filename_timestamp}.json"
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            snapshot,
            file,
            indent=2,
        )

    return output_path


# ============================================================
# DISPLAY SNAPSHOT
# ============================================================

def print_sentiment_snapshot(
    results: list[dict],
) -> None:

    print()
    print("=" * 92)
    print("GAINZ SENTIMENT SNAPSHOT")
    print("=" * 92)

    print(
        f"{'Ticker':<8}"
        f"{'Score':>10}"
        f"{'Sentiment':>14}"
        f"{'Articles':>12}"
        f"{'Confidence':>14}"
        f"{'Level':>12}"
    )

    print("-" * 92)

    for result in results:

        symbol = result.get(
            "symbol",
            "",
        )

        sentiment_score = result.get(
            "sentiment_score",
            0.0,
        )

        sentiment_label = result.get(
            "sentiment_label",
            "NEUTRAL",
        )

        article_count = result.get(
            "article_count",
            0,
        )

        confidence_score = result.get(
            "confidence_score",
            0.0,
        )

        confidence_label = result.get(
            "confidence_label",
            "LOW",
        )

        print(
            f"{symbol:<8}"
            f"{sentiment_score:>+10.3f}"
            f"{sentiment_label:>14}"
            f"{article_count:>12}"
            f"{confidence_score:>14.3f}"
            f"{confidence_label:>12}"
        )

    print("=" * 92)


# ============================================================
# SUMMARY
# ============================================================

def print_summary(
    results: list[dict],
) -> None:

    positive = sum(
        result.get("sentiment_label")
        == "POSITIVE"
        for result in results
    )

    neutral = sum(
        result.get("sentiment_label")
        == "NEUTRAL"
        for result in results
    )

    negative = sum(
        result.get("sentiment_label")
        == "NEGATIVE"
        for result in results
    )

    high_confidence = sum(
        result.get("confidence_label")
        == "HIGH"
        for result in results
    )

    medium_confidence = sum(
        result.get("confidence_label")
        == "MEDIUM"
        for result in results
    )

    low_confidence = sum(
        result.get("confidence_label")
        == "LOW"
        for result in results
    )

    print()
    print("SENTIMENT SUMMARY")
    print("-" * 40)

    print(
        f"Positive: {positive}"
    )

    print(
        f"Neutral:  {neutral}"
    )

    print(
        f"Negative: {negative}"
    )

    print()

    print(
        f"High confidence:   "
        f"{high_confidence}"
    )

    print(
        f"Medium confidence: "
        f"{medium_confidence}"
    )

    print(
        f"Low confidence:    "
        f"{low_confidence}"
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    results = scan_sentiment_universe(
        symbols=GAINZ_UNIVERSE,
        days=3,
        limit=10,
    )

    print_sentiment_snapshot(
        results
    )

    print_summary(
        results
    )

    saved_path = save_sentiment_snapshot(
        results
    )

    print()
    print(
        f"Sentiment snapshot saved to: "
        f"{saved_path}"
    )