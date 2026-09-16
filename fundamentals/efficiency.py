from __future__ import annotations

from datetime import datetime

from fundamentals.sec import (
    get_company_facts,
    get_fact_units,
)

from fundamentals.normalizer import (
    get_normalized_income_metrics,
)

from fundamentals.financial_health import (
    clean_instant_observations,
    find_instant_fact,
)


# ============================================================
# SEC CONCEPTS
# ============================================================

NET_INCOME_CONCEPTS = [
    "NetIncomeLoss",
    "ProfitLoss",
]

EQUITY_CONCEPTS = [
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
]

ASSETS_CONCEPTS = [
    "Assets",
]


# ============================================================
# BASIC HELPERS
# ============================================================

def parse_date(
    value: str | None,
) -> datetime | None:

    if not value:
        return None

    try:
        return datetime.strptime(
            value,
            "%Y-%m-%d",
        )

    except ValueError:
        return None


def duration_days(
    observation: dict,
) -> int | None:

    start = parse_date(
        observation.get("start")
    )

    end = parse_date(
        observation.get("end")
    )

    if not start or not end:
        return None

    return (
        end - start
    ).days + 1


def safe_divide(
    numerator,
    denominator,
) -> float | None:

    if numerator is None:
        return None

    if denominator is None:
        return None

    numerator = float(numerator)
    denominator = float(denominator)

    if denominator == 0:
        return None

    return numerator / denominator


# ============================================================
# CONCEPT FINDER
# ============================================================

def get_first_available_concept(
    company_facts: dict,
    concepts: list[str],
    unit: str = "USD",
) -> tuple[str | None, list[dict]]:

    for concept in concepts:

        observations = get_fact_units(
            company_facts,
            concept,
            unit=unit,
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
# ANNUAL NET INCOME
# ============================================================

def clean_annual_observations(
    observations: list[dict],
) -> list[dict]:
    """
    Extract approximately full-year observations
    from 10-K filings.

    We use duration rather than relying entirely on
    SEC fiscal-period labels.
    """

    results = []

    for observation in observations:

        if observation.get("form") != "10-K":
            continue

        if observation.get("val") is None:
            continue

        days = duration_days(
            observation
        )

        if days is None:
            continue

        # Allow 52/53-week fiscal years.
        if not (
            330 <= days <= 400
        ):
            continue

        results.append(
            {
                "start":
                    observation.get("start"),

                "end":
                    observation.get("end"),

                "filed":
                    observation.get("filed"),

                "value":
                    float(
                        observation.get("val")
                    ),

                "duration_days":
                    days,

                "accession":
                    observation.get("accn"),
            }
        )

    return results


def deduplicate_annual(
    observations: list[dict],
) -> list[dict]:
    """
    Keep the earliest filing for the same
    annual period/value.
    """

    grouped = {}

    for observation in observations:

        key = (
            observation.get("start"),
            observation.get("end"),
            observation.get("value"),
        )

        existing = grouped.get(
            key
        )

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
        key=lambda item:
            item.get("end")
            or "",
        reverse=True,
    )

    return results


# ============================================================
# QUARTER LOOKUP
# ============================================================

def quarters_inside_year(
    quarterly_observations: list[dict],
    annual_observation: dict,
) -> list[dict]:
    """
    Find standalone quarters that belong inside
    an annual reporting period.
    """

    annual_start = parse_date(
        annual_observation.get("start")
    )

    annual_end = parse_date(
        annual_observation.get("end")
    )

    if (
        annual_start is None
        or annual_end is None
    ):
        return []

    matches = []

    for quarter in quarterly_observations:

        quarter_start = parse_date(
            quarter.get("start")
        )

        quarter_end = parse_date(
            quarter.get("end")
        )

        if (
            quarter_start is None
            or quarter_end is None
        ):
            continue

        if (
            quarter_start >= annual_start
            and quarter_end <= annual_end
        ):

            matches.append(
                quarter
            )

    matches.sort(
        key=lambda item:
            item.get("end")
            or ""
    )

    return matches


# ============================================================
# DERIVE Q4
# ============================================================

