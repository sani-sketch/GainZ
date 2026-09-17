import json
import os
import matplotlib.pyplot as plt
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

from broker.trading212 import Trading212Broker


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


def run_gainz(execute_demo=False):
    command = [
        sys.executable,
        str(RUNNER_PATH),
    ]

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

st.markdown(
    """
    <div class="sf-topbar">
        <div class="sf-search">⌕ &nbsp; Search stocks, ETFs, or insights...</div>
        <div class="sf-env">● Trading 212 Practice</div>
        <div class="sf-lock">🔒 Real money locked</div>
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

                fig, ax = plt.subplots(figsize=(10, 4))
                fig.patch.set_alpha(0)
                ax.set_facecolor("none")

                ax.plot(
                    chart_df.index,
                    chart_df["portfolio_value"],
                    linewidth=2,
                )

                min_value = chart_df["portfolio_value"].min()
                max_value = chart_df["portfolio_value"].max()
                movement = max_value - min_value

                padding = max(
                    movement * 0.35,
                    max_value * 0.002,
                    5,
                )

                ax.set_ylim(
                    min_value - padding,
                    max_value + padding,
                )

                ax.set_ylabel(
                    f"Portfolio Value ({currency_symbol})"
                )
                ax.set_xlabel("")
                ax.grid(True, alpha=0.12)
                ax.spines["top"].set_visible(False)
                ax.spines["right"].set_visible(False)

                fig.autofmt_xdate()

                st.pyplot(
                    fig,
                    use_container_width=True,
                )

                plt.close(fig)

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
                    use_container_width=True,
                )

                plt.close(fig)

                allocation_display = allocation_df.copy()

                allocation_display["Weight"] = allocation_display[
                    "Weight"
                ].map(
                    lambda x: f"{x * 100:.1f}%"
                )

                st.dataframe(
                    allocation_display[
                        ["Ticker", "Weight"]
                    ].head(6),
                    use_container_width=True,
                    hide_index=True,
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

                ticker = html.escape(
                    str(row.get("Ticker", ""))
                )

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
                        <span>
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


if nav_page == "Performance":
    # ============================================================
    # PERFORMANCE
    # ============================================================

    st.divider()

    st.subheader("Performance")

    p1, p2, p3, p4 = st.columns(4)

    p1.metric(
        "Unrealised P/L",
        f"{currency_symbol}{unrealized_ppl:,.2f}",
    )

    p2.metric(
        "Realised P/L",
        f"{currency_symbol}{realized_ppl:,.2f}",
    )

    p3.metric(
        "Total P/L",
        f"{currency_symbol}{total_ppl:,.2f}",
    )

    p4.metric(
        "Portfolio Value",
        f"{currency_symbol}{investment_value:,.2f}",
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

        st.dataframe(
            performance_df,
            use_container_width=True,
            hide_index=True,
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

            st.dataframe(
                target_df,
                use_container_width=True,
                hide_index=True,
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

            st.dataframe(
                orders_df,
                use_container_width=True,
                hide_index=True,
            )

        else:

            st.success(
                "No pending broker orders."
            )




if nav_page == "Risk & Controls":
    # ============================================================
    # MASTER SAFETY CONTROLS — PRACTICE ONLY
    # ============================================================

    st.divider()
    st.subheader("🛑 Emergency Controls")

    paused = gainz_is_paused()

    if paused:
        st.warning(
            "GainZ is PAUSED on this dashboard instance. Automatic execution "
            "must also check this pause flag before it can be relied on as a "
            "cross-system lock."
        )
    else:
        st.success("GainZ dashboard pause is currently OFF.")

    m1, m2 = st.columns(2)

    with m1:
        if not paused:
            if st.button(
                "⏸️ Pause GainZ",
                use_container_width=True,
                disabled=preview_mode,
            ):
                set_gainz_paused(True)
                st.success("GainZ dashboard pause enabled.")
                st.rerun()
        else:
            if st.button(
                "▶️ Resume GainZ",
                use_container_width=True,
                disabled=preview_mode,
            ):
                set_gainz_paused(False)
                st.success("GainZ dashboard pause removed.")
                st.rerun()

    with m2:
        st.metric(
            "Automation State",
            "PAUSED" if paused else "ACTIVE",
        )

    st.caption(
        "Important: Render and GitHub Actions run separately. This dashboard pause "
        "is not yet a guaranteed GitHub Actions kill-switch. Do not rely on it to "
        "block scheduled orders until we add a shared persistent pause state."
    )

    st.markdown("#### 🚨 Sell Entire Practice Portfolio")

    # ------------------------------------------------------------
    # Calculate full-portfolio exit values directly from
    # Trading 212 walletImpact data (GBP)
    # ------------------------------------------------------------

    portfolio_value_for_exit = 0.0
    portfolio_cost_for_exit = 0.0
    portfolio_profit_for_exit = 0.0

    for position in raw_positions:

        wallet = position.get(
            "walletImpact",
            {},
        ) or {}

        portfolio_value_for_exit += float_value(
            wallet.get(
                "currentValue"
            )
        )

        portfolio_cost_for_exit += float_value(
            wallet.get(
                "totalCost"
            )
        )

        portfolio_profit_for_exit += float_value(
            wallet.get(
                "unrealizedProfitLoss"
            )
        )


    # ------------------------------------------------------------
    # Portfolio return %
    # ------------------------------------------------------------

    if portfolio_cost_for_exit > 0:

        portfolio_return_for_exit = (
            portfolio_profit_for_exit
            / portfolio_cost_for_exit
        ) * 100

    else:

        portfolio_return_for_exit = 0.0


    # ------------------------------------------------------------
    # Exit summary
    # ------------------------------------------------------------

    st.write(
        f"Open positions: **{len(raw_positions)}**"
    )

    e1, e2, e3, e4 = st.columns(4)

    e1.metric(
        "Current Value",
        f"{currency_symbol}{portfolio_value_for_exit:,.2f}",
    )

    e2.metric(
        "Total Cost",
        f"{currency_symbol}{portfolio_cost_for_exit:,.2f}",
    )

    e3.metric(
        "Profit to Book",
        f"{currency_symbol}{portfolio_profit_for_exit:,.2f}",
        delta=f"{portfolio_return_for_exit:+.2f}%",
    )

    e4.metric(
        "Est. Cash From Sale",
        f"{currency_symbol}{portfolio_value_for_exit:,.2f}",
    )


    # ------------------------------------------------------------
    # Human-readable explanation
    # ------------------------------------------------------------

    if portfolio_profit_for_exit > 0:

        st.success(
            f"💰 If you sold the entire portfolio at approximately "
            f"the current prices, you would book around "
            f"{currency_symbol}{portfolio_profit_for_exit:,.2f} "
            f"of profit ({portfolio_return_for_exit:+.2f}%)."
        )

    elif portfolio_profit_for_exit < 0:

        st.warning(
            f"⚠️ The portfolio currently has an unrealised loss of "
            f"{currency_symbol}{abs(portfolio_profit_for_exit):,.2f} "
            f"({portfolio_return_for_exit:+.2f}%). "
            f"Selling everything now would approximately realise this loss."
        )

    else:

        st.info(
            "The portfolio is currently approximately at break-even."
        )


    st.caption(
        "Estimate only. Final realised P/L can differ because market prices "
        "and GBP/USD FX rates may change before the orders are filled."
    )


    # ------------------------------------------------------------
    # SELL ALL confirmation
    # ------------------------------------------------------------

    sell_all_text = st.text_input(
        "Type SELL ALL to unlock the full-portfolio exit",
        key="sell_all_confirmation_text",
        disabled=(
            preview_mode
            or not raw_positions
            or pending_count > 0
        ),
    )

    sell_all_ack = st.checkbox(
        "I understand this will submit SELL orders for every open "
        "Trading 212 Practice position.",
        key="sell_all_ack",
        disabled=(
            preview_mode
            or not raw_positions
            or pending_count > 0
        ),
    )


    # ------------------------------------------------------------
    # Final safety check
    # ------------------------------------------------------------

    sell_all_disabled = (
        preview_mode
        or not credentials_present()
        or not raw_positions
        or pending_count > 0
        or sell_all_text.strip().upper() != "SELL ALL"
        or not sell_all_ack
    )


    # ------------------------------------------------------------
    # Execute SELL ALL
    # ------------------------------------------------------------

    if st.button(
        "🚨 Close All Practice Positions",
        type="primary",
        use_container_width=True,
        disabled=sell_all_disabled,
    ):

        # Pause locally before attempting liquidation
        set_gainz_paused(True)

        with st.spinner(
            "Submitting Practice sell orders for all open positions..."
        ):

            results = submit_practice_sell_all(
                raw_positions
            )


        if not results:

            st.warning(
                "No sellable Practice positions were found."
            )

        else:

            result_df = pd.DataFrame(
                results
            )

            st.dataframe(
                result_df,
                use_container_width=True,
                hide_index=True,
            )


            failed = result_df[
                result_df["status"]
                .str.upper()
                .isin(
                    [
                        "REJECTED",
                        "FAILED",
                        "ERROR",
                    ]
                )
            ]


            if failed.empty:

                st.success(
                    f"All available Practice sell orders were submitted. "
                    f"Approximately "
                    f"{currency_symbol}{portfolio_profit_for_exit:,.2f} "
                    f"of current unrealised P/L was available to be realised "
                    f"before execution."
                )

                st.info(
                    "GainZ dashboard pause has been enabled."
                )

            else:

                st.error(
                    "At least one sell did not submit successfully. "
                    "Do not retry blindly. Review the result table "
                    "and Trading 212 orders first."
                )


            st.cache_data.clear()


if nav_page == "Dashboard":
    # ============================================================
    # CONTROLS
    # ============================================================

    st.divider()

    st.subheader("SF Alpha Actions")

    b1, b2, b3 = st.columns(3)


    with b1:

        if st.button(
            "🔄 Refresh Broker Data",
            use_container_width=True,
        ):

            st.cache_data.clear()
            st.rerun()


    with b2:

        if st.button(
            "🧠 Generate Plan",
            use_container_width=True,
            disabled=(
                preview_mode
                or not credentials_present()
            ),
        ):

            with st.spinner(
                "Generating GainZ plan..."
            ):

                result = run_gainz(
                    execute_demo=False
                )

            if result["success"]:

                st.success(
                    "GainZ plan generated."
                )

            else:

                st.error(
                    result["stderr"]
                    or "Plan generation failed."
                )


    with b3:

        practice_confirm = st.checkbox(
            "I confirm this is Practice money",
            disabled=preview_mode,
        )

        execute_disabled = (
            preview_mode
            or not credentials_present()
            or not practice_confirm
            or pending_count > 0
        )

        if st.button(
            "🧪 Execute Practice",
            type="primary",
            use_container_width=True,
            disabled=execute_disabled,
        ):

            with st.spinner(
                "Submitting Practice orders..."
            ):

                result = run_gainz(
                    execute_demo=True
                )

            st.cache_data.clear()

            if result["success"]:

                st.success(
                    "Practice orders submitted."
                )

            else:

                st.error(
                    result["stderr"]
                    or "Practice execution failed."
                )


    if preview_mode:

        st.info(
            "Trading controls are disabled in Preview mode."
        )

    elif pending_count > 0:

        st.warning(
            "Practice execution is disabled while broker "
            "orders are pending."
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
