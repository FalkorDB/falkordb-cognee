#!/usr/bin/env bash
# Kill any foreground (non-systemd) cognee sidecar processes,
# then restart the systemd service.
set -euo pipefail

LOG="$HOME/work/openclaw/config/cognee-takeover.txt"
mkdir -p "$(dirname "$LOG")"
exec > >(tee "$LOG") 2>&1

echo "=== Stop foreground sidecar; hand port 8765 to systemd ==="
echo "Date: $(date)"
echo

PIDS="$(pgrep -af 'uvicorn.*02_cognee_sidecar' | awk '{print $1}' || true)"
SYS_PID="$(systemctl show -p MainPID --value cognee-sidecar 2>/dev/null || echo 0)"

if [ -z "$PIDS" ]; then
  echo "No foreground sidecar processes found."
else
  for pid in $PIDS; do
    if [ "$pid" = "$SYS_PID" ]; then
      echo "Skipping systemd-managed pid $pid"
      continue
    fi
    echo "Killing foreground sidecar pid $pid"
    kill "$pid" || true
  done
  sleep 2
  # Force-kill anything still holding 8765
  REMAINING="$(ss -ltnp 2>/dev/null | awk '/:8765 /{print $0}')"
  if [ -n "$REMAINING" ]; then
    echo "Still holding port: $REMAINING"
    PID2="$(echo "$REMAINING" | grep -oP 'pid=\K[0-9]+' | head -1)"
    if [ -n "$PID2" ] && [ "$PID2" != "$SYS_PID" ]; then
      echo "Force-killing pid $PID2"
      kill -9 "$PID2" || true
    fi
  fi
fi

echo
echo "--- restarting systemd service ---"
sudo systemctl restart cognee-sidecar
sleep 3

echo
echo "--- status ---"
systemctl status cognee-sidecar --no-pager || true
echo
echo "--- port 8765 ---"
ss -ltnp 2>/dev/null | grep 8765 || echo "(nothing listening)"

echo
echo "Done. If active, run smoke test:"
echo "  ~/work/script/coscripts/05_smoke_sidecar.sh"
