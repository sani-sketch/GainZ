from __future__ import annotations

import os

import requests
from dotenv import load_dotenv


load_dotenv()

FMP_BASE_URL = "https://financialmodelingprep.com/stable"


def _get_api_key() -> str:
    """
    Load the FMP API key from .env.
    """

    api_key = os.getenv("FMP_API_KEY")

    if not api_key:
        raise RuntimeError(
            "FMP_API_KEY is missing from .env"
        )

    return api_key


def _request(
    endpoint: str,
    params: dict | None = None,
) -> list[dict]:
    """
    Send a request to Financial Modeling Prep.
    """

    params = dict(params or {})
    params["apikey"] = _get_api_key()

    response = requests.get(
        f"{FMP_BASE_URL}/{endpoint}",
        params=params,
        timeout=20,
    )

    response.raise_for_status()

    data = response.json()

    if isinstance(data, dict) and (
        "Error Message" in data
        or "error" in data
    ):
        raise RuntimeError(
            f"FMP API error: {data}"
        )

    if not isinstance(data, list):
        raise RuntimeError(
            f"Unexpected FMP response: {data}"
        )

    return data


def get_income_statement(
    symbol: str,
    period: str = "quarter",
    limit: int = 12,
) -> list[dict]:
    """
    Fetch historical income statements.
    """

    symbol = symbol.strip().upper()

    return _request(
        "income-statement",
        {
            "symbol": symbol,
            "period": period,
            "limit": limit,
        },
    )


def get_balance_sheet(
    symbol: str,
    period: str = "quarter",
    limit: int = 12,
) -> list[dict]:
    """
    Fetch historical balance sheets.
    """

    symbol = symbol.strip().upper()

    return _request(
        "balance-sheet-statement",
        {
            "symbol": symbol,
            "period": period,
            "limit": limit,
        },
    )


def get_cash_flow_statement(
    symbol: str,
    period: str = "quarter",
    limit: int = 12,
) -> list[dict]:
    """
    Fetch historical cash-flow statements.
    """

    symbol = symbol.strip().upper()

    return _request(
        "cash-flow-statement",
        {
            "symbol": symbol,
            "period": period,
            "limit": limit,
        },
    )


def get_financial_statements(
    symbol: str,
    period: str = "quarter",
    limit: int = 12,
) -> dict:
    """
    Fetch the three core financial statements.

    No scoring is performed here.
    """

    symbol = symbol.strip().upper()

    return {
        "symbol": symbol,
        "income_statement": get_income_statement(
            symbol,
            period=period,
            limit=limit,
        ),
        "balance_sheet": get_balance_sheet(
            symbol,
            period=period,
            limit=limit,
        ),
        "cash_flow_statement": get_cash_flow_statement(
            symbol,
            period=period,
            limit=limit,
        ),
    }


if __name__ == "__main__":

    symbol = "AMD"

    print(f"Testing FMP fundamentals for {symbol}...")
    print()

    statements = get_financial_statements(
        symbol,
        period="quarter",
        limit=4,
    )

    print(
        "Income statements:",
        len(statements["income_statement"]),
    )

    print(
        "Balance sheets:",
        len(statements["balance_sheet"]),
    )

    print(
        "Cash-flow statements:",
        len(statements["cash_flow_statement"]),
    )

    print()

    if statements["income_statement"]:

        latest = statements[
            "income_statement"
        ][0]

        print("Latest income statement:")
        print("Date:", latest.get("date"))
        print(
            "Filing date:",
            latest.get("filingDate"),
        )
        print(
            "Revenue:",
            latest.get("revenue"),
        )
        print(
            "Net income:",
            latest.get("netIncome"),
        )
        print(
            "EPS:",
            latest.get("eps"),
        )