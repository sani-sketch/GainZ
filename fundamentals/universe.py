from __future__ import annotations

import time

from fundamentals.snapshot import (
    build_fundamental_snapshot,
)


# ============================================================
# GAINZ UNIVERSE
# ============================================================

GAINZ_UNIVERSE = [
    "AMD",
    "MU",
    "MPC",
    "PANW",
    "FTNT",
    "PSX",
    "INTC",
    "STT",
    "CRM",
    "MRK",
    "BAC",
    "TMO",
    "MS",
    "ADP",
    "UNH",
]


# ============================================================
# HELPERS
# ============================================================

def available(value) -> bool:
    return value is not None


def marker(value) -> str:
    return "OK" if available(value) else "--"


def count_metrics(
    snapshot: dict,
) -> tuple[int, int]:
    """
    Count available core analytical metrics.

    Raw balance-sheet values such as cash/assets are
    useful inputs, but the coverage score focuses on
    the metrics we are most likely to use later in
    the fundamental model.
    """

    growth = snapshot.get(
        "growth",
        {},
    )

    profitability = snapshot.get(
        "profitability",
        {},
    )

    cash = snapshot.get(
        "cash_generation",
        {},
    )

    health = snapshot.get(
        "financial_health",
        {},
    )

    efficiency = snapshot.get(
        "efficiency",
        {},
    )

    metrics = [
        # Growth
        growth.get("revenue_yoy"),
        growth.get("net_income_yoy"),
        growth.get("eps_yoy"),

        # Profitability
        profitability.get("gross_margin"),
        profitability.get("operating_margin"),
        profitability.get("net_margin"),

        profitability.get(
            "gross_margin_change"
        ),

        profitability.get(
            "operating_margin_change"
        ),

        profitability.get(
            "net_margin_change"
        ),

        # Cash generation
        cash.get("operating_cash_flow"),
        cash.get("free_cash_flow"),
        cash.get("fcf_margin"),

        # Financial health
        health.get("net_cash"),
        health.get("debt_to_equity"),

        # Efficiency
        efficiency.get("roe"),
        efficiency.get("roa"),
    ]

    total = len(
        metrics
    )

    present = sum(
        1
        for value in metrics
        if available(value)
    )

    return (
        present,
        total,
    )


# ============================================================
# SCAN ONE SYMBOL
# ============================================================

def scan_symbol(
    symbol: str,
) -> dict:

    symbol = (
        symbol
        .strip()
        .upper()
    )

    try:

        snapshot = (
            build_fundamental_snapshot(
                symbol
            )
        )

        present, total = (
            count_metrics(
                snapshot
            )
        )

        growth = snapshot.get(
            "growth",
            {},
        )

        profitability = snapshot.get(
            "profitability",
            {},
        )

        cash = snapshot.get(
            "cash_generation",
            {},
        )

        health = snapshot.get(
            "financial_health",
            {},
        )

        efficiency = snapshot.get(
            "efficiency",
            {},
        )

        return {
            "symbol":
                symbol,

            "status":
                "OK",

            "error":
                None,

            "company":
                snapshot.get(
                    "company"
                ),

            "period_end":
                snapshot.get(
                    "period_end"
                ),

            "available_from":
                snapshot.get(
                    "available_from"
                ),

            "coverage_present":
                present,

            "coverage_total":
                total,

            "coverage":
                (
                    present / total
                    if total
                    else 0
                ),

            # Growth
            "revenue_yoy":
                growth.get(
                    "revenue_yoy"
                ),

            "net_income_yoy":
                growth.get(
                    "net_income_yoy"
                ),

            "eps_yoy":
                growth.get(
                    "eps_yoy"
                ),

            # Profitability
            "gross_margin":
                profitability.get(
                    "gross_margin"
                ),

            "operating_margin":
                profitability.get(
                    "operating_margin"
                ),

            "net_margin":
                profitability.get(
                    "net_margin"
                ),

            # Cash
            "operating_cash_flow":
                cash.get(
                    "operating_cash_flow"
                ),

            "free_cash_flow":
                cash.get(
                    "free_cash_flow"
                ),

            "fcf_margin":
                cash.get(
                    "fcf_margin"
                ),

            # Health
            "net_cash":
                health.get(
                    "net_cash"
                ),

            "debt_to_equity":
                health.get(
                    "debt_to_equity"
                ),

            # Efficiency
            "roe":
                efficiency.get(
                    "roe"
                ),

            "roa":
                efficiency.get(
                    "roa"
                ),
        }

    except Exception as exc:

        return {
            "symbol":
                symbol,

            "status":
                "ERROR",

            "error":
                (
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),

            "coverage_present":
                0,

            "coverage_total":
                16,

            "coverage":
                0.0,
        }


