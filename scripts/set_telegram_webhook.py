#!/usr/bin/env python3
"""Set the Telegram webhook for Jarvis Pessoal.

Usage:
    python scripts/set_telegram_webhook.py

Requires environment variables:
    TELEGRAM_BOT_TOKEN
    APP_BASE_URL
    TELEGRAM_WEBHOOK_SECRET (optional but recommended)
"""

import os
import sys

import httpx


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    base_url = os.environ.get("APP_BASE_URL", "")
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")

    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN not set")
        sys.exit(1)
    if not base_url:
        print("ERROR: APP_BASE_URL not set")
        sys.exit(1)

    webhook_url = f"{base_url.rstrip('/')}/webhooks/telegram"
    api_url = f"https://api.telegram.org/bot{token}/setWebhook"

    payload = {"url": webhook_url}
    if secret:
        payload["secret_token"] = secret

    print(f"Setting webhook to: {webhook_url}")
    resp = httpx.post(api_url, json=payload, timeout=30.0)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")


if __name__ == "__main__":
    main()
