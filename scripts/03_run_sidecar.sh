#!/usr/bin/env bash
# Run the cognee sidecar in the foreground (for development / testing).
set -euo pipefail

cd "$(dirname "$0")"
# shellcheck disable=SC1091
source "$HOME/.cognee-venv/bin/activate"

export PYTHONUNBUFFERED=1
exec uvicorn 02_cognee_sidecar:app --host 127.0.0.1 --port 8765 --log-level info
