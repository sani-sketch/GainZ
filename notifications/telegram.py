from __future__ import annotations

import os

import requests
from dotenv import load_dotenv


load_dotenv()


def send_telegram_message(message: str) -> bool:
    """
    Send a message to the configured Telegram chat.

    This function is notification-only.
    It does not execute any trades.
    """

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token:
        print("Telegram notification skipped: TELEGRAM_BOT_TOKEN not configured.")
        return False

    if not chat_id:
        print("Telegram notification skipped: TELEGRAM_CHAT_ID not configured.")
        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{bot_token}/sendMessage"
    )

    payload = {
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=10,
        )

        response.raise_for_status()

        print("Telegram notification sent.")
        return True

    except requests.RequestException as error:
        print(
            f"Telegram notification failed: {error}"
        )
        return False


if __name__ == "__main__":
    send_telegram_message(
        "🧪 GainZ Telegram test\n\n"
        "Notifications are connected.\n"
        "No trade was executed."
    )