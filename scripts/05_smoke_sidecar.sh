#!/usr/bin/env bash
# OUT OF DATE: this custom sidecar setup is superseded by the official Cognee
# OpenClaw integration. New setups should use the plugin at
# https://github.com/topoteretes/cognee-integrations/tree/main/integrations/openclaw
# and its skills/falkor/SKILL.md FalkorDB setup skill. Kept as a working reference.
# End-to-end smoke test against the running sidecar.
set -euo pipefail

URL="${URL:-http://127.0.0.1:8765}"
LOG="$HOME/work/openclaw/config/cognee-smoke.txt"
mkdir -p "$(dirname "$LOG")"
exec > >(tee "$LOG") 2>&1

echo "=== sidecar smoke test ==="
echo "Date: $(date)"
echo "URL:  $URL"
echo

echo "--- /healthz ---"
curl -sS "$URL/healthz" | jq .

echo "--- /remember ---"
curl -sS -X POST "$URL/remember" \
  -H 'content-type: application/json' \
  -d '{"text":"Hadar plays tennis at 2pm on Sundays."}' | jq .

echo "--- /recall ---"
curl -sS -X POST "$URL/recall" \
  -H 'content-type: application/json' \
  -d '{"query":"When does Hadar play tennis?"}' | jq .

echo
echo "=== Done. Log: $LOG ==="
