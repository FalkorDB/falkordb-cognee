#!/usr/bin/env bash
# Phase 1 runner: activate the cognee venv and run the standalone POC.
set -euo pipefail

VENV="$HOME/.cognee-venv"
DIR="$HOME/work/script/coscripts"
LOG="$HOME/work/openclaw/config/cognee-phase1.txt"

mkdir -p "$(dirname "$LOG")"
exec > >(tee "$LOG") 2>&1

echo "=== Cognee phase 1 (standalone POC) ==="
echo "Date: $(date)"

if [ ! -d "$VENV" ]; then
  echo "ERROR: $VENV not found. Run 00_install_cognee.sh first." >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"
cd "$DIR"

echo "Python: $(python --version)"
echo "Running 01_test_cognee_falkor.py..."
echo

python 01_test_cognee_falkor.py

echo
echo "=== Phase 1 done. Log: $LOG ==="
