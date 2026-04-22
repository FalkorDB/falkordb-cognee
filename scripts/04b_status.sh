#!/usr/bin/env bash
# Quick status check + fix log perms after running 04_install_service.sh
set -euo pipefail

LOG="$HOME/work/openclaw/config/cognee-service-install.txt"
OUT="$HOME/work/openclaw/config/cognee-service-status.txt"

# Fix ownership of root-owned log so we can read it
if [ -f "$LOG" ] && [ ! -r "$LOG" ]; then
  sudo chown "$USER:$USER" "$LOG"
fi

mkdir -p "$(dirname "$OUT")"
{
  echo "=== cognee-sidecar status ==="
  echo "Date: $(date)"
  echo
  echo "--- systemctl is-active ---"
  systemctl is-active cognee-sidecar || true
  echo
  echo "--- systemctl status ---"
  systemctl status cognee-sidecar --no-pager || true
  echo
  echo "--- last 40 journal lines ---"
  journalctl -u cognee-sidecar -n 40 --no-pager || true
  echo
  echo "--- port 8765 listeners ---"
  ss -ltnp 2>/dev/null | grep 8765 || echo "(nothing listening on 8765)"
  echo
  echo "--- foreground sidecar process? ---"
  ps -ef | grep -E 'uvicorn.*02_cognee_sidecar' | grep -v grep || echo "(no foreground uvicorn)"
} | tee "$OUT"

echo
echo "Done. Status: $OUT"
echo "Install log: $LOG"
