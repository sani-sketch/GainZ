from __future__ import annotations

import math
from datetime import datetime, timezone

from sentiment.finbert import score_text
from sentiment.news import get_company_news


# ============================================================
# RECENCY WEIGHT
# ============================================================

def calculate_recency_weight(
    published_at: str | None,
    half_life_hours: float = 24.0,
) -> float:
    """
    Give newer articles more influence.

    Approx:
        now  -> 1.00
        12h  -> 0.71
        24h  -> 0.50
        48h  -> 0.25
        72h  -> 0.125
    """

    if not published_at:
        return 0.25

    try:
        published = datetime.fromisoformat(
            published_at.replace("Z", "+00:00")
        )

        if published.tzinfo is None:
            published = published.replace(
                tzinfo=timezone.utc
            )

        now = datetime.now(timezone.utc)

        age_hours = (
            now - published
        ).total_seconds() / 3600

        age_hours = max(
            0.0,
            age_hours,
        )

        return float(
            math.pow(
                0.5,
                age_hours / half_life_hours,
            )
        )

    except (ValueError, TypeError):
        return 0.25


# ============================================================
# SCORE ONE ARTICLE
# ============================================================

def score_article(article: dict) -> dict:
    """
    Run FinBERT on one article and calculate its
    recency weight.
    """

    headline = str(
        article.get("headline", "")
    ).strip()

    summary = str(
        article.get("summary", "")
    ).strip()

    # Give headline slightly more influence
    text = f"{headline}. {headline}. {summary}"

    sentiment = score_text(text)

    recency_weight = calculate_recency_weight(
        article.get("published_at")
    )

    return {
        **article,
        "positive": sentiment["positive"],
        "negative": sentiment["negative"],
        "neutral": sentiment["neutral"],
        "sentiment_score": sentiment["score"],
        "sentiment_label": sentiment["label"],
        "recency_weight": recency_weight,
    }


# ============================================================
# CONFIDENCE
# ============================================================

def calculate_confidence(
    articles: list[dict],
    target_article_count: int = 10,
) -> dict:
    """
    Estimate how much evidence supports the sentiment score.

    Confidence is based on:

    1. Article coverage
    2. Average relevance
    3. Average recency

    Confidence remains separate from sentiment.
    """

    if not articles:
        return {
            "confidence_score": 0.0,
            "confidence_label": "LOW",
            "coverage_score": 0.0,
            "average_relevance": 0.0,
            "average_recency": 0.0,
        }

    article_count = len(articles)

    # --------------------------------------------------------
    # COVERAGE
    #
    # 10 articles = full coverage for this V1 model.
    # --------------------------------------------------------

    coverage_score = min(
        article_count / target_article_count,
        1.0,
    )

    # --------------------------------------------------------
    # AVERAGE RELEVANCE
    # --------------------------------------------------------

    average_relevance = sum(
        article.get(
            "relevance_score",
            0.0,
        )
        for article in articles
    ) / article_count

    # --------------------------------------------------------
    # AVERAGE RECENCY
    # --------------------------------------------------------

    average_recency = sum(
        article.get(
            "recency_weight",
            0.0,
        )
        for article in articles
    ) / article_count

    # --------------------------------------------------------
    # FINAL CONFIDENCE
    #
    # Coverage is important, but relevance and freshness
    # also matter.
    # --------------------------------------------------------

    confidence_score = (
        0.40 * coverage_score
        + 0.35 * average_relevance
        + 0.25 * average_recency
    )

    confidence_score = max(
        0.0,
        min(
            confidence_score,
            1.0,
        ),
    )

    # --------------------------------------------------------
    # CONFIDENCE LABEL
    # --------------------------------------------------------

    if confidence_score >= 0.75:
        confidence_label = "HIGH"

    elif confidence_score >= 0.50:
        confidence_label = "MEDIUM"

    else:
        confidence_label = "LOW"

    return {
        "confidence_score": confidence_score,
        "confidence_label": confidence_label,
        "coverage_score": coverage_score,
        "average_relevance": average_relevance,
        "average_recency": average_recency,
    }


