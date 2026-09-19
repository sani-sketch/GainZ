from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv

from broker.trading212 import Trading212Broker


ROOT = Path(__file__).resolve().parent

# Load the same .env file used by GainZ.
load_dotenv(ROOT / ".env")


def main() -> None:
    """
    READ-ONLY diagnostic for Trading 212 Practice pending orders.

    This script does NOT:
    - place orders
    - cancel orders
    - modify orders

    It only fetches the current Practice active-order response.
    """

    print("Connecting to Trading 212 Practice...")

    broker = Trading212Broker(
        environment="demo"
    )

    pending_orders = broker.orders()

    print(
        f"Pending Practice orders found: "
        f"{len(pending_orders)}"
    )

    print(
        "\n========== RAW PENDING ORDERS =========="
    )

    for index, pending in enumerate(
        pending_orders[:3],
        start=1,
    ):
        print(
            f"\nPENDING ORDER {index}:"
        )

        print(
            json.dumps(
                pending,
                indent=2,
                default=str,
            )
        )

    print(
        "\n========== END RAW PENDING ORDERS =========="
    )


if __name__ == "__main__":
    main()