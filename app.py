import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv


# ============================================================
# CONFIG
# ============================================================

ROOT = Path(__file__).resolve().parent
REPORT_PATH = ROOT / "outputs" / "trading212_demo_report.json"
RUNNER_PATH = ROOT / "run_trading212.py"
ENV_PATH = ROOT / ".env"

# Load credentials from .env
load_dotenv(ENV_PATH)

st.set_page_config(
    page_title="GainZ Control Panel",
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
            REPORT_PATH.read_text(
                encoding="utf-8"
            )
        )
    except Exception as exc:
        st.error(
            f"Could not read report: {exc}"
        )
        return None


def run_gainz(execute_demo=False):
    """
    Run GainZ through the same Python environment
    currently running Streamlit.

    IMPORTANT:
    Only DEMO execution is exposed here.
    """

    command = [
        sys.executable,
        str(RUNNER_PATH),
    ]

    if execute_demo:
        command.append("--execute-demo")

    env = os.environ.copy()

    try:
        result = subprocess.run(
            command,
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "GainZ timed out after 180 seconds.",
            "returncode": -1,
        }

    except Exception as exc:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(exc),
            "returncode": -1,
        }


# ============================================================
# HEADER
# ============================================================

st.title("📈 GainZ Control Panel")
st.caption(
    "Regime-aware quantitative portfolio system • "
    "Trading 212 Practice environment"
)

st.success(
    "🟢 PRACTICE / DEMO ENVIRONMENT"
)

st.error(
    "🔒 LIVE TRADING IS LOCKED — this dashboard "
    "does not expose a live-money execution button."
)


# ============================================================
# CONNECTION STATUS
# ============================================================

st.subheader("System Status")

status1, status2, status3, status4 = st.columns(4)

status1.metric(
    "Trading Environment",
    "PRACTICE",
)

status2.metric(
    "API Credentials",
    "READY" if credentials_present() else "MISSING",
)

status3.metric(
    "Live Trading",
    "LOCKED",
)

status4.metric(
    "Report",
    "AVAILABLE" if REPORT_PATH.exists() else "NONE",
)


# ============================================================
# CONTROL PANEL
# ============================================================

st.divider()

st.subheader("GainZ Controls")

col1, col2, col3 = st.columns(3)


# ------------------------------------------------------------
# BUTTON 1: REFRESH DISPLAY
# ------------------------------------------------------------

with col1:
    if st.button(
        "🔄 Refresh Dashboard",
        use_container_width=True,
    ):
        st.rerun()


# ------------------------------------------------------------
# BUTTON 2: GENERATE / DRY RUN
# ------------------------------------------------------------

with col2:
    dry_run_clicked = st.button(
        "🧠 Generate New Plan",
        use_container_width=True,
        disabled=not credentials_present(),
    )


# ------------------------------------------------------------
# BUTTON 3: PRACTICE EXECUTION
# ------------------------------------------------------------

with col3:
    practice_confirmed = st.checkbox(
        "I confirm this is Practice money"
    )

    execute_clicked = st.button(
        "🧪 Execute Practice Orders",
        use_container_width=True,
        type="primary",
        disabled=(
            not credentials_present()
            or not practice_confirmed
        ),
    )


# ============================================================
# RUN DRY MODE
# ============================================================

if dry_run_clicked:

    with st.spinner(
        "GainZ is analysing the market..."
    ):
        result = run_gainz(
            execute_demo=False
        )

    if result["success"]:
        st.success(
            "GainZ generated a new portfolio plan. "
            "No orders were submitted."
        )

        if result["stdout"]:
            with st.expander(
                "Dry-run terminal output"
            ):
                st.code(
                    result["stdout"]
                )

        st.rerun()

    else:
        st.error(
            "GainZ dry run failed."
        )

        if result["stderr"]:
            st.code(
                result["stderr"]
            )


# ============================================================
# EXECUTE PRACTICE ORDERS
# ============================================================

if execute_clicked:

    st.warning(
        "Submitting orders to Trading 212 "
        "PRACTICE account..."
    )

    with st.spinner(
        "Sending Practice orders..."
    ):
        result = run_gainz(
            execute_demo=True
        )

    if result["success"]:
        st.success(
            "Practice execution completed."
        )

        if result["stdout"]:
            with st.expander(
                "Execution terminal output"
            ):
                st.code(
                    result["stdout"]
                )

        st.rerun()

    else:
        st.error(
            "Practice execution failed."
        )

        if result["stderr"]:
            st.code(
                result["stderr"]
            )


# ============================================================
# LOAD CURRENT REPORT
# ============================================================

report = load_report()

if report is None:
    st.divider()

    st.info(
        "No GainZ report exists yet. "
        "Click 'Generate New Plan'."
    )

    st.stop()


decision = report.get(
    "decision",
    {},
)

weights = report.get(
    "target_weights",
    {},
)

orders = report.get(
    "orders",
    [],
)

cash_available = float(
    report.get(
        "cash_available",
        0,
    )
)

executed = report.get(
    "executed",
    False,
)

environment = report.get(
    "environment",
    "demo",
)


# ============================================================
# MAIN METRICS
# ============================================================

st.divider()

st.subheader("Current GainZ Decision")

m1, m2, m3, m4, m5, m6 = st.columns(6)

m1.metric(
    "Environment",
    environment.upper(),
)

m2.metric(
    "Mode",
    decision.get(
        "mode",
        "N/A",
    ),
)

m3.metric(
    "Exposure",
    f"{decision.get('exposure', 0) * 100:.1f}%",
)

m4.metric(
    "Cash Available",
    f"£{cash_available:,.2f}",
)

