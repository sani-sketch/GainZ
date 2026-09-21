import json
import os
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import subprocess
import sys
from pathlib import Path
import html

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from portfolio.history import (
    save_portfolio_snapshot,
    load_portfolio_history,
    calculate_daily_performance,
)
from portfolio.realized_pnl import (
    calculate_realized_pnl,
    get_today_realized_pnl,
)

from broker.trading212 import Trading212Broker, Trading212Error
from execution.planner import PlannedOrder
from execution.engine import execute_orders
from run_trading212 import (
    SETTINGS,
    MAX_POSITION_WEIGHT,
    MAX_ORDER_WEIGHT,
    MAX_EXPOSURE_WEIGHT,
    MAX_DAILY_LOSS_WEIGHT,
    build_new_cash_orders,
    get_usd_to_gbp_rate,
    load_prices,
)


# ============================================================
# CONFIG
# ============================================================

ROOT = Path(__file__).resolve().parent
REPORT_PATH = ROOT / "outputs" / "trading212_demo_report.json"
RUNNER_PATH = ROOT / "run_trading212.py"
ENV_PATH = ROOT / ".env"
PAUSE_PATH = ROOT / "outputs" / "gainz_paused.flag"

load_dotenv(ENV_PATH)

st.set_page_config(
    page_title="SF Alpha",
    page_icon="◈",
    layout="wide",
)

CACHE_TTL = 120


# ============================================================
# BROKER READS
# ============================================================
@st.cache_data(ttl=CACHE_TTL)
def get_account_summary():
    broker = Trading212Broker(environment="demo")
    return broker.account_summary()


@st.cache_data(ttl=CACHE_TTL)
def get_raw_positions():
    broker = Trading212Broker(environment="demo")
    return broker.raw_positions()


@st.cache_data(ttl=CACHE_TTL)
def get_orders():
    broker = Trading212Broker(environment="demo")
    return broker.orders()


@st.cache_data(ttl=CACHE_TTL)
def get_historical_orders():
    """Read historical Trading 212 Practice orders. Read only."""
    broker = Trading212Broker(environment="demo")
    return broker.historical_orders()


@st.cache_data(ttl=CACHE_TTL)
def get_isa_account_summary():
    """Read Trading 212 Stocks ISA account summary. Read only."""
    broker = Trading212Broker(environment="isa")
    return broker.account_summary()


@st.cache_data(ttl=CACHE_TTL)
def get_isa_raw_positions():
    """Read Trading 212 Stocks ISA positions. Read only."""
    broker = Trading212Broker(environment="isa")
    return broker.raw_positions()


@st.cache_data(ttl=CACHE_TTL)
def get_isa_orders():
    """Read Trading 212 Stocks ISA pending orders. Read only."""
    broker = Trading212Broker(environment="isa")
    return broker.orders()


@st.cache_data(ttl=CACHE_TTL)
def get_isa_historical_orders():
    """Read Trading 212 Stocks ISA historical orders. Read only."""
    broker = Trading212Broker(environment="isa")
    return broker.historical_orders()


# ============================================================
# GENERAL HELPERS
# ============================================================

def credentials_present():
    key = os.getenv("TRADING212_API_KEY")
    secret = os.getenv("TRADING212_API_SECRET")

    return bool(
        key
        and secret
        and key != "replace_me"
        and secret != "replace_me"
    )


def isa_credentials_present():
    key = os.getenv("TRADING212_ISA_API_KEY")
    secret = os.getenv("TRADING212_ISA_API_SECRET")

    return bool(
        key
        and secret
        and key != "replace_me"
        and secret != "replace_me"
    )


