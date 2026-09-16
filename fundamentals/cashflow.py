from __future__ import annotations

from datetime import datetime

from fundamentals.sec import (
    get_company_facts,
    get_fact_units,
)

from fundamentals.normalizer import (
    get_normalized_income_metrics,
)


# ============================================================
# SEC CONCEPTS
# ============================================================

OPERATING_CASH_FLOW_CONCEPTS = [
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
]

CAPEX_CONCEPTS = [
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsForAdditionsToPropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
]


# ============================================================
# HELPERS
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
            return concept, observations

    return None, []


# ============================================================
# FILTER SEC CASH-FLOW FACTS
# ============================================================

def clean_cashflow_observations(
    observations: list[dict],
) -> list[dict]:
    """
    Keep useful 10-Q / 10-K cash-flow observations.

    SEC cash-flow facts can represent:

    ~90 days  = Q1
    ~180 days = H1 / Q2 YTD
    ~270 days = 9M / Q3 YTD
    ~365 days = FY

    We preserve duration because it is required
    to derive standalone quarters correctly.
    """

    results = []

    for observation in observations:

        if observation.get("form") not in {
            "10-Q",
            "10-K",
        }:
            continue

        if observation.get("val") is None:
            continue

        days = duration_days(
            observation
        )

        if days is None:
            continue

        results.append(
            {
                "start":
                    observation.get("start"),

                "end":
                    observation.get("end"),

                "filed":
                    observation.get("filed"),

                "form":
                    observation.get("form"),

                "fiscal_year":
                    observation.get("fy"),

                "fiscal_period":
                    observation.get("fp"),

                "value":
                    float(
                        observation.get("val")
                    ),

                "accession":
                    observation.get("accn"),

                "duration_days":
                    days,
            }
        )

    return results


# ============================================================
# DEDUPLICATE
# ============================================================

