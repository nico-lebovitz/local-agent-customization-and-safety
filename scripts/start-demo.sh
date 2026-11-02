#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
PYTHON="$ROOT/run/workshop/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo 'Install the demo first: bash scripts/install.sh demo' >&2
  exit 1
fi
cd "$ROOT/run/workshop"
echo 'Workshop UI: http://127.0.0.1:7861 (Ctrl-C to stop)'
echo 'Recorded replay needs no model server. New live runs require Lightning on port 8002.'
exec "$PYTHON" -m uvicorn workshop_agent.server:app --host 127.0.0.1 --port 7861
