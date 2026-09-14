import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from broker.trading212 import Trading212Broker


# ============================================================
# CONFIG
# ============================================================

ROOT = Path(__file__).resolve().parent
REPORT_PATH = ROOT / "outputs" / "trading212_demo_report.json"
RUNNER_PATH = ROOT / "run_trading212.py"
ENV_PATH = ROOT / ".env"

load_dotenv(ENV_PATH)

st.set_page_config(
    page_title="GainZ",
    page_icon="📈",
    layout="wide",
)


# ============================================================
# CONSTANTS
# ============================================================

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
    """
    One positions API call only.

    We use this raw response for:
    - open positions
    - portfolio table
    - profit/loss
    """
    broker = Trading212Broker(environment="demo")
    return broker.raw_positions()


@st.cache_data(ttl=CACHE_TTL)
def get_orders():
    broker = Trading212Broker(environment="demo")
    return broker.orders()


# ============================================================
# HELPERS
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


def is_rate_limit_error(error):
    if not error:
        return False

    text = str(error).lower()

    return (
        "429" in text
        or "toomanyrequests" in text
        or "too many requests" in text
    )


def symbol_from_ticker(ticker):
    ticker = str(ticker or "")

    if "_" in ticker:
        return ticker.split("_")[0]

    return ticker


def float_value(value, default=0.0):
    try:
        return float(value or 0)

    except (TypeError, ValueError):
        return default


# ============================================================
# ACCOUNT HELPERS
# ============================================================

def extract_cash(account):
    """
    Trading 212 account summary may contain nested cash data.
    """

    if not isinstance(account, dict):
        return 0.0

    cash = account.get("cash", {})

    if isinstance(cash, dict):

        for key in (
            "availableToTrade",
            "free",
            "total",
            "cash",
        ):
            if key in cash:
                return float_value(
                    cash.get(key)
                )

    return float_value(cash)


def extract_investment_value(account):
    """
    Try to get account-currency investment value from Trading 212.
    """

    if not isinstance(account, dict):
        return None

    investments = account.get(
        "investments",
        {}
    )

    if isinstance(investments, dict):

        for key in (
            "currentValue",
            "value",
            "marketValue",
        ):
            if key in investments:
                return float_value(
                    investments.get(key)
                )

    for key in (
        "portfolioValue",
        "investmentsValue",
    ):
        if key in account:
            return float_value(
                account.get(key)
            )

    return None


def extract_account_ppl(account):
    """
    Prefer broker-provided account P/L where available.
    """

    if not isinstance(account, dict):
        return None

    for key in (
        "ppl",
        "profitLoss",
        "unrealizedPpl",
    ):
        if key in account:
            return float_value(
                account.get(key)
            )

    investments = account.get(
        "investments",
        {}
    )

    if isinstance(investments, dict):

        for key in (
            "ppl",
            "profitLoss",
            "unrealizedPpl",
        ):
            if key in investments:
                return float_value(
                    investments.get(key)
                )

    return None


# ============================================================
# SAFE BROKER FETCH
# ============================================================

def fetch_with_fallback(
    cache_key,
    fetch_function,
):
    """
    Fetch broker data.

    If Trading 212 temporarily rate-limits us,
    retain the last successful response stored in the
    user's Streamlit session.
    """

    try:
        value = fetch_function()

        st.session_state[
            cache_key
        ] = value

        return value, None

    except Exception as exc:

        old_value = st.session_state.get(
            cache_key
        )

        return old_value, str(exc)


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("GainZ")

preview_mode = st.sidebar.checkbox(
    "Preview dashboard with sample data",
    value=False,
)

st.sidebar.caption(
    "Preview mode uses simulated data."
)

st.sidebar.caption(
    f"Broker data refreshes every {CACHE_TTL} seconds."
)


# ============================================================
# HEADER
# ============================================================

st.title("📈 GainZ")

st.caption(
    "Automated Practice Trading"
)

if preview_mode:

    st.warning(
        "🧪 Preview mode is ON — showing sample data"
    )

else:

    st.success(
        "🟢 Connected to Trading 212 Practice"
    )

st.info(
    "🔒 Real-money trading is locked"
)