# ============================================================
# SCORE TICKER
# ============================================================

def score_ticker_news(
    symbol: str,
    days: int = 3,
    limit: int = 10,
) -> dict:
    """
    Calculate relevance + recency weighted FinBERT
    sentiment and a separate confidence score.

    This does NOT affect GainZ trading decisions.
    """

    symbol = symbol.strip().upper()

    articles = get_company_news(
        symbol=symbol,
        days=days,
        limit=limit,
    )

    scored_articles = [
        score_article(article)
        for article in articles
    ]

    # --------------------------------------------------------
    # NO NEWS
    # --------------------------------------------------------

    if not scored_articles:
        return {
            "symbol": symbol,
            "article_count": 0,
            "sentiment_score": 0.0,
            "sentiment_label": "NEUTRAL",
            "confidence_score": 0.0,
            "confidence_label": "LOW",
            "articles": [],
        }

    # ========================================================
    # RELEVANCE + RECENCY WEIGHTED SENTIMENT
    # ========================================================

    weighted_sum = 0.0
    total_weight = 0.0

    for article in scored_articles:

        sentiment_score = article[
            "sentiment_score"
        ]

        relevance_score = article.get(
            "relevance_score",
            1.0,
        )

        recency_weight = article.get(
            "recency_weight",
            1.0,
        )

        combined_weight = (
            relevance_score
            * recency_weight
        )

        weighted_contribution = (
            sentiment_score
            * combined_weight
        )

        article["combined_weight"] = (
            combined_weight
        )

        article["weighted_contribution"] = (
            weighted_contribution
        )

        weighted_sum += (
            weighted_contribution
        )

        total_weight += (
            combined_weight
        )

    if total_weight > 0:
        final_score = (
            weighted_sum
            / total_weight
        )
    else:
        final_score = 0.0

    # ========================================================
    # SENTIMENT LABEL
    # ========================================================

    if final_score >= 0.25:
        overall_label = "POSITIVE"

    elif final_score <= -0.25:
        overall_label = "NEGATIVE"

    else:
        overall_label = "NEUTRAL"

    # ========================================================
    # CONFIDENCE
    # ========================================================

    confidence = calculate_confidence(
        scored_articles
    )

    return {
        "symbol": symbol,
        "article_count": len(scored_articles),
        "sentiment_score": final_score,
        "sentiment_label": overall_label,
        "confidence_score": confidence[
            "confidence_score"
        ],
        "confidence_label": confidence[
            "confidence_label"
        ],
        "coverage_score": confidence[
            "coverage_score"
        ],
        "average_relevance": confidence[
            "average_relevance"
        ],
        "average_recency": confidence[
            "average_recency"
        ],
        "articles": scored_articles,
    }


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    result = score_ticker_news(
        "AMD",
        days=3,
        limit=10,
    )

    print()
    print("=" * 70)
    print("GAINZ SENTIMENT + CONFIDENCE TEST")
    print("=" * 70)

    print(
        f"Ticker: "
        f"{result['symbol']}"
    )

    print(
        f"Articles: "
        f"{result['article_count']}"
    )

    print(
        f"Sentiment: "
        f"{result['sentiment_label']}"
    )

    print(
        f"Sentiment score: "
        f"{result['sentiment_score']:+.3f}"
    )

    print(
        f"Confidence: "
        f"{result['confidence_label']}"
    )

    print(
        f"Confidence score: "
        f"{result['confidence_score']:.3f}"
    )

    print(
        f"Coverage: "
        f"{result.get('coverage_score', 0.0):.3f}"
    )

    print(
        f"Average relevance: "
        f"{result.get('average_relevance', 0.0):.3f}"
    )

    print(
        f"Average recency: "
        f"{result.get('average_recency', 0.0):.3f}"
    )

    print()