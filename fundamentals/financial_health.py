from __future__ import annotations

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

CASH_CONCEPTS = [
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
]

SHORT_TERM_DEBT_CONCEPTS = [
    "ShortTermBorrowings",
    "ShortTermDebtCurrent",
    "LongTermDebtCurrent",
]

LONG_TERM_DEBT_CONCEPTS = [
    "LongTermDebtNoncurrent",
    "LongTermDebt",
]

TOTAL_DEBT_CONCEPTS = [
    "LongTermDebtAndFinanceLeaseObligationsCurrent",
    "LongTermDebtAndFinanceLeaseObligations",
]

EQUITY_CONCEPTS = [
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
]

ASSETS_CONCEPTS = [
    "Assets",
]


# ============================================================
# GENERIC HELPERS
# ============================================================

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


def get_first_available_concept(
    company_facts: dict,
    concepts: list[str],
    unit: str = "USD",
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

            return (
                concept,
                observations,
            )

    return (
        None,
        [],
    )


# ============================================================
# INSTANT FACT CLEANING
# ============================================================

def clean_instant_observations(
    observations: list[dict],
) -> list[dict]:
    """
    Keep balance-sheet observations from
    10-Q and 10-K filings.

    Instant facts have an 'end' date but normally
    no meaningful 'start' date.
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

        if not observation.get("end"):
            continue

        results.append(
            {
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
            }
        )

    return results


# ============================================================
# FIND POINT-IN-TIME FACT
# ============================================================

def find_instant_fact(
    observations: list[dict],
    period_end: str,
) -> dict | None:
    """
    Find a balance-sheet fact for a particular
    quarter-end date.

    SEC may repeat the same historical balance-sheet
    value in later filings.

    We preserve the earliest filing containing the
    value for that period end.
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
            item.get("filed")
            or "9999-12-31"
    )

    return matches[0]


# ============================================================
# GET ONE BALANCE-SHEET METRIC
# ============================================================

def get_balance_metric(
    company_facts: dict,
    concepts: list[str],
    period_end: str,
) -> dict:
    """
    Find the first concept that has a usable
    observation for the requested period end.
    """

    for concept in concepts:

        observations = get_fact_units(
            company_facts,
            concept,
            unit="USD",
        )

        cleaned = (
            clean_instant_observations(
                observations
            )
        )

        fact = find_instant_fact(
            cleaned,
            period_end,
        )

        if fact is not None:

            return {
                "concept": concept,
                "fact": fact,
            }

    return {
        "concept": None,
        "fact": None,
    }


# ============================================================
# VALUE HELPER
# ============================================================

def fact_value(
    result: dict,
) -> float | None:

    fact = result.get(
        "fact"
    )

    if fact is None:
        return None

    return fact.get(
        "value"
    )


# ============================================================
# FINANCIAL HEALTH
# ============================================================

