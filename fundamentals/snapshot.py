from __future__ import annotations

from fundamentals.normalizer import (
    calculate_growth_snapshot,
)

from fundamentals.profitability import (
    analyze_profitability,
)

from fundamentals.cashflow import (
    analyze_cashflow,
)

from fundamentals.financial_health import (
    analyze_financial_health,
)

from fundamentals.efficiency import (
    analyze_efficiency,
)


# ============================================================
# FUNDAMENTAL SNAPSHOT
# ============================================================

def build_fundamental_snapshot(
    symbol: str,
) -> dict:
    """
    Combine all GainZ fundamental modules into one
    standardized point-in-time snapshot.

    No scoring is performed here.

    Sections:
        - Growth
        - Profitability
        - Cash generation
        - Financial health
        - Efficiency
    """

    symbol = (
        symbol
        .strip()
        .upper()
    )

    # --------------------------------------------------------
    # Run individual fundamental modules
    # --------------------------------------------------------

    growth = (
        calculate_growth_snapshot(
            symbol
        )
    )

    profitability = (
        analyze_profitability(
            symbol
        )
    )

    cashflow = (
        analyze_cashflow(
            symbol
        )
    )

    financial_health = (
        analyze_financial_health(
            symbol
        )
    )

    efficiency = (
        analyze_efficiency(
            symbol
        )
    )

    # --------------------------------------------------------
    # Growth values
    # --------------------------------------------------------

    revenue_growth = (
        growth
        .get("revenue_yoy", {})
        .get("growth")
    )

    net_income_growth = (
        growth
        .get("net_income_yoy", {})
        .get("growth")
    )

    eps_growth = (
        growth
        .get("eps_yoy", {})
        .get("growth")
    )

    # --------------------------------------------------------
    # Profitability values
    # --------------------------------------------------------

    profitability_current = (
        profitability.get(
            "current",
            {},
        )
    )

    profitability_change = (
        profitability.get(
            "change",
            {},
        )
    )

    # --------------------------------------------------------
    # Filing date
    #
    # Snapshot should only be considered available
    # once every included component was public.
    # --------------------------------------------------------

    filing_dates = [
        growth.get(
            "latest_filing_date"
        ),

        profitability.get(
            "filing_date"
        ),

        cashflow.get(
            "filing_date"
        ),

        financial_health.get(
            "filing_date"
        ),

        efficiency.get(
            "filing_date"
        ),
    ]

    filing_dates = [
        date
        for date in filing_dates
        if date
    ]

    available_from = (
        max(filing_dates)
        if filing_dates
        else None
    )

    # --------------------------------------------------------
    # Standardized snapshot
    # --------------------------------------------------------

    return {
        "symbol":
            symbol,

        "company":
            growth.get(
                "company"
            ),

        "period_end":
            profitability.get(
                "period_end"
            ),

        "available_from":
            available_from,

        # ====================================================
        # GROWTH
        # ====================================================

        "growth": {
            "revenue_yoy":
                revenue_growth,

            "net_income_yoy":
                net_income_growth,

            "eps_yoy":
                eps_growth,
        },

        # ====================================================
        # PROFITABILITY
        # ====================================================

        "profitability": {
            "gross_margin":
                profitability_current.get(
                    "gross_margin"
                ),

            "operating_margin":
                profitability_current.get(
                    "operating_margin"
                ),

            "net_margin":
                profitability_current.get(
                    "net_margin"
                ),

            "gross_margin_change":
                profitability_change.get(
                    "gross_margin"
                ),

            "operating_margin_change":
                profitability_change.get(
                    "operating_margin"
                ),

            "net_margin_change":
                profitability_change.get(
                    "net_margin"
                ),
        },

        # ====================================================
        # CASH GENERATION
        # ====================================================

        "cash_generation": {
            "operating_cash_flow":
                cashflow.get(
                    "operating_cash_flow"
                ),

            "capex":
                cashflow.get(
                    "capex"
                ),

            "free_cash_flow":
                cashflow.get(
                    "free_cash_flow"
                ),

            "fcf_margin":
                cashflow.get(
                    "fcf_margin"
                ),
        },

        # ====================================================
        # FINANCIAL HEALTH
        # ====================================================

        "financial_health": {
            "cash":
                financial_health.get(
                    "cash"
                ),

            "total_debt":
                financial_health.get(
                    "total_debt"
                ),

            "net_debt":
                financial_health.get(
                    "net_debt"
                ),

            "net_cash":
                financial_health.get(
                    "net_cash"
                ),

            "debt_to_equity":
                financial_health.get(
                    "debt_to_equity"
                ),

            "equity":
                financial_health.get(
                    "equity"
                ),

            "assets":
                financial_health.get(
                    "assets"
                ),
        },

        # ====================================================
        # EFFICIENCY
        # ====================================================

        "efficiency": {
            "ttm_net_income":
                efficiency.get(
                    "ttm_net_income"
                ),

            "average_equity":
                efficiency.get(
                    "average_equity"
                ),

            "average_assets":
                efficiency.get(
                    "average_assets"
                ),

            "roe":
                efficiency.get(
                    "roe"
                ),

            "roa":
                efficiency.get(
                    "roa"
                ),
        },

        # ====================================================
        # DATA QUALITY / TRACEABILITY
        # ====================================================

        "metadata": {
            "growth_filing_date":
                growth.get(
                    "latest_filing_date"
                ),

            "profitability_filing_date":
                profitability.get(
                    "filing_date"
                ),

            "cashflow_filing_date":
                cashflow.get(
                    "filing_date"
                ),

            "financial_health_filing_date":
                financial_health.get(
                    "filing_date"
                ),

            "efficiency_filing_date":
                efficiency.get(
                    "filing_date"
                ),

            "cashflow_ocf_source":
                cashflow.get(
                    "operating_cash_flow_source"
                ),

            "cashflow_capex_source":
                cashflow.get(
                    "capex_source"
                ),

            "debt_source":
                financial_health.get(
                    "debt_source"
                ),
        },
    }


