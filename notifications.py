"""Telegram notifications for GainZ.

Uses:
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID

If secrets are missing, messages are printed to stdout.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request


def notify(message: str) -> None:
    """
    Send a formatted Telegram notification.

    Supports Telegram HTML formatting.
    """

    print(f"NOTIFY: {message}", flush=True)

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print(
            "Telegram secrets not configured. "
            "Notification printed only.",
            flush=True,
        )
        return

    url = (
        f"https://api.telegram.org/"
        f"bot{token}/sendMessage"
    )

    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }
    ).encode()

    try:
        request = urllib.request.Request(
            url,
            data=payload,
            method="POST",
        )

        with urllib.request.urlopen(
            request,
            timeout=20,
        ) as response:
            body = response.read().decode()

        result = json.loads(body)

        if not result.get("ok"):
            raise RuntimeError(
                f"Telegram API returned an error: {result}"
            )

    except Exception as exc:
        print(
            f"Telegram notification failed: {exc}",
            flush=True,
        )


def notify_success(
    dashboard_url: str,
    mode: str = "GAINZ",
    positions: int | None = None,
    exposure: float | None = None,
    pending: int | None = None,
    rejected: int | None = None,
) -> None:
    """
    Send a successful GainZ run notification.
    """

    lines = [
        "📈 <b>GainZ Daily Update</b>",
        "",
        "✅ <b>Status:</b> Completed",
        f"🧠 <b>Mode:</b> {mode}",
    ]

    if positions is not None:
        lines.append(
            f"💼 <b>Positions:</b> {positions}"
        )

    if exposure is not None:
        lines.append(
            f"💰 <b>Exposure:</b> {exposure:.0%}"
        )

    if pending is not None:
        lines.append(
            f"⏳ <b>Pending:</b> {pending}"
        )

    if rejected is not None:
        lines.append(
            f"🚫 <b>Rejected:</b> {rejected}"
        )

    lines.extend(
        [
            "",
            f"🔗 <a href='{dashboard_url}'>Open GainZ Dashboard</a>",
        ]
    )

    notify("\n".join(lines))


def notify_skipped(
    dashboard_url: str,
    reason: str,
) -> None:
    """
    Send a skipped-run notification.
    """

    message = (
        "⏸️ <b>GainZ Skipped</b>\n\n"
        f"📌 <b>Reason:</b> {reason}\n\n"
        f"🔗 <a href='{dashboard_url}'>"
        "Open GainZ Dashboard</a>"
    )

    notify(message)


def notify_failure(
    dashboard_url: str,
    error_message: str | None = None,
) -> None:
    """
    Send a failure notification.
    """

    lines = [
        "🚨 <b>GainZ Alert</b>",
        "",
        "❌ <b>Status:</b> Automation failed",
    ]

    if error_message:
        safe_error = str(error_message)[:500]

        lines.extend(
            [
                "",
                "⚠️ <b>Error:</b>",
                safe_error,
            ]
        )

    lines.extend(
        [
            "",
            "Open GitHub Actions for the full logs.",
            "",
            f"🔗 <a href='{dashboard_url}'>Open GainZ Dashboard</a>",
        ]
    )

    notify("\n".join(lines))