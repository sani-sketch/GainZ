from __future__ import annotations

from fundamentals.sec import (
    get_company_facts,
)

from fundamentals.normalizer import (
    get_normalized_income_metrics,
    get_first_available_concept,
    extract_standalone_quarters,
    find_year_ago_quarter,
)


# ============================================================
# SEC CONCEPTS
# ============================================================

GROSS_PROFIT_CONCEPTS = [
    "GrossProfit",
]

OPERATING_INCOME_CONCEPTS = [
    "OperatingIncomeLoss",
]


# ============================================================
# BASIC HELPERS
# ============================================================

def safe_divide(
    numerator,
    denominator,
) -> float | None:
    """
    Safely divide two values.
    """

    if numerator is None:
        return None

    if denominator is None:
        return None

    numerator = float(numerator)
    denominator = float(denominator)

    if denominator == 0:
        return None

    return numerator / denominator


def find_matching_period(
    observations: list[dict],
    target: dict | None,
) -> dict | None:
    """
    Find an observation matching the target
    quarter's start/end dates.

    This is safer than assuming all SEC metric
    arrays have exactly the same ordering.
    """

    if target is None:
        return None

    target_start = target.get("start")
    target_end = target.get("end")

    for observation in observations:

        if (
            observation.get("start") == target_start
            and observation.get("end") == target_end
        ):
            return observation

    # Fallback to period end if start dates differ
    # slightly between reported concepts.

    for observation in observations:

        if (
            observation.get("end")
            == target_end
        ):
            return observation

    return None


# ============================================================
# MARGIN CALCULATION
# ============================================================

def calculate_margin(
    numerator_observation: dict | None,
    revenue_observation: dict | None,
) -> float | None:
    """
    Calculate a profitability margin.

    Example:

        Gross Margin =
        Gross Profit / Revenue
    """

    if numerator_observation is None:
        return None

    if revenue_observation is None:
        return None

    return safe_divide(
        numerator_observation.get(
            "value"
        ),
        revenue_observation.get(
            "value"
        ),
    )


# ============================================================
# PROFITABILITY ANALYSIS
# ============================================================

