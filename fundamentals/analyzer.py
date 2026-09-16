from __future__ import annotations

from fundamentals.fmp import get_financial_statements


# ============================================================
# SAFE MATH
# ============================================================

def safe_divide(
    numerator,
    denominator,
) -> float | None:
    """
    Divide safely.

    Returns None when calculation is not possible.
    """

    if numerator is None or denominator in (None, 0):
        return None

    try:
        return float(numerator) / float(denominator)

    except (TypeError, ValueError, ZeroDivisionError):
        return None


def growth_rate(
    current,
    previous,
) -> float | None:
    """
    Calculate growth rate.

    Example:
        100 -> 120 = +0.20 = +20%
    """

    if current is None or previous in (None, 0):
        return None

    try:
        return (
            float(current) - float(previous)
        ) / abs(float(previous))

    except (TypeError, ValueError, ZeroDivisionError):
        return None


# ============================================================
# FIND MATCHING QUARTER
# ============================================================

def find_year_ago_statement(
    statements: list[dict],
    latest: dict,
) -> dict | None:
    """
    Find the same fiscal quarter from the previous year.

    Example:
        Q2 2026 -> Q2 2025
    """

    latest_period = latest.get("period")
    latest_year = latest.get("calendarYear")

    if latest_year is None:
        return None

    try:
        previous_year = int(latest_year) - 1
    except (TypeError, ValueError):
        return None

    for statement in statements[1:]:

        statement_period = statement.get("period")
        statement_year = statement.get("calendarYear")

        try:
            statement_year = int(statement_year)
        except (TypeError, ValueError):
            continue

        if (
            statement_period == latest_period
            and statement_year == previous_year
        ):
            return statement

    return None


# ============================================================
# ANALYZE FUNDAMENTALS
# ============================================================

def analyze_fundamentals(
    symbol: str,
) -> dict:
    """
    Calculate raw fundamental metrics for one company.

    No scoring is performed here.
    """

    symbol = symbol.strip().upper()

    statements = get_financial_statements(
        symbol=symbol,
        period="quarter",
        limit=12,
    )

    income = statements[
        "income_statement"
    ]

    balance = statements[
        "balance_sheet"
    ]

    cash_flow = statements[
        "cash_flow_statement"
    ]

    if not income:
        raise RuntimeError(
            f"No income statements found for {symbol}"
        )

    if not balance:
        raise RuntimeError(
            f"No balance sheets found for {symbol}"
        )

    if not cash_flow:
        raise RuntimeError(
            f"No cash-flow statements found for {symbol}"
        )

    latest_income = income[0]
    latest_balance = balance[0]
    latest_cash_flow = cash_flow[0]

    previous_income = find_year_ago_statement(
        income,
        latest_income,
    )

    # ========================================================
    # GROWTH
    # ========================================================

    revenue_yoy = None
    net_income_yoy = None
    eps_yoy = None

    if previous_income:

        revenue_yoy = growth_rate(
            latest_income.get("revenue"),
            previous_income.get("revenue"),
        )

        net_income_yoy = growth_rate(
            latest_income.get("netIncome"),
            previous_income.get("netIncome"),
        )

        eps_yoy = growth_rate(
            latest_income.get("eps"),
            previous_income.get("eps"),
        )

    # ========================================================
    # PROFITABILITY
    # ========================================================

    revenue = latest_income.get(
        "revenue"
    )

    gross_margin = safe_divide(
        latest_income.get("grossProfit"),
        revenue,
    )

    operating_margin = safe_divide(
        latest_income.get("operatingIncome"),
        revenue,
    )

    net_margin = safe_divide(
        latest_income.get("netIncome"),
        revenue,
    )

    # ========================================================
    # CASH GENERATION
    # ========================================================

    operating_cash_flow = (
        latest_cash_flow.get(
            "operatingCashFlow"
        )
    )

    capital_expenditure = (
        latest_cash_flow.get(
            "capitalExpenditure"
        )
    )

    free_cash_flow = (
        latest_cash_flow.get(
            "freeCashFlow"
        )
    )

    # Some datasets may not provide FCF directly.
    if (
        free_cash_flow is None
        and operating_cash_flow is not None
        and capital_expenditure is not None
    ):
        free_cash_flow = (
            operating_cash_flow
            + capital_expenditure
        )

    fcf_margin = safe_divide(
        free_cash_flow,
        revenue,
    )

    # ========================================================
    # BALANCE SHEET
    # ========================================================

    cash = latest_balance.get(
        "cashAndCashEquivalents"
    )

    total_debt = latest_balance.get(
        "totalDebt"
    )

    total_equity = latest_balance.get(
        "totalStockholdersEquity"
    )

    total_assets = latest_balance.get(
        "totalAssets"
    )

    debt_to_equity = safe_divide(
        total_debt,
        total_equity,
    )

    # ========================================================
    # EFFICIENCY
    # ========================================================

    net_income = latest_income.get(
        "netIncome"
    )

    roe = safe_divide(
        net_income,
        total_equity,
    )

    roa = safe_divide(
        net_income,
        total_assets,
    )

    # ========================================================
    # RESULT
    # ========================================================

    return {
        "symbol": symbol,

        "filing_date": latest_income.get(
            "filingDate"
        ),

        "fiscal_date": latest_income.get(
            "date"
        ),

        "period": latest_income.get(
            "period"
        ),

        # Growth
        "revenue_yoy": revenue_yoy,
        "net_income_yoy": net_income_yoy,
        "eps_yoy": eps_yoy,

        # Profitability
        "gross_margin": gross_margin,
        "operating_margin": operating_margin,
        "net_margin": net_margin,

        # Cash generation
        "operating_cash_flow": operating_cash_flow,
        "free_cash_flow": free_cash_flow,
        "fcf_margin": fcf_margin,

        # Financial health
        "cash": cash,
        "total_debt": total_debt,
        "debt_to_equity": debt_to_equity,

        # Efficiency
        "roe": roe,
        "roa": roa,
    }


