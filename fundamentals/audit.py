from __future__ import annotations

from fundamentals.universe import (
    GAINZ_UNIVERSE,
    scan_symbol,
)


# ============================================================
# QA THRESHOLDS
# ============================================================
#
# These are NOT investment thresholds.
#
# They simply identify values that deserve manual inspection
# before we allow them into the GainZ scoring engine.
# ============================================================

EXTREME_GROWTH = 2.00          # +/- 200%
EXTREME_MARGIN = 0.70          # +/- 70%
EXTREME_MARGIN_CHANGE = 0.30   # +/- 30 percentage points
EXTREME_FCF_MARGIN = 0.60      # +/- 60%
EXTREME_ROE = 0.75             # +/- 75%
EXTREME_ROA = 0.40             # +/- 40%
EXTREME_DEBT_TO_EQUITY = 3.00  # 3.0x


# ============================================================
# KNOWN SECTOR-SENSITIVE METRICS
# ============================================================
#
# Missing these metrics does not automatically indicate a
# data-quality problem for these companies.
#
# BAC, MS and STT are treated separately because conventional
# industrial-company metrics such as gross margin, FCF margin,
# and debt/equity can be economically inappropriate.
# ============================================================

FINANCIAL_TICKERS = {
    "BAC",
    "MS",
    "STT",
}

SECTOR_OPTIONAL_FIELDS = {
    "BAC": {
        "gross_margin",
        "operating_margin",
        "free_cash_flow",
        "fcf_margin",
        "debt_to_equity",
        "net_cash",
    },

    "MS": {
        "gross_margin",
        "operating_margin",
        "free_cash_flow",
        "fcf_margin",
        "debt_to_equity",
        "net_cash",
    },

    "STT": {
        "gross_margin",
        "operating_margin",
        "free_cash_flow",
        "fcf_margin",
        "debt_to_equity",
        "net_cash",
    },
}


# ============================================================
# ISSUE CREATOR
# ============================================================

def make_issue(
    symbol: str,
    severity: str,
    category: str,
    metric: str,
    value,
    message: str,
) -> dict:

    return {
        "symbol": symbol,
        "severity": severity,
        "category": category,
        "metric": metric,
        "value": value,
        "message": message,
    }


# ============================================================
# MISSING DATA CHECK
# ============================================================

def audit_missing_fields(
    result: dict,
) -> list[dict]:

    symbol = result["symbol"]

    issues = []

    fields = [
        ("revenue_yoy", "Revenue YoY"),
        ("net_income_yoy", "Net Income YoY"),
        ("eps_yoy", "EPS YoY"),

        ("gross_margin", "Gross Margin"),
        ("operating_margin", "Operating Margin"),
        ("net_margin", "Net Margin"),

        (
            "operating_cash_flow",
            "Operating Cash Flow",
        ),

        (
            "free_cash_flow",
            "Free Cash Flow",
        ),

        (
            "fcf_margin",
            "FCF Margin",
        ),

        (
            "net_cash",
            "Net Cash",
        ),

        (
            "debt_to_equity",
            "Debt / Equity",
        ),

        ("roe", "ROE"),
        ("roa", "ROA"),
    ]

    optional = SECTOR_OPTIONAL_FIELDS.get(
        symbol,
        set(),
    )

    for key, label in fields:

        if result.get(key) is not None:
            continue

        if key in optional:

            issues.append(
                make_issue(
                    symbol=symbol,
                    severity="INFO",
                    category="SECTOR_OPTIONAL",
                    metric=key,
                    value=None,
                    message=(
                        f"{label} unavailable; "
                        f"currently treated as sector-sensitive."
                    ),
                )
            )

        else:

            issues.append(
                make_issue(
                    symbol=symbol,
                    severity="REVIEW",
                    category="MISSING",
                    metric=key,
                    value=None,
                    message=(
                        f"{label} is missing and "
                        f"should be investigated."
                    ),
                )
            )

    return issues


# ============================================================
# GROWTH CHECKS
# ============================================================

