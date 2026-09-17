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

    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    today = now.date().isoformat()

    # Only one official snapshot per UTC day.
    # If today's snapshot already exists, update it with the latest values.
    existing_rows = []

    if HISTORY_FILE.exists():
        with HISTORY_FILE.open("r", encoding="utf-8") as f:
            existing_rows = list(csv.DictReader(f))

    row = {
        "timestamp": now.isoformat(),
        "portfolio_value": round(float(portfolio_value), 2),
        "cash": round(float(cash), 2),
        "invested_value": round(float(invested_value), 2),
        "unrealised_pnl": round(float(unrealised_pnl), 2),
        "realised_pnl": round(float(realised_pnl), 2),
    }

    updated = False

    for index, existing in enumerate(existing_rows):
        timestamp = existing.get("timestamp", "")

        if timestamp.startswith(today):
            existing_rows[index] = row
            updated = True
            break

    if not updated:
        existing_rows.append(row)

    with HISTORY_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=row.keys(),
        )

        writer.writeheader()
        writer.writerows(existing_rows)


def load_portfolio_history():
    if not HISTORY_FILE.exists():
        return []

    with HISTORY_FILE.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def calculate_daily_performance():
    rows = load_portfolio_history()

    if not rows:
        return []

    parsed = []

    for row in rows:
        try:
            parsed.append(
                {
                    "timestamp": row["timestamp"],
                    "portfolio_value": float(row["portfolio_value"]),
                    "cash": float(row["cash"]),
                    "invested_value": float(row["invested_value"]),
                    "unrealised_pnl": float(row["unrealised_pnl"]),
                    "realised_pnl": float(row["realised_pnl"]),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue

    parsed.sort(
        key=lambda row: row["timestamp"]
    )

    results = []

    for index, row in enumerate(parsed):

        if index == 0:
            daily_pnl = 0.0
            daily_return = 0.0

        else:
            previous_value = parsed[index - 1]["portfolio_value"]
            current_value = row["portfolio_value"]

            daily_pnl = current_value - previous_value

            daily_return = (
                (daily_pnl / previous_value) * 100
                if previous_value
                else 0.0
            )

        results.append(
            {
                **row,
                "daily_pnl": round(daily_pnl, 2),
                "daily_return": round(daily_return, 4),
            }
        )

    return results