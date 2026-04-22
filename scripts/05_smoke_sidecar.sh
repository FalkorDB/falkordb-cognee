#!/usr/bin/env bash
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
