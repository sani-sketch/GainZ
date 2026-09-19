"""Minimal Trading 212 Public API adapter.

Supports demo, live, and Stocks & Shares ISA access.
ISA uses separate credentials. Real-money ISA order submission is locked unless
GAINZ_ENABLE_ISA_TRADING=YES is explicitly set.
Credentials are read from environment variables.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request

from broker.base import Position, OrderResult


class Trading212Error(RuntimeError):
    pass


class Trading212Broker:
    # API rate-limit safety. A 429 is retried only a small number of times.
    MAX_429_RETRIES = 3
    DEFAULT_429_WAIT_SECONDS = 5.0

    BASES = {
        "demo": "https://demo.trading212.com/api/v0",
        "live": "https://live.trading212.com/api/v0",
        "isa": "https://live.trading212.com/api/v0",
    }

    def __init__(
        self,
        environment: str = "demo",
        api_key: str | None = None,
        api_secret: str | None = None,
    ):
        if environment not in self.BASES:
            raise ValueError(
                "environment must be 'demo', 'live', or 'isa'"
            )

        self.environment = environment
        self.base = self.BASES[environment]

        if environment == "isa":
            default_api_key = os.getenv("TRADING212_ISA_API_KEY")
            default_api_secret = os.getenv("TRADING212_ISA_API_SECRET")
            credential_name = "ISA"
        else:
            default_api_key = os.getenv("TRADING212_API_KEY")
            default_api_secret = os.getenv("TRADING212_API_SECRET")
            credential_name = environment.upper()

        self.api_key = api_key or default_api_key
        self.api_secret = api_secret or default_api_secret

        if not self.api_key or not self.api_secret:
            raise Trading212Error(
                f"Missing Trading 212 {credential_name} API credentials."
            )

        if (
            environment == "live"
            and os.getenv("GAINZ_ENABLE_LIVE") != "YES"
        ):
            raise Trading212Error(
                "LIVE trading is locked. "
                "Set GAINZ_ENABLE_LIVE=YES only after validation."
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

        # ---------------------------------------------------------
        # Rate-limit handling
        # ---------------------------------------------------------
        # Trading 212 can return HTTP 429 when too many API calls
        # are made in a short period. Retry only 429 responses.
        #
        # IMPORTANT:
        # - POST order requests are NOT blindly retried.
        # - This protects against accidentally creating a duplicate
        #   order when the broker may have accepted a request but the
        #   response was rate-limited/lost.
        # - GET requests may be retried because they are read-only.
        # ---------------------------------------------------------

        is_read_only = method.upper() in {
            "GET",
            "HEAD",
            "OPTIONS",
        }

        max_retries = (
            self.MAX_429_RETRIES
            if is_read_only
            else 0
        )

        for attempt in range(max_retries + 1):

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

                if exc.code == 429 and attempt < max_retries:

                    retry_after = None

                    try:
                        raw_retry_after = (
                            exc.headers.get("Retry-After")
                        )

                        if raw_retry_after:
                            retry_after = float(
                                raw_retry_after
                            )

                    except (
                        TypeError,
                        ValueError,
                    ):
                        retry_after = None

                    if retry_after is None:
                        retry_after = (
                            self.DEFAULT_429_WAIT_SECONDS
                            * (attempt + 1)
                        )

                    retry_after = max(
                        1.0,
                        min(
                            retry_after,
                            60.0,
                        ),
                    )

                    time.sleep(retry_after)
                    continue

                if exc.code == 429:

                    raise Trading212Error(
                        "Trading 212 HTTP 429: too many requests. "
                        "Read-only API retries were exhausted. "
                        "Wait before trying again."
                    ) from exc

                raise Trading212Error(
                    f"Trading 212 HTTP {exc.code}: {body}"
                ) from exc

            except urllib.error.URLError as exc:

                raise Trading212Error(
                    f"Trading 212 connection error: {exc}"
                ) from exc

        raise Trading212Error(
            "Trading 212 request failed after rate-limit retries."
        )

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

        if (
            self.environment == "isa"
            and os.getenv("GAINZ_ENABLE_ISA_TRADING") != "YES"
        ):
            raise Trading212Error(
                "ISA order submission is locked. "
                "Set GAINZ_ENABLE_ISA_TRADING=YES only after "
                "the real-money dashboard and confirmation flow "
                "have been validated."
            )

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
                        f"Trading 212 {self.environment.upper()} "
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