def load_report():
    if not REPORT_PATH.exists():
        return {}

    try:
        return json.loads(
            REPORT_PATH.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return {}


def run_gainz(execute_demo=False, investment_amount=None):
    command = [
        sys.executable,
        str(RUNNER_PATH),
    ]

    if investment_amount is not None:
        command.extend([
            "--investment-amount",
            str(float(investment_amount)),
        ])

    if execute_demo:
        command.append("--execute-demo")

    try:
        result = subprocess.run(
            command,
            cwd=str(ROOT),
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=180,
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    except Exception as exc:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(exc),
        }


def friendly_strategy(name):
    mapping = {
        "N15_momentum_trend_none": "Momentum + Trend",
    }

    return mapping.get(
        name,
        name or "Unknown",
    )


def friendly_risk(name):
    mapping = {
        "vol12_defensive": "Defensive",
    }

    return mapping.get(
        name,
        name or "Unknown",
    )


def float_value(value, default=0.0):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return default


def flatten_historical_order(record):
    """Convert Trading 212 historical order/fill payload into dashboard columns."""
    if not isinstance(record, dict):
        return {}

    order = record.get("order", {}) or {}
    fill = record.get("fill", {}) or {}
    instrument = order.get("instrument", {}) or {}
    wallet = fill.get("walletImpact", {}) or {}

    ticker = symbol_from_ticker(
        order.get("ticker")
        or instrument.get("ticker")
        or ""
    )

    return {
        "Ticker": ticker,
        "Side": str(order.get("side", "")).upper(),
        "Qty": float_value(
            fill.get("quantity", order.get("filledQuantity", order.get("quantity", 0)))
        ),
        "Price": float_value(fill.get("price", 0)),
        "Status": str(order.get("status", "")),
        "Filled At": fill.get("filledAt") or order.get("createdAt") or "",
        "Net Value": float_value(wallet.get("netValue", 0)),
        "Currency": wallet.get("currency") or order.get("currency") or "",
    }


def is_rate_limit_error(error):
    if not error:
        return False

    text = str(error).lower()

    return (
        "429" in text
        or "toomanyrequests" in text
        or "too many requests" in text
    )


# ============================================================
# TICKER HELPERS
# ============================================================

def symbol_from_ticker(ticker):
    ticker = str(ticker or "").strip()

    if not ticker:
        return "Unknown"

    if "_" in ticker:
        return ticker.split("_")[0]

    return ticker


def extract_position_symbol(position):
    """
    Trading 212 position format:

    {
        "instrument": {
            "ticker": "PANW_US_EQ",
            "name": "Palo Alto Networks",
            "isin": "...",
            "currency": "USD"
        },
        ...
    }
    """

    if not isinstance(position, dict):
        return "Unknown"

    instrument = position.get(
        "instrument",
        {}
    )

    if isinstance(instrument, dict):

        ticker = instrument.get(
            "ticker"
        )

        if ticker:
            return symbol_from_ticker(
                ticker
            )

        symbol = instrument.get(
            "symbol"
        )

        if symbol:
            return symbol_from_ticker(
                symbol
            )

        name = instrument.get(
            "name"
        )

        if name:
            return str(name)

    if isinstance(instrument, str):
        return symbol_from_ticker(
            instrument
        )

    return "Unknown"


def extract_position_name(position):
    instrument = position.get(
        "instrument",
        {}
    )

    if isinstance(instrument, dict):
        return str(
            instrument.get(
                "name",
                ""
            )
        )

    return ""


def extract_position_currency(position):
    instrument = position.get(
        "instrument",
        {}
    )

    if isinstance(instrument, dict):
        return str(
            instrument.get(
                "currency",
                ""
            )
        )

    return ""


def extract_position_isin(position):
    instrument = position.get("instrument", {}) or {}
    if isinstance(instrument, dict):
        return str(instrument.get("isin", "") or "").strip()
    return ""


def ticker_logo_url(position):
    """
    Real security/provider logo via Parqet.
    Prefer ISIN because it works better for ETFs and non-US listings.
    """
    isin = extract_position_isin(position)
    symbol = extract_position_symbol(position)

    if isin:
        return (
            "https://assets.parqet.com/logos/isin/"
            f"{isin}?format=png&size=96"
        )

    if symbol and symbol != "Unknown":
        return (
            "https://assets.parqet.com/logos/symbol/"
            f"{symbol}?format=png&size=96"
        )

    return ""


def symbol_logo_url(symbol):
    """Return a real company/security logo URL for a plain ticker symbol."""
    symbol = symbol_from_ticker(symbol)

    if not symbol or symbol == "Unknown":
        return ""

    return (
        "https://assets.parqet.com/logos/symbol/"
        f"{symbol}?format=png&size=96"
    )


def ticker_logo_html(symbol, size=28):
    """HTML logo with a clean ticker fallback if the remote image fails."""
    clean_symbol = symbol_from_ticker(symbol)
    logo = symbol_logo_url(clean_symbol)

    if not logo:
        return (
            f'<span class="sf-inline-logo-fallback">'
            f'{html.escape(clean_symbol[:2])}</span>'
        )

    return (
        f'<img class="sf-inline-ticker-logo" '
        f'style="width:{int(size)}px;height:{int(size)}px;" '
        f'src="{html.escape(logo)}" '
        f'alt="{html.escape(clean_symbol)} logo" '
        f'onerror="this.style.display=\'none\';" />'
    )


def add_logo_column(df, ticker_column="Ticker"):
    """Add a real-logo image column to a dataframe containing tickers."""
    if df is None or df.empty or ticker_column not in df.columns:
        return df

    result = df.copy()
    result.insert(
        0,
        "Logo",
        result[ticker_column].map(symbol_logo_url),
    )
    return result


LOGO_COLUMN_CONFIG = {
    "Logo": st.column_config.ImageColumn(
        " ",
        width="small",
    )
}


def render_holding_card(position, portfolio_total, currency_symbol="£"):
    symbol = extract_position_symbol(position)
    name = extract_position_name(position) or symbol
    logo = ticker_logo_url(position)

    quantity = float_value(position.get("quantity"))
    wallet = position.get("walletImpact", {}) or {}
    value = float_value(wallet.get("currentValue"))
    pnl = float_value(wallet.get("unrealizedProfitLoss"))
    cost = float_value(wallet.get("totalCost"))
    return_pct = (pnl / cost * 100) if cost else 0.0
    weight = (value / portfolio_total * 100) if portfolio_total else 0.0

    pnl_class = "sf-green" if pnl >= 0 else "sf-red"
    logo_html = (
        f'<img class="sf-ticker-logo" src="{html.escape(logo)}" '
        f'alt="{html.escape(symbol)} logo" />'
        if logo
        else f'<div class="sf-logo-fallback">{html.escape(symbol[:2])}</div>'
    )

    st.markdown(
        f"""
        <div class="sf-holding-card">
            <div class="sf-holding-left">
                {logo_html}
                <div>
                    <div class="sf-holding-symbol">{html.escape(symbol)}</div>
                    <div class="sf-holding-name">{html.escape(name)}</div>
                    <div class="sf-holding-meta">
                        {quantity:,.6f} units • {weight:.1f}% of portfolio
                    </div>
                </div>
            </div>
            <div class="sf-holding-right">
                <div class="sf-holding-value">
                    {currency_symbol}{value:,.2f}
                </div>
                <div class="{pnl_class}">
                    {currency_symbol}{pnl:+,.2f} • {return_pct:+.2f}%
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# TRADING 212 ACCOUNT MAPPING
# ============================================================

def extract_currency(account):
    if not isinstance(account, dict):
        return "GBP"

    return str(
        account.get(
            "currency",
            "GBP",
        )
    )


def extract_total_value(account):
    if not isinstance(account, dict):
        return 0.0

    return float_value(
        account.get(
            "totalValue",
            0,
        )
    )


def extract_cash(account):
    if not isinstance(account, dict):
        return 0.0

    cash = account.get(
        "cash",
        {},
    )

    if isinstance(cash, dict):
        return float_value(
            cash.get(
                "availableToTrade",
                0,
            )
        )

    return 0.0


def extract_reserved_cash(account):
    if not isinstance(account, dict):
        return 0.0

    cash = account.get(
        "cash",
        {},
    )

    if isinstance(cash, dict):
        return float_value(
            cash.get(
                "reservedForOrders",
                0,
            )
        )

    return 0.0


def extract_investment_value(account):
    if not isinstance(account, dict):
        return 0.0

    investments = account.get(
        "investments",
        {},
    )

    if isinstance(investments, dict):
        return float_value(
            investments.get(
                "currentValue",
                0,
            )
        )

    return 0.0


def extract_total_cost(account):
    if not isinstance(account, dict):
        return 0.0

    investments = account.get(
        "investments",
        {},
    )

    if isinstance(investments, dict):
        return float_value(
            investments.get(
                "totalCost",
                0,
            )
        )

    return 0.0


def extract_realized_ppl(account):
    if not isinstance(account, dict):
        return 0.0

    investments = account.get(
        "investments",
        {},
    )

    if isinstance(investments, dict):
        return float_value(
            investments.get(
                "realizedProfitLoss",
                0,
            )
        )

    return 0.0


def extract_unrealized_ppl(account):
    if not isinstance(account, dict):
        return 0.0

    investments = account.get(
        "investments",
        {},
    )

    if isinstance(investments, dict):
        return float_value(
            investments.get(
                "unrealizedProfitLoss",
                0,
            )
        )

    return 0.0


def extract_total_ppl(account):
    return (
        extract_realized_ppl(account)
        + extract_unrealized_ppl(account)
    )


# ============================================================
# SAFE FETCH
# ============================================================

def fetch_with_fallback(
    cache_key,
    fetch_function,
):
    try:
        value = fetch_function()

        st.session_state[
            cache_key
        ] = value

        return value, None

    except Exception as exc:

        previous_value = st.session_state.get(
            cache_key
        )

        return previous_value, str(exc)



# ============================================================
# MANUAL PRACTICE SELL
# ============================================================

def gainz_is_paused():
    return PAUSE_PATH.exists()


def set_gainz_paused(paused):
    PAUSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if paused:
        PAUSE_PATH.write_text("PAUSED", encoding="utf-8")
    elif PAUSE_PATH.exists():
        PAUSE_PATH.unlink()


def submit_practice_sell_all(raw_positions):
    """Submit sell orders for every open Trading 212 Practice position."""
    broker = Trading212Broker(environment="demo")
    results = []

    for position in raw_positions:
        symbol = extract_position_symbol(position)
        available = float_value(
            position.get(
                "quantityAvailableForTrading",
                position.get("quantity", 0),
            )
        )

        if symbol == "Unknown" or available <= 0:
            continue

        try:
            result = broker.market_order(symbol, -abs(available))
            results.append({
                "symbol": symbol,
                "quantity": available,
                "status": str(getattr(result, "status", "SUBMITTED")),
                "order_id": getattr(result, "order_id", None),
                "message": str(getattr(result, "message", "")),
            })
        except Exception as exc:
            results.append({
                "symbol": symbol,
                "quantity": available,
                "status": "ERROR",
                "order_id": None,
                "message": str(exc),
            })
            break

    return results


# ============================================================
# MANUAL ISA ORDERS — EXPLICIT BUTTON + CONFIRMATION ONLY
# ============================================================

def submit_manual_isa_order(symbol, quantity):
    """
    Submit exactly one manually confirmed Stocks ISA market order.

    This helper is only called from the Stocks ISA BUY/SELL confirmation UI.
    It is never called by strategy runs, page loads, refreshes, or GitHub Actions.
    """
    broker = Trading212Broker(environment="isa")

    if broker.environment != "isa":
        raise Trading212Error("Manual ISA order blocked: broker is not in ISA mode.")

    if os.getenv("GAINZ_ENABLE_ISA_TRADING") != "YES":
        raise Trading212Error(
            "ISA order submission is locked. "
            "Set GAINZ_ENABLE_ISA_TRADING=YES to permit a manually confirmed order."
        )

    pending = broker.orders()
    if pending:
        raise Trading212Error(
            f"Manual ISA order blocked: {len(pending)} pending ISA order(s) already exist."
        )

    symbol = str(symbol or "").strip().upper()
    quantity = float(quantity)

    if not symbol:
        raise Trading212Error("Manual ISA order blocked: ticker is required.")

    if quantity == 0:
        raise Trading212Error("Manual ISA order blocked: quantity must be non-zero.")

    return broker.market_order(symbol, quantity)


# ============================================================
# ISA GAINZ BUY — FROZEN PREVIEW + EXECUTION HELPERS
# ============================================================

def isa_position_signature(raw_positions):
    """Stable symbol/quantity signature used to detect portfolio changes."""
    rows = []

    for position in raw_positions or []:
        symbol = extract_position_symbol(position)
        quantity = float_value(
            position.get(
                "quantityAvailableForTrading",
                position.get("quantity", 0),
            )
        )

        if symbol != "Unknown" and quantity > 0:
            rows.append(
                (
                    str(symbol).strip().upper(),
                    round(float(quantity), 8),
                )
            )

    return sorted(rows)


def build_isa_gainz_preview(investment_amount, target_weights):
    """
    Build and risk-check an ISA-specific BUY-only plan.

    This never submits an order. The returned order quantities are frozen
    into session state and are the only quantities eligible for confirmation.
    """
    broker = Trading212Broker(environment="isa")

    account = broker.account_summary()
    raw_positions = broker.raw_positions()
    positions = broker.positions()
    pending_orders = broker.orders()

    if pending_orders:
        raise Trading212Error(
            f"ISA investment preview blocked: {len(pending_orders)} "
            "pending ISA order(s) already exist."
        )

    cash = extract_cash(account)
    amount = float(investment_amount)

    if amount <= 0:
        raise Trading212Error(
            "ISA investment amount must be greater than £0."
        )

    if amount > cash:
        raise Trading212Error(
            f"Requested ISA investment £{amount:.2f} exceeds "
            f"available cash £{cash:.2f}."
        )

    positive_weights = {
        str(symbol).strip().upper(): float_value(weight)
        for symbol, weight in (target_weights or {}).items()
        if float_value(weight) > 0
    }

    if not positive_weights:
        raise Trading212Error(
            "GainZ has no positive target weights available."
        )

    prices = {}
    for symbol in positive_weights:
        price_frame = load_prices(symbol)
        if price_frame.empty:
            continue
        prices[symbol] = float(price_frame["Close"].iloc[-1])

    usd_to_gbp = get_usd_to_gbp_rate()

    planned_orders = build_new_cash_orders(
        weights=positive_weights,
        deployment_cash=amount,
        prices=prices,
        usd_to_gbp=usd_to_gbp,
    )

    if not planned_orders:
        raise Trading212Error(
            "GainZ produced no executable ISA BUY orders."
        )

    invested_value = sum(
        float(position.market_value)
        for position in positions
    )
    equity = float(cash) + invested_value

    historical_orders = broker.historical_orders()
    realized_analysis = calculate_realized_pnl(historical_orders)
    today_realized_pnl = get_today_realized_pnl(realized_analysis)

    risk_results = execute_orders(
        broker=broker,
        orders=planned_orders,
        dry_run=True,
        positions=positions,
        equity=equity,
        pending_orders=pending_orders,
        max_position_weight=MAX_POSITION_WEIGHT,
        max_order_weight=MAX_ORDER_WEIGHT,
        max_exposure_weight=MAX_EXPOSURE_WEIGHT,
        today_realized_pnl=today_realized_pnl,
        max_daily_loss_weight=MAX_DAILY_LOSS_WEIGHT,
    )

    frozen_orders = []
    result_rows = []

    for order, result in zip(planned_orders, risk_results):
        status = str(
            getattr(result, "status", "") or ""
        ).upper()

        result_rows.append(
            {
                "symbol": order.symbol,
                "side": "BUY",
                "quantity": float(order.quantity),
                "reference_price": float(order.reference_price),
                "estimated_value": float(order.estimated_value),
                "status": status,
                "message": str(
                    getattr(result, "message", "") or ""
                ),
            }
        )

        if status == "DRY_RUN_APPROVED":
            frozen_orders.append(
                {
                    "symbol": str(order.symbol).strip().upper(),
                    "quantity": float(order.quantity),
                    "reference_price": float(order.reference_price),
                    "estimated_value": float(order.estimated_value),
                }
            )

    return {
        "amount": amount,
        "cash_at_preview": float(cash),
        "position_signature": isa_position_signature(raw_positions),
        "orders": result_rows,
        "frozen_orders": frozen_orders,
        "all_approved": (
            bool(result_rows)
            and len(frozen_orders) == len(result_rows)
        ),
        "usd_to_gbp": float(usd_to_gbp),
    }


def execute_frozen_isa_buy_preview(preview):
    """
    Revalidate then submit exactly the BUY quantities frozen in the preview.

    No strategy recalculation occurs between preview and confirmation.
    """
    if os.getenv("GAINZ_ENABLE_ISA_TRADING") != "YES":
        raise Trading212Error(
            "ISA order submission is locked."
        )

    broker = Trading212Broker(environment="isa")

    pending_orders = broker.orders()
    if pending_orders:
        raise Trading212Error(
            f"ISA investment blocked: {len(pending_orders)} "
            "pending ISA order(s) already exist."
        )

    account = broker.account_summary()
    cash = extract_cash(account)
    amount = float(preview.get("amount", 0.0))

    if amount <= 0:
        raise Trading212Error(
            "ISA investment blocked: invalid frozen investment amount."
        )

    if amount > cash:
        raise Trading212Error(
            f"ISA investment blocked: available cash is now £{cash:.2f}, "
            f"below the confirmed £{amount:.2f} amount."
        )

    raw_positions = broker.raw_positions()
    current_signature = isa_position_signature(raw_positions)
    frozen_signature = sorted(
        [
            (
                str(symbol).strip().upper(),
                round(float(quantity), 8),
            )
            for symbol, quantity in preview.get(
                "position_signature",
                [],
            )
        ]
    )

    if current_signature != frozen_signature:
        raise Trading212Error(
            "ISA investment blocked because the live holdings changed "
            "after the preview. Build the portfolio again."
        )

    frozen_rows = preview.get("frozen_orders", []) or []
    if not frozen_rows:
        raise Trading212Error(
            "ISA investment blocked: the frozen preview contains no orders."
        )

    planned_orders = [
        PlannedOrder(
            symbol=str(row["symbol"]).strip().upper(),
            side="BUY",
            quantity=float(row["quantity"]),
            reference_price=float(row["reference_price"]),
            estimated_value=float(row["estimated_value"]),
        )
        for row in frozen_rows
    ]

    positions = broker.positions()
    invested_value = sum(
        float(position.market_value)
        for position in positions
    )
    equity = float(cash) + invested_value

    historical_orders = broker.historical_orders()
    realized_analysis = calculate_realized_pnl(historical_orders)
    today_realized_pnl = get_today_realized_pnl(realized_analysis)

    recheck = execute_orders(
        broker=broker,
        orders=planned_orders,
        dry_run=True,
        positions=positions,
        equity=equity,
        pending_orders=[],
        max_position_weight=MAX_POSITION_WEIGHT,
        max_order_weight=MAX_ORDER_WEIGHT,
        max_exposure_weight=MAX_EXPOSURE_WEIGHT,
        today_realized_pnl=today_realized_pnl,
        max_daily_loss_weight=MAX_DAILY_LOSS_WEIGHT,
    )

    blocked = [
        result
        for result in recheck
        if str(getattr(result, "status", "")).upper()
        != "DRY_RUN_APPROVED"
    ]

    if blocked:
        first = blocked[0]
        raise Trading212Error(
            "ISA investment blocked by the current risk checks: "
            + str(getattr(first, "message", "") or "risk check failed")
        )

    submitted = []

    for order in planned_orders:
        try:
            result = broker.market_order(
                order.symbol,
                abs(float(order.quantity)),
            )

            status = str(
                getattr(result, "status", "SUBMITTED")
                or "SUBMITTED"
            ).upper()

            submitted.append(
                {
                    "symbol": order.symbol,
                    "quantity": float(order.quantity),
                    "status": status,
                    "order_id": getattr(result, "order_id", None),
                    "message": str(
                        getattr(result, "message", "") or ""
                    ),
                }
            )

            if status in {"REJECTED", "FAILED", "ERROR"}:
                break

        except Exception as exc:
            submitted.append(
                {
                    "symbol": order.symbol,
                    "quantity": float(order.quantity),
                    "status": "ERROR",
                    "order_id": None,
                    "message": str(exc),
                }
            )
            break

    return submitted


# ============================================================
# SF ALPHA UI / SIDEBAR
# ============================================================

st.markdown(
    """
    <style>
    :root {
        --sf-bg: #070b10;
        --sf-panel: #0d131a;
        --sf-panel-2: #111820;
        --sf-border: rgba(192, 200, 210, 0.16);
        --sf-silver: #d9dee5;
        --sf-muted: #8f9aaa;
        --sf-green: #24e0a4;
        --sf-red: #ff5c5c;
    }

    .stApp {
        background:
            radial-gradient(circle at 72% -10%, rgba(120,130,145,.08), transparent 28%),
            linear-gradient(180deg, #070b10 0%, #090e14 100%);
        color: var(--sf-silver);
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0b1118 0%, #0a0f15 100%);
        border-right: 1px solid var(--sf-border);
    }

    [data-testid="stSidebar"] > div:first-child {
        padding-top: 1.25rem;
    }

    .sf-monogram {
        width: 46px;
        height: 46px;
        border: 1px solid rgba(220,225,232,.30);
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 0 auto .85rem auto;
        font-family: Georgia, serif;
        font-size: 1.35rem;
        color: #eef1f5;
        box-shadow: inset 0 0 18px rgba(255,255,255,.025);
    }

    .sf-brand {
        padding: .45rem .25rem 1.25rem .25rem;
        border-bottom: 1px solid var(--sf-border);
        margin-bottom: 1rem;
    }

    .sf-brand-title {
        font-size: 1.25rem;
        font-weight: 500;
        letter-spacing: .30rem;
        color: #eef1f5;
        text-align: center;
    }

    .sf-brand-sub {
        color: var(--sf-muted);
        font-size: .72rem;
        margin-top: .35rem;
        text-align: center;
    }

    .sf-header {
        padding: .25rem 0 .9rem 0;
    }

    .sf-title {
        font-size: 2.05rem;
        font-weight: 600;
        letter-spacing: -.03em;
        color: #f2f4f7;
    }

    .sf-subtitle {
        color: var(--sf-muted);
        margin-top: .15rem;
    }

    div[data-testid="stMetric"] {
        background: linear-gradient(145deg, rgba(18,25,33,.96), rgba(10,15,21,.96));
        border: 1px solid var(--sf-border);
        border-radius: 14px;
        padding: 1rem 1.05rem;
        box-shadow: 0 10px 28px rgba(0,0,0,.16);
    }

    div[data-testid="stMetric"] label {
        color: #aab3bf !important;
    }

    div[data-testid="stMetricValue"] {
        color: #f2f4f7;
    }

    div[data-testid="stDataFrame"],
    div[data-testid="stExpander"] {
        border-radius: 14px;
    }

    .stButton > button {
        border-radius: 10px;
        border: 1px solid rgba(210,216,224,.20);
        background: linear-gradient(180deg, #171e27, #10161e);
    }

    .stButton > button:hover {
        border-color: rgba(230,234,240,.55);
    }

    hr {
        border-color: rgba(192,200,210,.12) !important;
    }

    h1, h2, h3 {
        letter-spacing: -.02em;
    }

    .block-container {
        padding-top: 3.6rem;
        padding-bottom: 2rem;
        max-width: 1500px;
    }

    [data-testid="stSidebar"] [role="radiogroup"] > label {
        padding: .35rem .35rem;
        border-radius: 9px;
    }

    [data-testid="stSidebar"] [role="radiogroup"] > label:hover {
        background: rgba(255,255,255,.035);
    }

    .sf-panel {
        background: linear-gradient(145deg, rgba(17,24,32,.97), rgba(10,15,21,.97));
        border: 1px solid var(--sf-border);
        border-radius: 14px;
        padding: 1rem 1.1rem;
        min-height: 100%;
    }

    .sf-panel-title {
        color: #eef1f5;
        font-size: 1rem;
        font-weight: 600;
        margin-bottom: .65rem;
    }

    .sf-muted { color: var(--sf-muted); }
    .sf-green { color: var(--sf-green); }
    .sf-red { color: var(--sf-red); }

    .sf-topbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 1rem;
        margin: .55rem 0 1.15rem 0;
        position: relative;
        z-index: 2;
    }

    .sf-search {
        flex: 1;
        max-width: 560px;
        padding: .72rem 1rem;
        border: 1px solid var(--sf-border);
        border-radius: 12px;
        background: rgba(13,19,26,.92);
        color: #8995a5;
        font-size: .84rem;
    }

    .sf-env {
        padding: .62rem .9rem;
        border: 1px solid rgba(36,224,164,.22);
        border-radius: 999px;
        background: rgba(36,224,164,.06);
        color: #35dda7;
        font-size: .80rem;
        white-space: nowrap;
    }

    .sf-lock {
        color: #8f9aaa;
        font-size: .78rem;
        white-space: nowrap;
    }

    .sf-perf-shell {
        min-height: 285px;
        background:
            linear-gradient(180deg, rgba(17,24,32,.98), rgba(9,14,20,.98));
        border: 1px solid var(--sf-border);
        border-radius: 14px;
        padding: 1.05rem 1.15rem;
    }

    .sf-perf-empty {
        height: 185px;
        margin-top: .85rem;
        border-top: 1px solid rgba(192,200,210,.08);
        display: flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        color: #758190;
        font-size: .82rem;
        background:
            linear-gradient(rgba(192,200,210,.035) 1px, transparent 1px),
            linear-gradient(90deg, rgba(192,200,210,.035) 1px, transparent 1px);
        background-size: 100% 46px, 90px 100%;
    }

    .sf-mini-card {
        background: linear-gradient(145deg, rgba(17,24,32,.97), rgba(10,15,21,.97));
        border: 1px solid var(--sf-border);
        border-radius: 14px;
        padding: 1rem 1.05rem;
        min-height: 250px;
    }

    .sf-order-row, .sf-status-row {
        display: grid;
        align-items: center;
        gap: .55rem;
        padding: .48rem 0;
        border-bottom: 1px solid rgba(192,200,210,.07);
        font-size: .82rem;
    }

    .sf-order-row {
        grid-template-columns: 54px 1fr .7fr .85fr;
    }

    .sf-status-row {
        grid-template-columns: 18px 1fr;
    }

    .sf-badge-buy, .sf-badge-sell {
        display: inline-block;
        text-align: center;
        border-radius: 999px;
        padding: .22rem .42rem;
        font-size: .70rem;
        font-weight: 700;
    }

    .sf-badge-buy {
        color: #42e7b1;
        background: rgba(36,224,164,.12);
        border: 1px solid rgba(36,224,164,.18);
    }

    .sf-badge-sell {
        color: #ff7777;
        background: rgba(255,92,92,.12);
        border: 1px solid rgba(255,92,92,.18);
    }

    .sf-dot-ok {
        width: 9px; height: 9px; border-radius: 50%;
        background: #24e0a4;
        box-shadow: 0 0 10px rgba(36,224,164,.35);
    }

    .sf-dot-warn {
        width: 9px; height: 9px; border-radius: 50%;
        background: #d9dee5;
        opacity: .55;
    }

    .sf-status {
        display: inline-block;
        padding: .38rem .72rem;
        border: 1px solid rgba(36,224,164,.24);
        background: rgba(36,224,164,.07);
        border-radius: 999px;
        color: #42e7b1;
        font-size: .82rem;
        margin-top: .35rem;
    }

    .sf-holding-card {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        padding: .95rem 1rem;
        margin: .55rem 0;
        border: 1px solid var(--sf-border);
        border-radius: 14px;
        background: linear-gradient(145deg, rgba(17,24,32,.97), rgba(10,15,21,.97));
        transition: transform .16s ease, border-color .16s ease;
    }

    .sf-holding-card:hover {
        transform: translateY(-2px);
        border-color: rgba(220,225,232,.34);
    }

    .sf-holding-left {
        display: flex;
        align-items: center;
        gap: .85rem;
        min-width: 0;
    }

    .sf-ticker-logo, .sf-logo-fallback {
        width: 44px;
        height: 44px;
        border-radius: 12px;
        background: #f4f5f7;
        object-fit: contain;
        padding: 5px;
        flex: 0 0 44px;
    }

    .sf-logo-fallback {
        display: flex;
        align-items: center;
        justify-content: center;
        color: #111820;
        font-weight: 800;
        padding: 0;
    }

    .sf-inline-ticker-logo, .sf-inline-logo-fallback {
        width: 28px;
        height: 28px;
        border-radius: 8px;
        background: #f4f5f7;
        object-fit: contain;
        padding: 3px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        vertical-align: middle;
        margin-right: .45rem;
    }

    .sf-inline-logo-fallback {
        color: #111820;
        font-size: .62rem;
        font-weight: 800;
        padding: 0;
    }

    .sf-holding-symbol {
        color: #f2f4f7;
        font-size: .98rem;
        font-weight: 700;
    }

    .sf-holding-name {
        color: #aab3bf;
        font-size: .80rem;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 420px;
    }

    .sf-holding-meta {
        color: #6f7c8c;
        font-size: .72rem;
        margin-top: .15rem;
    }

    .sf-holding-right {
        text-align: right;
        white-space: nowrap;
        font-size: .82rem;
    }

    .sf-holding-value {
        color: #f2f4f7;
        font-size: 1rem;
        font-weight: 700;
        margin-bottom: .12rem;
    }

    .sf-live-pill {
        display: inline-block;
        padding: .32rem .62rem;
        border-radius: 999px;
        color: #ffcb6b;
        background: rgba(255,203,107,.08);
        border: 1px solid rgba(255,203,107,.22);
        font-size: .72rem;
        font-weight: 700;
        letter-spacing: .04em;
    }

    .sf-invest-hero {
        margin-top: .75rem;
        padding: 1.55rem 1.6rem 1.25rem 1.6rem;
        border: 1px solid rgba(220,225,232,.18);
        border-radius: 20px;
        background:
            radial-gradient(circle at 50% 0%, rgba(36,224,164,.08), transparent 45%),
            linear-gradient(145deg, rgba(17,24,32,.99), rgba(8,13,19,.99));
        text-align: center;
        box-shadow: 0 18px 50px rgba(0,0,0,.20);
    }

    .sf-invest-kicker {
        color: #42e7b1;
        font-size: .72rem;
        font-weight: 800;
        letter-spacing: .14em;
        text-transform: uppercase;
        margin-bottom: .35rem;
    }

    .sf-invest-title {
        color: #f2f4f7;
        font-size: 1.65rem;
        font-weight: 700;
        letter-spacing: -.03em;
    }

    .sf-invest-copy {
        color: #8f9aaa;
        font-size: .86rem;
        margin-top: .35rem;
        margin-bottom: .35rem;
    }

    div[data-testid="stNumberInput"] input {
        font-size: 2rem !important;
        font-weight: 750 !important;
        text-align: center !important;
        min-height: 68px !important;
        border-radius: 15px !important;
    }

    div[data-testid="stNumberInput"] label {
        text-align: center;
        width: 100%;
        font-weight: 700;
    }

    .sf-invest-note {
        color: #758190;
        text-align: center;
        font-size: .75rem;
        margin-top: .35rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.sidebar.markdown(
    """
    <div class="sf-brand">
        <div class="sf-monogram">SF</div>
        <div class="sf-brand-title">SF ALPHA</div>
        <div class="sf-brand-sub">Systematic Investment Engine</div>
    </div>
    """,
    unsafe_allow_html=True,
)

nav_page = st.sidebar.radio(
    "Navigation",
    [
        "Dashboard",
        "Portfolio",
        "Strategy",
        "Orders",
        "Performance",
        "Risk & Controls",
        "Stocks ISA",
        "System",
    ],
    label_visibility="collapsed",
)

st.sidebar.divider()

preview_mode = st.sidebar.checkbox(
    "Preview dashboard with sample data",
    value=False,
)

st.sidebar.caption("Preview mode uses simulated data.")
st.sidebar.caption(f"Broker data cached for {CACHE_TTL} seconds.")
st.sidebar.markdown("---")
st.sidebar.caption("SF ALPHA • TEST ENVIRONMENT")

# ============================================================
# HEADER
# ============================================================

topbar_environment = (
    "● Trading 212 Stocks ISA"
    if nav_page == "Stocks ISA"
    else "● Trading 212 Practice"
)

isa_manual_trading_enabled = (
    os.getenv("GAINZ_ENABLE_ISA_TRADING") == "YES"
)

topbar_lock = (
    (
        "● Manual ISA trading enabled"
        if isa_manual_trading_enabled
        else "🔒 ISA order submission locked"
    )
    if nav_page == "Stocks ISA"
    else "🔒 Real money locked"
)

st.markdown(
    f"""
    <div class="sf-topbar">
        <div class="sf-search">⌕ &nbsp; Search stocks, ETFs, or insights...</div>
        <div class="sf-env">{topbar_environment}</div>
        <div class="sf-lock">{topbar_lock}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="sf-header">
        <div class="sf-title">SF Alpha</div>
        <div class="sf-subtitle">Systematic Investment Engine</div>
    </div>
    """,
    unsafe_allow_html=True,
)

if preview_mode:
    st.warning("Preview mode is ON — showing sample data")

# ============================================================
# LOAD STRATEGY REPORT
# ============================================================

report = load_report()

decision = report.get(
    "decision",
    {},
)

weights = report.get(
    "target_weights",
    {},
)

executed = bool(
    report.get(
        "executed",
        False,
    )
)


# ============================================================
# LOAD BROKER DATA
# ============================================================

account = {}
raw_positions = []
broker_orders = []
historical_orders = []

account_error = None
positions_error = None
orders_error = None
historical_orders_error = None


if not preview_mode:

    account, account_error = fetch_with_fallback(
        "last_good_account",
        get_account_summary,
    )

    raw_positions, positions_error = fetch_with_fallback(
        "last_good_positions",
        get_raw_positions,
    )

    broker_orders, orders_error = fetch_with_fallback(
        "last_good_orders",
        get_orders,
    )

    historical_orders, historical_orders_error = fetch_with_fallback(
        "last_good_historical_orders",
        get_historical_orders,
    )


account = account or {}
raw_positions = raw_positions or []
broker_orders = broker_orders or []
historical_orders = historical_orders or []

# ============================================================
# PREVIEW DATA
# ============================================================

if preview_mode:

    account = {
        "currency": "GBP",
        "totalValue": 4997.08,
        "cash": {
            "availableToTrade": 1805.05,
            "reservedForOrders": 0.0,
            "inPies": 0.0,
        },
        "investments": {
            "currentValue": 3192.03,
            "totalCost": 3190.16,
            "realizedProfitLoss": 0.0,
            "unrealizedProfitLoss": 1.87,
        },
    }

    report = {
        "executed": True,
        "decision": {
            "mode": "GAINZ",
            "variant": "N15_momentum_trend_none",
            "risk": "vol12_defensive",
            "gainz_sharpe": 2.21,
            "benchmark_sharpe": 1.27,
        },
        "target_weights": {
            "PANW": 0.0587,
            "AMD": 0.0587,
            "MU": 0.0587,
        },
    }

    decision = report["decision"]
    weights = report["target_weights"]
    executed = True

    raw_positions = [
        {
            "instrument": {
                "ticker": "PANW_US_EQ",
                "name": "Palo Alto Networks",
                "currency": "USD",
            },
            "quantity": 0.8398,
            "currentPrice": 374.00,
            "averagePricePaid": 350.10716837,
            "walletImpact": {
                "currency": "GBP",
                "totalCost": 218.19,
                "currentValue": 232.53,
                "unrealizedProfitLoss": 14.34,
                "fxImpact": -0.52,
            },
        },
        {
            "instrument": {
                "ticker": "AMD_US_EQ",
                "name": "Advanced Micro Devices",
                "currency": "USD",
            },
            "quantity": 1.20,
            "currentPrice": 160.00,
            "averagePricePaid": 155.00,
            "walletImpact": {
                "currency": "GBP",
                "totalCost": 140.00,
                "currentValue": 144.50,
                "unrealizedProfitLoss": 4.50,
                "fxImpact": -0.10,
            },
        },
    ]

    broker_orders = []


# ============================================================
# ACCOUNT VALUES
# ============================================================

currency = extract_currency(
    account
)

currency_symbol = (
    "£"
    if currency == "GBP"
    else currency + " "
)

total_account_value = extract_total_value(
    account
)

cash_available = extract_cash(
    account
)

reserved_cash = extract_reserved_cash(
    account
)

investment_value = extract_investment_value(
    account
)

total_cost = extract_total_cost(
    account
)

realized_ppl = extract_realized_ppl(
    account
)

unrealized_ppl = extract_unrealized_ppl(
    account
)

total_ppl = extract_total_ppl(
    account
)

# Broker-native realised P/L from historical filled SELL orders.
realized_analysis = calculate_realized_pnl(historical_orders)

open_position_count = len(
    raw_positions
)

pending_count = len(
    broker_orders
)

# ============================================================
# PORTFOLIO HISTORY
# ============================================================

if not preview_mode and account and not account_error:
    save_portfolio_snapshot(
        portfolio_value=total_account_value,
        cash=cash_available,
        invested_value=investment_value,
        unrealised_pnl=unrealized_ppl,
        realised_pnl=realized_ppl,
    )


# ============================================================
# EXPOSURE
# ============================================================

if total_account_value > 0:

    exposure = (
        investment_value
        / total_account_value
    )

else:

    exposure = 0.0


# ============================================================
# SYSTEM HEALTH
# ============================================================

all_errors = [
    error
    for error in (
        account_error,
        positions_error,
        orders_error,
        historical_orders_error,
    )
    if error
]

rate_limited = any(
    is_rate_limit_error(error)
    for error in all_errors
)


if preview_mode:

    health = "PREVIEW"
    health_icon = "🧪"

elif rate_limited:

    health = "LIMITED"
    health_icon = "🟡"

elif all_errors and not raw_positions:

    health = "ERROR"
    health_icon = "🔴"

elif pending_count > 0:

    health = "PENDING"
    health_icon = "🟡"

else:

    health = "HEALTHY"
    health_icon = "🟢"


# ============================================================
# RATE LIMIT WARNING
# ============================================================

if rate_limited:

    st.warning(
        "Trading 212 temporarily rate-limited one or more "
        "dashboard requests. GainZ is showing the last "
        "successfully loaded data where available."
    )


st.markdown(f"### {nav_page}")

if nav_page == "Dashboard":
    # ============================================================
    # DASHBOARD — SF ALPHA
    # ============================================================

    d1, d2, d3, d4 = st.columns(4)

    d1.metric(
        "Portfolio Value",
        f"{currency_symbol}{total_account_value:,.2f}",
        delta=f"{currency_symbol}{total_ppl:+,.2f} total P/L",
    )

    total_return_pct = (
        (total_ppl / total_cost) * 100
        if total_cost
        else 0.0
    )

    d2.metric(
        "Total Return",
        f"{total_return_pct:+.2f}%",
        delta=f"{currency_symbol}{total_ppl:+,.2f}",
    )

    d3.metric(
        "Cash Available",
        f"{currency_symbol}{cash_available:,.2f}",
    )

    d4.metric(
        "Open Positions",
        open_position_count,
    )

    # ============================================================
    # PORTFOLIO PERFORMANCE
    # ============================================================

    st.markdown("### Portfolio Performance")

    left, right = st.columns([2.55, 1.25])

    with left:
        st.markdown(
            '<div class="sf-panel-title">Portfolio Performance</div>',
            unsafe_allow_html=True,
        )

        history = load_portfolio_history()

        if history:
            history_df = pd.DataFrame(history)

            history_df["timestamp"] = pd.to_datetime(
                history_df["timestamp"],
                utc=True,
                errors="coerce",
            )

            history_df["portfolio_value"] = pd.to_numeric(
                history_df["portfolio_value"],
                errors="coerce",
            )

            history_df = (
                history_df
                .dropna(subset=["timestamp", "portfolio_value"])
                .sort_values("timestamp")
            )

            if len(history_df) >= 2:
                chart_df = history_df.set_index("timestamp")[
                    ["portfolio_value"]
                ]

                fig = go.Figure()

                fig.add_trace(
                    go.Scatter(
                        x=chart_df.index,
                        y=chart_df["portfolio_value"],
                        mode="lines+markers",
                        name="Portfolio Value",
                        line=dict(width=2.5),
                        marker=dict(size=6),
                        fill="tozeroy",
                        fillcolor="rgba(120, 130, 145, 0.08)",
                        hovertemplate=(
                            "<b>%{x|%d %b %Y}</b><br>"
                            + currency_symbol
                            + "%{y:,.2f}<extra></extra>"
                        ),
                    )
                )

                min_value = chart_df["portfolio_value"].min()
                max_value = chart_df["portfolio_value"].max()
                movement = max_value - min_value
                padding = max(
                    movement * 0.35,
                    max_value * 0.002,
                    5,
                )

                fig.update_layout(
                    height=390,
                    margin=dict(l=8, r=8, t=20, b=8),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    hovermode="x unified",
                    showlegend=False,
                    xaxis=dict(
                        showgrid=False,
                        rangeslider=dict(visible=False),
                        rangeselector=dict(
                            buttons=[
                                dict(count=7, label="1W", step="day", stepmode="backward"),
                                dict(count=1, label="1M", step="month", stepmode="backward"),
                                dict(count=3, label="3M", step="month", stepmode="backward"),
                                dict(count=1, label="1Y", step="year", stepmode="backward"),
                                dict(label="ALL", step="all"),
                            ]
                        ),
                    ),
                    yaxis=dict(
                        range=[
                            min_value - padding,
                            max_value + padding,
                        ],
                        gridcolor="rgba(192,200,210,.08)",
                        title=f"Portfolio Value ({currency_symbol})",
                    ),
                )

                st.plotly_chart(
                    fig,
                    width='stretch',
                    config={
                        "displaylogo": False,
                        "scrollZoom": True,
                    },
                )

                first_value = history_df["portfolio_value"].iloc[0]
                latest_value = history_df["portfolio_value"].iloc[-1]
                change = latest_value - first_value

                change_pct = (
                    (change / first_value) * 100
                    if first_value
                    else 0.0
                )

                st.caption(
                    f"Recorded performance: "
                    f"{currency_symbol}{change:+,.2f} "
                    f"({change_pct:+.2f}%) • "
                    f"{len(history_df)} genuine snapshots"
                )

            else:
                st.info(
                    "First genuine portfolio snapshot recorded. "
                    "The equity curve will appear after another daily snapshot."
                )

        else:
            st.info(
                "Waiting for the first genuine portfolio snapshot."
            )

    # ============================================================
    # PORTFOLIO STATS
    # ============================================================

    with right:
        r1, r2 = st.columns(2)

        r1.metric(
            "Invested",
            f"{currency_symbol}{investment_value:,.2f}",
        )

        r2.metric(
            "Exposure",
            f"{exposure * 100:.1f}%",
        )

        st.metric(
            "Unrealised P/L",
            f"{currency_symbol}{unrealized_ppl:+,.2f}",
        )

        st.metric(
            "Realised P/L",
            f"{currency_symbol}{realized_ppl:+,.2f}",
        )

    # ============================================================
    # PORTFOLIO OVERVIEW
    # ============================================================

    st.markdown("### Portfolio Overview")

    lower1, lower2, lower3 = st.columns([1.08, 1.42, 1])

    with lower1:
        st.markdown(
            '<div class="sf-panel-title">Portfolio Allocation</div>',
            unsafe_allow_html=True,
        )

        if raw_positions:
            allocation_rows = []

            for position in raw_positions:
                symbol = extract_position_symbol(position)
                wallet = position.get("walletImpact", {}) or {}
                value = float_value(wallet.get("currentValue"))

                if value > 0:
                    allocation_rows.append(
                        {
                            "Ticker": symbol,
                            "Value": value,
                        }
                    )

            allocation_df = pd.DataFrame(allocation_rows)

            if (
                not allocation_df.empty
                and allocation_df["Value"].sum() > 0
            ):
                allocation_df["Weight"] = (
                    allocation_df["Value"]
                    / allocation_df["Value"].sum()
                )

                fig, ax = plt.subplots(figsize=(4.2, 4.2))
                fig.patch.set_alpha(0)
                ax.set_facecolor("none")

                ax.pie(
                    allocation_df["Value"],
                    startangle=90,
                    wedgeprops={
                        "width": 0.34,
                        "edgecolor": "none",
                    },
                )

                ax.text(
                    0,
                    0.05,
                    f"{currency_symbol}{investment_value / 1000:.2f}K",
                    ha="center",
                    va="center",
                    fontsize=14,
                    fontweight="bold",
                )

                ax.text(
                    0,
                    -0.12,
                    "INVESTED",
                    ha="center",
                    va="center",
                    fontsize=7,
                    alpha=0.65,
                )

                ax.axis("equal")

                st.pyplot(
                    fig,
                    width='stretch',
                )

                plt.close(fig)

                allocation_display = allocation_df.copy()

                allocation_display["Weight"] = allocation_display[
                    "Weight"
                ].map(
                    lambda x: f"{x * 100:.1f}%"
                )

                allocation_display = add_logo_column(
                    allocation_display,
                    "Ticker",
                )

                st.dataframe(
                    allocation_display[
                        ["Logo", "Ticker", "Weight"]
                    ].head(6),
                    width='stretch',
                    hide_index=True,
                    column_config=LOGO_COLUMN_CONFIG,
                )

            else:
                st.caption(
                    "No portfolio allocation data available."
                )

        else:
            st.caption("No open positions.")

    with lower2:
        st.markdown(
            '<div class="sf-panel-title">Recent Orders</div>',
            unsafe_allow_html=True,
        )

        clean_orders = []

        if broker_orders:
            for item in broker_orders[:5]:
                if not isinstance(item, dict):
                    continue

                clean_orders.append(
                    {
                        "Ticker": symbol_from_ticker(
                            item.get("ticker", "")
                        ),
                        "Side": str(
                            item.get("side", "")
                        ).upper(),
                        "Qty": float_value(
                            item.get(
                                "filledQuantity",
                                item.get("quantity", 0),
                            )
                        ),
                        "Status": str(
                            item.get("status", "")
                        ),
                    }
                )

        elif historical_orders:
            clean_orders = [
                flatten_historical_order(item)
                for item in historical_orders[:5]
            ]

            clean_orders = [
                row
                for row in clean_orders
                if row
            ]

        if clean_orders:
            for row in clean_orders:
                side = str(
                    row.get("Side", "")
                ).upper()

                badge_class = (
                    "sf-badge-sell"
                    if side == "SELL"
                    else "sf-badge-buy"
                )

                raw_ticker = str(row.get("Ticker", ""))
                ticker = html.escape(raw_ticker)
                ticker_logo = ticker_logo_html(raw_ticker)

                qty = float_value(
                    row.get("Qty", 0)
                )

                status = html.escape(
                    str(row.get("Status", ""))
                )

                st.markdown(
                    f"""
                    <div class="sf-order-row">
                        <span class="{badge_class}">
                            {html.escape(side or "—")}
                        </span>
                        <span style="display:flex;align-items:center;">
                            {ticker_logo}
                            <strong>{ticker}</strong>
                        </span>
                        <span>{qty:g}</span>
                        <span class="sf-green">
                            {status}
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        else:
            st.caption(
                "No recent broker orders available."
            )

    with lower3:
        st.markdown(
            '<div class="sf-panel-title">System Status</div>',
            unsafe_allow_html=True,
        )

        statuses = [
            (
                "Broker connection",
                not bool(account_error),
            ),
            (
                "Positions feed",
                not bool(positions_error),
            ),
            (
                "Order feed",
                not bool(orders_error),
            ),
            (
                "Strategy engine",
                bool(report),
            ),
        ]

        for label, ok in statuses:
            dot = (
                "sf-dot-ok"
                if ok
                else "sf-dot-warn"
            )

            st.markdown(
                f"""
                <div class="sf-status-row">
                    <span class="{dot}"></span>
                    <span>{html.escape(label)}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown(
            """
            <div class="sf-status-row">
                <span>🔒</span>
                <span>Real-money execution locked</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


if nav_page == "Portfolio":
    st.divider()
    st.subheader("Practice Portfolio")

    st.markdown("### Invest with GainZ")
    st.caption(
        "Practice / Demo only. You choose the capital amount; "
        "GainZ chooses the BUY-only allocation."
    )

    st.markdown(
        """
        <div class="sf-invest-hero">
            <div class="sf-invest-kicker">✦ GainZ Practice Allocation</div>
            <div class="sf-invest-title">How much do you want to invest?</div>
            <div class="sf-invest-copy">
                Build and risk-check a new-cash portfolio before submitting any Practice orders.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if "practice_gainz_invest_amount" not in st.session_state:
        st.session_state["practice_gainz_invest_amount"] = 0.0

    def set_practice_amount(amount):
        st.session_state["practice_gainz_invest_amount"] = float(amount)

    q1, q2, q3, q4 = st.columns(4)

    q1.button(
        "£100",
        key="practice_quick_100",
        width='stretch',
        on_click=set_practice_amount,
        args=(100.0,),
    )
    q2.button(
        "£250",
        key="practice_quick_250",
        width='stretch',
        on_click=set_practice_amount,
        args=(250.0,),
    )
    q3.button(
        "£500",
        key="practice_quick_500",
        width='stretch',
        on_click=set_practice_amount,
        args=(500.0,),
    )
    q4.button(
        "MAX CASH",
        key="practice_quick_max",
        width='stretch',
        on_click=set_practice_amount,
        args=(float(cash_available),),
    )

    practice_amount = st.number_input(
        "Practice investment amount (£)",
        min_value=0.0,
        step=50.0,
        format="%.2f",
        key="practice_gainz_invest_amount",
    )

    if st.button(
        "✦ BUILD MY PORTFOLIO",
        key="practice_build_gainz_portfolio",
        width='stretch',
        type="primary",
    ):
        if practice_amount <= 0:
            st.error("Enter an investment amount greater than £0.")
        elif practice_amount > cash_available:
            st.error(
                f"That amount is above the Practice cash currently available "
                f"({currency_symbol}{cash_available:,.2f})."
            )
        else:
            with st.spinner("GainZ is building and risk-checking the Practice portfolio..."):
                preview_result = run_gainz(
                    execute_demo=False,
                    investment_amount=practice_amount,
                )

            if not preview_result["success"]:
                st.error("GainZ could not build the Practice portfolio.")
                st.code(preview_result["stderr"] or preview_result["stdout"])
            else:
                fresh_report = load_report()
                st.session_state["practice_gainz_preview"] = {
                    "amount": float(practice_amount),
                    "report": fresh_report,
                }
                st.rerun()

    practice_preview = st.session_state.get("practice_gainz_preview")

    if practice_preview:
        preview_report = practice_preview.get("report", {}) or {}
        preview_orders = preview_report.get("orders", []) or []
        preview_amount = float(practice_preview.get("amount", 0.0))

        approved_orders = [
            row for row in preview_orders
            if str(row.get("status", "")).upper() == "DRY_RUN_APPROVED"
        ]
        blocked_orders = [
            row for row in preview_orders
            if str(row.get("status", "")).upper() == "BLOCKED"
        ]
        target_weights_preview = preview_report.get("target_weights", {}) or {}
        planned_stock_value = preview_amount * sum(
            max(float_value(weight), 0.0)
            for weight in target_weights_preview.values()
        )
        planned_stock_value = min(planned_stock_value, preview_amount)
        reserve = max(preview_amount - planned_stock_value, 0.0)

        st.markdown("### Practice Investment Preview")
        st.caption(
            "No order has been submitted. Existing holdings are used for risk checks "
            "but are not sold by this new-cash action."
        )

        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Capital Assigned", f"{currency_symbol}{preview_amount:,.2f}")
        p2.metric("Planned for Stocks", f"{currency_symbol}{planned_stock_value:,.2f}")
        p3.metric("GainZ Cash Reserve", f"{currency_symbol}{reserve:,.2f}")
        p4.metric("Risk Approved", f"{len(approved_orders)}/{len(preview_orders)}")

        if preview_orders:
            preview_df = pd.DataFrame(preview_orders)
            display_df = pd.DataFrame({
                "Ticker": preview_df["symbol"],
                "Side": preview_df.get("side", pd.Series(["BUY"] * len(preview_df))),
                "Quantity": preview_df["quantity"].map(lambda x: f"{float_value(x):.6f}"),
                "Risk Status": preview_df["status"],
                "Risk Message": preview_df["message"],
            })
            display_df = add_logo_column(
                display_df,
                "Ticker",
            )
            st.dataframe(
                display_df,
                hide_index=True,
                width='stretch',
                column_config=LOGO_COLUMN_CONFIG,
            )

        if blocked_orders:
            st.error(
                f"{len(blocked_orders)} proposed order(s) were blocked by the risk engine. "
                "Practice execution is disabled until the preview is fully approved."
            )
        elif approved_orders and len(approved_orders) == len(preview_orders):
            st.success(
                "All proposed Practice BUY orders passed the current execution risk checks."
            )

            confirm = st.checkbox(
                "I understand this will submit Practice/Demo orders to Trading 212.",
                key="practice_confirm_checkbox",
            )

            if st.button(
                "CONFIRM PRACTICE INVESTMENT",
                key="practice_confirm_investment",
                width='stretch',
                type="primary",
                disabled=not confirm,
            ):
                with st.spinner("Submitting Practice orders..."):
                    execution_result = run_gainz(
                        execute_demo=True,
                        investment_amount=preview_amount,
                    )

                if execution_result["success"]:
                    executed_report = load_report()
                    execution_orders = executed_report.get("orders", []) or []

                    accepted_statuses = {
                        "SUBMITTED",
                        "FILLED",
                        "ACCEPTED",
                        "PENDING",
                    }
                    failed_statuses = {
                        "BLOCKED",
                        "REJECTED",
                        "FAILED",
                        "ERROR",
                    }

                    accepted_orders = [
                        row for row in execution_orders
                        if str(row.get("status", "")).upper() in accepted_statuses
                    ]
                    failed_orders = [
                        row for row in execution_orders
                        if str(row.get("status", "")).upper() in failed_statuses
                    ]
                    unknown_orders = [
                        row for row in execution_orders
                        if str(row.get("status", "")).upper()
                        not in accepted_statuses | failed_statuses
                    ]

                    if execution_orders:
                        st.dataframe(
                            pd.DataFrame(execution_orders),
                            hide_index=True,
                            width='stretch',
                        )

                    if (
                        execution_orders
                        and len(accepted_orders) == len(execution_orders)
                        and not failed_orders
                        and not unknown_orders
                    ):
                        st.session_state.pop("practice_gainz_preview", None)
                        get_account_summary.clear()
                        get_raw_positions.clear()
                        get_orders.clear()
                        get_historical_orders.clear()

                        st.success(
                            f"Trading 212 returned an accepted/submitted status "
                            f"for all {len(accepted_orders)} Practice order(s). "
                            f"Check Trading 212 History for final fill confirmation."
                        )
                    else:
                        st.error(
                            "Practice execution was NOT verified as fully submitted. "
                            "The preview has been kept. Do not retry until these "
                            "results are reviewed."
                        )
                        st.caption(
                            f"Accepted/submitted: {len(accepted_orders)} · "
                            f"Blocked/failed: {len(failed_orders)} · "
                            f"Unknown: {len(unknown_orders)}"
                        )

                        diagnostic = (
                            execution_result.get("stderr")
                            or execution_result.get("stdout")
                        )
                        if diagnostic:
                            with st.expander("Execution diagnostics"):
                                st.code(diagnostic)
                else:
                    st.error(
                        "Practice execution process failed. No successful "
                        "submission is being reported, and the preview has "
                        "been kept."
                    )
                    st.code(
                        execution_result.get("stderr")
                        or execution_result.get("stdout")
                        or "No subprocess diagnostic output was returned."
                    )

        if st.button(
            "Clear Practice Preview",
            key="practice_clear_preview",
            width='stretch',
        ):
            st.session_state.pop("practice_gainz_preview", None)
            st.rerun()

    st.warning(
        "🧪 PRACTICE / DEMO ONLY — this page cannot submit Stocks ISA real-money orders."
    )


if nav_page == "Performance":
    # ============================================================
    # PERFORMANCE
    # ============================================================

    st.divider()
    st.subheader("Performance")

    daily_equity = calculate_daily_performance()
    realised_daily = realized_analysis.get("daily", [])
    realised_trades = realized_analysis.get("trades", [])

    # ------------------------------------------------------------
    # TOP KPIs
    # ------------------------------------------------------------

    latest_equity_change = (
        float(daily_equity[-1].get("daily_pnl", 0.0))
        if daily_equity else 0.0
    )

    latest_equity_return = (
        float(daily_equity[-1].get("daily_return", 0.0))
        if daily_equity else 0.0
    )

    broker_history_realised = float(
        realized_analysis.get("total_realized_pnl", 0.0)
    )

    k1, k2, k3, k4 = st.columns(4)

    k1.metric(
        "Broker Realised P/L",
        f"{currency_symbol}{broker_history_realised:,.2f}",
    )

    k2.metric(
        "Unrealised P/L",
        f"{currency_symbol}{unrealized_ppl:,.2f}",
    )

    k3.metric(
        "Total P/L",
        f"{currency_symbol}{total_ppl:,.2f}",
    )

    k4.metric(
        "Portfolio Value",
        f"{currency_symbol}{total_account_value:,.2f}",
    )

    st.caption(
        "Realised P/L uses Trading 212's broker-reported realisedProfitLoss "
        "from filled SELL transactions. Portfolio/equity change is shown "
        "separately and is not treated as realised trading profit."
    )

    # ------------------------------------------------------------
    # DAILY REALISED TRADING P/L
    # ------------------------------------------------------------

    st.markdown("### Daily Realised Trading P/L")

    if realised_daily:
        realised_df = pd.DataFrame(realised_daily)

        realised_df["date"] = pd.to_datetime(
            realised_df["date"],
            errors="coerce",
        )

        realised_df["realized_pnl"] = pd.to_numeric(
            realised_df["realized_pnl"],
            errors="coerce",
        ).fillna(0.0)

        realised_df = (
            realised_df
            .dropna(subset=["date"])
            .sort_values("date")
        )

        realised_df["cumulative_realized_pnl"] = (
            realised_df["realized_pnl"].cumsum()
        )

        winning_days = int(
            (realised_df["realized_pnl"] > 0).sum()
        )
        losing_days = int(
            (realised_df["realized_pnl"] < 0).sum()
        )

        best_day = float(
            realised_df["realized_pnl"].max()
        )
        worst_day = float(
            realised_df["realized_pnl"].min()
        )

        r1, r2, r3, r4 = st.columns(4)

        r1.metric(
            "Winning Days",
            winning_days,
        )

        r2.metric(
            "Losing Days",
            losing_days,
        )

        r3.metric(
            "Best Realised Day",
            f"{currency_symbol}{best_day:+,.2f}",
        )

        r4.metric(
            "Worst Realised Day",
            f"{currency_symbol}{worst_day:+,.2f}",
        )

        chart_daily = realised_df.set_index("date")[
            ["realized_pnl"]
        ].rename(
            columns={"realized_pnl": "Daily Realised P/L"}
        )

        st.bar_chart(
            chart_daily,
            width="stretch",
        )

        st.markdown("### Cumulative Realised P/L")

        chart_cumulative = realised_df.set_index("date")[
            ["cumulative_realized_pnl"]
        ].rename(
            columns={
                "cumulative_realized_pnl":
                "Cumulative Realised P/L"
            }
        )

        st.line_chart(
            chart_cumulative,
            width="stretch",
        )

        daily_table = realised_df.copy()
        daily_table["Date"] = daily_table["date"].dt.strftime(
            "%d %b %Y"
        )
        daily_table["Realised P/L"] = daily_table[
            "realized_pnl"
        ].map(
            lambda value:
            f"{currency_symbol}{value:+,.2f}"
        )
        daily_table["Cumulative P/L"] = daily_table[
            "cumulative_realized_pnl"
        ].map(
            lambda value:
            f"{currency_symbol}{value:+,.2f}"
        )

        st.dataframe(
            daily_table[
                ["Date", "Realised P/L", "Cumulative P/L"]
            ],
            hide_index=True,
            width="stretch",
        )

    else:
        st.info(
            "No broker-reported realised SELL P/L is available yet."
        )

    # ------------------------------------------------------------
    # PORTFOLIO / EQUITY HISTORY
    # ------------------------------------------------------------

    st.markdown("### Portfolio Equity History")

    if daily_equity:
        equity_df = pd.DataFrame(daily_equity)

        equity_df["timestamp"] = pd.to_datetime(
            equity_df["timestamp"],
            utc=True,
            errors="coerce",
        )

        equity_df["portfolio_value"] = pd.to_numeric(
            equity_df["portfolio_value"],
            errors="coerce",
        )

        equity_df["daily_pnl"] = pd.to_numeric(
            equity_df["daily_pnl"],
            errors="coerce",
        ).fillna(0.0)

        equity_df["daily_return"] = pd.to_numeric(
            equity_df["daily_return"],
            errors="coerce",
        ).fillna(0.0)

        equity_df = (
            equity_df
            .dropna(subset=["timestamp", "portfolio_value"])
            .sort_values("timestamp")
        )

        e1, e2, e3 = st.columns(3)

        e1.metric(
            "Latest Equity Change",
            f"{currency_symbol}{latest_equity_change:+,.2f}",
        )

        e2.metric(
            "Latest Equity Return",
            f"{latest_equity_return:+.2f}%",
        )

        e3.metric(
            "Recorded Days",
            len(equity_df),
        )

        equity_chart = equity_df.set_index("timestamp")[
            ["portfolio_value"]
        ].rename(
            columns={"portfolio_value": "Portfolio Value"}
        )

        st.line_chart(
            equity_chart,
            width="stretch",
        )

        st.caption(
            "Equity change measures changes in total portfolio value. "
            "It is not the same as realised trading P/L and is not "
            "cash-flow adjusted."
        )

    else:
        st.info(
            "Portfolio history will appear after daily snapshots "
            "have been recorded."
        )

    # ------------------------------------------------------------
    # RECENT REALISED TRADES
    # ------------------------------------------------------------

    st.markdown("### Recent Realised Trades")

    if realised_trades:
        trades_df = pd.DataFrame(realised_trades)

        trades_df["filled_at"] = pd.to_datetime(
            trades_df["filled_at"],
            utc=True,
            errors="coerce",
        )

        trades_df = trades_df.sort_values(
            "filled_at",
            ascending=False,
        )

        trades_df["Time"] = trades_df["filled_at"].dt.strftime(
            "%d %b %Y %H:%M UTC"
        )

        trades_df["Ticker"] = (
            trades_df["ticker"]
            .astype(str)
            .str.replace("_US_EQ", "", regex=False)
        )

        trades_df["Quantity"] = pd.to_numeric(
            trades_df["quantity"],
            errors="coerce",
        ).map(
            lambda value:
            f"{value:,.4f}"
            if pd.notna(value)
            else "—"
        )

        trades_df["Proceeds"] = pd.to_numeric(
            trades_df["proceeds"],
            errors="coerce",
        ).map(
            lambda value:
            f"{currency_symbol}{value:,.2f}"
            if pd.notna(value)
            else "—"
        )

        trades_df["Realised P/L"] = pd.to_numeric(
            trades_df["realized_pnl"],
            errors="coerce",
        ).map(
            lambda value:
            f"{currency_symbol}{value:+,.2f}"
            if pd.notna(value)
            else "—"
        )

        trades_df["Fees"] = pd.to_numeric(
            trades_df["fees"],
            errors="coerce",
        ).map(
            lambda value:
            f"{currency_symbol}{value:,.2f}"
            if pd.notna(value)
            else "—"
        )

        trades_display = trades_df[
            [
                "Time",
                "Ticker",
                "Quantity",
                "Proceeds",
                "Realised P/L",
                "Fees",
            ]
        ].head(50).copy()
        trades_display = add_logo_column(
            trades_display,
            "Ticker",
        )

        st.dataframe(
            trades_display,
            hide_index=True,
            width="stretch",
            column_config=LOGO_COLUMN_CONFIG,
        )

    else:
        st.info(
            "No filled SELL transactions with broker-reported "
            "realised P/L were found."
        )


if nav_page == "Portfolio":
    # ============================================================
    # HOLDINGS
    # ============================================================

    st.divider()

    st.subheader("Holdings")

    performance_rows = []

    for position in raw_positions:

        ticker = extract_position_symbol(
            position
        )

        company_name = extract_position_name(
            position
        )

        stock_currency = extract_position_currency(
            position
        )

        quantity = float_value(
            position.get(
                "quantity"
            )
        )

        average_price = float_value(
            position.get(
                "averagePricePaid"
            )
        )

        current_price = float_value(
            position.get(
                "currentPrice"
            )
        )

        wallet = position.get(
            "walletImpact",
            {},
        )

        total_cost_gbp = float_value(
            wallet.get(
                "totalCost"
            )
        )

        current_value_gbp = float_value(
            wallet.get(
                "currentValue"
            )
        )

        position_ppl_gbp = float_value(
            wallet.get(
                "unrealizedProfitLoss"
            )
        )

        fx_impact_gbp = float_value(
            wallet.get(
                "fxImpact"
            )
        )

        target_weight = float_value(
            weights.get(
                ticker,
                0,
            )
        )

        return_pct = (
            (
                position_ppl_gbp
                / total_cost_gbp
            )
            * 100
            if total_cost_gbp
            else 0
        )

        performance_rows.append(
            {
                "Ticker": ticker,
                "Company": company_name,
                "Currency": stock_currency,
                "Quantity": round(
                    quantity,
                    4,
                ),
                "Average Price": round(
                    average_price,
                    2,
                ),
                "Current Price": round(
                    current_price,
                    2,
                ),
                "Cost (£)": round(
                    total_cost_gbp,
                    2,
                ),
                "Value (£)": round(
                    current_value_gbp,
                    2,
                ),
                "P/L (£)": round(
                    position_ppl_gbp,
                    2,
                ),
                "FX (£)": round(
                    fx_impact_gbp,
                    2,
                ),
                "Return %": round(
                    return_pct,
                    2,
                ),
                "Target %": round(
                    target_weight * 100,
                    2,
                ),
            }
        )


    if performance_rows:

        performance_df = pd.DataFrame(
            performance_rows
        )

        performance_df = add_logo_column(
            performance_df,
            "Ticker",
        )

        st.dataframe(
            performance_df,
            width='stretch',
            hide_index=True,
            column_config=LOGO_COLUMN_CONFIG,
        )

    else:

        st.info(
            "No open Practice positions."
        )


    st.caption(
        "GBP cost, value and P/L come directly from Trading 212 "
        "walletImpact data. US stock prices are quoted in USD."
    )




if nav_page == "Strategy":
    # ============================================================
    # GAINZ STRATEGY
    # ============================================================

    st.divider()

    st.subheader("SF Alpha Strategy")

    mode = decision.get(
        "mode",
        "N/A",
    )

    strategy = friendly_strategy(
        decision.get(
            "variant"
        )
    )

    risk_mode = friendly_risk(
        decision.get(
            "risk"
        )
    )


    if preview_mode:

        action_text = (
            "Preview mode is showing sample data."
        )

    elif executed:

        action_text = (
            "Practice orders were submitted by GainZ."
        )

    elif report:

        action_text = (
            "A GainZ strategy plan is available."
        )

    else:

        action_text = (
            "Broker data is live. "
            "No local strategy report is currently available on Render."
        )


    t1, t2, t3 = st.columns(3)

    t1.write(
        f"**Mode:** {mode}"
    )

    t2.write(
        f"**Strategy:** {strategy}"
    )

    t3.write(
        f"**Risk:** {risk_mode}"
    )

    st.write(
        f"**Status:** {action_text}"
    )


    # ============================================================
    # TARGET PORTFOLIO
    # ============================================================

    with st.expander(
        "🎯 View target portfolio"
    ):

        if weights:

            target_rows = [
                {
                    "Ticker": ticker,
                    "Target Weight %": round(
                        float_value(
                            weight
                        )
                        * 100,
                        2,
                    ),
                }
                for ticker, weight
                in weights.items()
            ]

            target_df = pd.DataFrame(
                target_rows
            )

            target_display = add_logo_column(
                target_df,
                "Ticker",
            )

            st.dataframe(
                target_display,
                width='stretch',
                hide_index=True,
                column_config=LOGO_COLUMN_CONFIG,
            )

            st.bar_chart(
                target_df.set_index(
                    "Ticker"
                )[
                    "Target Weight %"
                ]
            )

        else:

            st.info(
                "Target portfolio is not currently available "
                "on this Render instance."
            )



if nav_page == "Orders":
    # ============================================================
    # BROKER ORDERS
    # ============================================================

    with st.expander(
        "📋 View broker orders"
    ):

        if broker_orders:

            orders_df = pd.DataFrame(
                broker_orders
            )

            preferred_columns = [
                "ticker",
                "side",
                "quantity",
                "filledQuantity",
                "status",
                "createdAt",
            ]

            existing_columns = [
                column
                for column in preferred_columns
                if column in orders_df.columns
            ]

            if existing_columns:

                orders_df = orders_df[
                    existing_columns
                ]

            if "ticker" in orders_df.columns:
                orders_df["Ticker"] = orders_df["ticker"].map(
                    symbol_from_ticker
                )
                orders_df = add_logo_column(
                    orders_df,
                    "Ticker",
                )

            st.dataframe(
                orders_df,
                width='stretch',
                hide_index=True,
                column_config=LOGO_COLUMN_CONFIG,
            )

        else:

            st.success(
                "No pending broker orders."
            )




if nav_page == "Risk & Controls":
    st.divider()
    st.subheader("Risk & Controls")
    st.caption(
        "Practice safety dashboard. These guardrails are display-only for now "
        "and do not change order execution."
    )

    largest_position_value = 0.0
    largest_position_symbol = "—"
    for position in raw_positions:
        wallet = position.get("walletImpact", {}) or {}
        value = float_value(wallet.get("currentValue", 0))
        if value > largest_position_value:
            largest_position_value = value
            largest_position_symbol = extract_position_symbol(position)

    largest_position_pct = (
        largest_position_value / total_account_value * 100
        if total_account_value > 0 else 0.0
    )
    exposure_pct = exposure * 100

    max_position_pct = 15.0
    max_exposure_pct = 90.0
    max_order_pct = 10.0
    daily_loss_limit_pct = 3.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Portfolio Exposure", f"{exposure_pct:.1f}%")
    c2.metric("Largest Position", f"{largest_position_pct:.1f}%", delta=largest_position_symbol, delta_color="off")
    c3.metric("Pending Orders", pending_count)
    c4.metric("Real-Money Trading", "LOCKED")

    st.markdown("### Safety Checks")
    controls = [
        {"Control": "Maximum position size", "Status": "PASS" if largest_position_pct <= max_position_pct else "REVIEW", "Current": f"{largest_position_pct:.1f}%", "Guardrail": f"≤ {max_position_pct:.0f}%", "Purpose": "Avoid too much money in one stock."},
        {"Control": "Maximum portfolio exposure", "Status": "PASS" if exposure_pct <= max_exposure_pct else "REVIEW", "Current": f"{exposure_pct:.1f}%", "Guardrail": f"≤ {max_exposure_pct:.0f}%", "Purpose": "Keep the account from being fully invested."},
        {"Control": "Maximum order value", "Status": "DISPLAY ONLY", "Current": "Not enforced", "Guardrail": f"≤ {max_order_pct:.0f}% of account", "Purpose": "Prevent unexpectedly large orders."},
        {"Control": "Daily loss limit", "Status": "DISPLAY ONLY", "Current": "Not enforced", "Guardrail": f"{daily_loss_limit_pct:.0f}% stop", "Purpose": "Stop new trading after a large daily loss."},
        {"Control": "Duplicate-order protection", "Status": "DISPLAY ONLY", "Current": "Not enforced", "Guardrail": "Block duplicates", "Purpose": "Prevent the same trade being sent twice."},
        {"Control": "Pending-order protection", "Status": "CLEAR" if pending_count == 0 else "PENDING", "Current": f"{pending_count} pending", "Guardrail": "Review unresolved orders", "Purpose": "Avoid conflicting orders."},
        {"Control": "Live trading lock", "Status": "LOCKED", "Current": "Practice only", "Guardrail": "Real money disabled", "Purpose": "Prevent accidental real-money execution."},
    ]
    st.dataframe(pd.DataFrame(controls), hide_index=True, width="stretch")

    st.markdown("### Current Safety State")
    if preview_mode:
        st.info("Preview mode is active, so values may use sample data.")
    elif account_error or positions_error:
        st.warning("Some broker data could not refresh, so observations may use last-good data.")
    else:
        st.success("Practice environment connected. Real-money execution remains locked.")

    st.markdown("### Before Real Money")
    st.write(
        "Later, these guardrails can be moved into the execution path so every "
        "proposed order must pass the risk engine before reaching Trading 212."
    )


if nav_page == "Stocks ISA":
    st.divider()
    st.subheader("Stocks ISA — Real Money")
    st.caption(
        "Live Trading 212 Stocks ISA data. "
        "Manual SELL orders can only be submitted from the explicit sell panel below. GainZ investing remains separate."
    )

    if preview_mode:
        st.warning(
            "Preview mode affects the Practice dashboard only. "
            "The Stocks ISA page always uses the real ISA connection."
        )

    if not isa_credentials_present():
        st.error(
            "Stocks ISA credentials are missing. Add "
            "TRADING212_ISA_API_KEY and TRADING212_ISA_API_SECRET "
            "to the environment."
        )
    else:
        isa_account, isa_account_error = fetch_with_fallback(
            "last_good_isa_account",
            get_isa_account_summary,
        )
        isa_positions, isa_positions_error = fetch_with_fallback(
            "last_good_isa_positions",
            get_isa_raw_positions,
        )
        isa_orders, isa_orders_error = fetch_with_fallback(
            "last_good_isa_orders",
            get_isa_orders,
        )

        isa_account = isa_account or {}
        isa_positions = isa_positions or []
        isa_orders = isa_orders or []

        isa_currency = extract_currency(isa_account)
        isa_symbol = "£" if isa_currency == "GBP" else isa_currency + " "
        isa_total = extract_total_value(isa_account)
        isa_cash = extract_cash(isa_account)
        isa_invested = extract_investment_value(isa_account)
        isa_realised = extract_realized_ppl(isa_account)
        isa_unrealised = extract_unrealized_ppl(isa_account)
        isa_total_pnl = isa_realised + isa_unrealised
        isa_exposure = (
            isa_invested / isa_total
            if isa_total > 0
            else 0.0
        )

        if isa_account_error:
            st.warning(
                "The ISA account summary could not refresh. "
                "Showing last-good data where available."
            )

        i1, i2, i3, i4 = st.columns(4)
        i1.metric(
            "ISA Value",
            f"{isa_symbol}{isa_total:,.2f}",
            delta=f"{isa_symbol}{isa_total_pnl:+,.2f} total P/L",
        )
        i2.metric(
            "Available to Trade",
            f"{isa_symbol}{isa_cash:,.2f}",
        )
        i3.metric(
            "Invested",
            f"{isa_symbol}{isa_invested:,.2f}",
        )
        i4.metric(
            "Open Positions",
            len(isa_positions),
        )

        p1, p2, p3 = st.columns(3)
        p1.metric(
            "Unrealised P/L",
            f"{isa_symbol}{isa_unrealised:+,.2f}",
        )
        p2.metric(
            "Realised P/L",
            f"{isa_symbol}{isa_realised:+,.2f}",
        )
        p3.metric(
            "Exposure",
            f"{isa_exposure * 100:.1f}%",
        )

        st.markdown("### ISA Holdings")

        isa_rows = []
        for position in isa_positions:
            ticker = extract_position_symbol(position)
            company = extract_position_name(position)
            instrument_currency = extract_position_currency(position)
            quantity = float_value(position.get("quantity"))
            average_price = float_value(position.get("averagePricePaid"))
            current_price = float_value(position.get("currentPrice"))
            wallet = position.get("walletImpact", {}) or {}
            cost = float_value(wallet.get("totalCost"))
            value = float_value(wallet.get("currentValue"))
            pnl = float_value(wallet.get("unrealizedProfitLoss"))
            return_pct = (pnl / cost * 100) if cost else 0.0
            weight_pct = (value / isa_total * 100) if isa_total else 0.0

            isa_rows.append(
                {
                    "Ticker": ticker,
                    "Company": company,
                    "Currency": instrument_currency,
                    "Quantity": round(quantity, 6),
                    "Average Price": round(average_price, 2),
                    "Current Price": round(current_price, 2),
                    "Cost (£)": round(cost, 2),
                    "Value (£)": round(value, 2),
                    "P/L (£)": round(pnl, 2),
                    "Return %": round(return_pct, 2),
                    "Weight %": round(weight_pct, 2),
                }
            )

        if isa_rows:
            st.markdown(
                '<span class="sf-live-pill">● REAL ISA HOLDINGS</span>',
                unsafe_allow_html=True,
            )

            for position in isa_positions:
                render_holding_card(
                    position,
                    portfolio_total=isa_total,
                    currency_symbol=isa_symbol,
                )

            with st.expander("View detailed holdings table"):
                isa_holdings_df = add_logo_column(
                    pd.DataFrame(isa_rows),
                    "Ticker",
                )
                st.dataframe(
                    isa_holdings_df,
                    width='stretch',
                    hide_index=True,
                    column_config=LOGO_COLUMN_CONFIG,
                )

            st.markdown(
                '<div style="font-size:12pt; margin-top:.45rem;">'
                'Logos provided by '
                '<a href="https://parqet.com/api" target="_blank">Parqet</a>'
                '</div>',
                unsafe_allow_html=True,
            )
        elif isa_positions_error:
            st.warning(
                "ISA positions could not be refreshed."
            )
        else:
            st.info("No open Stocks ISA positions.")

        if isa_rows:
            st.markdown("### Interactive Portfolio Mix")

            mix_df = pd.DataFrame(isa_rows)
            fig_mix = go.Figure(
                data=[
                    go.Pie(
                        labels=mix_df["Ticker"],
                        values=mix_df["Value (£)"],
                        hole=0.66,
                        textinfo="label+percent",
                        hovertemplate=(
                            "<b>%{label}</b><br>"
                            + isa_symbol
                            + "%{value:,.2f}<br>"
                            + "%{percent}<extra></extra>"
                        ),
                    )
                ]
            )

            fig_mix.update_layout(
                height=390,
                margin=dict(l=10, r=10, t=15, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                showlegend=True,
                annotations=[
                    dict(
                        text=(
                            f"<b>{isa_symbol}{isa_invested:,.2f}</b>"
                            "<br><span style='font-size:11px'>INVESTED</span>"
                        ),
                        x=0.5,
                        y=0.5,
                        font=dict(size=18),
                        showarrow=False,
                    )
                ],
            )

            st.plotly_chart(
                fig_mix,
                width='stretch',
                config={"displaylogo": False},
            )

        # ========================================================
        # SELL ENTIRE ISA PORTFOLIO — MODAL CONFIRMATION
        # ========================================================

        st.markdown("### Sell from Stocks ISA")

        sellable_positions = []

        for position in isa_positions:
            symbol = extract_position_symbol(position)
            available = float_value(
                position.get(
                    "quantityAvailableForTrading",
                    position.get("quantity", 0),
                )
            )
            wallet = position.get("walletImpact", {}) or {}
            market_value = float_value(wallet.get("currentValue"))

            if symbol != "Unknown" and available > 0:
                sellable_positions.append(
                    {
                        "symbol": symbol,
                        "quantity": available,
                        "market_value": market_value,
                    }
                )

        sell_portfolio_value = sum(
            item["market_value"]
            for item in sellable_positions
        )

        isa_manual_enabled = (
            os.getenv("GAINZ_ENABLE_ISA_TRADING") == "YES"
        )

        if sellable_positions:
            st.markdown(
                f"""
                <div style="
                    border:1px solid rgba(255,190,80,.24);
                    background:linear-gradient(
                        145deg,
                        rgba(72,48,20,.22),
                        rgba(17,24,32,.97)
                    );
                    border-radius:16px;
                    padding:1.05rem 1.15rem;
                    margin:.35rem 0 .75rem 0;
                ">
                    <div style="
                        color:#f1c27d;
                        font-size:1rem;
                        font-weight:700;
                        margin-bottom:.25rem;
                    ">
                        Sell Entire Portfolio
                    </div>
                    <div style="
                        color:#8f9aaa;
                        font-size:.82rem;
                        line-height:1.5;
                    ">
                        Sell all {len(sellable_positions)} Stocks ISA holding(s).
                        Estimated current value:
                        <strong style="color:#eef1f5;">
                            £{sell_portfolio_value:,.2f}
                        </strong>.
                        Nothing is submitted when this page loads, refreshes,
                        or when GainZ runs.
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            button_left, button_center, button_right = st.columns(
                [2.15, 1.35, 2.15]
            )

            with button_center:
                open_sell_modal = st.button(
                    "Sell Entire Portfolio",
                    key="isa_open_sell_entire_portfolio_modal",
                    type="primary",
                    width="stretch",
                )

            if open_sell_modal:
                st.session_state[
                    "isa_sell_entire_modal_open"
                ] = True

            @st.dialog("Confirm Sell Entire Portfolio")
            def confirm_sell_entire_isa_modal():
                # Re-read immediately when the modal opens so the
                # confirmation is based on the latest broker state.
                try:
                    preview_broker = Trading212Broker(
                        environment="isa"
                    )

                    preview_pending = preview_broker.orders()

                    if preview_pending:
                        st.error(
                            f"Sell blocked: {len(preview_pending)} pending "
                            "ISA order(s) already exist."
                        )
                        if st.button(
                            "Close",
                            key="isa_sell_modal_close_pending",
                            width="stretch",
                        ):
                            st.session_state[
                                "isa_sell_entire_modal_open"
                            ] = False
                            st.rerun()
                        return

                    preview_positions = (
                        preview_broker.raw_positions()
                    )

                    preview_plan = []

                    for position in preview_positions:
                        symbol = extract_position_symbol(
                            position
                        )
                        available = float_value(
                            position.get(
                                "quantityAvailableForTrading",
                                position.get(
                                    "quantity",
                                    0,
                                ),
                            )
                        )
                        wallet = (
                            position.get(
                                "walletImpact",
                                {},
                            )
                            or {}
                        )
                        value = float_value(
                            wallet.get("currentValue")
                        )

                        if (
                            symbol != "Unknown"
                            and available > 0
                        ):
                            preview_plan.append(
                                {
                                    "symbol": symbol,
                                    "quantity": available,
                                    "market_value": value,
                                }
                            )

                    if not preview_plan:
                        st.info(
                            "There are no ISA holdings available to sell."
                        )
                        if st.button(
                            "Close",
                            key="isa_sell_modal_close_empty",
                            width="stretch",
                        ):
                            st.session_state[
                                "isa_sell_entire_modal_open"
                            ] = False
                            st.rerun()
                        return

                    preview_value = sum(
                        item["market_value"]
                        for item in preview_plan
                    )

                    preview_symbols = ", ".join(
                        item["symbol"]
                        for item in preview_plan
                    )

                    st.markdown(
                        """
                        <div style="
                            text-align:center;
                            margin:.15rem 0 1rem 0;
                        ">
                            <div style="
                                width:56px;
                                height:56px;
                                margin:0 auto .8rem auto;
                                border-radius:50%;
                                display:flex;
                                align-items:center;
                                justify-content:center;
                                border:1px solid rgba(255,92,92,.55);
                                background:rgba(255,92,92,.08);
                                font-size:1.35rem;
                            ">!</div>
                            <div style="
                                color:#aab3bf;
                                font-size:.86rem;
                                line-height:1.55;
                            ">
                                You are about to sell your entire Stocks ISA
                                portfolio using market orders.
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    c1, c2 = st.columns(2)
                    c1.metric(
                        "Total holdings",
                        len(preview_plan),
                    )
                    c2.metric(
                        "Estimated value",
                        f"£{preview_value:,.2f}",
                    )

                    st.markdown(
                        f"""
                        <div style="
                            border:1px solid rgba(255,92,92,.30);
                            background:rgba(255,92,92,.08);
                            border-radius:12px;
                            padding:.85rem .95rem;
                            margin:.75rem 0 .9rem 0;
                            color:#e5e9ef;
                            font-size:.82rem;
                            line-height:1.55;
                        ">
                            <strong>This action cannot be undone once the orders fill.</strong><br>
                            Holdings to sell: {html.escape(preview_symbols)}.<br>
                            Actual execution prices may differ from the
                            current values shown on the dashboard.
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    if not isa_manual_enabled:
                        st.warning(
                            "ISA trading is currently locked. "
                            "The final sell button is disabled."
                        )

                    cancel_col, confirm_col = st.columns(2)

                    with cancel_col:
                        if st.button(
                            "Cancel",
                            key="isa_sell_entire_cancel",
                            width="stretch",
                        ):
                            st.session_state[
                                "isa_sell_entire_modal_open"
                            ] = False
                            st.rerun()

                    with confirm_col:
                        confirm_clicked = st.button(
                            "Confirm Sell",
                            key="isa_sell_entire_confirm",
                            type="primary",
                            width="stretch",
                            disabled=not isa_manual_enabled,
                        )

                    if confirm_clicked:
                        # Final fail-closed re-check immediately before
                        # submitting any real-money order.
                        final_broker = Trading212Broker(
                            environment="isa"
                        )

                        final_pending = final_broker.orders()

                        if final_pending:
                            st.error(
                                "Sell blocked because a pending ISA order "
                                "appeared after the preview."
                            )
                            return

                        final_positions = (
                            final_broker.raw_positions()
                        )

                        final_plan = []

                        for position in final_positions:
                            symbol = extract_position_symbol(
                                position
                            )
                            available = float_value(
                                position.get(
                                    "quantityAvailableForTrading",
                                    position.get(
                                        "quantity",
                                        0,
                                    ),
                                )
                            )

                            if (
                                symbol != "Unknown"
                                and available > 0
                            ):
                                final_plan.append(
                                    (
                                        symbol,
                                        float(available),
                                    )
                                )

                        preview_signature = sorted(
                            (
                                item["symbol"],
                                round(
                                    float(item["quantity"]),
                                    10,
                                ),
                            )
                            for item in preview_plan
                        )

                        final_signature = sorted(
                            (
                                symbol,
                                round(quantity, 10),
                            )
                            for symbol, quantity
                            in final_plan
                        )

                        if (
                            final_signature
                            != preview_signature
                        ):
                            st.error(
                                "Sell blocked because your ISA holdings "
                                "changed after the confirmation modal opened. "
                                "Close the modal and review the portfolio again."
                            )
                            return

                        submitted = []

                        try:
                            # IMPORTANT:
                            # The zero-pending-order check above is performed
                            # once for the entire confirmed liquidation batch.
                            # Reuse this broker for every holding so an order
                            # submitted by this batch does not incorrectly
                            # block the next holding.
                            if (
                                os.getenv("GAINZ_ENABLE_ISA_TRADING")
                                != "YES"
                            ):
                                raise Trading212Error(
                                    "ISA order submission is locked."
                                )

                            for symbol, quantity in final_plan:
                                result = final_broker.market_order(
                                    symbol,
                                    -abs(float(quantity)),
                                )

                                status = str(
                                    getattr(
                                        result,
                                        "status",
                                        "SUBMITTED",
                                    )
                                    or "SUBMITTED"
                                ).upper()

                                submitted.append(
                                    {
                                        "symbol": symbol,
                                        "quantity": quantity,
                                        "status": status,
                                        "order_id": getattr(
                                            result,
                                            "order_id",
                                            None,
                                        ),
                                    }
                                )

                                if status in {
                                    "REJECTED",
                                    "FAILED",
                                    "ERROR",
                                }:
                                    raise Trading212Error(
                                        f"{symbol} SELL returned "
                                        f"status {status}."
                                    )

                        except Exception as exc:
                            st.error(
                                "Order submission stopped. "
                                f"{len(submitted)} order(s) may already "
                                f"have been submitted. {exc}"
                            )

                            if submitted:
                                st.dataframe(
                                    pd.DataFrame(submitted),
                                    width="stretch",
                                    hide_index=True,
                                )
                            return

                        st.success(
                            f"{len(submitted)} ISA SELL order(s) submitted."
                        )

                        if submitted:
                            st.dataframe(
                                pd.DataFrame(submitted),
                                width="stretch",
                                hide_index=True,
                            )

                        st.session_state[
                            "isa_sell_entire_modal_open"
                        ] = False

                        get_isa_account_summary.clear()
                        get_isa_raw_positions.clear()
                        get_isa_orders.clear()

                except Exception as exc:
                    st.error(
                        f"Unable to prepare ISA sell confirmation: {exc}"
                    )

            if st.session_state.get(
                "isa_sell_entire_modal_open",
                False,
            ):
                confirm_sell_entire_isa_modal()

            with st.expander(
                "View details before selling",
                expanded=False,
            ):
                details_df = pd.DataFrame(
                    [
                        {
                            "Ticker": item["symbol"],
                            "Quantity": (
                                f'{item["quantity"]:.8f}'
                            ),
                            "Market Value": (
                                f'£{item["market_value"]:,.2f}'
                            ),
                        }
                        for item in sellable_positions
                    ]
                )

                st.dataframe(
                    details_df,
                    width="stretch",
                    hide_index=True,
                )

                st.caption(
                    "These are market orders. Actual execution prices "
                    "can differ from the current values shown above."
                )

        else:
            st.info(
                "There are no ISA holdings currently available to sell."
            )

        st.divider()

        st.markdown("### Invest with GainZ")

        st.markdown(
            """
            <div class="sf-invest-hero">
                <div class="sf-invest-kicker">✦ GainZ Allocation Engine</div>
                <div class="sf-invest-title">How much do you want to invest?</div>
                <div class="sf-invest-copy">
                    Build an exact, risk-checked Stocks ISA order plan before confirming.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        def set_isa_invest_amount(amount):
            st.session_state["isa_gainz_invest_amount"] = float(amount)
            st.session_state.pop("isa_gainz_preview", None)

        isa_invest_amount = st.number_input(
            "Investment amount (£)",
            min_value=0.0,
            value=0.0,
            step=50.0,
            format="%.2f",
            key="isa_gainz_invest_amount",
        )

        quick1, quick2, quick3, quick4 = st.columns(4)

        quick1.button(
            "£100",
            key="isa_quick_100",
            width="stretch",
            on_click=set_isa_invest_amount,
            args=(100.0,),
        )
        quick2.button(
            "£250",
            key="isa_quick_250",
            width="stretch",
            on_click=set_isa_invest_amount,
            args=(250.0,),
        )
        quick3.button(
            "£500",
            key="isa_quick_500",
            width="stretch",
            on_click=set_isa_invest_amount,
            args=(500.0,),
        )
        quick4.button(
            "MAX CASH",
            key="isa_quick_max",
            width="stretch",
            on_click=set_isa_invest_amount,
            args=(float(isa_cash),),
        )

        st.markdown(
            '<div class="sf-invest-note">'
            'No ticker selection required • GainZ uses the current strategy '
            'and the ISA risk controls'
            '</div>',
            unsafe_allow_html=True,
        )

        st.markdown("")

        if st.button(
            "✦ BUILD MY PORTFOLIO",
            key="isa_build_gainz_portfolio",
            width="stretch",
            type="primary",
        ):
            if isa_invest_amount <= 0:
                st.error("Enter an investment amount greater than £0.")

            elif isa_invest_amount > isa_cash:
                shortfall = max(
                    float(isa_invest_amount) - float(isa_cash),
                    0.0,
                )
                st.warning(
                    f"Not enough ISA cash. You entered "
                    f"{isa_symbol}{isa_invest_amount:,.2f}, but only "
                    f"{isa_symbol}{isa_cash:,.2f} is currently available. "
                    f"Additional cash needed: {isa_symbol}{shortfall:,.2f}."
                )

            else:
                try:
                    build_weights = weights

                    if not build_weights:
                        with st.spinner(
                            "Running GainZ and calculating the current target portfolio..."
                        ):
                            strategy_result = run_gainz(
                                execute_demo=False,
                            )

                        if not strategy_result.get("success"):
                            details = (
                                strategy_result.get("stderr")
                                or strategy_result.get("stdout")
                                or "GainZ strategy run failed."
                            )
                            raise RuntimeError(
                                "GainZ could not calculate the current target portfolio. "
                                + str(details).strip()
                            )

                        fresh_report = load_report()
                        build_weights = fresh_report.get(
                            "target_weights",
                            {},
                        ) or {}

                        if not build_weights:
                            raise RuntimeError(
                                "GainZ completed but produced no positive target portfolio."
                            )

                    with st.spinner(
                        "Building and risk-checking the exact ISA portfolio..."
                    ):
                        st.session_state["isa_gainz_preview"] = (
                            build_isa_gainz_preview(
                                isa_invest_amount,
                                build_weights,
                            )
                        )
                    st.rerun()

                except Exception as exc:
                    st.error(
                        f"GainZ could not build the ISA portfolio: {exc}"
                    )

        gainz_preview = st.session_state.get("isa_gainz_preview")

        if gainz_preview:
            preview_amount = float(
                gainz_preview.get("amount", 0.0)
            )
            preview_orders = gainz_preview.get("orders", []) or []
            frozen_orders = (
                gainz_preview.get("frozen_orders", []) or []
            )
            all_approved = bool(
                gainz_preview.get("all_approved", False)
            )

            planned_stock_value = sum(
                float_value(row.get("estimated_value"))
                for row in frozen_orders
            )
            reserve = max(
                preview_amount - planned_stock_value,
                0.0,
            )

            st.markdown("### GainZ ISA Investment Preview")
            st.caption(
                "No order has been submitted. These exact quantities are "
                "frozen for this preview and will not be recalculated when "
                "you press Confirm Investment."
            )

            g1, g2, g3, g4 = st.columns(4)
            g1.metric(
                "Capital Assigned",
                f"{isa_symbol}{preview_amount:,.2f}",
            )
            g2.metric(
                "Planned for Stocks",
                f"{isa_symbol}{planned_stock_value:,.2f}",
            )
            g3.metric(
                "GainZ Cash Reserve",
                f"{isa_symbol}{reserve:,.2f}",
            )
            g4.metric(
                "Risk Approved",
                f"{len(frozen_orders)}/{len(preview_orders)}",
            )

            if preview_orders:
                preview_df = pd.DataFrame(preview_orders)

                display_df = pd.DataFrame(
                    {
                        "Ticker": preview_df["symbol"],
                        "Side": preview_df["side"],
                        "Quantity": preview_df["quantity"].map(
                            lambda value: f"{float_value(value):.8f}"
                        ),
                        "Est. Value (£)": preview_df[
                            "estimated_value"
                        ].map(
                            lambda value: f"£{float_value(value):,.2f}"
                        ),
                        "Risk Status": preview_df["status"],
                        "Risk Message": preview_df["message"],
                    }
                )

                display_df = add_logo_column(
                    display_df,
                    "Ticker",
                )

                st.dataframe(
                    display_df,
                    hide_index=True,
                    width="stretch",
                    column_config=LOGO_COLUMN_CONFIG,
                )

            blocked_order_count = max(
                len(preview_orders) - len(frozen_orders),
                0,
            )

            if frozen_orders:
                if blocked_order_count:
                    st.warning(
                        f"{len(frozen_orders)} of {len(preview_orders)} proposed "
                        f"ISA BUY orders passed the risk engine. "
                        f"{blocked_order_count} blocked order(s) will be excluded "
                        "from real-money execution."
                    )
                else:
                    st.success(
                        "All proposed ISA BUY orders passed the current "
                        "execution risk checks."
                    )

                @st.dialog("Confirm ISA Investment")
                def show_isa_buy_confirmation():
                    st.markdown(
                        f"""
                        You are about to submit **{len(frozen_orders)} real-money
                        BUY order(s)** to your Trading 212 Stocks ISA.

                        **Capital assigned:** {isa_symbol}{preview_amount:,.2f}

                        **Risk-approved stock deployment:**
                        {isa_symbol}{planned_stock_value:,.2f}

                        **Excluded by risk controls:** {blocked_order_count} order(s)

                        Only the risk-approved frozen orders will be submitted.
                        Blocked orders will not be sent to Trading 212. The exact
                        approved share quantities shown in the preview are frozen.
                        Market execution prices can still differ.
                        """
                    )

                    if os.getenv("GAINZ_ENABLE_ISA_TRADING") != "YES":
                        st.warning(
                            "ISA order submission is currently locked."
                        )

                    cancel_col, confirm_col = st.columns(2)

                    if cancel_col.button(
                        "Cancel",
                        key="isa_buy_confirm_cancel",
                        width="stretch",
                    ):
                        st.rerun()

                    if confirm_col.button(
                        "Confirm Investment",
                        key="isa_buy_confirm_submit",
                        width="stretch",
                        type="primary",
                        disabled=(
                            os.getenv("GAINZ_ENABLE_ISA_TRADING")
                            != "YES"
                        ),
                    ):
                        try:
                            with st.spinner(
                                "Re-checking ISA and submitting "
                                "the confirmed BUY orders..."
                            ):
                                submitted = (
                                    execute_frozen_isa_buy_preview(
                                        gainz_preview
                                    )
                                )

                            accepted_statuses = {
                                "SUBMITTED",
                                "FILLED",
                                "ACCEPTED",
                                "PENDING",
                                "NEW",
                            }

                            accepted = [
                                row
                                for row in submitted
                                if str(
                                    row.get("status", "")
                                ).upper() in accepted_statuses
                            ]

                            failed = [
                                row
                                for row in submitted
                                if str(
                                    row.get("status", "")
                                ).upper() not in accepted_statuses
                            ]

                            if failed:
                                st.error(
                                    f"Order submission stopped. "
                                    f"{len(accepted)} order(s) may already "
                                    "have been submitted."
                                )
                                st.dataframe(
                                    pd.DataFrame(submitted),
                                    hide_index=True,
                                    width="stretch",
                                )
                            else:
                                st.session_state[
                                    "isa_gainz_preview"
                                ] = None
                                get_isa_account_summary.clear()
                                get_isa_raw_positions.clear()
                                get_isa_orders.clear()
                                get_isa_historical_orders.clear()

                                st.success(
                                    f"{len(accepted)} real-money ISA BUY "
                                    "order(s) were submitted."
                                )
                                st.dataframe(
                                    pd.DataFrame(submitted),
                                    hide_index=True,
                                    width="stretch",
                                )

                        except Exception as exc:
                            st.error(
                                f"ISA investment was not submitted: {exc}"
                            )

                if st.button(
                    "CONFIRM ISA INVESTMENT",
                    key="isa_open_buy_confirmation",
                    width="stretch",
                    type="primary",
                ):
                    show_isa_buy_confirmation()

            elif preview_orders:
                st.error(
                    "None of the proposed ISA BUY orders passed the current "
                    "risk checks, so there is nothing available to confirm."
                )

        st.markdown("### ISA Safety State")

        isa_trading_unlocked = (
            os.getenv("GAINZ_ENABLE_ISA_TRADING") == "YES"
        )

        safety_rows = [
            {
                "Check": "ISA API connection",
                "Status": (
                    "CONNECTED"
                    if not isa_account_error
                    else "CHECK"
                ),
            },
            {
                "Check": "Positions feed",
                "Status": (
                    "CONNECTED"
                    if not isa_positions_error
                    else "CHECK"
                ),
            },
            {
                "Check": "Pending orders",
                "Status": (
                    f"{len(isa_orders)} pending"
                    if isa_orders
                    else "CLEAR"
                ),
            },
            {
                "Check": "Dashboard manual SELL",
                "Status": (
                    "ENABLED"
                    if isa_trading_unlocked
                    else "LOCKED"
                ),
            },
            {
                "Check": "Broker ISA execution lock",
                "Status": (
                    "UNLOCKED"
                    if isa_trading_unlocked
                    else "LOCKED"
                ),
            },
        ]

        st.dataframe(
            pd.DataFrame(safety_rows),
            hide_index=True,
            width="stretch",
        )

        if isa_trading_unlocked:
            st.warning(
                "Manual ISA trading is enabled. "
                "No order is submitted by page load, refresh, strategy execution, "
                "or the GainZ allocation preview. A real order requires the "
                "Manual ISA Trade panel plus the exact confirmation phrase."
            )
        else:
            st.success(
                "Real-money ISA order submission remains locked."
            )


if nav_page == "System":
    s1, s2, s3 = st.columns(3)
    s1.metric("Environment", "PRACTICE")
    s2.metric("System Health", health)
    s3.metric("Cache", f"{CACHE_TTL}s")
    st.caption("Real-money trading is locked in this test application.")

    # ============================================================
    # CONNECTION STATUS
    # ============================================================

    st.divider()

    with st.expander(
        "🔌 Connection status"
    ):

        st.write(
            "**Trading environment:** Practice / Demo"
        )

        st.write(
            "**Account currency:**",
            currency,
        )

        st.write(
            "**Live money:** Locked"
        )

        st.write(
            "**Cache duration:**",
            f"{CACHE_TTL} seconds",
        )

        st.write(
            "**Account API:**",
            "✅ OK"
            if not account_error
            else "⚠️ Temporary issue",
        )

        st.write(
            "**Positions API:**",
            "✅ OK"
            if not positions_error
            else "⚠️ Temporary issue",
        )

        st.write(
            "**Orders API:**",
            "✅ OK"
            if not orders_error
            else "⚠️ Temporary issue",
        )

        if all_errors:

            st.caption(
                "Technical details:"
            )

            for error in all_errors:

                st.code(
                    str(error)
                )



# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "SF Alpha • Test Environment • Trading 212 Practice • "
    "Broker reads cached for 120 seconds • "
    "Real-money trading locked • "
    "Historical performance does not guarantee future returns."
)# ============================================================