# ============================================================
# DISPLAY HELPERS
# ============================================================

def format_percent(
    value: float | None,
) -> str:

    if value is None:
        return "N/A"

    return f"{value * 100:+.2f}%"


def format_money(
    value,
) -> str:

    if value is None:
        return "N/A"

    value = float(value)

    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"

    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"

    return f"${value:,.0f}"


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    result = analyze_fundamentals(
        "AMD"
    )

    print()
    print("=" * 70)
    print("GAINZ FUNDAMENTAL ANALYSIS — AMD")
    print("=" * 70)

    print(
        f"Filing date:       "
        f"{result['filing_date']}"
    )

    print(
        f"Fiscal date:       "
        f"{result['fiscal_date']}"
    )

    print(
        f"Period:            "
        f"{result['period']}"
    )

    print()
    print("GROWTH")
    print("-" * 40)

    print(
        "Revenue YoY:      ",
        format_percent(
            result["revenue_yoy"]
        ),
    )

    print(
        "Net income YoY:   ",
        format_percent(
            result["net_income_yoy"]
        ),
    )

    print(
        "EPS YoY:          ",
        format_percent(
            result["eps_yoy"]
        ),
    )

    print()
    print("PROFITABILITY")
    print("-" * 40)

    print(
        "Gross margin:     ",
        format_percent(
            result["gross_margin"]
        ),
    )

    print(
        "Operating margin: ",
        format_percent(
            result["operating_margin"]
        ),
    )

    print(
        "Net margin:       ",
        format_percent(
            result["net_margin"]
        ),
    )

    print()
    print("CASH GENERATION")
    print("-" * 40)

    print(
        "Operating CF:     ",
        format_money(
            result["operating_cash_flow"]
        ),
    )

    print(
        "Free cash flow:   ",
        format_money(
            result["free_cash_flow"]
        ),
    )

    print(
        "FCF margin:       ",
        format_percent(
            result["fcf_margin"]
        ),
    )

    print()
    print("FINANCIAL HEALTH")
    print("-" * 40)

    print(
        "Cash:             ",
        format_money(
            result["cash"]
        ),
    )

    print(
        "Total debt:       ",
        format_money(
            result["total_debt"]
        ),
    )

    print(
        "Debt / equity:    ",
        (
            f"{result['debt_to_equity']:.2f}"
            if result["debt_to_equity"] is not None
            else "N/A"
        ),
    )

    print()
    print("EFFICIENCY")
    print("-" * 40)

    print(
        "ROE:              ",
        format_percent(
            result["roe"]
        ),
    )

    print(
        "ROA:              ",
        format_percent(
            result["roa"]
        ),
    )