def analyze_profitability(
    symbol: str,
) -> dict:
    """
    Calculate current and year-ago:

    - Gross margin
    - Operating margin
    - Net margin

    Also calculate margin changes in
    percentage points.
    """

    symbol = (
        symbol
        .strip()
        .upper()
    )

    # --------------------------------------------------------
    # Existing normalized metrics
    # --------------------------------------------------------

    income_metrics = (
        get_normalized_income_metrics(
            symbol
        )
    )

    revenue_quarters = (
        income_metrics["revenue"]
    )

    net_income_quarters = (
        income_metrics["net_income"]
    )

    if not revenue_quarters:

        raise RuntimeError(
            f"No normalized revenue "
            f"quarters found for {symbol}"
        )

    # --------------------------------------------------------
    # Determine current + year-ago quarter
    # --------------------------------------------------------

    current_revenue = (
        revenue_quarters[0]
    )

    previous_revenue = (
        find_year_ago_quarter(
            revenue_quarters,
            current_revenue,
        )
    )

    # --------------------------------------------------------
    # Fetch company facts
    # --------------------------------------------------------

    company = get_company_facts(
        symbol
    )

    # --------------------------------------------------------
    # Gross profit
    # --------------------------------------------------------

    (
        gross_profit_concept,
        gross_profit_raw,
    ) = get_first_available_concept(
        company,
        GROSS_PROFIT_CONCEPTS,
        "USD",
    )

    gross_profit_quarters = (
        extract_standalone_quarters(
            gross_profit_raw
        )
    )

    # --------------------------------------------------------
    # Operating income
    # --------------------------------------------------------

    (
        operating_income_concept,
        operating_income_raw,
    ) = get_first_available_concept(
        company,
        OPERATING_INCOME_CONCEPTS,
        "USD",
    )

    operating_income_quarters = (
        extract_standalone_quarters(
            operating_income_raw
        )
    )

    # --------------------------------------------------------
    # Match current quarter
    # --------------------------------------------------------

    current_gross_profit = (
        find_matching_period(
            gross_profit_quarters,
            current_revenue,
        )
    )

    current_operating_income = (
        find_matching_period(
            operating_income_quarters,
            current_revenue,
        )
    )

    current_net_income = (
        find_matching_period(
            net_income_quarters,
            current_revenue,
        )
    )

    # --------------------------------------------------------
    # Match year-ago quarter
    # --------------------------------------------------------

    previous_gross_profit = (
        find_matching_period(
            gross_profit_quarters,
            previous_revenue,
        )
    )

    previous_operating_income = (
        find_matching_period(
            operating_income_quarters,
            previous_revenue,
        )
    )

    previous_net_income = (
        find_matching_period(
            net_income_quarters,
            previous_revenue,
        )
    )

    # --------------------------------------------------------
    # Current margins
    # --------------------------------------------------------

    current_gross_margin = (
        calculate_margin(
            current_gross_profit,
            current_revenue,
        )
    )

    current_operating_margin = (
        calculate_margin(
            current_operating_income,
            current_revenue,
        )
    )

    current_net_margin = (
        calculate_margin(
            current_net_income,
            current_revenue,
        )
    )

    # --------------------------------------------------------
    # Previous margins
    # --------------------------------------------------------

    previous_gross_margin = (
        calculate_margin(
            previous_gross_profit,
            previous_revenue,
        )
    )

    previous_operating_margin = (
        calculate_margin(
            previous_operating_income,
            previous_revenue,
        )
    )

    previous_net_margin = (
        calculate_margin(
            previous_net_income,
            previous_revenue,
        )
    )

    # --------------------------------------------------------
    # Margin changes
    #
    # Values are decimals.
    #
    # Example:
    # current = 0.25
    # previous = 0.20
    #
    # change = 0.05
    #        = +5 percentage points
    # --------------------------------------------------------

    def margin_change(
        current,
        previous,
    ) -> float | None:

        if current is None:
            return None

        if previous is None:
            return None

        return (
            float(current)
            - float(previous)
        )

    # --------------------------------------------------------
    # Result
    # --------------------------------------------------------

    return {
        "symbol": symbol,

        "company":
            income_metrics["company"],

        "filing_date":
            current_revenue.get(
                "filed"
            ),

        "period_end":
            current_revenue.get(
                "end"
            ),

        "year_ago_period_end":
            (
                previous_revenue.get(
                    "end"
                )
                if previous_revenue
                else None
            ),

        "gross_profit_concept":
            gross_profit_concept,

        "operating_income_concept":
            operating_income_concept,

        "current": {
            "revenue":
                current_revenue.get(
                    "value"
                ),

            "gross_profit":
                (
                    current_gross_profit.get(
                        "value"
                    )
                    if current_gross_profit
                    else None
                ),

            "operating_income":
                (
                    current_operating_income.get(
                        "value"
                    )
                    if current_operating_income
                    else None
                ),

            "net_income":
                (
                    current_net_income.get(
                        "value"
                    )
                    if current_net_income
                    else None
                ),

            "gross_margin":
                current_gross_margin,

            "operating_margin":
                current_operating_margin,

            "net_margin":
                current_net_margin,
        },

        "year_ago": {
            "revenue":
                (
                    previous_revenue.get(
                        "value"
                    )
                    if previous_revenue
                    else None
                ),

            "gross_profit":
                (
                    previous_gross_profit.get(
                        "value"
                    )
                    if previous_gross_profit
                    else None
                ),

            "operating_income":
                (
                    previous_operating_income.get(
                        "value"
                    )
                    if previous_operating_income
                    else None
                ),

            "net_income":
                (
                    previous_net_income.get(
                        "value"
                    )
                    if previous_net_income
                    else None
                ),

            "gross_margin":
                previous_gross_margin,

            "operating_margin":
                previous_operating_margin,

            "net_margin":
                previous_net_margin,
        },

        "change": {
            "gross_margin":
                margin_change(
                    current_gross_margin,
                    previous_gross_margin,
                ),

            "operating_margin":
                margin_change(
                    current_operating_margin,
                    previous_operating_margin,
                ),

            "net_margin":
                margin_change(
                    current_net_margin,
                    previous_net_margin,
                ),
        },
    }


