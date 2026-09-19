from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path


HISTORY_FILE = Path("data/portfolio_history.csv")


def save_portfolio_snapshot(
    portfolio_value: float,
    cash: float,
    invested_value: float,
    unrealised_pnl: float,
    realised_pnl: float,
) -> None:
    """
    Save one genuine portfolio snapshot per UTC day.

    If the dashboard is refreshed multiple times during the same day,
    all existing snapshots for that day are removed and replaced with
    the latest snapshot.

    This prevents Streamlit reruns from creating fake multiple
    "daily" observations.
    """

    HISTORY_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    now = datetime.now(timezone.utc)
    today = now.date().isoformat()

    existing_rows = []

    # ------------------------------------------------------------
    # Load existing history
    # ------------------------------------------------------------

    if HISTORY_FILE.exists():
        try:
            with HISTORY_FILE.open(
                "r",
                encoding="utf-8",
            ) as f:
                existing_rows = list(
                    csv.DictReader(f)
                )

        except Exception:
            existing_rows = []

    # ------------------------------------------------------------
    # Remove ALL existing snapshots from today
    # ------------------------------------------------------------

    existing_rows = [
        row
        for row in existing_rows
        if not row.get(
            "timestamp",
            "",
        ).startswith(today)
    ]

    # ------------------------------------------------------------
    # Create latest genuine snapshot
    # ------------------------------------------------------------

    latest_row = {
        "timestamp": now.isoformat(),
        "portfolio_value": round(
            float(portfolio_value),
            2,
        ),
        "cash": round(
            float(cash),
            2,
        ),
        "invested_value": round(
            float(invested_value),
            2,
        ),
        "unrealised_pnl": round(
            float(unrealised_pnl),
            2,
        ),
        "realised_pnl": round(
            float(realised_pnl),
            2,
        ),
    }

    existing_rows.append(latest_row)

    # ------------------------------------------------------------
    # Write clean history back to CSV
    # ------------------------------------------------------------

    with HISTORY_FILE.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=[
                "timestamp",
                "portfolio_value",
                "cash",
                "invested_value",
                "unrealised_pnl",
                "realised_pnl",
            ],
        )

        writer.writeheader()
        writer.writerows(existing_rows)


def load_portfolio_history():
    """
    Load all recorded portfolio snapshots.
    """

    if not HISTORY_FILE.exists():
        return []

    try:
        with HISTORY_FILE.open(
            "r",
            encoding="utf-8",
        ) as f:
            return list(
                csv.DictReader(f)
            )

    except Exception:
        return []


def calculate_daily_performance():
    """
    Calculate portfolio changes between daily snapshots.

    IMPORTANT:
    daily_pnl currently represents the change in total portfolio
    value between snapshots.

    It should therefore be treated as portfolio/equity change,
    not transaction-level realised trading profit.

    Before SF Alpha is used with real money, deposits and
    withdrawals should be accounted for separately.
    """

    rows = load_portfolio_history()

    if not rows:
        return []

    parsed = []

    # ------------------------------------------------------------
    # Parse and validate history
    # ------------------------------------------------------------

    for row in rows:
        try:
            parsed.append(
                {
                    "timestamp": row["timestamp"],
                    "portfolio_value": float(
                        row["portfolio_value"]
                    ),
                    "cash": float(
                        row["cash"]
                    ),
                    "invested_value": float(
                        row["invested_value"]
                    ),
                    "unrealised_pnl": float(
                        row["unrealised_pnl"]
                    ),
                    "realised_pnl": float(
                        row["realised_pnl"]
                    ),
                }
            )

        except (
            KeyError,
            TypeError,
            ValueError,
        ):
            continue

    if not parsed:
        return []

    # ------------------------------------------------------------
    # Sort chronologically
    # ------------------------------------------------------------

    parsed.sort(
        key=lambda row: row["timestamp"]
    )

    # ------------------------------------------------------------
    # Defensive daily deduplication
    #
    # Even if an older CSV already contains multiple snapshots
    # from the same day, keep only the latest one.
    # ------------------------------------------------------------

    daily_rows = {}

    for row in parsed:
        try:
            day = row[
                "timestamp"
            ][:10]

            daily_rows[day] = row

        except Exception:
            continue

    parsed = [
        daily_rows[day]
        for day in sorted(daily_rows)
    ]

    # ------------------------------------------------------------
    # Calculate day-to-day portfolio changes
    # ------------------------------------------------------------

    results = []

    for index, row in enumerate(parsed):

        if index == 0:
            daily_pnl = 0.0
            daily_return = 0.0

        else:
            previous_value = parsed[
                index - 1
            ]["portfolio_value"]

            current_value = row[
                "portfolio_value"
            ]

            daily_pnl = (
                current_value
                - previous_value
            )

            daily_return = (
                (
                    daily_pnl
                    / previous_value
                )
                * 100
                if previous_value
                else 0.0
            )

        results.append(
            {
                **row,
                "daily_pnl": round(
                    daily_pnl,
                    2,
                ),
                "daily_return": round(
                    daily_return,
                    4,
                ),
            }
        )

    return results