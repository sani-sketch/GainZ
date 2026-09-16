from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

import requests
from dotenv import load_dotenv


load_dotenv()

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


# ============================================================
# COMPANY ALIASES
# ============================================================

COMPANY_TERMS = {
    "AMD": [
        "amd",
        "advanced micro devices",
        "lisa su",
    ],
    "MU": [
        "micron",
        "micron technology",
        "micron technology inc",
    ],
    "MPC": [
        "marathon petroleum",
        "marathon petroleum corp",
    ],
    "PANW": [
        "palo alto networks",
    ],
    "FTNT": [
        "fortinet",
    ],
    "PSX": [
        "phillips 66",
    ],
    "INTC": [
        "intel",
        "intel corp",
        "intel corporation",
    ],
    "STT": [
        "state street",
        "state street corporation",
    ],
    "CRM": [
        "salesforce",
    ],
    "MRK": [
        "merck",
        "merck & co",
    ],
    "BAC": [
        "bank of america",
        "bofa",
    ],
    "TMO": [
        "thermo fisher",
        "thermo fisher scientific",
    ],
    "MS": [
        "morgan stanley",
    ],
    "ADP": [
        "automatic data processing",
    ],
    "UNH": [
        "unitedhealth",
        "unitedhealth group",
    ],
}


# ============================================================
# TERM MATCHING
# ============================================================

def contains_term(
    text: str,
    term: str,
) -> bool:
    """
    Match company terms using word boundaries.

    This prevents short ticker symbols or company names
    from accidentally matching parts of unrelated words.
    """

    text = str(
        text or ""
    ).lower()

    term = str(
        term or ""
    ).lower().strip()

    if not term:
        return False

    pattern = (
        r"\b"
        + re.escape(term)
        + r"\b"
    )

    return (
        re.search(
            pattern,
            text,
        )
        is not None
    )


# ============================================================
# RELEVANCE SCORE
# ============================================================

def calculate_relevance(
    symbol: str,
    headline: str,
    summary: str,
) -> float:
    """
    Estimate how relevant an article is to a company.

    Approximate scale:

    1.00 = very strongly company-focused
    0.90 = company clearly appears in headline + summary
    0.75 = company appears in headline
    0.60 = company repeatedly appears in summary
    0.35 = company appears once in summary
    0.00 = no meaningful company reference
    """

    symbol = symbol.upper()

    terms = COMPANY_TERMS.get(
        symbol,
        [],
    )

    # If we do not explicitly know this company,
    # use the ticker only when reasonably safe.
    if not terms:
        if len(symbol) >= 3:
            terms = [
                symbol.lower()
            ]
        else:
            return 0.0

    headline = str(
        headline or ""
    ).lower()

    summary = str(
        summary or ""
    ).lower()

    headline_matches = sum(
        contains_term(
            headline,
            term,
        )
        for term in terms
    )

    summary_matches = sum(
        contains_term(
            summary,
            term,
        )
        for term in terms
    )

    # --------------------------------------------------------
    # Multiple known company terms appear in headline
    # --------------------------------------------------------

    if headline_matches >= 2:
        return 1.0

    # --------------------------------------------------------
    # Company appears in both headline and summary
    # --------------------------------------------------------

    if (
        headline_matches >= 1
        and summary_matches >= 1
    ):
        return 0.90

    # --------------------------------------------------------
    # Company appears in headline
    # --------------------------------------------------------

    if headline_matches >= 1:
        return 0.75

    # --------------------------------------------------------
    # Company repeatedly appears in summary
    # --------------------------------------------------------

    if summary_matches >= 2:
        return 0.60

    # --------------------------------------------------------
    # Company appears once in summary
    # --------------------------------------------------------

    if summary_matches == 1:
        return 0.35

    return 0.0


def is_relevant_article(
    symbol: str,
    headline: str,
    summary: str,
    minimum_relevance: float = 0.35,
) -> bool:
    """
    Return True when an article meets the minimum
    relevance threshold.
    """

    relevance = calculate_relevance(
        symbol,
        headline,
        summary,
    )

    return (
        relevance
        >= minimum_relevance
    )


# ============================================================
# HEADLINE NORMALIZATION
# ============================================================

def normalize_headline(
    headline: str,
) -> str:
    """
    Normalize headline text for duplicate detection.
    """

    headline = str(
        headline or ""
    ).lower()

    # Remove punctuation
    headline = re.sub(
        r"[^a-z0-9\s]",
        " ",
        headline,
    )

    # Remove repeated whitespace
    headline = re.sub(
        r"\s+",
        " ",
        headline,
    ).strip()

    return headline


