#!/usr/bin/env python3
"""Get current Telegram webhook info for Jarvis Pessoal.

Usage:
    python scripts/get_telegram_webhook_info.py

Requires environment variables:
    TELEGRAM_BOT_TOKEN
"""

import os
import sys

import httpx


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")

    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN not set")
        sys.exit(1)

    api_url = f"https://api.telegram.org/bot{token}/getWebhookInfo"

    print("Fetching webhook info...")
    resp = httpx.get(api_url, timeout=30.0)
    print(f"Status: {resp.status_code}")

    import json
    print(json.dumps(resp.json(), indent=2))


if __name__ == "__main__":
    main()