def derive_q4(
    annual_observation: dict,
    quarterly_observations: list[dict],
) -> dict | None:
    """
    Derive Q4:

        Q4 =
        Full Year
        - Q1
        - Q2
        - Q3
    """

    quarters = quarters_inside_year(
        quarterly_observations,
        annual_observation,
    )

    # We expect the three reported 10-Q quarters.
    #
    # There can occasionally be duplicates or unusual
    # reporting structures, so select one quarter for
    # each unique end date.

    unique = {}

    for quarter in quarters:

        end = quarter.get(
            "end"
        )

        if end:
            unique[end] = quarter

    quarters = list(
        unique.values()
    )

    quarters.sort(
        key=lambda item:
            item.get("end")
            or ""
    )

    if len(quarters) != 3:

        return None

    annual_value = float(
        annual_observation[
            "value"
        ]
    )

    first_three_total = sum(
        float(
            quarter["value"]
        )
        for quarter in quarters
    )

    q4_value = (
        annual_value
        - first_three_total
    )

    return {
        "start":
            None,

        "end":
            annual_observation.get(
                "end"
            ),

        "filed":
            annual_observation.get(
                "filed"
            ),

        "value":
            q4_value,

        "source":
            "derived_from_10k",

        "annual_value":
            annual_value,

        "q1_q2_q3_total":
            first_three_total,
    }


# ============================================================
# BUILD COMPLETE QUARTER SERIES
# ============================================================

def build_complete_net_income_quarters(
    quarterly_observations: list[dict],
    annual_observations: list[dict],
) -> list[dict]:
    """
    Combine reported Q1-Q3 standalone quarters with
    derived Q4 observations.
    """

    results = []

    for quarter in quarterly_observations:

        item = dict(
            quarter
        )

        item["source"] = (
            "reported_10q"
        )

        results.append(
            item
        )

    for annual in annual_observations:

        q4 = derive_q4(
            annual,
            quarterly_observations,
        )

        if q4 is not None:

            results.append(
                q4
            )

    # Deduplicate by period end.
    #
    # Prefer reported observations if both reported
    # and derived observations somehow exist.

    grouped = {}

    for observation in results:

        end = observation.get(
            "end"
        )

        if not end:
            continue

        existing = grouped.get(
            end
        )

        if existing is None:

            grouped[end] = observation
            continue

        if (
            existing.get("source")
            == "derived_from_10k"
            and observation.get("source")
            == "reported_10q"
        ):

            grouped[end] = observation

    results = list(
        grouped.values()
    )

    results.sort(
        key=lambda item:
            item.get("end")
            or "",
        reverse=True,
    )

    return results


# ============================================================
# TTM NET INCOME
# ============================================================

def calculate_ttm_net_income(
    quarters: list[dict],
    latest_period_end: str,
) -> dict:
    """
    Calculate trailing-12-month net income using
    the four latest completed fiscal quarters up to
    the requested period end.
    """

    eligible = [
        quarter
        for quarter in quarters
        if (
            quarter.get("end")
            and quarter["end"]
            <= latest_period_end
        )
    ]

    eligible.sort(
        key=lambda item:
            item.get("end")
            or "",
        reverse=True,
    )

    latest_four = eligible[
        :4
    ]

    if len(latest_four) < 4:

        return {
            "value": None,
            "quarters": latest_four,
        }

    value = sum(
        float(
            quarter["value"]
        )
        for quarter in latest_four
    )

    return {
        "value":
            value,

        "quarters":
            latest_four,
    }


# ============================================================
# BALANCE-SHEET SERIES
# ============================================================

def get_instant_series(
    company_facts: dict,
    concepts: list[str],
) -> tuple[str | None, list[dict]]:

    for concept in concepts:

        raw = get_fact_units(
            company_facts,
            concept,
            unit="USD",
        )

        cleaned = (
            clean_instant_observations(
                raw
            )
        )

        if cleaned:

            return (
                concept,
                cleaned,
            )

    return (
        None,
        [],
    )


# ============================================================
# PRIOR-YEAR BALANCE
# ============================================================