# ============================================================
# DISPLAY HELPERS
# ============================================================

def format_percent(
    value,
) -> str:
    """
    Format decimal as percentage.
    """

    if value is None:
        return "N/A"

    return (
        f"{float(value) * 100:.1f}%"
    )


def format_percentage_points(
    value,
) -> str:
    """
    Format decimal difference as
    percentage-point change.
    """

    if value is None:
        return "N/A"

    return (
        f"{float(value) * 100:+.1f} pp"
    )


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


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    symbol = "AMD"

    result = (
        analyze_profitability(
            symbol
        )
    )

    print()

    print(
        "=" * 78
    )

    print(
        f"GAINZ PROFITABILITY TEST — {symbol}"
    )

    print(
        "=" * 78
    )

    print(
        f"Company: "
        f"{result['company']}"
    )

    print(
        f"Current period: "
        f"{result['period_end']}"
    )

    print(
        f"Year-ago period: "
        f"{result['year_ago_period_end']}"
    )

    print(
        f"Filed: "
        f"{result['filing_date']}"
    )

    print()

    print(
        f"Gross profit concept: "
        f"{result['gross_profit_concept']}"
    )

    print(
        f"Operating income concept: "
        f"{result['operating_income_concept']}"
    )

    # --------------------------------------------------------
    # Current
    # --------------------------------------------------------

    current = result[
        "current"
    ]

    previous = result[
        "year_ago"
    ]

    change = result[
        "change"
    ]

    print()
    print(
        "CURRENT QUARTER"
    )

    print(
        "-" * 78
    )

    print(
        f"Revenue:          "
        f"{format_money(current['revenue'])}"
    )

    print(
        f"Gross profit:     "
        f"{format_money(current['gross_profit'])}"
    )

    print(
        f"Operating income: "
        f"{format_money(current['operating_income'])}"
    )

    print(
        f"Net income:       "
        f"{format_money(current['net_income'])}"
    )

    print()

    print(
        f"Gross margin:     "
        f"{format_percent(current['gross_margin'])}"
    )

    print(
        f"Operating margin: "
        f"{format_percent(current['operating_margin'])}"
    )

    print(
        f"Net margin:       "
        f"{format_percent(current['net_margin'])}"
    )

    # --------------------------------------------------------
    # Previous
    # --------------------------------------------------------

    print()
    print(
        "YEAR-AGO QUARTER"
    )

    print(
        "-" * 78
    )

    print(
        f"Revenue:          "
        f"{format_money(previous['revenue'])}"
    )

    print(
        f"Gross profit:     "
        f"{format_money(previous['gross_profit'])}"
    )

    print(
        f"Operating income: "
        f"{format_money(previous['operating_income'])}"
    )

    print(
        f"Net income:       "
        f"{format_money(previous['net_income'])}"
    )

    print()

    print(
        f"Gross margin:     "
        f"{format_percent(previous['gross_margin'])}"
    )

    print(
        f"Operating margin: "
        f"{format_percent(previous['operating_margin'])}"
    )

    print(
        f"Net margin:       "
        f"{format_percent(previous['net_margin'])}"
    )

    # --------------------------------------------------------
    # Changes
    # --------------------------------------------------------

    print()
    print(
        "YOY MARGIN CHANGE"
    )

    print(
        "-" * 78
    )

    print(
        f"Gross margin:     "
        f"{format_percentage_points(change['gross_margin'])}"
    )

    print(
        f"Operating margin: "
        f"{format_percentage_points(change['operating_margin'])}"
    )

    print(
        f"Net margin:       "
        f"{format_percentage_points(change['net_margin'])}"
    )