# ============================================================
# DISPLAY HELPERS
# ============================================================

def format_percent(
    value,
) -> str:

    if value is None:
        return "N/A"

    return (
        f"{float(value) * 100:+.1f}%"
    )


def format_margin(
    value,
) -> str:

    if value is None:
        return "N/A"

    return (
        f"{float(value) * 100:.1f}%"
    )


def format_pp(
    value,
) -> str:

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
        build_fundamental_snapshot(
            symbol
        )
    )

    print()

    print(
        "=" * 78
    )

    print(
        f"GAINZ FUNDAMENTAL SNAPSHOT — {symbol}"
    )

    print(
        "=" * 78
    )

    print(
        f"Company:        "
        f"{result['company']}"
    )

    print(
        f"Period end:     "
        f"{result['period_end']}"
    )

    print(
        f"Available from: "
        f"{result['available_from']}"
    )

    # --------------------------------------------------------
    # Growth
    # --------------------------------------------------------

    growth = result[
        "growth"
    ]

    print()
    print(
        "GROWTH"
    )
    print(
        "-" * 78
    )

    print(
        f"Revenue YoY:    "
        f"{format_percent(growth['revenue_yoy'])}"
    )

    print(
        f"Net Income YoY: "
        f"{format_percent(growth['net_income_yoy'])}"
    )

    print(
        f"EPS YoY:        "
        f"{format_percent(growth['eps_yoy'])}"
    )

    # --------------------------------------------------------
    # Profitability
    # --------------------------------------------------------

    profitability = result[
        "profitability"
    ]

    print()
    print(
        "PROFITABILITY"
    )
    print(
        "-" * 78
    )

    print(
        f"Gross Margin:        "
        f"{format_margin(profitability['gross_margin'])}"
    )

    print(
        f"Operating Margin:    "
        f"{format_margin(profitability['operating_margin'])}"
    )

    print(
        f"Net Margin:          "
        f"{format_margin(profitability['net_margin'])}"
    )

    print(
        f"Gross Margin Δ:      "
        f"{format_pp(profitability['gross_margin_change'])}"
    )

    print(
        f"Operating Margin Δ:  "
        f"{format_pp(profitability['operating_margin_change'])}"
    )

    print(
        f"Net Margin Δ:        "
        f"{format_pp(profitability['net_margin_change'])}"
    )

    # --------------------------------------------------------
    # Cash generation
    # --------------------------------------------------------

    cash = result[
        "cash_generation"
    ]

    print()
    print(
        "CASH GENERATION"
    )
    print(
        "-" * 78
    )

    print(
        f"Operating Cash Flow: "
        f"{format_money(cash['operating_cash_flow'])}"
    )

    print(
        f"CapEx:               "
        f"{format_money(cash['capex'])}"
    )

    print(
        f"Free Cash Flow:      "
        f"{format_money(cash['free_cash_flow'])}"
    )

    print(
        f"FCF Margin:          "
        f"{format_margin(cash['fcf_margin'])}"
    )

    # --------------------------------------------------------
    # Financial health
    # --------------------------------------------------------

    health = result[
        "financial_health"
    ]

    print()
    print(
        "FINANCIAL HEALTH"
    )
    print(
        "-" * 78
    )

    print(
        f"Cash:            "
        f"{format_money(health['cash'])}"
    )

    print(
        f"Total Debt:      "
        f"{format_money(health['total_debt'])}"
    )

    print(
        f"Net Cash:        "
        f"{format_money(health['net_cash'])}"
    )

    print(
        f"Debt / Equity:   "
        f"{format_ratio(health['debt_to_equity'])}"
    )

    print(
        f"Equity:          "
        f"{format_money(health['equity'])}"
    )

    print(
        f"Assets:          "
        f"{format_money(health['assets'])}"
    )

    # --------------------------------------------------------
    # Efficiency
    # --------------------------------------------------------

    efficiency = result[
        "efficiency"
    ]

    print()
    print(
        "EFFICIENCY"
    )
    print(
        "-" * 78
    )

    print(
        f"TTM Net Income:  "
        f"{format_money(efficiency['ttm_net_income'])}"
    )

    print(
        f"ROE:             "
        f"{format_margin(efficiency['roe'])}"
    )

    print(
        f"ROA:             "
        f"{format_margin(efficiency['roa'])}"
    )

    # --------------------------------------------------------
    # Metadata
    # --------------------------------------------------------

    metadata = result[
        "metadata"
    ]

    print()
    print(
        "DATA TRACEABILITY"
    )
    print(
        "-" * 78
    )

    print(
        f"Growth filed:       "
        f"{metadata['growth_filing_date']}"
    )

    print(
        f"Profitability filed:"
        f" {metadata['profitability_filing_date']}"
    )

    print(
        f"Cash flow filed:    "
        f"{metadata['cashflow_filing_date']}"
    )

    print(
        f"Health filed:       "
        f"{metadata['financial_health_filing_date']}"
    )

    print(
        f"Efficiency filed:   "
        f"{metadata['efficiency_filing_date']}"
    )

    print(
        f"OCF source:         "
        f"{metadata['cashflow_ocf_source']}"
    )

    print(
        f"CapEx source:       "
        f"{metadata['cashflow_capex_source']}"
    )

    print(
        f"Debt source:        "
        f"{metadata['debt_source']}"
    )