#!/usr/bin/env bash
# OUT OF DATE: superseded by the official Cognee OpenClaw integration:
# https://github.com/topoteretes/cognee-integrations/tree/main/integrations/openclaw
# Kept as a working reference.
# Properly set plugins.slots.memory -> openclaw-cognee and remove the bogus
# plugins.memorySlot key, then restart the gateway.
set -euo pipefail

LOG="$HOME/work/openclaw/config/cognee-slot-fix2.txt"
mkdir -p "$(dirname "$LOG")"
exec > >(tee "$LOG") 2>&1

CFG="$HOME/.openclaw/openclaw.json"
BACKUP="$HOME/.openclaw/openclaw.json.bak.slotfix2.$(date +%Y%m%d-%H%M%S)"

echo "=== Fix memory slot ==="
echo "Date: $(date)"
cp "$CFG" "$BACKUP"
echo "Backup: $BACKUP"
echo

python3 - "$CFG" <<'PY'
import json, sys
path = sys.argv[1]
with open(path) as f:
    cfg = json.load(f)

plugins = cfg.setdefault("plugins", {})

# Remove bad key from previous attempt.
if "memorySlot" in plugins:
    plugins.pop("memorySlot")
    print("removed bogus plugins.memorySlot")

# Set the real one.
slots = plugins.setdefault("slots", {})
old = slots.get("memory")
slots["memory"] = "openclaw-cognee"
print(f"plugins.slots.memory: {old!r} -> 'openclaw-cognee'")

with open(path, "w") as f:
    json.dump(cfg, f, indent=2)
PY

echo
echo "--- restarting gateway ---"
if command -v openclaw >/dev/null 2>&1; then
  openclaw gateway restart || sudo systemctl restart openclaw-gateway || true
else
  sudo systemctl restart openclaw-gateway || true
fi

sleep 8
echo
echo "--- recent gateway log ---"
LOGFILE="/tmp/openclaw/openclaw-$(date +%F).log"
if [ -f "$LOGFILE" ]; then
  tail -100 "$LOGFILE" | grep -iE 'cognee|mem0|ready|memory|plugin|error' | tail -40
fi

echo
echo "Done."
