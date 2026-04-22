#!/usr/bin/env bash
set -euo pipefail
CONFIG="$HOME/.openclaw/openclaw.json"
LOG="$HOME/work/openclaw/config/cognee-set-userid.txt"
mkdir -p "$(dirname "$LOG")"
ts="$(date +%Y%m%d-%H%M%S)"
cp "$CONFIG" "$CONFIG.bak.userid.$ts"
echo "[$(date)] backup -> $CONFIG.bak.userid.$ts" | tee "$LOG"

python3 - <<PY 2>&1 | tee -a "$LOG"
import json
p="$CONFIG"
c=json.load(open(p))
cfg=c["plugins"]["entries"]["openclaw-cognee"]["config"]
cfg.pop("user", None)            # remove the bogus key we added
old=cfg.get("userId")
cfg["userId"]="guy"
json.dump(c,open(p,"w"),indent=2)
print(f"userId: {old} -> guy ; removed stray 'user' key")
print("AFTER:", json.dumps(cfg, indent=2))
PY

echo "[$(date)] restarting gateway..." | tee -a "$LOG"
openclaw gateway restart 2>&1 | tee -a "$LOG"
sleep 4
GLOG="/tmp/openclaw/openclaw-$(date +%F).log"
echo "--- recent gateway log ---" | tee -a "$LOG"
[ -f "$GLOG" ] && tail -n 60 "$GLOG" | grep -aE 'cognee|ready \(' | tail -10 | tee -a "$LOG" || true
echo "[$(date)] done" | tee -a "$LOG"
