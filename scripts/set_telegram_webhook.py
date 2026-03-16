#!/usr/bin/env python3
"""Set the Telegram webhook for Jarvis Pessoal.

Usage:
    python scripts/set_telegram_webhook.py

Env vars read (in priority order for base URL):
    APP_BASE_URL             -- explicit override (e.g. https://mybot.replit.app)
    REPLIT_DOMAINS           -- auto-detected from Replit environment
    TELEGRAM_BOT_TOKEN       -- required
    TELEGRAM_WEBHOOK_SECRET  -- optional but strongly recommended
"""

import os
import sys

import httpx


def _resolve_base_url() -> str:
    explicit = os.environ.get("APP_BASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")

    replit_domains = os.environ.get("REPLIT_DOMAINS", "").strip()
    if replit_domains:
        domain = replit_domains.split(",")[0].strip()
        return f"https://{domain}"

    return ""


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    base_url = _resolve_base_url()

    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN not set")
        sys.exit(1)
    if not base_url:
        print("ERROR: could not determine base URL.")
        print("  Set APP_BASE_URL=https://<your-deployment>.replit.app")
        sys.exit(1)

    webhook_url = f"{base_url}/webhooks/telegram"
    api_url = f"https://api.telegram.org/bot{token}/setWebhook"

    payload: dict = {"url": webhook_url, "max_connections": 40}
    if secret:
        payload["secret_token"] = secret

    print(f"Base URL  : {base_url}")
    print(f"Webhook   : {webhook_url}")
    print(f"Secret    : {'set' if secret else 'NOT SET (recommended)'}")
    print()

    resp = httpx.post(api_url, json=payload, timeout=30.0)
    data = resp.json()
    print(f"Status    : {resp.status_code}")
    print(f"OK        : {data.get('ok')}")
    print(f"Result    : {data.get('description', data)}")

    if data.get("ok"):
        print("\n✅ Webhook configured successfully!")
    else:
        print("\n❌ Failed to set webhook. Check the token and try again.")
        sys.exit(1)


if __name__ == "__main__":
    main()
