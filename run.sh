#!/usr/bin/env sh
set -eu
cd -- "$(dirname -- "$0")"
if command -v uv >/dev/null 2>&1; then
  uv sync --frozen --inexact
  exec uv run --no-sync python launch.py
fi
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.txt
exec .venv/bin/python launch.py