def deduplicate_cashflow(
    observations: list[dict],
) -> list[dict]:
    """
    Preserve earliest filing for the same
    underlying duration/value observation.
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

    return list(
        grouped.values()
    )


# ============================================================
# MATCH YTD OBSERVATION
# ============================================================

def find_observation_for_end(
    observations: list[dict],
    period_end: str,
) -> dict | None:
    """
    Find the most appropriate cash-flow observation
    ending on a particular fiscal quarter date.

    When several observations exist, prefer the one
    with the longest duration because cash-flow
    statements generally provide the cumulative YTD
    amount needed for Q2/Q3 derivation.
    """

    matches = [
        item
        for item in observations
        if item.get("end") == period_end
    ]

    if not matches:
        return None

    matches.sort(
        key=lambda item:
            item.get(
                "duration_days",
                0,
            ),
        reverse=True,
    )

    return matches[0]


# ============================================================
# DERIVE STANDALONE QUARTER
# ============================================================

def derive_quarter_value(
    current_ytd: dict | None,
    previous_ytd: dict | None,
) -> float | None:
    """
    Derive standalone-quarter cash flow.

    Q1:
        Q1 YTD itself is the quarter.

    Q2:
        H1 YTD - Q1 YTD

    Q3:
        9M YTD - H1 YTD
    """

    if current_ytd is None:
        return None

    current_value = float(
        current_ytd["value"]
    )

    current_days = (
        current_ytd.get(
            "duration_days"
        )
    )

    if current_days is None:
        return None

    # Roughly one quarter.
    if 70 <= current_days <= 120:
        return current_value

    if previous_ytd is None:
        return None

    previous_value = float(
        previous_ytd["value"]
    )

    return (
        current_value
        - previous_value
    )


# ============================================================
# FIND PRIOR FISCAL QUARTER
# ============================================================

def find_previous_revenue_quarter(
    revenue_quarters: list[dict],
    current_index: int,
) -> dict | None:
    """
    Revenue quarters are sorted newest first.

    For the current quarter, retrieve the immediately
    preceding normalized fiscal quarter.
    """

    next_index = (
        current_index + 1
    )

    if next_index >= len(
        revenue_quarters
    ):
        return None

    return revenue_quarters[
        next_index
    ]


# ============================================================
# BUILD CASH FLOW FOR A QUARTER
# ============================================================

def build_quarter_cashflow(
    revenue_quarters: list[dict],
    current_index: int,
    cashflow_observations: list[dict],
) -> dict | None:

    if current_index >= len(
        revenue_quarters
    ):
        return None

    revenue_quarter = (
        revenue_quarters[
            current_index
        ]
    )

    period_end = (
        revenue_quarter.get(
            "end"
        )
    )

    current_ytd = (
        find_observation_for_end(
            cashflow_observations,
            period_end,
        )
    )

    if current_ytd is None:
        return None

    current_days = (
        current_ytd.get(
            "duration_days"
        )
    )

    # Q1 doesn't need subtraction.
    if (
        current_days is not None
        and 70 <= current_days <= 120
    ):

        value = (
            derive_quarter_value(
                current_ytd,
                None,
            )
        )

        return {
            "period_end":
                period_end,

            "filed":
                current_ytd.get(
                    "filed"
                ),

            "value":
                value,

            "source":
                "reported_quarter",
        }

    previous_revenue = (
        find_previous_revenue_quarter(
            revenue_quarters,
            current_index,
        )
    )

    if previous_revenue is None:
        return None

    previous_end = (
        previous_revenue.get(
            "end"
        )
    )

    previous_ytd = (
        find_observation_for_end(
            cashflow_observations,
            previous_end,
        )
    )

    if previous_ytd is None:
        return None

    # YTD subtraction is only valid when both
    # observations share the same fiscal start.
    if (
        current_ytd.get("start")
        != previous_ytd.get("start")
    ):
        return None

    value = derive_quarter_value(
        current_ytd,
        previous_ytd,
    )

    return {
        "period_end":
            period_end,

        "filed":
            current_ytd.get(
                "filed"
            ),

        "value":
            value,

        "source":
            "derived_from_ytd",
    }


# ============================================================
# CASH FLOW ANALYSIS
# ============================================================

def analyze_cashflow(
    symbol: str,
) -> dict:

    symbol = (
        symbol
        .strip()
        .upper()
    )

    # --------------------------------------------------------
    # Revenue quarters
    # --------------------------------------------------------

    income = (
        get_normalized_income_metrics(
            symbol
        )
    )

    revenue_quarters = (
        income["revenue"]
    )

    if not revenue_quarters:

        raise RuntimeError(
            f"No normalized revenue "
            f"quarters found for {symbol}"
        )

    # --------------------------------------------------------
    # SEC company facts
    # --------------------------------------------------------

    company = get_company_facts(
        symbol
    )

    # --------------------------------------------------------
    # Operating cash flow
    # --------------------------------------------------------

    (
        ocf_concept,
        ocf_raw,
    ) = get_first_available_concept(
        company,
        OPERATING_CASH_FLOW_CONCEPTS,
    )

    ocf_clean = (
        deduplicate_cashflow(
            clean_cashflow_observations(
                ocf_raw
            )
        )
    )

    # --------------------------------------------------------
    # CapEx
    # --------------------------------------------------------

    (
        capex_concept,
        capex_raw,
    ) = get_first_available_concept(
        company,
        CAPEX_CONCEPTS,
    )

    capex_clean = (
        deduplicate_cashflow(
            clean_cashflow_observations(
                capex_raw
            )
        )
    )

    # --------------------------------------------------------
    # Current quarter
    # --------------------------------------------------------

    current_revenue = (
        revenue_quarters[0]
    )

    current_ocf = (
        build_quarter_cashflow(
            revenue_quarters,
            0,
            ocf_clean,
        )
    )

    current_capex = (
        build_quarter_cashflow(
            revenue_quarters,
            0,
            capex_clean,
        )
    )

    ocf_value = (
        current_ocf.get("value")
        if current_ocf
        else None
    )

    capex_value = (
        current_capex.get("value")
        if current_capex
        else None
    )

    # SEC PaymentsToAcquire... concepts generally
    # represent positive cash outflows.
    #
    # Therefore:
    #
    # FCF = Operating Cash Flow - CapEx

    if (
        ocf_value is not None
        and capex_value is not None
    ):

        free_cash_flow = (
            float(ocf_value)
            - float(capex_value)
        )

    else:
        free_cash_flow = None

    revenue_value = (
        current_revenue.get(
            "value"
        )
    )

    fcf_margin = safe_divide(
        free_cash_flow,
        revenue_value,
    )

    return {
        "symbol":
            symbol,

        "company":
            income["company"],

        "period_end":
            current_revenue.get(
                "end"
            ),

        "filing_date":
            current_revenue.get(
                "filed"
            ),

        "ocf_concept":
            ocf_concept,

        "capex_concept":
            capex_concept,

        "revenue":
            revenue_value,

        "operating_cash_flow":
            ocf_value,

        "operating_cash_flow_source":
            (
                current_ocf.get(
                    "source"
                )
                if current_ocf
                else None
            ),

        "capex":
            capex_value,

        "capex_source":
            (
                current_capex.get(
                    "source"
                )
                if current_capex
                else None
            ),

        "free_cash_flow":
            free_cash_flow,

        "fcf_margin":
            fcf_margin,
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
        analyze_cashflow(
            symbol
        )
    )

    print()

    print(
        "=" * 78
    )

    print(
        f"GAINZ CASH GENERATION TEST — {symbol}"
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
        f"OCF concept: "
        f"{result['ocf_concept']}"
    )

    print(
        f"CapEx concept: "
        f"{result['capex_concept']}"
    )

    print()

    print(
        "CASH GENERATION"
    )

    print(
        "-" * 78
    )

    print(
        f"Revenue:             "
        f"{format_money(result['revenue'])}"
    )

    print(
        f"Operating cash flow: "
        f"{format_money(result['operating_cash_flow'])}"
    )

    print(
        f"OCF source:          "
        f"{result['operating_cash_flow_source']}"
    )

    print(
        f"CapEx:               "
        f"{format_money(result['capex'])}"
    )

    print(
        f"CapEx source:        "
        f"{result['capex_source']}"
    )

    print(
        f"Free cash flow:      "
        f"{format_money(result['free_cash_flow'])}"
    )

    print(
        f"FCF margin:          "
        f"{format_percent(result['fcf_margin'])}"
    )