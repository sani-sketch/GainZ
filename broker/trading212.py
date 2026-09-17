"""Minimal Trading 212 Public API adapter.

Live trading is deliberately locked unless BOTH:
- environment='live' is explicitly requested
- GAINZ_ENABLE_LIVE=YES is set

Credentials are read from environment variables.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request

from broker.base import Position, OrderResult


class Trading212Error(RuntimeError):
    pass


class Trading212Broker:
    BASES = {
        "demo": "https://demo.trading212.com/api/v0",
        "live": "https://live.trading212.com/api/v0",
    }

    def __init__(
        self,
        environment: str = "demo",
        api_key: str | None = None,
        api_secret: str | None = None,
    ):
        if environment not in self.BASES:
            raise ValueError(
                "environment must be 'demo' or 'live'"
            )

        # -----------------------------------------------------
        # LIVE SAFETY LOCK
        # -----------------------------------------------------

        if (
            environment == "live"
            and os.getenv("GAINZ_ENABLE_LIVE") != "YES"
        ):
            raise Trading212Error(
                "LIVE trading is locked. "
                "Set GAINZ_ENABLE_LIVE=YES only after demo validation."
            )

        self.environment = environment
        self.base = self.BASES[environment]

        self.api_key = (
            api_key
            or os.getenv("TRADING212_API_KEY")
        )

        self.api_secret = (
            api_secret
            or os.getenv("TRADING212_API_SECRET")
        )

        if not self.api_key or not self.api_secret:
            raise Trading212Error(
                "Missing TRADING212_API_KEY/"
                "TRADING212_API_SECRET"
            )

        self._instrument_map = None

    # =========================================================
    # HTTP REQUEST
    # =========================================================

    def _request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
    ):
        credentials = base64.b64encode(
            f"{self.api_key}:{self.api_secret}".encode()
        ).decode()

        headers = {
            "Authorization": f"Basic {credentials}",
            "Accept": "application/json",
        }

        data = None

        if payload is not None:
            headers["Content-Type"] = "application/json"

            data = json.dumps(
                payload
            ).encode()

        request = urllib.request.Request(
            self.base + path,
            data=data,
            headers=headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=20,
            ) as response:

                body = response.read().decode()

                if not body:
                    return {}

                return json.loads(body)

        except urllib.error.HTTPError as exc:
            body = exc.read().decode(
                errors="replace"
            )

            raise Trading212Error(
                f"Trading 212 HTTP {exc.code}: {body}"
            ) from exc

        except urllib.error.URLError as exc:
            raise Trading212Error(
                f"Trading 212 connection error: {exc}"
            ) from exc

    # =========================================================
    # ACCOUNT
    # =========================================================

    def account_summary(self) -> dict:
        return self._request(
            "GET",
            "/equity/account/summary",
        )

    # =========================================================
    # INSTRUMENT METADATA
    # =========================================================

    def _instruments(
        self,
    ) -> dict[str, str]:

        if self._instrument_map is None:

            raw = self._request(
                "GET",
                "/equity/metadata/instruments",
            )

            items = (
                raw.get("items", raw)
                if isinstance(raw, dict)
                else raw
            )

            mapping = {}

            for item in items or []:

                ticker = str(
                    item.get(
                        "ticker",
                        "",
                    )
                )

                symbol = (
                    ticker
                    .split("_")[0]
                    .upper()
                )

                if symbol and ticker:
                    mapping.setdefault(
                        symbol,
                        ticker,
                    )

            self._instrument_map = mapping

        return self._instrument_map

    def broker_ticker(
        self,
        symbol: str,
    ) -> str:

        symbol = symbol.upper()

        try:
            return self._instruments()[
                symbol
            ]

        except KeyError as exc:
            raise Trading212Error(
                f"No Trading 212 instrument mapping "
                f"found for {symbol}"
            ) from exc

    # =========================================================
    # POSITIONS
    # =========================================================

    def positions(
        self,
    ) -> list[Position]:

        raw = self._request(
            "GET",
            "/equity/positions",
        )

        items = (
            raw.get("items", raw)
            if isinstance(raw, dict)
            else raw
        )

        output = []

        for position in items or []:

            # Trading 212 currently returns the ticker
            # inside the nested instrument object.

            instrument = position.get(
                "instrument",
                {},
            )

            if isinstance(
                instrument,
                dict,
            ):
                ticker = str(
                    instrument.get(
                        "ticker",
                        "",
                    )
                )
            else:
                ticker = ""

            symbol = (
                ticker
                .split("_")[0]
                .upper()
            )

            if not symbol:
                raise Trading212Error(
                    "Could not determine symbol "
                    f"from Trading 212 position: {position}"
                )

            quantity = float(
                position.get(
                    "quantity",
                    0.0,
                )
                or 0.0
            )

            # Trading 212's currentPrice is the
            # instrument price, e.g. USD for US stocks.

            price = float(
                position.get(
                    "currentPrice",
                    0.0,
                )
                or 0.0
            )

            # walletImpact gives us the value in the
            # Trading 212 account wallet currency.
            #
            # For your current Practice account,
            # this is GBP.

            wallet_impact = position.get(
                "walletImpact",
                {},
            )

            if isinstance(
                wallet_impact,
                dict,
            ):
                market_value = float(
                    wallet_impact.get(
                        "currentValue",
                        0.0,
                    )
                    or 0.0
                )
            else:
                market_value = 0.0

            output.append(
                Position(
                    symbol,
                    quantity,
                    price,
                    market_value,
                )
            )

        return output

    # =========================================================
    # RAW POSITIONS
    # =========================================================

    def raw_positions(
        self,
    ) -> list[dict]:

        raw = self._request(
            "GET",
            "/equity/positions",
        )

        if isinstance(
            raw,
            dict,
        ):
            return raw.get(
                "items",
                [],
            )

        return raw or []

    # =========================================================
    # PENDING / ACTIVE ORDERS
    # =========================================================

    def orders(
        self,
    ) -> list[dict]:

        raw = self._request(
            "GET",
            "/equity/orders",
        )

        if isinstance(
            raw,
            dict,
        ):
            return (
                raw.get(
                    "items",
                    [],
                )
                or []
            )

        return raw or []

    # =========================================================
    # HISTORICAL ORDERS
    # =========================================================

    def historical_orders(
        self,
        limit: int = 50,
        max_pages: int = 20,
    ) -> list[dict]:
        """
        Retrieve historical Trading 212 orders.

        READ ONLY.

        This method does not place, modify,
        or cancel any Trading 212 orders.

        Trading 212 historical endpoints use
        cursor-based pagination.
        """

        limit = max(
            1,
            min(
                int(limit),
                50,
            ),
        )

        path = (
            "/equity/history/orders"
            f"?limit={limit}"
        )

        historical = []

        for _ in range(max_pages):

            raw = self._request(
                "GET",
                path,
            )

            if not isinstance(
                raw,
                dict,
            ):
                break

            items = (
                raw.get(
                    "items",
                    [],
                )
                or []
            )

            historical.extend(
                items
            )

            next_page = raw.get(
                "nextPagePath"
            )

            if not next_page:
                break

            next_page = str(
                next_page
            )

            # self.base already contains /api/v0.
            #
            # Trading 212 may return the next page
            # beginning with /api/v0, so strip it
            # before passing it back to _request().

            prefix = "/api/v0"

            if next_page.startswith(
                prefix
            ):
                next_page = next_page[
                    len(prefix):
                ]

            if not next_page.startswith(
                "/"
            ):
                next_page = (
                    "/"
                    + next_page
                )

            path = next_page

        return historical

    # =========================================================
    # MARKET ORDER
    # =========================================================

    def market_order(
        self,
        symbol: str,
        quantity: float,
    ) -> OrderResult:

        ticker = self.broker_ticker(
            symbol
        )

        original_quantity = float(
            quantity
        )

        # Trading 212 may require different quantity
        # precision depending on the instrument.
        #
        # In DEMO mode only, retry progressively lower
        # decimal precision on precision-specific errors.

        precisions = [
            4,
            3,
            2,
            1,
            0,
        ]

        last_error = None

        for precision in precisions:

            rounded_quantity = round(
                original_quantity,
                precision,
            )

            if rounded_quantity == 0:
                continue

            payload = {
                "ticker": ticker,
                "quantity": rounded_quantity,
            }

            try:
                raw = self._request(
                    "POST",
                    "/equity/orders/market",
                    payload,
                )

                order_id = None

                if isinstance(
                    raw,
                    dict,
                ):
                    if raw.get(
                        "id"
                    ) is not None:
                        order_id = str(
                            raw.get(
                                "id"
                            )
                        )

                return OrderResult(
                    symbol=symbol,
                    quantity=rounded_quantity,
                    status="SUBMITTED",
                    order_id=order_id,
                    message=(
                        "Trading 212 DEMO "
                        "market order submitted "
                        f"with precision={precision}"
                    ),
                )

            except Trading212Error as exc:

                last_error = exc
                error_text = str(
                    exc
                )

                if (
                    "quantity-precision-mismatch"
                    not in error_text
                ):
                    raise

                # Precision retry is deliberately
                # restricted to DEMO mode.

                if self.environment != "demo":
                    raise

        raise Trading212Error(
            f"Could not submit {symbol}. "
            "Trading 212 rejected all quantity precisions. "
            f"Last error: {last_error}"
        )