def find_prior_year_fact(
    observations: list[dict],
    current_period_end: str,
    tolerance_days: int = 20,
) -> dict | None:

    current_date = parse_date(
        current_period_end
    )

    if current_date is None:
        return None

    candidates = []

    # First collapse repeated historical SEC facts
    # to their earliest filing for each period end.

    unique_ends = {}

    for observation in observations:

        end = observation.get(
            "end"
        )

        if not end:
            continue

        existing = unique_ends.get(
            end
        )

        if existing is None:

            unique_ends[end] = observation
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

            unique_ends[end] = observation

    for observation in unique_ends.values():

        candidate_date = parse_date(
            observation.get("end")
        )

        if candidate_date is None:
            continue

        difference = (
            current_date
            - candidate_date
        ).days

        distance = abs(
            difference - 365
        )

        if distance <= tolerance_days:

            candidates.append(
                (
                    distance,
                    observation,
                )
            )

    if not candidates:

        return None

    candidates.sort(
        key=lambda item:
            item[0]
    )

    return candidates[0][1]


# ============================================================
# EFFICIENCY ANALYSIS
# ============================================================

def analyze_efficiency(
    symbol: str,
) -> dict:

    symbol = (
        symbol
        .strip()
        .upper()
    )

    # --------------------------------------------------------
    # Normalized income data
    # --------------------------------------------------------

    income = (
        get_normalized_income_metrics(
            symbol
        )
    )

    revenue_quarters = (
        income["revenue"]
    )

    net_income_quarters = (
        income["net_income"]
    )

    if not revenue_quarters:

        raise RuntimeError(
            f"No normalized revenue "
            f"quarters found for {symbol}"
        )

    latest_period_end = (
        revenue_quarters[0][
            "end"
        ]
    )

    # --------------------------------------------------------
    # SEC facts
    # --------------------------------------------------------

    company = get_company_facts(
        symbol
    )

    # --------------------------------------------------------
    # Annual net income
    # --------------------------------------------------------

    (
        net_income_concept,
        raw_net_income,
    ) = get_first_available_concept(
        company,
        NET_INCOME_CONCEPTS,
    )

    annual_net_income = (
        deduplicate_annual(
            clean_annual_observations(
                raw_net_income
            )
        )
    )

    # --------------------------------------------------------
    # Build Q1/Q2/Q3 + derived Q4 series
    # --------------------------------------------------------

    complete_quarters = (
        build_complete_net_income_quarters(
            net_income_quarters,
            annual_net_income,
        )
    )

    # --------------------------------------------------------
    # TTM net income
    # --------------------------------------------------------

    ttm = (
        calculate_ttm_net_income(
            complete_quarters,
            latest_period_end,
        )
    )

    ttm_net_income = (
        ttm["value"]
    )

    # --------------------------------------------------------
    # Equity
    # --------------------------------------------------------

    (
        equity_concept,
        equity_series,
    ) = get_instant_series(
        company,
        EQUITY_CONCEPTS,
    )

    current_equity = (
        find_instant_fact(
            equity_series,
            latest_period_end,
        )
    )

    prior_equity = (
        find_prior_year_fact(
            equity_series,
            latest_period_end,
        )
    )

    # --------------------------------------------------------
    # Assets
    # --------------------------------------------------------

    (
        assets_concept,
        assets_series,
    ) = get_instant_series(
        company,
        ASSETS_CONCEPTS,
    )

    current_assets = (
        find_instant_fact(
            assets_series,
            latest_period_end,
        )
    )

    prior_assets = (
        find_prior_year_fact(
            assets_series,
            latest_period_end,
        )
    )

    # --------------------------------------------------------
    # Average balances
    # --------------------------------------------------------

    if (
        current_equity
        and prior_equity
    ):

        average_equity = (
            float(
                current_equity["value"]
            )
            +
            float(
                prior_equity["value"]
            )
        ) / 2

    else:

        average_equity = None

    if (
        current_assets
        and prior_assets
    ):

        average_assets = (
            float(
                current_assets["value"]
            )
            +
            float(
                prior_assets["value"]
            )
        ) / 2

    else:

        average_assets = None

    # --------------------------------------------------------
    # ROE / ROA
    # --------------------------------------------------------

    roe = safe_divide(
        ttm_net_income,
        average_equity,
    )

    roa = safe_divide(
        ttm_net_income,
        average_assets,
    )

    # --------------------------------------------------------
    # Filing date
    # --------------------------------------------------------

    filing_dates = []

    for quarter in ttm[
        "quarters"
    ]:

        if quarter.get(
            "filed"
        ):

            filing_dates.append(
                quarter["filed"]
            )

    if current_equity and current_equity.get(
        "filed"
    ):

        filing_dates.append(
            current_equity["filed"]
        )

    if current_assets and current_assets.get(
        "filed"
    ):

        filing_dates.append(
            current_assets["filed"]
        )

    filing_date = (
        max(filing_dates)
        if filing_dates
        else None
    )

    # --------------------------------------------------------
    # Return
    # --------------------------------------------------------

    return {
        "symbol":
            symbol,

        "company":
            income["company"],

        "period_end":
            latest_period_end,

        "filing_date":
            filing_date,

        "net_income_concept":
            net_income_concept,

        "ttm_net_income":
            ttm_net_income,

        "ttm_quarters":
            ttm["quarters"],

        "equity_concept":
            equity_concept,

        "current_equity":
            (
                current_equity.get(
                    "value"
                )
                if current_equity
                else None
            ),

        "prior_equity":
            (
                prior_equity.get(
                    "value"
                )
                if prior_equity
                else None
            ),

        "average_equity":
            average_equity,

        "assets_concept":
            assets_concept,

        "current_assets":
            (
                current_assets.get(
                    "value"
                )
                if current_assets
                else None
            ),

        "prior_assets":
            (
                prior_assets.get(
                    "value"
                )
                if prior_assets
                else None
            ),

        "average_assets":
            average_assets,

        "roe":
            roe,

        "roa":
            roa,
    }


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

    return (
        f"${value:,.0f}"
    )


