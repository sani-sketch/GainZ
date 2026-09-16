from __future__ import annotations

from datetime import datetime

from fundamentals.sec import (
    get_company_facts,
    get_revenue_observations,
    get_fact_units,
)


# ============================================================
# SEC CONCEPTS
# ============================================================

NET_INCOME_CONCEPTS = [
    "NetIncomeLoss",
    "ProfitLoss",
]

EPS_CONCEPTS = [
    "EarningsPerShareDiluted",
    "EarningsPerShareBasicAndDiluted",
    "EarningsPerShareBasic",
]


# ============================================================
# DATE HELPERS
# ============================================================

def parse_date(value: str | None) -> datetime | None:
    """
    Convert YYYY-MM-DD into datetime.
    """

    if not value:
        return None

    try:
        return datetime.strptime(
            value,
            "%Y-%m-%d",
        )

    except ValueError:
        return None


def duration_days(observation: dict) -> int | None:
    """
    Calculate the number of days covered by
    an SEC duration fact.
    """

    start = parse_date(
        observation.get("start")
    )

    end = parse_date(
        observation.get("end")
    )

    if not start or not end:
        return None

    return (end - start).days + 1


# ============================================================
# QUARTER DETECTION
# ============================================================

def is_standalone_quarter(
    observation: dict,
    minimum_days: int = 70,
    maximum_days: int = 120,
) -> bool:
    """
    Determine whether a duration fact represents
    approximately one standalone fiscal quarter.
    """

    days = duration_days(
        observation
    )

    if days is None:
        return False

    return (
        minimum_days
        <= days
        <= maximum_days
    )


# ============================================================
# NORMALIZE OBSERVATION
# ============================================================

def normalize_observation(
    observation: dict,
) -> dict:
    """
    Convert raw SEC observation into
    GainZ representation.
    """

    return {
        "start": observation.get("start"),
        "end": observation.get("end"),
        "filed": observation.get("filed"),
        "form": observation.get("form"),
        "fiscal_year": observation.get("fy"),
        "fiscal_period": observation.get("fp"),
        "value": observation.get("val"),
        "accession": observation.get("accn"),
        "duration_days": duration_days(
            observation
        ),
    }


# ============================================================
# DEDUPLICATION
# ============================================================

def deduplicate_quarters(
    observations: list[dict],
) -> list[dict]:
    """
    Deduplicate repeated SEC quarterly facts.

    Preserve the earliest filing for the same
    underlying period/value combination.
    """

    grouped = {}

    for observation in observations:

        key = (
            observation.get("end"),
            observation.get("value"),
        )

        existing = grouped.get(key)

        if existing is None:
            grouped[key] = observation
            continue

        existing_filed = (
            existing.get("filed")
            or "9999-12-31"
        )

        candidate_filed = (
            observation.get("filed")
            or "9999-12-31"
        )

        if candidate_filed < existing_filed:
            grouped[key] = observation

    results = list(
        grouped.values()
    )

    results.sort(
        key=lambda item: (
            item.get("end") or "",
            item.get("filed") or "",
        ),
        reverse=True,
    )

    return results


# ============================================================
# EXTRACT STANDALONE QUARTERS
# ============================================================

def extract_standalone_quarters(
    observations: list[dict],
) -> list[dict]:
    """
    Extract standalone quarterly duration facts.

    For V1 we use 10-Q facts covering
    approximately one fiscal quarter.
    """

    quarters = []

    for observation in observations:

        if observation.get("form") != "10-Q":
            continue

        if observation.get("val") is None:
            continue

        if not is_standalone_quarter(
            observation
        ):
            continue

        quarters.append(
            normalize_observation(
                observation
            )
        )

    return deduplicate_quarters(
        quarters
    )


# ============================================================
# GENERIC SEC CONCEPT FINDER
# ============================================================

def get_first_available_concept(
    company_facts: dict,
    concepts: list[str],
    unit: str,
) -> tuple[str | None, list[dict]]:
    """
    Find the first available SEC XBRL concept.
    """

    for concept in concepts:

        observations = get_fact_units(
            company_facts,
            concept,
            unit=unit,
        )

        if observations:
            return concept, observations

    return None, []


# ============================================================
# NORMALIZED INCOME METRICS
# ============================================================

def get_normalized_income_metrics(
    symbol: str,
) -> dict:
    """
    Retrieve normalized standalone quarterly:

    - Revenue
    - Net income
    - EPS
    """

    symbol = symbol.strip().upper()

    company = get_company_facts(
        symbol
    )

    # Revenue

    (
        revenue_concept,
        revenue_raw,
    ) = get_revenue_observations(
        company
    )

    # Net income

    (
        net_income_concept,
        net_income_raw,
    ) = get_first_available_concept(
        company,
        NET_INCOME_CONCEPTS,
        "USD",
    )

    # EPS

    (
        eps_concept,
        eps_raw,
    ) = get_first_available_concept(
        company,
        EPS_CONCEPTS,
        "USD/shares",
    )

    return {
        "symbol": symbol,
        "company": company.get(
            "entity_name"
        ),
        "cik": company.get(
            "cik"
        ),

        "revenue_concept":
            revenue_concept,

        "revenue":
            extract_standalone_quarters(
                revenue_raw
            ),

        "net_income_concept":
            net_income_concept,

        "net_income":
            extract_standalone_quarters(
                net_income_raw
            ),

        "eps_concept":
            eps_concept,

        "eps":
            extract_standalone_quarters(
                eps_raw
            ),
    }


# ============================================================
# YOY HELPERS
# ============================================================

def growth_rate(
    current,
    previous,
) -> float | None:
    """
    Calculate year-over-year growth.

    Example:
        current = 150
        previous = 100

        result = 0.50
    """

    if current is None:
        return None

    if previous is None:
        return None

    current = float(current)
    previous = float(previous)

    if previous == 0:
        return None

    return (
        current - previous
    ) / abs(previous)


