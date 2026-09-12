"""Optional phone notifications for GainZ.

If TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set, messages are sent to Telegram.
Otherwise notifications are simply printed to stdout.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request


def notify(message: str) -> None:
    print(f"NOTIFY: {message}", flush=True)

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode()

    try:
        req = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=15) as response:
            response.read()
    except Exception as exc:
        print(f"Telegram notification failed: {exc}", flush=True)
