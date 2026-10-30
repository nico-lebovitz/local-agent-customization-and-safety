#!/usr/bin/env bash
set -euo pipefail
export SQLITE_TMPDIR=/tmp
export OPENCLAW_STATE_DIR=/home/sandbox/.openclaw-live
export OPENCLAW_CONFIG_PATH=/home/sandbox/.openclaw/openclaw.json
export COURSE_MODEL_URL=http://host.openshell.internal:8002
mkdir -p "$OPENCLAW_STATE_DIR"
exec 9>"$OPENCLAW_STATE_DIR/workshop-terminal.lock"
if ! flock -n 9; then
  printf '%s\n' 'The OpenClaw demo is already open in another terminal (possibly Jupyter).' 'Exit that OpenClaw session with /exit, then run this command again.' >&2
  exit 1
fi
python3 - <<'CHECK'
import socket,sys
with socket.socket() as s:
    try: s.bind(('127.0.0.1',18790))
    except OSError:
        sys.exit('The demo bridge is already running on port 18790. Exit the other OpenClaw terminal before retrying.')
CHECK
node /opt/workshop/run/claw/terminal/bridge.mjs &
BRIDGE_PID=$!
cleanup() {
  kill "$BRIDGE_PID" 2>/dev/null || true
  wait "$BRIDGE_PID" 2>/dev/null || true
}
trap cleanup EXIT
python3 - <<'READY'
import socket,time,sys
for _ in range(50):
    try:
        with socket.create_connection(('127.0.0.1',18790),timeout=.1): break
    except OSError: time.sleep(.1)
else: sys.exit('The local model bridge did not start.')
READY
kill -0 "$BRIDGE_PID"
openclaw "$@"