# ============================================================
# LOAD REPORT
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

execution_orders = report.get(
    "orders",
    [],
)

executed = bool(
    report.get(
        "executed",
        False,
    )
)


# ============================================================
# BROKER DATA
# ============================================================

account = {}
raw_positions = []
broker_orders = []

account_error = None
positions_error = None
orders_error = None


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


account = account or {}
raw_positions = raw_positions or []
broker_orders = broker_orders or []


# ============================================================
# PREVIEW DATA
# ============================================================

if preview_mode:

    account = {
        "cash": {
            "availableToTrade": 3500.00,
        },
        "investments": {
            "currentValue": 1500.00,
        },
        "ppl": 72.50,
    }

    report = {
        "environment": "demo",
        "executed": True,
        "decision": {
            "mode": "GAINZ",
            "variant": "N15_momentum_trend_none",
            "risk": "vol12_defensive",
            "exposure": 0.88,
            "gainz_sharpe": 2.21,
            "benchmark_sharpe": 1.27,
        },
        "target_weights": {
            "AMD": 0.0587,
            "MU": 0.0587,
            "PANW": 0.0587,
            "FTNT": 0.0587,
            "CRM": 0.0587,
            "BAC": 0.0587,
        },
    }

    decision = report["decision"]
    weights = report["target_weights"]
    executed = True

    raw_positions = [
        {
            "ticker": "AMD_US_EQ",
            "quantity": 1.50,
            "averagePrice": 175.00,
            "currentPrice": 190.00,
            "ppl": 22.50,
        },
        {
            "ticker": "MU_US_EQ",
            "quantity": 2.00,
            "averagePrice": 150.00,
            "currentPrice": 145.00,
            "ppl": -10.00,
        },
        {
            "ticker": "CRM_US_EQ",
            "quantity": 1.10,
            "averagePrice": 250.00,
            "currentPrice": 265.00,
            "ppl": 16.50,
        },
    ]

    broker_orders = [
        {
            "ticker": "PANW_US_EQ",
            "side": "BUY",
            "quantity": 0.84,
            "filledQuantity": 0,
            "status": "NEW",
            "createdAt": "Preview",
        }
    ]


# ============================================================
# CALCULATED VALUES
# ============================================================

cash_available = extract_cash(
    account
)

investment_value = extract_investment_value(
    account
)

account_ppl = extract_account_ppl(
    account
)

open_position_count = len(
    raw_positions
)

pending_count = len(
    broker_orders
)


# Exposure in account currency, if broker provides both values.

if (
    investment_value is not None
    and investment_value + cash_available > 0
):

    exposure = (
        investment_value
        / (
            investment_value
            + cash_available
        )
    )

else:

    exposure = float_value(
        decision.get(
            "exposure",
            0,
        )
    )


# ============================================================
# SYSTEM HEALTH
# ============================================================

all_errors = [
    error
    for error in (
        account_error,
        positions_error,
        orders_error,
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
        "successfully loaded data where available. "
        "You do not need to keep refreshing."
    )


# ============================================================
# OVERVIEW
# ============================================================

st.subheader("Overview")

c1, c2, c3, c4 = st.columns(4)

c1.metric(
    "System",
    f"{health_icon} {health}",
)

c2.metric(
    "Cash",
    f"£{cash_available:,.2f}",
)

c3.metric(
    "Exposure",
    f"{exposure * 100:.0f}%",
)

c4.metric(
    "Open Positions",
    open_position_count,
)


# ============================================================
# TODAY
# ============================================================

st.divider()

st.subheader("Today")

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
        "A GainZ plan has been generated."
    )