def audit_growth(
    result: dict,
) -> list[dict]:

    symbol = result["symbol"]

    issues = []

    fields = [
        (
            "revenue_yoy",
            "Revenue YoY",
        ),

        (
            "net_income_yoy",
            "Net Income YoY",
        ),

        (
            "eps_yoy",
            "EPS YoY",
        ),
    ]

    for key, label in fields:

        value = result.get(
            key
        )

        if value is None:
            continue

        if abs(float(value)) >= EXTREME_GROWTH:

            issues.append(
                make_issue(
                    symbol=symbol,
                    severity="REVIEW",
                    category="EXTREME_GROWTH",
                    metric=key,
                    value=value,
                    message=(
                        f"{label} exceeds "
                        f"+/-200%; verify SEC "
                        f"period/context selection."
                    ),
                )
            )

    return issues


# ============================================================
# PROFITABILITY CHECKS
# ============================================================

def audit_profitability(
    result: dict,
) -> list[dict]:

    symbol = result["symbol"]

    issues = []

    fields = [
        (
            "gross_margin",
            "Gross Margin",
        ),

        (
            "operating_margin",
            "Operating Margin",
        ),

        (
            "net_margin",
            "Net Margin",
        ),
    ]

    for key, label in fields:

        value = result.get(
            key
        )

        if value is None:
            continue

        if abs(float(value)) >= EXTREME_MARGIN:

            issues.append(
                make_issue(
                    symbol=symbol,
                    severity="REVIEW",
                    category="EXTREME_MARGIN",
                    metric=key,
                    value=value,
                    message=(
                        f"{label} exceeds "
                        f"+/-70%; verify numerator "
                        f"and revenue periods."
                    ),
                )
            )

    # --------------------------------------------------------
    # Cross-metric consistency checks
    # --------------------------------------------------------

    gross_margin = result.get(
        "gross_margin"
    )

    operating_margin = result.get(
        "operating_margin"
    )

    if (
        gross_margin is not None
        and operating_margin is not None
        and float(operating_margin)
        > float(gross_margin) + 0.05
    ):

        issues.append(
            make_issue(
                symbol=symbol,
                severity="REVIEW",
                category="MARGIN_RELATIONSHIP",
                metric="operating_margin",
                value=operating_margin,
                message=(
                    "Operating margin is more than "
                    "5 percentage points above gross "
                    "margin; inspect SEC concepts."
                ),
            )
        )

    return issues


# ============================================================
# CASH FLOW CHECKS
# ============================================================

def audit_cashflow(
    result: dict,
) -> list[dict]:

    symbol = result["symbol"]

    issues = []

    fcf_margin = result.get(
        "fcf_margin"
    )

    if (
        fcf_margin is not None
        and abs(float(fcf_margin))
        >= EXTREME_FCF_MARGIN
    ):

        severity = (
            "INFO"
            if symbol in FINANCIAL_TICKERS
            else "REVIEW"
        )

        issues.append(
            make_issue(
                symbol=symbol,
                severity=severity,
                category="EXTREME_FCF_MARGIN",
                metric="fcf_margin",
                value=fcf_margin,
                message=(
                    "FCF margin exceeds +/-60%; "
                    "verify cash-flow period "
                    "normalization and CapEx concept."
                ),
            )
        )

    return issues


# ============================================================
# FINANCIAL HEALTH CHECKS
# ============================================================

def audit_financial_health(
    result: dict,
) -> list[dict]:

    symbol = result["symbol"]

    issues = []

    debt_to_equity = result.get(
        "debt_to_equity"
    )

    if (
        debt_to_equity is not None
        and float(debt_to_equity)
        < 0
    ):

        issues.append(
            make_issue(
                symbol=symbol,
                severity="REVIEW",
                category="NEGATIVE_DEBT_EQUITY",
                metric="debt_to_equity",
                value=debt_to_equity,
                message=(
                    "Debt/equity is negative; "
                    "inspect equity and debt facts."
                ),
            )
        )

    if (
        debt_to_equity is not None
        and float(debt_to_equity)
        >= EXTREME_DEBT_TO_EQUITY
        and symbol not in FINANCIAL_TICKERS
    ):

        issues.append(
            make_issue(
                symbol=symbol,
                severity="REVIEW",
                category="HIGH_DEBT_EQUITY",
                metric="debt_to_equity",
                value=debt_to_equity,
                message=(
                    "Debt/equity exceeds 3.0x; "
                    "verify debt construction and "
                    "equity concept."
                ),
            )
        )

    return issues


