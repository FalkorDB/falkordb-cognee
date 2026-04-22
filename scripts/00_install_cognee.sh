#!/usr/bin/env bash
# Create a Python venv and install Cognee + the FalkorDB hybrid adapter.
set -euo pipefail

VENV="$HOME/.cognee-venv"
LOG="$HOME/work/openclaw/config/cognee-install.txt"
mkdir -p "$(dirname "$LOG")"
exec > >(tee "$LOG") 2>&1

echo "=== Cognee install ==="
echo "Date: $(date)"

# Cognee requires Python 3.11–3.13
PY="$(command -v python3.12 || command -v python3.11 || command -v python3.13 || command -v python3)"
echo "Python: $PY ($("$PY" --version))"

if [ ! -d "$VENV" ]; then
  "$PY" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

pip install --upgrade pip wheel
pip install \
  "cognee>=0.2.0" \
  "cognee-community-hybrid-adapter-falkor" \
  "falkordb>=1.0.9,<2.0.0" \
  "fastapi" \
  "uvicorn[standard]" \
  "python-dotenv"

echo
echo "Installed:"
pip list | grep -iE 'cognee|falkordb|fastapi|uvicorn'
echo
echo "Done. Activate with:  source $VENV/bin/activate"