else:

    action_text = (
        "Broker data is live. "
        "No local strategy report is available on this Render instance."
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
# PERFORMANCE
# ============================================================

st.divider()

st.subheader("Performance")

performance_rows = []

calculated_total_cost = 0.0
calculated_total_value = 0.0
calculated_total_ppl = 0.0


for position in raw_positions:

    ticker = symbol_from_ticker(
        position.get(
            "ticker"
        )
    )

    quantity = float_value(
        position.get(
            "quantity"
        )
    )

    average_price = float_value(
        position.get(
            "averagePrice"
        )
    )

    current_price = float_value(
        position.get(
            "currentPrice",
            average_price,
        )
    )

    cost = (
        quantity
        * average_price
    )

    current_value = (
        quantity
        * current_price
    )

    calculated_ppl = (
        current_value
        - cost
    )

    # Prefer broker P/L if Trading 212 supplies it.
    broker_ppl = position.get(
        "ppl"
    )

    if broker_ppl is not None:

        pnl = float_value(
            broker_ppl
        )

    else:

        pnl = calculated_ppl

    return_pct = (
        (calculated_ppl / cost) * 100
        if cost
        else 0
    )

    calculated_total_cost += cost
    calculated_total_value += current_value
    calculated_total_ppl += pnl

    performance_rows.append(
        {
            "Ticker": ticker,
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
            "P/L": round(
                pnl,
                2,
            ),
            "Return %": round(
                return_pct,
                2,
            ),
        }
    )


# Prefer broker-level account P/L if provided.
display_ppl = (
    account_ppl
    if account_ppl is not None
    else calculated_total_ppl
)


p1, p2, p3 = st.columns(3)

p1.metric(
    "Open Positions",
    open_position_count,
)

if investment_value is not None:

    p2.metric(
        "Portfolio Value",
        f"£{investment_value:,.2f}",
    )

else:

    p2.metric(
        "Portfolio",
        "Connected",
    )


p3.metric(
    "P/L",
    f"£{display_ppl:,.2f}",
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
    "Portfolio-level £ values use Trading 212 account data "
    "where available. Individual US-stock prices may be "
    "quoted in the instrument's trading currency."
)


# ============================================================
# ORDERS
# ============================================================

st.divider()

st.subheader("Orders")


rejected_count = len(
    [
        order
        for order in broker_orders
        if str(
            order.get(
                "status",
                ""
            )
        ).upper()
        in {
            "REJECTED",
            "FAILED",
            "ERROR",
        }
    ]
)


o1, o2, o3 = st.columns(3)

o1.metric(
    "Pending",
    pending_count,
)

o2.metric(
    "Positions",
    open_position_count,
)

o3.metric(
    "Rejected",
    rejected_count,
)


# ============================================================
# PORTFOLIO
# ============================================================

st.divider()

st.subheader("Portfolio")


if raw_positions:

    portfolio_rows = []

    for position in raw_positions:

        ticker = symbol_from_ticker(
            position.get(
                "ticker"
            )
        )

        quantity = float_value(
            position.get(
                "quantity"
            )
        )

        average_price = float_value(
            position.get(
                "averagePrice"
            )
        )

        current_price = float_value(
            position.get(
                "currentPrice",
                average_price,
            )
        )

        target_weight = float_value(
            weights.get(
                ticker,
                0
            )
        )

        portfolio_rows.append(
            {
                "Ticker": ticker,
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
                "Target %": round(
                    target_weight * 100,
                    2,
                ),
                "Status": "Held",
            }
        )

    portfolio_df = pd.DataFrame(
        portfolio_rows
    )

    st.dataframe(
        portfolio_df,
        use_container_width=True,
        hide_index=True,
    )

else:

    st.info(
        "No open Practice positions."
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
            "Target portfolio is not available on this "
            "Render instance yet."
        )


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


# ============================================================
# CONTROLS
# ============================================================

st.divider()

st.subheader("Controls")

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
# ADVANCED
# ============================================================

with st.expander(
    "⚙️ Advanced"
):

    st.write(
        "**Credentials:**",
        "Configured"
        if credentials_present()
        else "Missing",
    )

    if decision:

        st.write(
            "**GainZ Sharpe:**",
            round(
                float_value(
                    decision.get(
                        "gainz_sharpe"
                    )
                ),
                2,
            ),
        )

        st.write(
            "**Benchmark Sharpe:**",
            round(
                float_value(
                    decision.get(
                        "benchmark_sharpe"
                    )
                ),
                2,
            ),
        )

    st.write(
        "**Raw strategy report:**"
    )

    st.json(
        report
    )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "GainZ • Trading 212 Practice • "
    "Broker reads cached for 120 seconds • "
    "Real-money trading locked • "
    "Historical performance does not guarantee future returns."
)