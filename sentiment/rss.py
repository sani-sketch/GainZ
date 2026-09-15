from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import feedparser


@dataclass(frozen=True)
class NewsItem:
    symbol: str
    title: str
    summary: str
    link: str
    source: str
    published_at: datetime | None


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        dt = parsedate_to_datetime(value)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except Exception:
        return None


def _clean_text(value: str | None) -> str:
    if not value:
        return ""

    return " ".join(
        str(value)
        .replace("\n", " ")
        .replace("\r", " ")
        .split()
    )


def google_news_rss_url(
    symbol: str,
    company_name: str | None = None,
) -> str:
    """
    Build a Google News RSS search.

    We use both company name and ticker when available
    to reduce irrelevant ticker matches.
    """

    symbol = symbol.upper().strip()

    if company_name:
        query = f'"{company_name}" {symbol} stock'
    else:
        query = f'{symbol} stock'

    encoded = quote_plus(query)

    return (
        "https://news.google.com/rss/search"
        f"?q={encoded}"
        "&hl=en-US"
        "&gl=US"
        "&ceid=US:en"
    )


def fetch_stock_news(
    symbol: str,
    company_name: str | None = None,
    limit: int = 20,
) -> list[NewsItem]:
    """
    Fetch recent news for one stock.

    This function only retrieves news.
    It does NOT influence GainZ trading decisions.
    """

    url = google_news_rss_url(
        symbol=symbol,
        company_name=company_name,
    )

    feed = feedparser.parse(url)

    items: list[NewsItem] = []

    seen_titles: set[str] = set()

    for entry in feed.entries:

        title = _clean_text(
            entry.get("title")
        )

        if not title:
            continue

        # Basic duplicate protection
        title_key = title.lower()

        if title_key in seen_titles:
            continue

        seen_titles.add(title_key)

        summary = _clean_text(
            entry.get("summary")
        )

        link = str(
            entry.get("link", "")
        )

        published_at = _parse_date(
            entry.get("published")
        )

        source = "Google News"

        source_data = entry.get("source")

        if isinstance(source_data, dict):
            source = str(
                source_data.get(
                    "title",
                    source,
                )
            )

        items.append(
            NewsItem(
                symbol=symbol.upper(),
                title=title,
                summary=summary,
                link=link,
                source=source,
                published_at=published_at,
            )
        )

        if len(items) >= limit:
            break

    return items


def fetch_universe_news(
    symbols: list[str],
    company_names: dict[str, str] | None = None,
    limit_per_symbol: int = 10,
) -> dict[str, list[NewsItem]]:
    """
    Fetch news for multiple GainZ symbols.
    """

    company_names = company_names or {}

    output: dict[str, list[NewsItem]] = {}

    for symbol in symbols:

        symbol = symbol.upper()

        output[symbol] = fetch_stock_news(
            symbol=symbol,
            company_name=company_names.get(symbol),
            limit=limit_per_symbol,
        )

    return output