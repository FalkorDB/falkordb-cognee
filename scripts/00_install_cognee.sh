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
  "cognee==1.1.0" \
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
pip list | grep -iE 'cognee|falkordb|fastapi|uvicorn|pysqlite3'

# ---- SQLite sanity check ----------------------------------------------------
# Cognee 1.x SEGVs inside system libsqlite3 < ~3.46 (Ubuntu 24.04 ships
# 3.45.1). The sidecar/POC scripts shim sys.modules["sqlite3"] to
# pysqlite3 to dodge this, but warn here so the user knows why the shim
# matters and can confirm pysqlite3 is doing the work.
echo
echo "SQLite sanity check:"
SYS_SQLITE_VER="$(python -c 'import sqlite3; print(sqlite3.sqlite_version)' 2>/dev/null || echo unknown)"
PYSQ_VER="$(python -c 'import pysqlite3; print(pysqlite3.sqlite_version)' 2>/dev/null || echo missing)"
echo "  stdlib sqlite3 -> $SYS_SQLITE_VER (system libsqlite3)"
echo "  pysqlite3      -> $PYSQ_VER (bundled, used by sidecar shim)"

# Compare against 3.46.0 as the safe floor.
needs_shim() {
    python - <<'PY' 2>/dev/null
import sqlite3
def parse(v): return tuple(int(x) for x in v.split('.'))
print("yes" if parse(sqlite3.sqlite_version) < (3, 46, 0) else "no")
PY
}
if [ "$(needs_shim)" = "yes" ]; then
    cat <<EOF
  ⚠️  System SQLite ${SYS_SQLITE_VER} is older than 3.46. Cognee 1.x will
      SIGSEGV in this libsqlite3 unless Python's sqlite3 module is shimmed
      to pysqlite3. The pysqlite3 shim is built into:
          scripts/01_test_cognee_falkor.py
          scripts/02_cognee_sidecar.py
      Do NOT remove the "BEGIN sqlite3 shim" block at the top of those
      files. If you write your own entrypoint, paste the same shim
      verbatim before importing cognee/sqlalchemy.
EOF
elif [ "$PYSQ_VER" = "missing" ]; then
    echo "  ⚠️  pysqlite3-binary did not install — please rerun this script."
else
    echo "  ✅ System SQLite is recent enough; the shim is harmless but unnecessary."
fi
# ----------------------------------------------------------------------------

echo
echo "Done. Activate with:  source $VENV/bin/activate"