# ============================================================
# EFFICIENCY CHECKS
# ============================================================

def audit_efficiency(
    result: dict,
) -> list[dict]:

    symbol = result["symbol"]

    issues = []

    roe = result.get(
        "roe"
    )

    roa = result.get(
        "roa"
    )

    if (
        roe is not None
        and abs(float(roe))
        >= EXTREME_ROE
    ):

        issues.append(
            make_issue(
                symbol=symbol,
                severity="REVIEW",
                category="EXTREME_ROE",
                metric="roe",
                value=roe,
                message=(
                    "ROE exceeds +/-75%; verify "
                    "TTM net income and average equity."
                ),
            )
        )

    if (
        roa is not None
        and abs(float(roa))
        >= EXTREME_ROA
    ):

        issues.append(
            make_issue(
                symbol=symbol,
                severity="REVIEW",
                category="EXTREME_ROA",
                metric="roa",
                value=roa,
                message=(
                    "ROA exceeds +/-40%; verify "
                    "TTM net income and average assets."
                ),
            )
        )

    if (
        roe is None
        and roa is not None
    ):

        issues.append(
            make_issue(
                symbol=symbol,
                severity="REVIEW",
                category="EFFICIENCY_MISMATCH",
                metric="roe",
                value=None,
                message=(
                    "ROA exists but ROE is missing; "
                    "inspect current/prior equity facts."
                ),
            )
        )

    return issues


# ============================================================
# AUDIT ONE RESULT
# ============================================================

def audit_result(
    result: dict,
) -> list[dict]:

    if result.get(
        "status"
    ) == "ERROR":

        return [
            make_issue(
                symbol=result["symbol"],
                severity="ERROR",
                category="SNAPSHOT_ERROR",
                metric="snapshot",
                value=None,
                message=(
                    result.get("error")
                    or "Snapshot failed."
                ),
            )
        ]

    issues = []

    issues.extend(
        audit_missing_fields(
            result
        )
    )

    issues.extend(
        audit_growth(
            result
        )
    )

    issues.extend(
        audit_profitability(
            result
        )
    )

    issues.extend(
        audit_cashflow(
            result
        )
    )

    issues.extend(
        audit_financial_health(
            result
        )
    )

    issues.extend(
        audit_efficiency(
            result
        )
    )

    return issues


# ============================================================
# UNIVERSE AUDIT
# ============================================================

def run_audit(
    symbols: list[str] | None = None,
) -> tuple[list[dict], list[dict]]:

    symbols = (
        symbols
        or GAINZ_UNIVERSE
    )

    results = []
    issues = []

    total = len(
        symbols
    )

    for index, symbol in enumerate(
        symbols,
        start=1,
    ):

        print(
            f"[{index:02d}/{total:02d}] "
            f"Auditing {symbol}..."
        )

        result = scan_symbol(
            symbol
        )

        results.append(
            result
        )

        symbol_issues = (
            audit_result(
                result
            )
        )

        issues.extend(
            symbol_issues
        )

        review_count = sum(
            1
            for issue in symbol_issues
            if issue["severity"]
            in {"REVIEW", "ERROR"}
        )

        info_count = sum(
            1
            for issue in symbol_issues
            if issue["severity"]
            == "INFO"
        )

        print(
            f"      Review: "
            f"{review_count} | "
            f"Info: {info_count}"
        )

    return (
        results,
        issues,
    )


# ============================================================
# DISPLAY
# ============================================================

