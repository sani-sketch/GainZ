from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv

from broker.trading212 import Trading212Broker, Trading212Error


ROOT = Path(__file__).resolve().parent

# Load the existing GainZ credentials.
load_dotenv(ROOT / ".env")


def main() -> None:
    """
    Cancel NEW Trading 212 Practice orders created through the API.

    SAFETY:
    - This script is hard-coded to Trading 212 Practice / Demo.
    - It cannot cancel live/ISA orders.
    - It only considers orders with status NEW.
    - It only considers orders marked initiatedFrom=API.
    - It prints the complete list before doing anything.
    - It requires the user to type the exact confirmation phrase.
    - It verifies the remaining pending-order count afterwards.

    Trading 212 documents DELETE /equity/orders/{id} as the
    order-cancellation endpoint.
    """

    broker = Trading212Broker(
        environment="demo"
    )

    if broker.environment != "demo":
        raise RuntimeError(
            "SAFETY STOP: This script is Practice-only."
        )

    pending_orders = broker.orders()

    print(
        f"\nPending Practice orders found: "
        f"{len(pending_orders)}"
    )

    if not pending_orders:
        print(
            "\nNothing to cancel. "
            "Practice account already has 0 pending orders."
        )
        return

    print(
        "\n========== ORDERS TO REVIEW =========="
    )

    candidates = []

    for order in pending_orders:
        status = str(
            order.get("status", "")
        ).upper()

        initiated_from = str(
            order.get("initiatedFrom", "")
        ).upper()

        if (
            status == "NEW"
            and initiated_from == "API"
        ):
            candidates.append(order)

            print(
                f"ID={order.get('id')} | "
                f"{order.get('ticker')} | "
                f"{order.get('side')} | "
                f"quantity={order.get('quantity')} | "
                f"status={status} | "
                f"source={initiated_from}"
            )

    print(
        "\n========== END REVIEW =========="
    )

    if not candidates:
        print(
            "\nNo NEW API-created Practice orders "
            "were found. Nothing was cancelled."
        )
        return

    print(
        f"\nCandidate orders: {len(candidates)}"
    )

    print(
        "\nSAFETY CONFIRMATION"
    )

    print(
        "The orders above will be CANCELLED "
        "from Trading 212 Practice."
    )

    print(
        "This script will NOT touch Live or ISA."
    )

    confirmation = input(
        '\nType exactly CANCEL PRACTICE ORDERS to continue: '
    ).strip()

    if confirmation != "CANCEL PRACTICE ORDERS":
        print(
            "\nCancelled by user. "
            "No orders were modified."
        )
        return

    print(
        "\nStarting Practice-order cancellation..."
    )

    cancelled = 0
    failed = 0

    for order in candidates:

        order_id = order.get("id")

        if order_id is None:
            print(
                f"SKIP: {order.get('ticker')} "
                "has no order ID."
            )
            failed += 1
            continue

        path = (
            f"/equity/orders/{order_id}"
        )

        try:
            broker._request(
                "DELETE",
                path,
            )

            cancelled += 1

            print(
                f"CANCELLED: "
                f"{order.get('ticker')} "
                f"(ID {order_id})"
            )

        except Trading212Error as exc:

            failed += 1

            print(
                f"FAILED: "
                f"{order.get('ticker')} "
                f"(ID {order_id})"
            )

            print(
                f"  {exc}"
            )

    print(
        "\n========== CANCELLATION SUMMARY =========="
    )

    print(
        f"Cancelled: {cancelled}"
    )

    print(
        f"Failed: {failed}"
    )

    # --------------------------------------------------------
    # Verify the broker state after cancellation.
    # --------------------------------------------------------

    remaining = broker.orders()

    print(
        f"Remaining pending Practice orders: "
        f"{len(remaining)}"
    )

    if remaining:
        print(
            "\nRemaining orders:"
        )

        for order in remaining:
            print(
                json.dumps(
                    order,
                    indent=2,
                    default=str,
                )
            )

        print(
            "\nPractice account is NOT yet clean."
        )

    else:
        print(
            "\nSUCCESS: Practice account now has "
            "0 pending orders."
        )


if __name__ == "__main__":
    main()
