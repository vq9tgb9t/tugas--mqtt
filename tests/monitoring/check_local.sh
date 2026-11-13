#!/bin/sh
# From any directory; no broker/DB writes and no global dependency installation.
set -eu
cd "$(dirname "$0")/../.."
command -v uv >/dev/null
command -v flutter >/dev/null
uv run --with-requirements backend/monitoring/requirements-test.txt python -m unittest discover -s backend/monitoring -v
python3 mqtt/self_check.py
python3 -m unittest discover -s tests/monitoring -v
(
  cd flutter_app
  flutter analyze
  flutter test
)
printf '%s\n' 'Local checks complete. SKIP is not PASS; hardware and live services require separate acceptance.'
