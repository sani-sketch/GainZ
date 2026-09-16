from __future__ import annotations

from datetime import datetime

from fundamentals.normalizer import (
    get_normalized_income_metrics,
    find_year_ago_quarter,
    growth_rate,
)


# ============================================================
# DATE HELPERS
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


# ============================================================
# POINT-IN-TIME FILTER
# ============================================================

def available_as_of(
    quarters: list[dict],
    as_of_date: str,
) -> list[dict]:

    cutoff = parse_date(
        as_of_date
    )

    if cutoff is None:
        raise ValueError(
            f"Invalid as_of_date: {as_of_date}"
        )

    available = []

    for quarter in quarters:

        filed = parse_date(
            quarter.get("filed")
        )

        if filed is None:
            continue

        if filed <= cutoff:
            available.append(
                quarter
            )

    available.sort(
        key=lambda item: (
            item.get("end") or "",
            item.get("filed") or "",
        ),
        reverse=True,
    )

    return available


# ============================================================
# HISTORICAL METRIC
# ============================================================

def historical_metric_yoy(
    quarters: list[dict],
    as_of_date: str,
) -> dict:

    available = available_as_of(
        quarters,
        as_of_date,
    )

    if not available:

        return {
            "current": None,
            "previous": None,
            "growth": None,
        }

    current = available[0]

    previous = find_year_ago_quarter(
        available,
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
# LOAD FUNDAMENTAL DATA ONCE
# ============================================================

def load_growth_history(
    symbol: str,
) -> dict:
    """
    Fetch and normalize SEC fundamental data once.

    The returned dataset can then be reused for hundreds
    or thousands of historical trading dates without
    repeatedly calling SEC.
    """

    symbol = (
        symbol
        .strip()
        .upper()
    )

    metrics = (
        get_normalized_income_metrics(
            symbol
        )
    )

    return {
        "symbol":
            symbol,

        "company":
            metrics.get(
                "company"
            ),

        "revenue":
            metrics.get(
                "revenue",
                [],
            ),

        "net_income":
            metrics.get(
                "net_income",
                [],
            ),

        "eps":
            metrics.get(
                "eps",
                [],
            ),
    }


# ============================================================
# SNAPSHOT FROM PRELOADED DATA
# ============================================================

def historical_growth_snapshot_from_data(
    data: dict,
    as_of_date: str,
) -> dict:

    revenue = historical_metric_yoy(
        data["revenue"],
        as_of_date,
    )

    net_income = historical_metric_yoy(
        data["net_income"],
        as_of_date,
    )

    eps = historical_metric_yoy(
        data["eps"],
        as_of_date,
    )

    current_filings = []

    for result in [
        revenue,
        net_income,
        eps,
    ]:

        current = result.get(
            "current"
        )

        if (
            current
            and current.get("filed")
        ):
            current_filings.append(
                current["filed"]
            )

    latest_filing = (
        max(current_filings)
        if current_filings
        else None
    )

    return {
        "symbol":
            data["symbol"],

        "company":
            data.get(
                "company"
            ),

        "as_of_date":
            as_of_date,

        "latest_available_filing":
            latest_filing,

        "revenue_yoy":
            revenue,

        "net_income_yoy":
            net_income,

        "eps_yoy":
            eps,
    }


# ============================================================
# ORIGINAL SNAPSHOT INTERFACE
# ============================================================

def historical_growth_snapshot(
    symbol: str,
    as_of_date: str,
) -> dict:
    """
    Convenience interface for one-off queries.

    For large backtests use load_growth_history() once and
    historical_growth_score_from_data() repeatedly.
    """

    data = load_growth_history(
        symbol
    )

    return (
        historical_growth_snapshot_from_data(
            data,
            as_of_date,
        )
    )


# ============================================================
# SCORING HELPERS
# ============================================================

def linear_score(
    value,
    bad: float,
    good: float,
) -> float | None:

    if value is None:
        return None

    value = float(
        value
    )

    if good == bad:
        return None

    score = (
        (value - bad)
        / (good - bad)
        * 100
    )

    return max(
        0.0,
        min(
            100.0,
            score,
        ),
    )


def average_available(
    values: list[
        float | None
    ],
) -> float | None:

    usable = [
        float(value)
        for value in values
        if value is not None
    ]

    if not usable:
        return None

    return (
        sum(usable)
        / len(usable)
    )


# ============================================================
# SCORE FROM PRELOADED DATA
# ============================================================

def historical_growth_score_from_data(
    data: dict,
    as_of_date: str,
) -> dict:

    snapshot = (
        historical_growth_snapshot_from_data(
            data,
            as_of_date,
        )
    )

    revenue_growth = (
        snapshot[
            "revenue_yoy"
        ].get(
            "growth"
        )
    )

    net_income_growth = (
        snapshot[
            "net_income_yoy"
        ].get(
            "growth"
        )
    )

    eps_growth = (
        snapshot[
            "eps_yoy"
        ].get(
            "growth"
        )
    )

    revenue_score = linear_score(
        revenue_growth,
        bad=-0.25,
        good=0.50,
    )

    net_income_score = linear_score(
        net_income_growth,
        bad=-0.50,
        good=0.75,
    )

    eps_score = linear_score(
        eps_growth,
        bad=-0.50,
        good=0.75,
    )

    score = average_available(
        [
            revenue_score,
            net_income_score,
            eps_score,
        ]
    )

    return {
        **snapshot,

        "growth_score":
            score,

        "revenue_score":
            revenue_score,

        "net_income_score":
            net_income_score,

        "eps_score":
            eps_score,
    }


# ============================================================
# ORIGINAL SCORE INTERFACE
# ============================================================

def historical_growth_score(
    symbol: str,
    as_of_date: str,
) -> dict:
    """
    One-off point-in-time growth score.

    Kept for compatibility with existing code.
    """

    data = load_growth_history(
        symbol
    )

    return (
        historical_growth_score_from_data(
            data,
            as_of_date,
        )
    )


# ============================================================
# FORMATTING
# ============================================================

def format_percent(
    value,
) -> str:

    if value is None:
        return "N/A"

    return (
        f"{float(value) * 100:+.1f}%"
    )


def format_score(
    value,
) -> str:

    if value is None:
        return "N/A"

    return (
        f"{float(value):.1f}"
    )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    symbol = "AMD"

    test_dates = [
        "2025-05-01",
        "2025-08-10",
        "2025-11-10",
        "2026-02-10",
        "2026-05-10",
        "2026-08-10",
    ]

    # Fetch SEC data only once.
    data = load_growth_history(
        symbol
    )

    print()
    print(
        "=" * 96
    )
    print(
        f"GAINZ POINT-IN-TIME FUNDAMENTALS - {symbol}"
    )
    print(
        "=" * 96
    )

    print(
        f"{'As Of':<14}"
        f"{'Latest Filing':<16}"
        f"{'Revenue YoY':>15}"
        f"{'Net Income YoY':>18}"
        f"{'EPS YoY':>15}"
        f"{'Growth Score':>16}"
    )

    print(
        "-" * 96
    )

    for as_of_date in test_dates:

        result = (
            historical_growth_score_from_data(
                data,
                as_of_date,
            )
        )

        revenue_growth = (
            result[
                "revenue_yoy"
            ].get(
                "growth"
            )
        )

        net_income_growth = (
            result[
                "net_income_yoy"
            ].get(
                "growth"
            )
        )

        eps_growth = (
            result[
                "eps_yoy"
            ].get(
                "growth"
            )
        )

        print(
            f"{as_of_date:<14}"
            f"{str(result['latest_available_filing'] or '--'):<16}"
            f"{format_percent(revenue_growth):>15}"
            f"{format_percent(net_income_growth):>18}"
            f"{format_percent(eps_growth):>15}"
            f"{format_score(result['growth_score']):>16}"
        )

    print()

    print(
        "POINT-IN-TIME RULE:"
    )

    print(
        "Only SEC facts filed on or before each "
        "historical date are used."
    )