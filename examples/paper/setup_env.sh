#!/usr/bin/env bash
set -euo pipefail

PAPER_EXAMPLE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PAPER_ENV_DIR="${PYSPAIN_ENV_DIR:-$PAPER_EXAMPLE_DIR/.venv-paper}"
PAPER_REQUIREMENTS="${PYSPAIN_REQUIREMENTS_FILE:-$PAPER_EXAMPLE_DIR/requirements.txt}"

if command -v uv >/dev/null 2>&1; then
  if [ ! -x "$PAPER_ENV_DIR/bin/python" ]; then
    uv venv --python 3.11 --seed "$PAPER_ENV_DIR"
  fi
  uv pip install --python "$PAPER_ENV_DIR/bin/python" -r "$PAPER_REQUIREMENTS"
  uv pip check --python "$PAPER_ENV_DIR/bin/python"
else
  PAPER_PYTHON="$(command -v python3.11 || command -v python3 || true)"
  if [ -z "$PAPER_PYTHON" ]; then
    echo "Install Python 3.11 or uv before running this script." >&2
    exit 1
  fi
  "$PAPER_PYTHON" -c 'import sys; assert sys.version_info >= (3, 10), "Python >=3.10 is required; 3.11 is tested"'
  if [ ! -x "$PAPER_ENV_DIR/bin/python" ]; then
    "$PAPER_PYTHON" -m venv "$PAPER_ENV_DIR"
  fi
  "$PAPER_ENV_DIR/bin/python" -m pip install --upgrade pip
  "$PAPER_ENV_DIR/bin/python" -m pip install -r "$PAPER_REQUIREMENTS"
  "$PAPER_ENV_DIR/bin/python" -m pip check
fi

"$PAPER_ENV_DIR/bin/python" -m ipykernel install --prefix "$PAPER_ENV_DIR" \
  --name pyspainmobility-paper-final --display-name "Python (pySpainMobility paper final)"
printf '\nEnvironment ready: %s\n' "$PAPER_ENV_DIR"
printf 'Activate: source "%s/bin/activate"\n' "$PAPER_ENV_DIR"