def format_value(
    value,
) -> str:

    if value is None:
        return "--"

    if isinstance(
        value,
        (int, float),
    ):

        return (
            f"{float(value):.4f}"
        )

    return str(
        value
    )


def print_audit_report(
    issues: list[dict],
) -> None:

    print()

    print(
        "=" * 100
    )

    print(
        "GAINZ FUNDAMENTAL DATA AUDIT"
    )

    print(
        "=" * 100
    )

    important = [
        issue
        for issue in issues
        if issue["severity"]
        in {"ERROR", "REVIEW"}
    ]

    informational = [
        issue
        for issue in issues
        if issue["severity"]
        == "INFO"
    ]

    print()
    print(
        "REQUIRES REVIEW"
    )
    print(
        "-" * 100
    )

    if not important:

        print(
            "No review flags."
        )

    else:

        for issue in important:

            print(
                f"{issue['symbol']:<6} | "
                f"{issue['category']:<24} | "
                f"{issue['metric']:<22} | "
                f"{format_value(issue['value']):<12} | "
                f"{issue['message']}"
            )

    print()
    print(
        "SECTOR / INFORMATIONAL"
    )
    print(
        "-" * 100
    )

    if not informational:

        print(
            "No informational flags."
        )

    else:

        for issue in informational:

            print(
                f"{issue['symbol']:<6} | "
                f"{issue['category']:<24} | "
                f"{issue['metric']:<22} | "
                f"{issue['message']}"
            )


# ============================================================
# PRIORITY SUMMARY
# ============================================================

def print_priority_summary(
    issues: list[dict],
) -> None:

    review_issues = [
        issue
        for issue in issues
        if issue["severity"]
        in {"ERROR", "REVIEW"}
    ]

    by_symbol = {}

    for issue in review_issues:

        symbol = issue[
            "symbol"
        ]

        by_symbol.setdefault(
            symbol,
            [],
        )

        by_symbol[symbol].append(
            issue
        )

    ranked = sorted(
        by_symbol.items(),
        key=lambda item:
            len(item[1]),
        reverse=True,
    )

    print()

    print(
        "=" * 78
    )

    print(
        "QA PRIORITY"
    )

    print(
        "=" * 78
    )

    if not ranked:

        print(
            "No tickers currently require review."
        )

        return

    for symbol, symbol_issues in ranked:

        categories = sorted(
            {
                issue["category"]
                for issue
                in symbol_issues
            }
        )

        print(
            f"{symbol:<6} "
            f"{len(symbol_issues):>2} review flag(s) | "
            + ", ".join(
                categories
            )
        )


# ============================================================
# SUMMARY
# ============================================================

def print_summary(
    results: list[dict],
    issues: list[dict],
) -> None:

    errors = sum(
        1
        for issue in issues
        if issue["severity"]
        == "ERROR"
    )

    reviews = sum(
        1
        for issue in issues
        if issue["severity"]
        == "REVIEW"
    )

    info = sum(
        1
        for issue in issues
        if issue["severity"]
        == "INFO"
    )

    clean_symbols = 0

    for result in results:

        symbol = result[
            "symbol"
        ]

        has_review = any(
            issue["symbol"] == symbol
            and issue["severity"]
            in {"ERROR", "REVIEW"}
            for issue in issues
        )

        if not has_review:

            clean_symbols += 1

    print()

    print(
        "=" * 78
    )

    print(
        "AUDIT SUMMARY"
    )

    print(
        "=" * 78
    )

    print(
        f"Tickers scanned:     "
        f"{len(results)}"
    )

    print(
        f"Clean tickers:       "
        f"{clean_symbols}"
    )

    print(
        f"Review flags:        "
        f"{reviews}"
    )

    print(
        f"Errors:              "
        f"{errors}"
    )

    print(
        f"Informational flags: "
        f"{info}"
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    results, issues = (
        run_audit()
    )

    print_audit_report(
        issues
    )

    print_priority_summary(
        issues
    )

    print_summary(
        results,
        issues,
    )