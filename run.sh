#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

python_is_supported() {
  "$1" -c 'import sys; raise SystemExit(0 if (3, 11) <= sys.version_info < (3, 14) else 1)' \
    >/dev/null 2>&1
}

if [ -n "${PYTHON_BIN:-}" ]; then
  if ! python_is_supported "$PYTHON_BIN"; then
    echo "PYTHON_BIN must point to Python 3.11, 3.12, or 3.13."
    exit 1
  fi
else
  for candidate in python3.13 python3.12 python3.11 python3 \
    /opt/homebrew/bin/python3 /opt/anaconda3/bin/python3; do
    if command -v "$candidate" >/dev/null 2>&1 && python_is_supported "$candidate"; then
      PYTHON_BIN="$(command -v "$candidate")"
      break
    fi
  done
  if [ -z "${PYTHON_BIN:-}" ]; then
    echo "Python 3.11, 3.12, or 3.13 is required."
    echo "Install a compatible Python or set PYTHON_BIN, then run this launcher again."
    exit 1
  fi
fi

DATABASE_PATH="${COMPLEXATION_DB_PATH:-$PROJECT_DIR/data/generated/stability_constants_canonical.db}"
if [ ! -f "$DATABASE_PATH" ]; then
  echo "The read-only SQLite database was not found:"
  echo "$DATABASE_PATH"
  echo "Build it as described in data/README.md, or set COMPLEXATION_DB_PATH."
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  "$PYTHON_BIN" -m venv .venv
fi

.venv/bin/python -m pip install --disable-pip-version-check -r requirements-lock.txt
exec .venv/bin/python -m streamlit run app.py
