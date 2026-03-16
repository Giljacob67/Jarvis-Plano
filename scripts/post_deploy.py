#!/usr/bin/env python3
"""Post-deploy setup script for Jarvis Pessoal.

Run this once after publishing the app for the first time, or whenever
the deployment URL changes.

Usage:
    python scripts/post_deploy.py

What it does:
  1. Auto-detects the deployment URL (APP_BASE_URL or REPLIT_DOMAINS)
  2. Hits /health to confirm the server is up
  3. Registers the Telegram webhook

Required env vars:
    TELEGRAM_BOT_TOKEN
    TELEGRAM_WEBHOOK_SECRET  (recommended)
Optional:
    APP_BASE_URL             (auto-detected from REPLIT_DOMAINS if not set)
"""

import os
import sys

import httpx


def _resolve_base_url() -> str:
    explicit = os.environ.get("APP_BASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    domains = os.environ.get("REPLIT_DOMAINS", "").strip()
    if domains:
        domain = domains.split(",")[0].strip()
        return f"https://{domain}"
    return ""


def check_health(base_url: str) -> bool:
    url = f"{base_url}/health"
    print(f"Checking health: {url}")
    try:
        resp = httpx.get(url, timeout=15.0)
        data = resp.json()
        status = data.get("status", "unknown")
        print(f"  Status: {resp.status_code} — {status}")
        return resp.status_code == 200
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return False


def set_webhook(base_url: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN not set")
        return False

    webhook_url = f"{base_url}/webhooks/telegram"
    api_url = f"https://api.telegram.org/bot{token}/setWebhook"
    payload: dict = {"url": webhook_url, "max_connections": 40}
    if secret:
        payload["secret_token"] = secret

    print(f"\nSetting webhook: {webhook_url}")
    resp = httpx.post(api_url, json=payload, timeout=30.0)
    data = resp.json()
    ok = data.get("ok", False)
    print(f"  Result: {'✅ OK' if ok else '❌ FAILED'} — {data.get('description', '')}")
    return ok


def get_webhook_info(token: str) -> None:
    api_url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
    resp = httpx.get(api_url, timeout=10.0)
    data = resp.json().get("result", {})
    print(f"\nCurrent webhook info:")
    print(f"  URL    : {data.get('url', '(none)')}")
    print(f"  Pending: {data.get('pending_update_count', 0)} updates")
    if data.get("last_error_message"):
        print(f"  Error  : {data.get('last_error_message')}")


def main() -> None:
    base_url = _resolve_base_url()
    if not base_url:
        print("ERROR: Cannot determine deployment URL.")
        print("  Set APP_BASE_URL=https://your-app.replit.app")
        sys.exit(1)

    print(f"Deployment URL: {base_url}\n")

    healthy = check_health(base_url)
    if not healthy:
        print("\nWARNING: Health check failed. The app may not be running yet.")
        print("Wait a few seconds and try again.")

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if token:
        set_webhook(base_url)
        get_webhook_info(token)
    else:
        print("\nSkipping webhook setup — TELEGRAM_BOT_TOKEN not set")

    print("\n✅ Post-deploy setup complete!")
    print(f"   Your Jarvis is at: {base_url}")
    print(f"   Health endpoint:   {base_url}/health")


if __name__ == "__main__":
    main()
