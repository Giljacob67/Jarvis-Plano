#!/usr/bin/env bash
# Production entry point — reads $PORT from environment (Replit assigns it),
# falls back to 8000 for local development.
set -e
PORT="${PORT:-8000}"
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers 1
