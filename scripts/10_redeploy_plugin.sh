#!/usr/bin/env bash
# OUT OF DATE: superseded by the official Cognee OpenClaw integration:
# https://github.com/topoteretes/cognee-integrations/tree/main/integrations/openclaw
# Kept as a working reference.
# Re-deploy the openclaw-cognee plugin and restart gateway.
set -euo pipefail
LOG="$HOME/work/openclaw/config/cognee-plugin-redeploy.txt"
mkdir -p "$(dirname "$LOG")"
exec > >(tee "$LOG") 2>&1

SRC="$HOME/work/script/coscripts/openclaw-cognee"
DST="$HOME/.openclaw/extensions/openclaw-cognee"

echo "=== Re-deploy openclaw-cognee ==="
echo "Date: $(date)"

cp -r "$SRC/." "$DST/"
echo "Copied. Files:"
ls -la "$DST"

echo
echo "--- restarting gateway ---"
if command -v openclaw >/dev/null 2>&1; then
  openclaw gateway restart || sudo systemctl restart openclaw-gateway || true
else
  sudo systemctl restart openclaw-gateway || true
fi

sleep 8
echo
echo "--- gateway log: cognee + errors (last 60) ---"
LOGFILE="/tmp/openclaw/openclaw-$(date +%F).log"
if [ -f "$LOGFILE" ]; then
  tail -200 "$LOGFILE" | grep -aE 'cognee|error|Error|register threw' | tail -60
fi
echo
echo "Done."
