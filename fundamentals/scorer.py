from __future__ import annotations

from fundamentals.snapshot import (
    build_fundamental_snapshot,
)


# ============================================================
# HELPERS
# ============================================================

def clamp(
    value: float,
    minimum: float,
    maximum: float,
) -> float:

    return max(
        minimum,
        min(maximum, value),
    )


def linear_score(
    value,
    bad: float,
    good: float,
) -> float | None:
    """
    Convert a metric to 0-100.

    bad  -> 0
    good -> 100

    Values outside the range are capped.
    """

    if value is None:
        return None

    value = float(value)

    if good == bad:
        return None

    score = (
        (value - bad)
        / (good - bad)
        * 100
    )

    return clamp(
        score,
        0,
        100,
    )


def inverse_score(
    value,
    good: float,
    bad: float,
) -> float | None:
    """
    Lower values are better.

    good -> 100
    bad  -> 0
    """

    if value is None:
        return None

    value = float(value)

    if bad == good:
        return None

    score = (
        (bad - value)
        / (bad - good)
        * 100
    )

    return clamp(
        score,
        0,
        100,
    )


def average_available(
    values: list[float | None],
) -> float | None:
    """
    Missing metrics are excluded rather than
    automatically receiving zero.
    """

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


def weighted_available(
    components: list[
        tuple[float | None, float]
    ],
) -> float | None:
    """
    Redistribute weights across available components.
    """

    usable = [
        (score, weight)
        for score, weight in components
        if score is not None
    ]

    if not usable:
        return None

    total_weight = sum(
        weight
        for _, weight in usable
    )

    if total_weight == 0:
        return None

    return sum(
        float(score) * weight
        for score, weight in usable
    ) / total_weight


# ============================================================
# GROWTH
# ============================================================

def score_growth(
    snapshot: dict,
) -> dict:

    data = snapshot[
        "growth"
    ]

    # Capping happens naturally through linear_score.
    #
    # -25% growth = 0
    # +50% growth = 100

    revenue = linear_score(
        data.get("revenue_yoy"),
        bad=-0.25,
        good=0.50,
    )

    net_income = linear_score(
        data.get("net_income_yoy"),
        bad=-0.50,
        good=0.75,
    )

    eps = linear_score(
        data.get("eps_yoy"),
        bad=-0.50,
        good=0.75,
    )

    score = average_available(
        [
            revenue,
            net_income,
            eps,
        ]
    )

    return {
        "score": score,
        "revenue_score": revenue,
        "net_income_score": net_income,
        "eps_score": eps,
    }


# ============================================================
# PROFITABILITY
# ============================================================

def score_profitability(
    snapshot: dict,
) -> dict:

    data = snapshot[
        "profitability"
    ]

    gross = linear_score(
        data.get("gross_margin"),
        bad=0.10,
        good=0.70,
    )

    operating = linear_score(
        data.get("operating_margin"),
        bad=-0.05,
        good=0.30,
    )

    net = linear_score(
        data.get("net_margin"),
        bad=-0.05,
        good=0.25,
    )

    gross_change = linear_score(
        data.get(
            "gross_margin_change"
        ),
        bad=-0.10,
        good=0.10,
    )

    operating_change = linear_score(
        data.get(
            "operating_margin_change"
        ),
        bad=-0.10,
        good=0.10,
    )

    net_change = linear_score(
        data.get(
            "net_margin_change"
        ),
        bad=-0.10,
        good=0.10,
    )

    # Current profitability gets more weight
    # than one-year margin movement.

    current_score = average_available(
        [
            gross,
            operating,
            net,
        ]
    )

    change_score = average_available(
        [
            gross_change,
            operating_change,
            net_change,
        ]
    )

    score = weighted_available(
        [
            (current_score, 0.70),
            (change_score, 0.30),
        ]
    )

    return {
        "score": score,
        "current_score": current_score,
        "change_score": change_score,
    }


# ============================================================
# CASH GENERATION
# ============================================================

def score_cash_generation(
    snapshot: dict,
) -> dict:

    data = snapshot[
        "cash_generation"
    ]

    fcf = data.get(
        "free_cash_flow"
    )

    fcf_margin = data.get(
        "fcf_margin"
    )

    # Absolute FCF is used only for its sign.
    #
    # We deliberately avoid rewarding a huge company
    # simply because its absolute FCF is larger.

    if fcf is None:
        fcf_sign_score = None

    elif float(fcf) > 0:
        fcf_sign_score = 100.0

    elif float(fcf) < 0:
        fcf_sign_score = 0.0

    else:
        fcf_sign_score = 50.0

    margin_score = linear_score(
        fcf_margin,
        bad=-0.10,
        good=0.25,
    )

    score = weighted_available(
        [
            (margin_score, 0.75),
            (fcf_sign_score, 0.25),
        ]
    )

    return {
        "score": score,
        "fcf_margin_score": margin_score,
        "fcf_sign_score": fcf_sign_score,
    }