m5.metric(
    "Stocks",
    len(weights),
)

m6.metric(
    "Last Execution",
    "EXECUTED" if executed else "DRY RUN",
)


# ============================================================
# STRATEGY DETAILS
# ============================================================

st.divider()

st.subheader("Strategy")

strategy_col1, strategy_col2 = st.columns(2)

with strategy_col1:
    st.write(
        "**Selected strategy:**",
        decision.get(
            "variant",
            "N/A",
        ),
    )

    st.write(
        "**Risk model:**",
        decision.get(
            "risk",
            "N/A",
        ),
    )

with strategy_col2:
    gainz_sharpe = decision.get(
        "gainz_sharpe"
    )

    benchmark_sharpe = decision.get(
        "benchmark_sharpe"
    )

    if gainz_sharpe is not None:
        st.metric(
            "GainZ Sharpe",
            f"{gainz_sharpe:.2f}",
        )

    if benchmark_sharpe is not None:
        st.metric(
            "Benchmark Sharpe",
            f"{benchmark_sharpe:.2f}",
        )


# ============================================================
# TARGET PORTFOLIO
# ============================================================

st.divider()

st.subheader("Target Portfolio")

if weights:

    allocation_rows = []

    for ticker, weight in weights.items():

        target_value = (
            cash_available
            * float(weight)
        )

        allocation_rows.append(
            {
                "Ticker": ticker,
                "Target Weight %":
                    float(weight) * 100,
                "Approx Allocation £":
                    target_value,
            }
        )

    allocation_df = pd.DataFrame(
        allocation_rows
    )

    allocation_df = (
        allocation_df
        .sort_values(
            "Target Weight %",
            ascending=False,
        )
        .reset_index(
            drop=True
        )
    )

    allocation_df[
        "Target Weight %"
    ] = allocation_df[
        "Target Weight %"
    ].round(2)

    allocation_df[
        "Approx Allocation £"
    ] = allocation_df[
        "Approx Allocation £"
    ].round(2)

    st.dataframe(
        allocation_df,
        use_container_width=True,
        hide_index=True,
    )

    st.bar_chart(
        allocation_df.set_index(
            "Ticker"
        )["Target Weight %"]
    )

else:
    st.info(
        "GainZ currently has no stock allocations."
    )


# ============================================================
# ORDER TABLE
# ============================================================

st.divider()

st.subheader("Orders")

if orders:

    orders_df = pd.DataFrame(
        orders
    )

    display_columns = []

    for column in [
        "symbol",
        "quantity",
        "status",
        "message",
        "order_id",
    ]:
        if column in orders_df.columns:
            display_columns.append(
                column
            )

    display_df = (
        orders_df[
            display_columns
        ].copy()
    )

    rename_map = {
        "symbol": "Ticker",
        "quantity": "Quantity",
        "status": "Status",
        "message": "Details",
        "order_id": "Order ID",
    }

    display_df = display_df.rename(
        columns=rename_map
    )

    if "Quantity" in display_df.columns:
        display_df[
            "Quantity"
        ] = pd.to_numeric(
            display_df["Quantity"],
            errors="coerce",
        ).round(5)

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )

    statuses = [
        order.get(
            "status",
            "UNKNOWN",
        )
        for order in orders
    ]

    status_counts = (
        pd.Series(statuses)
        .value_counts()
    )

    st.write(
        "**Order status summary:**"
    )

    st.dataframe(
        status_counts.rename(
            "Count"
        ),
        use_container_width=True,
    )

else:
    st.info(
        "No orders generated."
    )


# ============================================================
# CASH BUFFER
# ============================================================

st.divider()

exposure = float(
    decision.get(
        "exposure",
        0,
    )
)

estimated_investment = (
    cash_available
    * exposure
)

estimated_cash_buffer = (
    cash_available
    - estimated_investment
)

cash1, cash2 = st.columns(2)

cash1.metric(
    "Approx Capital Deployed",
    f"£{estimated_investment:,.2f}",
)

cash2.metric(
    "Approx Cash Buffer",
    f"£{estimated_cash_buffer:,.2f}",
)


# ============================================================
# RAW REPORT
# ============================================================

st.divider()

with st.expander(
    "Advanced: Raw GainZ Report"
):
    st.json(
        report
    )


# ============================================================
# FOOTER
# ============================================================

st.caption(
    "GainZ • Practice environment • "
    "Automated trading research system. "
    "Historical results do not guarantee future performance."
)

st.divider()
st.subheader("Broker Order Status")

try:
    from broker.trading212 import Trading212Broker

    broker = Trading212Broker(environment="demo")

    broker_orders = broker.orders()
    broker_positions = broker.positions()

    pending_count = len(broker_orders)
    filled_count = len(broker_positions)

    c1, c2 = st.columns(2)

    c1.metric(
        "Pending Orders",
        pending_count,
    )

    c2.metric(
        "Open Positions",
        filled_count,
    )

    if broker_orders:
        orders_live_df = pd.DataFrame(broker_orders)

        st.write("### Pending Orders")

        st.dataframe(
            orders_live_df,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.success("No pending orders.")

    if broker_positions:
        positions_df = pd.DataFrame(
            [
                {
                    "Ticker": p.symbol,
                    "Quantity": p.quantity,
                    "Price": p.price,
                    "Value": p.value,
                }
                for p in broker_positions
            ]
        )

        st.write("### Open Positions")

        st.dataframe(
            positions_df,
            use_container_width=True,
            hide_index=True,
        )

except Exception as exc:
    st.error(
        f"Could not load broker status: {exc}"
    )