#!/usr/bin/env bash
# The one true app launch (mirrors scripts/gateway.sh): sources .env, runs
# the Ask API on :8310. Used interactively and by launchd (com.groundwork.app).
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
exec .venv/bin/uvicorn app.main:app --port 8310
