#!/usr/bin/env bash
# Install the Cognee sidecar as a systemd service.
# Run with: sudo ~/work/script/coscripts/04_install_service.sh
set -euo pipefail

UNIT_SRC="$HOME/work/script/coscripts/04_cognee_sidecar.service"
UNIT_DST="/etc/systemd/system/cognee-sidecar.service"
LOG="$HOME/work/openclaw/config/cognee-service-install.txt"

if [ "$(id -u)" != "0" ]; then
  # Not root — re-exec under sudo while preserving HOME so $LOG points at user's dir.
  exec sudo HOME="$HOME" "$0" "$@"
fi

mkdir -p "$(dirname "$LOG")"
exec > >(tee "$LOG") 2>&1

echo "=== Installing cognee-sidecar systemd service ==="
echo "Date:   $(date)"
echo "Source: $UNIT_SRC"
echo "Dest:   $UNIT_DST"
echo

if [ ! -f "$UNIT_SRC" ]; then
  echo "ERROR: unit file not found at $UNIT_SRC" >&2
  exit 1
fi

cp "$UNIT_SRC" "$UNIT_DST"
chmod 644 "$UNIT_DST"

systemctl daemon-reload
systemctl enable --now cognee-sidecar

echo
echo "--- status ---"
systemctl status cognee-sidecar --no-pager || true
echo
echo "--- last 20 log lines ---"
journalctl -u cognee-sidecar -n 20 --no-pager || true

echo
echo "Done. Verify with:"
echo "  ~/work/script/coscripts/05_smoke_sidecar.sh"
echo
echo "Logs (live):  journalctl -u cognee-sidecar -f"
