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
PAUSE_PATH = ROOT / "outputs" / "gainz_paused.flag"

load_dotenv(ENV_PATH)

st.set_page_config(
    page_title="GainZ",
    page_icon="📈",
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
    f"Broker data cached for {CACHE_TTL} seconds."
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
    f"{currency_symbol}{cash_available:,.2f}",
)

c3.metric(
    "Exposure",
    f"{exposure * 100:.1f}%",
)

c4.metric(
    "Open Positions",
    open_position_count,
)


# ============================================================
# ACCOUNT
# ============================================================

st.divider()

st.subheader("Account")

a1, a2, a3, a4 = st.columns(4)

a1.metric(
    "Total Value",
    f"{currency_symbol}{total_account_value:,.2f}",
)

a2.metric(
    "Invested",
    f"{currency_symbol}{investment_value:,.2f}",
)

a3.metric(
    "Total Cost",
    f"{currency_symbol}{total_cost:,.2f}",
)

a4.metric(
    "Available Cash",
    f"{currency_symbol}{cash_available:,.2f}",
)


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



# ============================================================
# GAINZ STRATEGY
# ============================================================

st.divider()

st.subheader("GainZ Strategy")

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

# ============================================================
# CONTROLS
# ============================================================

st.divider()

st.subheader("GainZ Actions")

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
    "GainZ • Trading 212 Practice • "
    "Broker reads cached for 120 seconds • "
    "Real-money trading locked • "
    "Historical performance does not guarantee future returns."
)# ============================================================