def format_percent(
    value,
) -> str:

    if value is None:
        return "N/A"

    return (
        f"{float(value) * 100:.1f}%"
    )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    symbol = "AMD"

    result = (
        analyze_efficiency(
            symbol
        )
    )

    print()

    print(
        "=" * 78
    )

    print(
        f"GAINZ EFFICIENCY TEST — {symbol}"
    )

    print(
        "=" * 78
    )

    print(
        f"Company: "
        f"{result['company']}"
    )

    print(
        f"Period end: "
        f"{result['period_end']}"
    )

    print(
        f"Filed: "
        f"{result['filing_date']}"
    )

    print()

    print(
        "TTM NET INCOME"
    )

    print(
        "-" * 78
    )

    print(
        f"TTM Net Income: "
        f"{format_money(result['ttm_net_income'])}"
    )

    print()

    for quarter in result[
        "ttm_quarters"
    ]:

        print(
            f"{quarter.get('end')} | "
            f"{format_money(quarter.get('value'))} | "
            f"{quarter.get('source')}"
        )

    print()

    print(
        "AVERAGE BALANCE SHEET"
    )

    print(
        "-" * 78
    )

    print(
        f"Current equity: "
        f"{format_money(result['current_equity'])}"
    )

    print(
        f"Prior equity:   "
        f"{format_money(result['prior_equity'])}"
    )

    print(
        f"Average equity: "
        f"{format_money(result['average_equity'])}"
    )

    print()

    print(
        f"Current assets: "
        f"{format_money(result['current_assets'])}"
    )

    print(
        f"Prior assets:   "
        f"{format_money(result['prior_assets'])}"
    )

    print(
        f"Average assets: "
        f"{format_money(result['average_assets'])}"
    )

    print()

    print(
        "EFFICIENCY"
    )

    print(
        "-" * 78
    )

    print(
        f"ROE: "
        f"{format_percent(result['roe'])}"
    )

    print(
        f"ROA: "
        f"{format_percent(result['roa'])}"
    )

    print()

    print(
        "SEC CONCEPTS"
    )

    print(
        "-" * 78
    )

    print(
        f"Net income: "
        f"{result['net_income_concept']}"
    )

    print(
        f"Equity:     "
        f"{result['equity_concept']}"
    )

    print(
        f"Assets:     "
        f"{result['assets_concept']}"
    )