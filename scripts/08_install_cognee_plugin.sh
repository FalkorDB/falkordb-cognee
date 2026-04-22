#!/usr/bin/env bash
# Install the openclaw-cognee plugin and wire it into ~/.openclaw/openclaw.json.
# - Copies plugin source to ~/.openclaw/extensions/openclaw-cognee/
# - Disables the existing openclaw-mem0 plugin (kept on disk for rollback)
# - Adds an openclaw-cognee entry to plugins.entries
# - Restarts the openclaw gateway
set -euo pipefail

LOG="$HOME/work/openclaw/config/cognee-plugin-install.txt"
mkdir -p "$(dirname "$LOG")"
exec > >(tee "$LOG") 2>&1

SRC="$HOME/work/script/coscripts/openclaw-cognee"
DST="$HOME/.openclaw/extensions/openclaw-cognee"
CFG="$HOME/.openclaw/openclaw.json"
BACKUP="$HOME/.openclaw/openclaw.json.bak.$(date +%Y%m%d-%H%M%S)"

echo "=== Install openclaw-cognee plugin ==="
echo "Date: $(date)"
echo "Src:  $SRC"
echo "Dst:  $DST"
echo

if [ ! -d "$SRC" ]; then
  echo "ERROR: plugin source not found at $SRC" >&2; exit 1
fi
if [ ! -f "$CFG" ]; then
  echo "ERROR: openclaw config not found at $CFG" >&2; exit 1
fi

mkdir -p "$DST"
cp -r "$SRC/." "$DST/"
echo "--- installed files ---"
ls -la "$DST"

echo
echo "--- backing up openclaw.json -> $BACKUP ---"
cp "$CFG" "$BACKUP"

python3 - "$CFG" <<'PY'
import json, sys
path = sys.argv[1]
with open(path) as f:
    cfg = json.load(f)

cfg.setdefault("plugins", {}).setdefault("entries", {})

# Disable mem0 (kept for easy rollback)
if "openclaw-mem0" in cfg["plugins"]["entries"]:
    cfg["plugins"]["entries"]["openclaw-mem0"]["enabled"] = False
    print("disabled openclaw-mem0")

# Add cognee entry (preserve existing config if re-installing)
cog = cfg["plugins"]["entries"].setdefault("openclaw-cognee", {})
cog["enabled"] = True
cog.setdefault("config", {
    "sidecarUrl": "http://127.0.0.1:8765",
    "userId": "alice",
    "autoCapture": True,
    "autoRecall": True,
    "topK": 5,
    "timeoutMs": 60000
})
print("enabled openclaw-cognee")

with open(path, "w") as f:
    json.dump(cfg, f, indent=2)
PY

echo
echo "--- restarting openclaw gateway ---"
if command -v openclaw >/dev/null 2>&1; then
  openclaw gateway restart || sudo systemctl restart openclaw-gateway || true
else
  sudo systemctl restart openclaw-gateway || true
fi

echo
echo "--- gateway recent logs (last 40 lines) ---"
TODAY="$(date +%F)"
LOGFILE="/tmp/openclaw/openclaw-${TODAY}.log"
if [ -f "$LOGFILE" ]; then
  tail -40 "$LOGFILE" | grep -E 'cognee|mem0|plugin|ready' || tail -40 "$LOGFILE"
else
  echo "(no gateway log at $LOGFILE)"
fi

echo
echo "Done. Backup: $BACKUP"
echo "To rollback:  cp \"$BACKUP\" \"$CFG\" && (sudo systemctl restart openclaw-gateway || openclaw gateway restart)"