# ============================================================
# DUPLICATE DETECTION
# ============================================================

def headlines_are_similar(
    headline_a: str,
    headline_b: str,
    threshold: float = 0.82,
) -> bool:
    """
    Detect likely duplicate/syndicated stories.

    1.0 = identical
    0.0 = completely different
    """

    a = normalize_headline(
        headline_a
    )

    b = normalize_headline(
        headline_b
    )

    if not a or not b:
        return False

    # Exact normalized match
    if a == b:
        return True

    similarity = SequenceMatcher(
        None,
        a,
        b,
    ).ratio()

    return (
        similarity
        >= threshold
    )


def deduplicate_articles(
    articles: list[dict],
) -> list[dict]:
    """
    Remove likely duplicate stories.

    The first occurrence is retained.
    """

    unique_articles = []

    for article in articles:

        headline = article.get(
            "headline",
            "",
        )

        duplicate = False

        for existing in unique_articles:

            existing_headline = (
                existing.get(
                    "headline",
                    "",
                )
            )

            if headlines_are_similar(
                headline,
                existing_headline,
            ):
                duplicate = True
                break

        if not duplicate:
            unique_articles.append(
                article
            )

    return unique_articles


# ============================================================
# FINNHUB NEWS
# ============================================================

def get_company_news(
    symbol: str,
    days: int = 3,
    limit: int = 20,
) -> list[dict]:
    """
    Fetch company news from Finnhub.

    Pipeline:

        Finnhub
            ↓
        Company alias matching
            ↓
        Relevance scoring
            ↓
        Duplicate detection
            ↓
        Clean article list
    """

    api_key = os.getenv(
        "FINNHUB_API_KEY"
    )

    if not api_key:
        raise RuntimeError(
            "FINNHUB_API_KEY is missing from .env"
        )

    symbol = (
        symbol
        .strip()
        .upper()
    )

    if not symbol:
        raise ValueError(
            "Symbol cannot be empty."
        )

    now = datetime.now(
        timezone.utc
    )

    start = (
        now
        - timedelta(
            days=days
        )
    )

    params = {
        "symbol": symbol,
        "from": start.strftime(
            "%Y-%m-%d"
        ),
        "to": now.strftime(
            "%Y-%m-%d"
        ),
        "token": api_key,
    }

    response = requests.get(
        f"{FINNHUB_BASE_URL}/company-news",
        params=params,
        timeout=20,
    )

    response.raise_for_status()

    raw_articles = (
        response.json()
    )

    if not isinstance(
        raw_articles,
        list,
    ):
        raise RuntimeError(
            "Unexpected response from Finnhub."
        )

    relevant_articles = []

    # ========================================================
    # RELEVANCE FILTER
    # ========================================================

    for item in raw_articles:

        headline = item.get(
            "headline",
            "",
        )

        summary = item.get(
            "summary",
            "",
        )

        relevance_score = (
            calculate_relevance(
                symbol,
                headline,
                summary,
            )
        )

        # Ignore weak/unrelated articles
        if relevance_score < 0.35:
            continue

        timestamp = item.get(
            "datetime"
        )

        published_at = None

        if timestamp:
            published_at = (
                datetime.fromtimestamp(
                    timestamp,
                    tz=timezone.utc,
                ).isoformat()
            )

        relevant_articles.append(
            {
                "symbol": symbol,
                "headline": headline,
                "summary": summary,
                "source": item.get(
                    "source",
                    "",
                ),
                "url": item.get(
                    "url",
                    "",
                ),
                "published_at": (
                    published_at
                ),
                "relevance_score": (
                    relevance_score
                ),
            }
        )

    # ========================================================
    # REMOVE DUPLICATES
    # ========================================================

    unique_articles = (
        deduplicate_articles(
            relevant_articles
        )
    )

    # Apply article limit AFTER filtering and deduplication
    return (
        unique_articles[:limit]
    )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    news = get_company_news(
        "AMD",
        days=3,
        limit=10,
    )

    print(
        f"\nFound {len(news)} "
        f"unique relevant AMD articles\n"
    )

    for index, article in enumerate(
        news,
        start=1,
    ):

        print(
            "=" * 70
        )

        print(
            f"ARTICLE {index}"
        )

        print(
            f"Relevance: "
            f"{article['relevance_score']:.2f}"
        )

        print(
            f"Source: "
            f"{article['source']}"
        )

        print(
            f"Published: "
            f"{article['published_at']}"
        )

        print(
            f"Headline: "
            f"{article['headline']}"
        )

        print()