def analyze_financial_health(
    symbol: str,
) -> dict:
    """
    Analyze latest balance-sheet financial health.

    Metrics:

    - Cash
    - Short-term debt
    - Long-term debt
    - Total debt
    - Net debt / net cash
    - Equity
    - Assets
    - Debt-to-equity
    """

    symbol = (
        symbol
        .strip()
        .upper()
    )

    # --------------------------------------------------------
    # Use normalized revenue to determine the
    # latest valid fiscal quarter.
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

    current_quarter = (
        revenue_quarters[0]
    )

    period_end = (
        current_quarter.get(
            "end"
        )
    )

    # --------------------------------------------------------
    # SEC facts
    # --------------------------------------------------------

    company = get_company_facts(
        symbol
    )

    # --------------------------------------------------------
    # Cash
    # --------------------------------------------------------

    cash_result = (
        get_balance_metric(
            company,
            CASH_CONCEPTS,
            period_end,
        )
    )

    # --------------------------------------------------------
    # Short-term debt
    # --------------------------------------------------------

    short_debt_result = (
        get_balance_metric(
            company,
            SHORT_TERM_DEBT_CONCEPTS,
            period_end,
        )
    )

    # --------------------------------------------------------
    # Long-term debt
    # --------------------------------------------------------

    long_debt_result = (
        get_balance_metric(
            company,
            LONG_TERM_DEBT_CONCEPTS,
            period_end,
        )
    )

    # --------------------------------------------------------
    # Optional directly reported debt
    # --------------------------------------------------------

    total_debt_result = (
        get_balance_metric(
            company,
            TOTAL_DEBT_CONCEPTS,
            period_end,
        )
    )

    # --------------------------------------------------------
    # Equity
    # --------------------------------------------------------

    equity_result = (
        get_balance_metric(
            company,
            EQUITY_CONCEPTS,
            period_end,
        )
    )

    # --------------------------------------------------------
    # Assets
    # --------------------------------------------------------

    assets_result = (
        get_balance_metric(
            company,
            ASSETS_CONCEPTS,
            period_end,
        )
    )

    # --------------------------------------------------------
    # Values
    # --------------------------------------------------------

    cash = fact_value(
        cash_result
    )

    short_term_debt = fact_value(
        short_debt_result
    )

    long_term_debt = fact_value(
        long_debt_result
    )

    directly_reported_debt = (
        fact_value(
            total_debt_result
        )
    )

    equity = fact_value(
        equity_result
    )

    assets = fact_value(
        assets_result
    )

    # --------------------------------------------------------
    # Total debt
    # --------------------------------------------------------

    debt_source = None

    if directly_reported_debt is not None:

        total_debt = float(
            directly_reported_debt
        )

        debt_source = (
            "direct_sec_concept"
        )

    elif (
        short_term_debt is not None
        or long_term_debt is not None
    ):

        total_debt = (
            float(
                short_term_debt
                or 0
            )
            +
            float(
                long_term_debt
                or 0
            )
        )

        debt_source = (
            "short_plus_long_term"
        )

    else:

        total_debt = None

    # --------------------------------------------------------
    # Net debt / net cash
    # --------------------------------------------------------

    if (
        total_debt is not None
        and cash is not None
    ):

        net_debt = (
            float(total_debt)
            - float(cash)
        )

        net_cash = (
            float(cash)
            - float(total_debt)
        )

    else:

        net_debt = None
        net_cash = None

    # --------------------------------------------------------
    # Debt / Equity
    # --------------------------------------------------------

    debt_to_equity = (
        safe_divide(
            total_debt,
            equity,
        )
    )

    # --------------------------------------------------------
    # Filing dates
    # --------------------------------------------------------

    filing_dates = []

    for result in [
        cash_result,
        short_debt_result,
        long_debt_result,
        total_debt_result,
        equity_result,
        assets_result,
    ]:

        fact = result.get(
            "fact"
        )

        if (
            fact
            and fact.get("filed")
        ):

            filing_dates.append(
                fact["filed"]
            )

    filing_date = (
        max(filing_dates)
        if filing_dates
        else current_quarter.get(
            "filed"
        )
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
            period_end,

        "filing_date":
            filing_date,

        "cash":
            cash,

        "cash_concept":
            cash_result["concept"],

        "short_term_debt":
            short_term_debt,

        "short_term_debt_concept":
            short_debt_result[
                "concept"
            ],

        "long_term_debt":
            long_term_debt,

        "long_term_debt_concept":
            long_debt_result[
                "concept"
            ],

        "direct_debt":
            directly_reported_debt,

        "direct_debt_concept":
            total_debt_result[
                "concept"
            ],

        "total_debt":
            total_debt,

        "debt_source":
            debt_source,

        "net_debt":
            net_debt,

        "net_cash":
            net_cash,

        "equity":
            equity,

        "equity_concept":
            equity_result[
                "concept"
            ],

        "assets":
            assets,

        "assets_concept":
            assets_result[
                "concept"
            ],

        "debt_to_equity":
            debt_to_equity,
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

    return (
        f"${value:,.0f}"
    )


def format_ratio(
    value,
) -> str:

    if value is None:
        return "N/A"

    return (
        f"{float(value):.2f}x"
    )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    symbol = "AMD"

    result = (
        analyze_financial_health(
            symbol
        )
    )

    print()

    print(
        "=" * 78
    )

    print(
        f"GAINZ FINANCIAL HEALTH TEST — {symbol}"
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
        "BALANCE SHEET"
    )

    print(
        "-" * 78
    )

    print(
        f"Cash:              "
        f"{format_money(result['cash'])}"
    )

    print(
        f"Total debt:        "
        f"{format_money(result['total_debt'])}"
    )

    print(
        f"Short-term debt:   "
        f"{format_money(result['short_term_debt'])}"
    )

    print(
        f"Long-term debt:    "
        f"{format_money(result['long_term_debt'])}"
    )

    print(
        f"Equity:            "
        f"{format_money(result['equity'])}"
    )

    print(
        f"Assets:            "
        f"{format_money(result['assets'])}"
    )

    print()

    print(
        "FINANCIAL HEALTH"
    )

    print(
        "-" * 78
    )

    print(
        f"Net debt:          "
        f"{format_money(result['net_debt'])}"
    )

    print(
        f"Net cash:          "
        f"{format_money(result['net_cash'])}"
    )

    print(
        f"Debt / Equity:     "
        f"{format_ratio(result['debt_to_equity'])}"
    )

    print(
        f"Debt source:       "
        f"{result['debt_source']}"
    )

    print()

    print(
        "SEC CONCEPTS"
    )

    print(
        "-" * 78
    )

    print(
        f"Cash:   "
        f"{result['cash_concept']}"
    )

    print(
        f"Debt:   "
        f"{result['direct_debt_concept']}"
    )

    print(
        f"Equity: "
        f"{result['equity_concept']}"
    )

    print(
        f"Assets: "
        f"{result['assets_concept']}"
    )