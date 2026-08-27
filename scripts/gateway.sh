#!/usr/bin/env bash
# The one true gateway launch (CLAUDE.md env facts; DIRECTION.md D3, D13).
# LITELLM_MODE=PRODUCTION disables LiteLLM's dev-mode load_dotenv(), which
# would otherwise re-read .env from the repo (found via the in-repo .venv)
# and claim conventionally-named variables as its own config.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
if [ -n "${DATABASE_URL:-}" ]; then
  echo "ERROR: DATABASE_URL is set. App-owned vars carry the APP_ prefix (D13):" >&2
  echo "       rename it to APP_DATABASE_URL in .env, then relaunch." >&2
  echo "       (If .env is already renamed, this shell exported the old var —" >&2
  echo "        run 'unset DATABASE_URL' or open a fresh terminal.)" >&2
  exit 1
fi
exec env LITELLM_MODE=PRODUCTION .venv/bin/litellm --config config/litellm.yaml --port 4000
