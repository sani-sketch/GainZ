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
        return None

    try:
        return json.loads(
            REPORT_PATH.read_text(encoding="utf-8")
        )
    except Exception:
        return None


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
        name or "Unknown"
    )


def friendly_risk(name):
    mapping = {
        "vol12_defensive": "Defensive",
    }

    return mapping.get(
        name,
        name or "Unknown"
    )


# ============================================================
# HEADER
# ============================================================

st.title("📈 GainZ")

st.caption(
    "Automated Practice Trading"
)

st.success(
    "🟢 System running in Practice mode"
)

st.info(
    "🔒 Real-money trading is locked"
)


# ============================================================
# LOAD BROKER STATE
# ============================================================

broker_error = None
account = {}
positions = []
pending_orders = []

try:
    broker = Trading212Broker(
        environment="demo"
    )

    account = broker.account_summary()
    positions = broker.positions()
    pending_orders = broker.orders()

except Exception as exc:
    broker_error = str(exc)


# ============================================================
# LOAD REPORT
# ============================================================

report = load_report() or {}

decision = report.get(
    "decision",
    {}
)

weights = report.get(
    "target_weights",
    {}
)

execution_orders = report.get(
    "orders",
    []
)

cash_available = float(
    report.get(
        "cash_available",
        0,
    )
    or 0
)

executed = bool(
    report.get(
        "executed",
        False,
    )
)

exposure = float(
    decision.get(
        "exposure",
        0,
    )
    or 0
)


# ============================================================
# SYSTEM HEALTH
# ============================================================

if broker_error:
    health = "ERROR"
    health_icon = "🔴"
elif pending_orders:
    health = "PENDING"
    health_icon = "🟡"
else:
    health = "HEALTHY"
    health_icon = "🟢"


# ============================================================
# MAIN SUMMARY CARDS
# ============================================================

st.subheader("Overview")

c1, c2, c3, c4 = st.columns(4)

c1.metric(
    "System",
    f"{health_icon} {health}"
)

c2.metric(
    "Cash",
    f"£{cash_available:,.2f}"
)

c3.metric(
    "Invested",
    f"{exposure * 100:.0f}%"
)

c4.metric(
    "Open Positions",
    len(positions)
)


# ============================================================
# TODAY
# ============================================================

st.divider()

st.subheader("Today")

if broker_error:

    st.error(
        f"GainZ cannot connect to Trading 212: {broker_error}"
    )

else:

    mode = decision.get(
        "mode",
        "N/A"
    )

    strategy = friendly_strategy(
        decision.get("variant")
    )

    risk_mode = friendly_risk(
        decision.get("risk")
    )

    if executed:
        action_text = "Practice orders were submitted."
    elif report:
        action_text = (
            "A new plan was generated. "
            "No orders were submitted."
        )
    else:
        action_text = (
            "No GainZ plan has been generated yet."
        )

    st.write(
        f"**Mode:** {mode}"
    )

    st.write(
        f"**Strategy:** {strategy}"
    )

    st.write(
        f"**Risk mode:** {risk_mode}"
    )

    st.write(
        f"**Today's action:** {action_text}"
    )


# ============================================================
# ORDER STATUS SUMMARY
# ============================================================

st.divider()

st.subheader("Orders")

o1, o2, o3 = st.columns(3)

pending_count = len(
    pending_orders
)

filled_count = len(
    positions
)

rejected_count = len(
    [
        order
        for order in execution_orders
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

o1.metric(
    "Pending",
    pending_count
)

o2.metric(
    "Open Positions",
    filled_count
)

o3.metric(
    "Rejected",
    rejected_count
)


# ============================================================
# PORTFOLIO
# ============================================================

st.divider()

st.subheader("Portfolio")

if positions:

    position_rows = []

    for p in positions:

        target_weight = weights.get(
            p.symbol,
            0
        )

        position_rows.append(
            {
                "Ticker": p.symbol,
                "Quantity": round(
                    p.quantity,
                    4
                ),
                "Price": round(
                    p.price,
                    2
                ),
                "Value": round(
                    p.value,
                    2
                ),
                "Target %": round(
                    target_weight * 100,
                    1
                ),
                "Status": "Held",
            }
        )

    positions_df = pd.DataFrame(
        position_rows
    )

    st.dataframe(
        positions_df,
        use_container_width=True,
        hide_index=True,
    )

else:
    st.info(
        "No open positions yet."
    )


# ============================================================
# TARGET PORTFOLIO
# ============================================================

with st.expander(
    "View target portfolio"
):

    if weights:

        target_rows = []

        for ticker, weight in weights.items():

            target_rows.append(
                {
                    "Ticker": ticker,
                    "Target Weight %":
                        round(
                            float(weight) * 100,
                            2
                        ),
                }
            )

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
            )["Target Weight %"]
        )

    else:
        st.info(
            "No target portfolio available."
        )


# ============================================================
# PENDING ORDERS
# ============================================================

with st.expander(
    "View pending broker orders"
):

    if pending_orders:

        pending_df = pd.DataFrame(
            pending_orders
        )

        preferred_columns = [
            "ticker",
            "side",
            "quantity",
            "filledQuantity",
            "status",
            "createdAt",
        ]

        existing = [
            column
            for column in preferred_columns
            if column in pending_df.columns
        ]

        if existing:
            pending_df = pending_df[
                existing
            ]

        st.dataframe(
            pending_df,
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.success(
            "No pending orders."
        )


# ============================================================
# CONTROLS
# ============================================================

st.divider()

st.subheader("Controls")

b1, b2, b3 = st.columns(3)

with b1:

    if st.button(
        "🔄 Refresh",
        use_container_width=True,
    ):
        st.rerun()


with b2:

    if st.button(
        "🧠 Generate Plan",
        use_container_width=True,
        disabled=not credentials_present(),
    ):

        with st.spinner(
            "GainZ is generating a new plan..."
        ):
            result = run_gainz(
                execute_demo=False
            )

        if result["success"]:
            st.success(
                "New plan generated."
            )
            st.rerun()

        else:
            st.error(
                result["stderr"]
            )


with b3:

    confirm = st.checkbox(
        "I confirm this is Practice money"
    )

    if st.button(
        "🧪 Execute Practice",
        use_container_width=True,
        type="primary",
        disabled=(
            not credentials_present()
            or not confirm
            or pending_count > 0
        ),
    ):

        with st.spinner(
            "Submitting Practice orders..."
        ):
            result = run_gainz(
                execute_demo=True
            )

        if result["success"]:
            st.success(
                "Practice orders submitted."
            )
            st.rerun()

        else:
            st.error(
                result["stderr"]
            )


if pending_count > 0:

    st.warning(
        "Execution is disabled while pending orders exist."
    )


# ============================================================
# ADVANCED
# ============================================================

st.divider()

with st.expander(
    "⚙️ Advanced"
):

    st.write(
        "**Environment:** Practice / Demo"
    )

    st.write(
        "**Live trading:** Locked"
    )

    st.write(
        "**Credentials:**",
        "Configured"
        if credentials_present()
        else "Missing"
    )

    if decision:

        st.write(
            "**GainZ Sharpe:**",
            round(
                decision.get(
                    "gainz_sharpe",
                    0
                ),
                2
            )
        )

        st.write(
            "**Benchmark Sharpe:**",
            round(
                decision.get(
                    "benchmark_sharpe",
                    0
                ),
                2
            )
        )

    st.write(
        "**Raw GainZ report:**"
    )

    st.json(
        report
    )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "GainZ • Practice trading only • "
    "Historical performance does not guarantee future returns."
)