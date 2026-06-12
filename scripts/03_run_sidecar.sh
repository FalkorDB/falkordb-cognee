#!/usr/bin/env bash
# OUT OF DATE: this custom sidecar setup is superseded by the official Cognee
# OpenClaw integration. New setups should use the plugin at
# https://github.com/topoteretes/cognee-integrations/tree/main/integrations/openclaw
# and its skills/falkor/SKILL.md FalkorDB setup skill. Kept as a working reference.
# Run the cognee sidecar in the foreground (for development / testing).
set -euo pipefail

cd "$(dirname "$0")"
# shellcheck disable=SC1091
source "$HOME/.cognee-venv/bin/activate"

export PYTHONUNBUFFERED=1
exec uvicorn 02_cognee_sidecar:app --host 127.0.0.1 --port 8765 --log-level info
