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
  "cognee==1.0.3" \
  "cognee-community-hybrid-adapter-falkor>=0.3.0,<0.4" \
  "falkordb>=1.0.9,<2.0.0" \
  "fastapi" \
  "uvicorn[standard]" \
  "python-dotenv" \
  "pysqlite3-binary"

# pysqlite3-binary ships a modern bundled SQLite (>=3.51). On Linux distros
# whose system libsqlite3 is older (e.g. Ubuntu 24.04 = 3.45.1), Cognee 1.x
# triggers a SIGSEGV inside libsqlite3's SELECT parser
# (sqlite3DbStrDup -> __strlen_evex). The sidecar's first lines swap
# sys.modules["sqlite3"] for pysqlite3 to avoid that crash. macOS users
# don't strictly need this, but it's harmless to install.

echo
echo "Installed:"
pip list | grep -iE 'cognee|falkordb|fastapi|uvicorn'
echo
echo "Done. Activate with:  source $VENV/bin/activate"