# ============================================================
# SCAN UNIVERSE
# ============================================================

def scan_universe(
    symbols: list[str] | None = None,
) -> list[dict]:

    symbols = (
        symbols
        or GAINZ_UNIVERSE
    )

    results = []

    total = len(
        symbols
    )

    for index, symbol in enumerate(
        symbols,
        start=1,
    ):

        print(
            f"[{index:02d}/{total:02d}] "
            f"Scanning {symbol}..."
        )

        result = scan_symbol(
            symbol
        )

        results.append(
            result
        )

        if result["status"] == "ERROR":

            print(
                f"      ERROR: "
                f"{result['error']}"
            )

        else:

            print(
                f"      Coverage: "
                f"{result['coverage_present']}"
                f"/"
                f"{result['coverage_total']}"
            )

        # Small pause between companies.
        time.sleep(
            0.25
        )

    return results


# ============================================================
# DISPLAY HELPERS
# ============================================================

def percent(
    value,
) -> str:

    if value is None:
        return "--"

    return (
        f"{float(value) * 100:.1f}%"
    )


def signed_percent(
    value,
) -> str:

    if value is None:
        return "--"

    return (
        f"{float(value) * 100:+.1f}%"
    )


def ratio(
    value,
) -> str:

    if value is None:
        return "--"

    return (
        f"{float(value):.2f}x"
    )


# ============================================================
# COVERAGE TABLE
# ============================================================

def print_coverage_table(
    results: list[dict],
) -> None:

    print()

    print(
        "=" * 108
    )

    print(
        "GAINZ FUNDAMENTAL UNIVERSE — COVERAGE"
    )

    print(
        "=" * 108
    )

    header = (
        f"{'Ticker':<7}"
        f"{'Status':<9}"
        f"{'Coverage':<11}"
        f"{'Growth':<9}"
        f"{'Gross':<8}"
        f"{'OpMar':<8}"
        f"{'FCF':<8}"
        f"{'D/E':<8}"
        f"{'ROE':<8}"
        f"{'ROA':<8}"
        f"{'Available':<12}"
    )

    print(
        header
    )

    print(
        "-" * 108
    )

    for result in results:

        if result.get(
            "status"
        ) == "ERROR":

            print(
                f"{result['symbol']:<7}"
                f"{'ERROR':<9}"
                f"{'0/16':<11}"
                f"{'--':<9}"
                f"{'--':<8}"
                f"{'--':<8}"
                f"{'--':<8}"
                f"{'--':<8}"
                f"{'--':<8}"
                f"{'--':<8}"
                f"{'--':<12}"
            )

            continue

        growth_ok = (
            available(
                result.get(
                    "revenue_yoy"
                )
            )
            or
            available(
                result.get(
                    "net_income_yoy"
                )
            )
            or
            available(
                result.get(
                    "eps_yoy"
                )
            )
        )

        coverage_text = (
            f"{result['coverage_present']}"
            f"/"
            f"{result['coverage_total']}"
        )

        print(
            f"{result['symbol']:<7}"
            f"{result['status']:<9}"
            f"{coverage_text:<11}"
            f"{marker(True if growth_ok else None):<9}"
            f"{marker(result.get('gross_margin')):<8}"
            f"{marker(result.get('operating_margin')):<8}"
            f"{marker(result.get('free_cash_flow')):<8}"
            f"{marker(result.get('debt_to_equity')):<8}"
            f"{marker(result.get('roe')):<8}"
            f"{marker(result.get('roa')):<8}"
            f"{str(result.get('available_from') or '--'):<12}"
        )