def find_year_ago_quarter(
    quarters: list[dict],
    current: dict,
    tolerance_days: int = 20,
) -> dict | None:
    """
    Find approximately the same fiscal quarter
    one year earlier.

    We use period-end dates rather than blindly
    trusting SEC fy/fp labels because comparative
    observations can carry labels from later filings.
    """

    current_end = parse_date(
        current.get("end")
    )

    if current_end is None:
        return None

    best_match = None
    best_difference = None

    for candidate in quarters:

        if candidate is current:
            continue

        candidate_end = parse_date(
            candidate.get("end")
        )

        if candidate_end is None:
            continue

        difference = (
            current_end - candidate_end
        ).days

        # Same quarter previous year should normally
        # be roughly 365 days earlier.
        distance_from_year = abs(
            difference - 365
        )

        if distance_from_year > tolerance_days:
            continue

        if (
            best_difference is None
            or distance_from_year
            < best_difference
        ):
            best_match = candidate
            best_difference = (
                distance_from_year
            )

    return best_match


def calculate_metric_yoy(
    quarters: list[dict],
) -> dict:
    """
    Calculate latest-quarter YoY growth
    for one metric.
    """

    if not quarters:

        return {
            "current": None,
            "previous": None,
            "growth": None,
        }

    current = quarters[0]

    previous = find_year_ago_quarter(
        quarters,
        current,
    )

    if previous is None:

        return {
            "current": current,
            "previous": None,
            "growth": None,
        }

    growth = growth_rate(
        current.get("value"),
        previous.get("value"),
    )

    return {
        "current": current,
        "previous": previous,
        "growth": growth,
    }


# ============================================================
# FUNDAMENTAL GROWTH SNAPSHOT
# ============================================================

def calculate_growth_snapshot(
    symbol: str,
) -> dict:
    """
    Build the latest GainZ fundamental
    growth snapshot.
    """

    metrics = (
        get_normalized_income_metrics(
            symbol
        )
    )

    revenue_yoy = (
        calculate_metric_yoy(
            metrics["revenue"]
        )
    )

    net_income_yoy = (
        calculate_metric_yoy(
            metrics["net_income"]
        )
    )

    eps_yoy = (
        calculate_metric_yoy(
            metrics["eps"]
        )
    )

    filing_dates = []

    for result in [
        revenue_yoy,
        net_income_yoy,
        eps_yoy,
    ]:

        current = result.get(
            "current"
        )

        if (
            current
            and current.get("filed")
        ):
            filing_dates.append(
                current["filed"]
            )

    latest_filing_date = (
        max(filing_dates)
        if filing_dates
        else None
    )

    return {
        "symbol": metrics["symbol"],
        "company": metrics["company"],
        "latest_filing_date":
            latest_filing_date,

        "revenue_yoy":
            revenue_yoy,

        "net_income_yoy":
            net_income_yoy,

        "eps_yoy":
            eps_yoy,
    }


# ============================================================
# DISPLAY HELPERS
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


def format_eps(
    value,
) -> str:

    if value is None:
        return "N/A"

    return (
        f"${float(value):.2f}"
    )


def format_percent(
    value,
) -> str:

    if value is None:
        return "N/A"

    return (
        f"{float(value) * 100:+.1f}%"
    )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    symbol = "AMD"

    result = (
        calculate_growth_snapshot(
            symbol
        )
    )

    print()

    print(
        "=" * 78
    )

    print(
        f"GAINZ FUNDAMENTAL GROWTH TEST — {symbol}"
    )

    print(
        "=" * 78
    )

    print(
        f"Company: "
        f"{result['company']}"
    )

    print(
        f"Latest filing: "
        f"{result['latest_filing_date']}"
    )

    print()

    # --------------------------------------------------------
    # Revenue
    # --------------------------------------------------------

    revenue = result[
        "revenue_yoy"
    ]

    print(
        "REVENUE"
    )

    print(
        "-" * 78
    )

    if revenue["current"]:

        print(
            "Current:  "
            f"{revenue['current']['end']} | "
            f"{format_money(revenue['current']['value'])}"
        )

    if revenue["previous"]:

        print(
            "Year ago: "
            f"{revenue['previous']['end']} | "
            f"{format_money(revenue['previous']['value'])}"
        )

    print(
        f"YoY:      "
        f"{format_percent(revenue['growth'])}"
    )

    # --------------------------------------------------------
    # Net income
    # --------------------------------------------------------

    print()

    net_income = result[
        "net_income_yoy"
    ]

    print(
        "NET INCOME"
    )

    print(
        "-" * 78
    )

    if net_income["current"]:

        print(
            "Current:  "
            f"{net_income['current']['end']} | "
            f"{format_money(net_income['current']['value'])}"
        )

    if net_income["previous"]:

        print(
            "Year ago: "
            f"{net_income['previous']['end']} | "
            f"{format_money(net_income['previous']['value'])}"
        )

    print(
        f"YoY:      "
        f"{format_percent(net_income['growth'])}"
    )

    # --------------------------------------------------------
    # EPS
    # --------------------------------------------------------

    print()

    eps = result[
        "eps_yoy"
    ]

    print(
        "EPS"
    )

    print(
        "-" * 78
    )

    if eps["current"]:

        print(
            "Current:  "
            f"{eps['current']['end']} | "
            f"{format_eps(eps['current']['value'])}"
        )

    if eps["previous"]:

        print(
            "Year ago: "
            f"{eps['previous']['end']} | "
            f"{format_eps(eps['previous']['value'])}"
        )

    print(
        f"YoY:      "
        f"{format_percent(eps['growth'])}"
    )