# ============================================================
# FINANCIAL HEALTH
# ============================================================

def score_financial_health(
    snapshot: dict,
) -> dict:

    data = snapshot[
        "financial_health"
    ]

    net_cash = data.get(
        "net_cash"
    )

    debt_to_equity = data.get(
        "debt_to_equity"
    )

    # Net cash:
    #
    # positive = balance sheet has more cash than debt
    # negative = net debt
    #
    # Because absolute net cash is size-dependent,
    # use only the direction in V1.

    if net_cash is None:
        net_cash_score = None

    elif float(net_cash) > 0:
        net_cash_score = 100.0

    elif float(net_cash) < 0:
        net_cash_score = 25.0

    else:
        net_cash_score = 50.0

    # Conventional D/E.
    #
    # 0x   = strongest end of this simple scale
    # 2x+  = weakest end
    #
    # Financial-sector treatment comes later.

    debt_score = inverse_score(
        debt_to_equity,
        good=0.0,
        bad=2.0,
    )

    score = weighted_available(
        [
            (net_cash_score, 0.50),
            (debt_score, 0.50),
        ]
    )

    return {
        "score": score,
        "net_cash_score": net_cash_score,
        "debt_score": debt_score,
    }


# ============================================================
# EFFICIENCY
# ============================================================

def score_efficiency(
    snapshot: dict,
) -> dict:

    data = snapshot[
        "efficiency"
    ]

    roe = linear_score(
        data.get("roe"),
        bad=0.00,
        good=0.30,
    )

    roa = linear_score(
        data.get("roa"),
        bad=0.00,
        good=0.15,
    )

    score = weighted_available(
        [
            (roe, 0.60),
            (roa, 0.40),
        ]
    )

    return {
        "score": score,
        "roe_score": roe,
        "roa_score": roa,
    }


# ============================================================
# COMPLETE FUNDAMENTAL SCORE
# ============================================================

def calculate_fundamental_score(
    symbol: str,
) -> dict:

    symbol = (
        symbol
        .strip()
        .upper()
    )

    snapshot = (
        build_fundamental_snapshot(
            symbol
        )
    )

    growth = score_growth(
        snapshot
    )

    profitability = score_profitability(
        snapshot
    )

    cash = score_cash_generation(
        snapshot
    )

    health = score_financial_health(
        snapshot
    )

    efficiency = score_efficiency(
        snapshot
    )

    # --------------------------------------------------------
    # Master weights
    # --------------------------------------------------------

    components = [
        (
            growth["score"],
            0.25,
        ),

        (
            profitability["score"],
            0.25,
        ),

        (
            cash["score"],
            0.20,
        ),

        (
            health["score"],
            0.15,
        ),

        (
            efficiency["score"],
            0.15,
        ),
    ]

    fundamental_score = (
        weighted_available(
            components
        )
    )

    # --------------------------------------------------------
    # Coverage
    # --------------------------------------------------------

    available_sections = sum(
        1
        for score, _
        in components
        if score is not None
    )

    coverage = (
        available_sections
        / len(components)
    )

    return {
        "symbol":
            symbol,

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

        "fundamental_score":
            fundamental_score,

        "coverage":
            coverage,

        "growth":
            growth,

        "profitability":
            profitability,

        "cash_generation":
            cash,

        "financial_health":
            health,

        "efficiency":
            efficiency,

        "snapshot":
            snapshot,
    }


# ============================================================
# DISPLAY
# ============================================================

def format_score(
    value,
) -> str:

    if value is None:
        return "N/A"

    return (
        f"{float(value):.1f}"
    )


if __name__ == "__main__":

    symbol = "AMD"

    result = (
        calculate_fundamental_score(
            symbol
        )
    )

    print()

    print(
        "=" * 78
    )

    print(
        f"GAINZ FUNDAMENTAL SCORE — {symbol}"
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

    print()

    print(
        f"Growth:             "
        f"{format_score(result['growth']['score'])}"
    )

    print(
        f"Profitability:      "
        f"{format_score(result['profitability']['score'])}"
    )

    print(
        f"Cash Generation:    "
        f"{format_score(result['cash_generation']['score'])}"
    )

    print(
        f"Financial Health:   "
        f"{format_score(result['financial_health']['score'])}"
    )

    print(
        f"Efficiency:         "
        f"{format_score(result['efficiency']['score'])}"
    )

    print(
        "-" * 78
    )

    print(
        f"FUNDAMENTAL SCORE:  "
        f"{format_score(result['fundamental_score'])}"
        f" / 100"
    )

    print(
        f"Section Coverage:   "
        f"{result['coverage'] * 100:.0f}%"
    )

    print()

    print(
        "OBSERVATIONAL ONLY — "
        "NOT CONNECTED TO TRADING DECISIONS"
    )