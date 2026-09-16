from __future__ import annotations

import os
import time

import requests
from dotenv import load_dotenv


load_dotenv()


# ============================================================
# SEC SETTINGS
# ============================================================

SEC_DATA_BASE_URL = "https://data.sec.gov"
SEC_WWW_BASE_URL = "https://www.sec.gov"

# SEC asks automated clients to identify themselves.
#
# Add this to .env:
#
# SEC_USER_AGENT=GainZ your-email@example.com
#
# Use your real contact email.
SEC_USER_AGENT = os.getenv(
    "SEC_USER_AGENT",
    "",
).strip()


# ============================================================
# HTTP
# ============================================================

def _headers() -> dict:
    """
    Build SEC-compliant request headers.
    """

    if not SEC_USER_AGENT:
        raise RuntimeError(
            "SEC_USER_AGENT is missing from .env. "
            "Add something like: "
            "SEC_USER_AGENT=GainZ your-email@example.com"
        )

    return {
        "User-Agent": SEC_USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
        "Host": "data.sec.gov",
    }


def _request_json(
    url: str,
) -> dict:
    """
    Fetch JSON from SEC.

    A small delay keeps our development requests
    comfortably below SEC rate limits.
    """

    response = requests.get(
        url,
        headers=_headers(),
        timeout=30,
    )

    response.raise_for_status()

    time.sleep(0.15)

    data = response.json()

    if not isinstance(data, dict):
        raise RuntimeError(
            f"Unexpected SEC response from {url}"
        )

    return data


# ============================================================
# TICKER → CIK
# ============================================================

def get_company_tickers() -> dict:
    """
    Download SEC ticker → CIK mapping.
    """

    url = (
        f"{SEC_WWW_BASE_URL}/files/"
        "company_tickers.json"
    )

    headers = {
        "User-Agent": SEC_USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
    }

    if not SEC_USER_AGENT:
        raise RuntimeError(
            "SEC_USER_AGENT is missing from .env."
        )

    response = requests.get(
        url,
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()

    time.sleep(0.15)

    return response.json()


def get_cik(
    symbol: str,
) -> str:
    """
    Resolve a ticker symbol to its zero-padded SEC CIK.
    """

    symbol = symbol.strip().upper()

    tickers = get_company_tickers()

    for company in tickers.values():

        ticker = str(
            company.get("ticker", "")
        ).upper()

        if ticker == symbol:

            cik = int(
                company["cik_str"]
            )

            return f"{cik:010d}"

    raise RuntimeError(
        f"Could not find SEC CIK for {symbol}"
    )


# ============================================================
# COMPANY FACTS
# ============================================================

def get_company_facts(
    symbol: str,
) -> dict:
    """
    Download SEC XBRL Company Facts for one company.
    """

    symbol = symbol.strip().upper()

    cik = get_cik(symbol)

    url = (
        f"{SEC_DATA_BASE_URL}/api/xbrl/"
        f"companyfacts/CIK{cik}.json"
    )

    data = _request_json(url)

    return {
        "symbol": symbol,
        "cik": cik,
        "entity_name": data.get(
            "entityName"
        ),
        "facts": data.get(
            "facts",
            {},
        ),
    }


# ============================================================
# XBRL FACT HELPERS
# ============================================================

def get_us_gaap_fact(
    company_facts: dict,
    concept: str,
) -> dict | None:
    """
    Retrieve one US-GAAP XBRL concept.
    """

    facts = company_facts.get(
        "facts",
        {}
    )

    us_gaap = facts.get(
        "us-gaap",
        {}
    )

    return us_gaap.get(
        concept
    )


def get_fact_units(
    company_facts: dict,
    concept: str,
    unit: str = "USD",
) -> list[dict]:
    """
    Retrieve observations for a US-GAAP concept/unit.
    """

    fact = get_us_gaap_fact(
        company_facts,
        concept,
    )

    if not fact:
        return []

    units = fact.get(
        "units",
        {}
    )

    observations = units.get(
        unit,
        [],
    )

    if not isinstance(
        observations,
        list,
    ):
        return []

    return observations


# ============================================================
# REVENUE CONCEPTS
# ============================================================

REVENUE_CONCEPTS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
]


def get_revenue_observations(
    company_facts: dict,
) -> tuple[str | None, list[dict]]:
    """
    Find the first supported SEC revenue concept.
    """

    for concept in REVENUE_CONCEPTS:

        observations = get_fact_units(
            company_facts,
            concept,
            unit="USD",
        )

        if observations:
            return (
                concept,
                observations,
            )

    return (
        None,
        [],
    )


# ============================================================
# CLEAN QUARTERLY OBSERVATIONS
# ============================================================

def get_recent_quarterly_observations(
    observations: list[dict],
    limit: int = 8,
) -> list[dict]:
    """
    Keep recent quarterly 10-Q / 10-K observations.

    The SEC dataset can contain multiple observations
    representing the same underlying period because facts
    may be repeated or amended in later filings.

    For this first retrieval test, we retain useful metadata
    including filed date and accession number.
    """

    filtered = []

    for observation in observations:

        form = observation.get(
            "form"
        )

        if form not in {
            "10-Q",
            "10-K",
        }:
            continue

        if observation.get("val") is None:
            continue

        filtered.append(
            observation
        )

    # Most recent filing first.
    filtered.sort(
        key=lambda item: (
            item.get("filed", ""),
            item.get("end", ""),
        ),
        reverse=True,
    )

    return filtered[:limit]


# ============================================================
# DISPLAY
# ============================================================

def format_money(
    value,
) -> str:

    if value is None:
        return "N/A"

    value = float(value)

    if abs(value) >= 1_000_000_000:
        return (
            f"${value / 1_000_000_000:.2f}B"
        )

    if abs(value) >= 1_000_000:
        return (
            f"${value / 1_000_000:.2f}M"
        )

    return f"${value:,.0f}"


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    symbol = "AMD"

    print()
    print("=" * 72)
    print(
        f"GAINZ SEC FUNDAMENTALS TEST — {symbol}"
    )
    print("=" * 72)

    company = get_company_facts(
        symbol
    )

    print(
        f"Company: {company['entity_name']}"
    )

    print(
        f"CIK:     {company['cik']}"
    )

    concept, revenue = (
        get_revenue_observations(
            company
        )
    )

    print(
        f"Revenue concept: {concept}"
    )

    recent = (
        get_recent_quarterly_observations(
            revenue,
            limit=8,
        )
    )

    print()
    print("RECENT SEC REVENUE OBSERVATIONS")
    print("-" * 72)

    if not recent:

        print(
            "No revenue observations found."
        )

    for observation in recent:

        print(
            f"Period end: "
            f"{observation.get('end')}"
        )

        print(
            f"Filed:      "
            f"{observation.get('filed')}"
        )

        print(
            f"Form:       "
            f"{observation.get('form')}"
        )

        print(
            f"Fiscal year:"
            f" {observation.get('fy')}"
        )

        print(
            f"Fiscal period:"
            f" {observation.get('fp')}"
        )

        print(
            f"Revenue:    "
            f"{format_money(observation.get('val'))}"
        )

        print(
            f"Accession:  "
            f"{observation.get('accn')}"
        )

        print("-" * 72)