# ============================================================
# KEY METRIC TABLE
# ============================================================

def print_metric_table(
    results: list[dict],
) -> None:

    print()

    print(
        "=" * 116
    )

    print(
        "GAINZ FUNDAMENTAL UNIVERSE — KEY METRICS"
    )

    print(
        "=" * 116
    )

    header = (
        f"{'Ticker':<7}"
        f"{'RevYoY':>10}"
        f"{'EPSYoY':>10}"
        f"{'GrossM':>10}"
        f"{'OpM':>10}"
        f"{'NetM':>10}"
        f"{'FCFM':>10}"
        f"{'D/E':>10}"
        f"{'ROE':>10}"
        f"{'ROA':>10}"
    )

    print(
        header
    )

    print(
        "-" * 116
    )

    for result in results:

        if result.get(
            "status"
        ) == "ERROR":

            print(
                f"{result['symbol']:<7}"
                f"{'ERROR':>10}"
            )

            continue

        print(
            f"{result['symbol']:<7}"
            f"{signed_percent(result.get('revenue_yoy')):>10}"
            f"{signed_percent(result.get('eps_yoy')):>10}"
            f"{percent(result.get('gross_margin')):>10}"
            f"{percent(result.get('operating_margin')):>10}"
            f"{percent(result.get('net_margin')):>10}"
            f"{percent(result.get('fcf_margin')):>10}"
            f"{ratio(result.get('debt_to_equity')):>10}"
            f"{percent(result.get('roe')):>10}"
            f"{percent(result.get('roa')):>10}"
        )


# ============================================================
# PROBLEM REPORT
# ============================================================

def print_problem_report(
    results: list[dict],
) -> None:

    print()

    print(
        "=" * 78
    )

    print(
        "MISSING DATA / ERRORS"
    )

    print(
        "=" * 78
    )

    found_problem = False

    fields = [
        ("revenue_yoy", "Revenue YoY"),
        ("net_income_yoy", "Net Income YoY"),
        ("eps_yoy", "EPS YoY"),
        ("gross_margin", "Gross Margin"),
        ("operating_margin", "Operating Margin"),
        ("net_margin", "Net Margin"),
        ("operating_cash_flow", "Operating Cash Flow"),
        ("free_cash_flow", "Free Cash Flow"),
        ("fcf_margin", "FCF Margin"),
        ("net_cash", "Net Cash"),
        ("debt_to_equity", "Debt / Equity"),
        ("roe", "ROE"),
        ("roa", "ROA"),
    ]

    for result in results:

        symbol = result[
            "symbol"
        ]

        if result.get(
            "status"
        ) == "ERROR":

            found_problem = True

            print(
                f"{symbol}: "
                f"{result.get('error')}"
            )

            continue

        missing = [
            label
            for key, label in fields
            if result.get(key) is None
        ]

        if missing:

            found_problem = True

            print(
                f"{symbol}: "
                + ", ".join(
                    missing
                )
            )

    if not found_problem:

        print(
            "No missing core metrics."
        )


# ============================================================
# SUMMARY
# ============================================================

def print_summary(
    results: list[dict],
) -> None:

    successful = [
        result
        for result in results
        if result.get(
            "status"
        ) == "OK"
    ]

    failed = [
        result
        for result in results
        if result.get(
            "status"
        ) == "ERROR"
    ]

    complete = [
        result
        for result in successful
        if (
            result.get(
                "coverage_present"
            )
            ==
            result.get(
                "coverage_total"
            )
        )
    ]

    print()

    print(
        "=" * 78
    )

    print(
        "SUMMARY"
    )

    print(
        "=" * 78
    )

    print(
        f"Universe size:       "
        f"{len(results)}"
    )

    print(
        f"Successful snapshots:"
        f" {len(successful)}"
    )

    print(
        f"Failed snapshots:    "
        f"{len(failed)}"
    )

    print(
        f"Full 16/16 coverage: "
        f"{len(complete)}"
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    results = (
        scan_universe()
    )

    print_coverage_table(
        results
    )

    print_metric_table(
        results
    )

    print_problem_report(
        results
    )

    print_summary(
        results
    )