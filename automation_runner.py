"""GainZ unattended Practice-mode scheduler.

Runs GainZ on US trading days at 09:40 America/New_York.
Safety defaults:
- DEMO/PRACTICE only
- skips execution when broker has pending orders
- skips weekends/NYSE holidays
- no live-mode switch
- sends optional Telegram notification
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal
from apscheduler.schedulers.blocking import BlockingScheduler

from broker.trading212 import Trading212Broker
from notifications import notify

ROOT = Path(__file__).resolve().parent
NY_TZ = ZoneInfo("America/New_York")


def is_nyse_trading_day(now: datetime | None = None) -> bool:
    now = now or datetime.now(NY_TZ)
    nyse = mcal.get_calendar("NYSE")
    schedule = nyse.schedule(start_date=now.date(), end_date=now.date())
    return not schedule.empty


def run_gainz_practice() -> None:
    now = datetime.now(NY_TZ)
    stamp = now.strftime("%Y-%m-%d %H:%M:%S %Z")
    print(f"[{stamp}] GainZ scheduled run started", flush=True)

    if not is_nyse_trading_day(now):
        msg = f"GainZ skipped: NYSE is closed today ({now.date()})."
        print(msg, flush=True)
        notify(msg)
        return

    broker = Trading212Broker(environment="demo")
    pending = broker.orders()

    if pending:
        msg = (
            f"GainZ skipped execution: {len(pending)} pending Trading 212 "
            "Practice order(s) already exist."
        )
        print(msg, flush=True)
        notify(msg)
        return

    command = [sys.executable, str(ROOT / "run_trading212.py"), "--execute-demo"]

    result = subprocess.run(
        command,
        cwd=str(ROOT),
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "Unknown error").strip()
        tail = err[-1800:]
        msg = f"GainZ Practice run FAILED.\n{tail}"
        print(msg, flush=True)
        notify(msg)
        return

    report_path = ROOT / "outputs" / "trading212_demo_report.json"
    summary = "GainZ Practice run completed successfully."

    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            decision = report.get("decision", {})
            orders = report.get("orders", [])
            submitted = sum(1 for o in orders if o.get("status") in {"SUBMITTED", "FILLED"})
            summary = (
                "GainZ Practice run completed.\n"
                f"Mode: {decision.get('mode', 'N/A')}\n"
                f"Exposure: {float(decision.get('exposure', 0)) * 100:.1f}%\n"
                f"Orders returned: {len(orders)}\n"
                f"Submitted/filled: {submitted}"
            )
        except Exception as exc:
            summary += f" Report parsing warning: {exc}"

    print(summary, flush=True)
    notify(summary)


def main() -> None:
    # A fixed New York-time schedule avoids London/US DST mismatch problems.
    scheduler = BlockingScheduler(timezone="America/New_York")
    scheduler.add_job(
        run_gainz_practice,
        trigger="cron",
        day_of_week="mon-fri",
        hour=9,
        minute=40,
        id="gainz_practice_daily",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=900,
    )

    print("GainZ automation worker running.", flush=True)
    print("Schedule: 09:40 America/New_York on weekdays; NYSE holidays are skipped.", flush=True)
    print("Mode: Trading 212 PRACTICE only.", flush=True)

    scheduler.start()


if __name__ == "__main__":
    main()
