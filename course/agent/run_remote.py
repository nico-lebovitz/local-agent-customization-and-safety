"""Stream inventory tool results while OpenClaw owns the agent loop."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

directory = Path(__file__).resolve().parent
state = Path('/home/sandbox/.openclaw-live')
state.mkdir(exist_ok=True)
# Use the same lock as the TUI, which shares the bridge port.
lock = (state / 'workshop-terminal.lock').open('w')
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    sys.exit('OpenClaw TUI is active. Exit it with /exit before running the notebook agent.')
os.environ.update(SQLITE_TMPDIR='/tmp', OPENCLAW_STATE_DIR=str(state),
                  OPENCLAW_CONFIG_PATH=str(directory / 'openclaw.json'),
                  COURSE_MODEL_URL='http://host.openshell.internal:8002')
bridge = subprocess.Popen(['node', str(directory / 'bridge.mjs')],
                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
agent = None
try:
    import socket
    for _ in range(50):
        if bridge.poll() is not None:
            raise RuntimeError('Could not start the OpenClaw bridge: ' + bridge.stderr.read().decode())
        try:
            with socket.create_connection(('127.0.0.1', 18790), timeout=.1):
                break
        except OSError:
            time.sleep(.1)
    else:
        raise TimeoutError('Bridge did not become ready')
    with (directory / 'openclaw-output.txt').open('w') as output:
        agent = subprocess.Popen([
            'openclaw', 'agent', '--local', '--session-id', directory.name,
            '--thinking', 'off', '--timeout', '240', '--json',
            '--message-file', str(directory / 'task.txt')],
            stdout=output, stderr=subprocess.STDOUT)
        cursor = 0
        announced_requests = set()
        deadline = time.monotonic() + 270
        next_progress = time.monotonic() + 15
        while True:
            # Chapter tools ask the host notebook to execute fixed lesson actions.
            # This is transport, not a model decision loop.
            for request_path in sorted((directory / 'requests').glob('*.json')):
                if request_path.name not in announced_requests:
                    payload = json.loads(request_path.read_text())
                    print('COURSE_REQUEST ' + json.dumps(payload), flush=True)
                    announced_requests.add(request_path.name)
            events = directory / 'events.jsonl'
            if events.exists():
                lines = events.read_text().splitlines()
                for line in lines[cursor:]:
                    event = json.loads(line)
                    result = event.get('result', {})
                    print('TOOL ' + event['tool'], flush=True)
                    if event['tool'].startswith('probe-'):
                        response = result.get('response', {})
                        print(json.dumps({'model': response.get('model'), 'seconds': result.get('seconds'),
                                          'choices': response.get('choices')}), flush=True)
                    elif event['tool'] == 'manifest':
                        print(json.dumps({'status': result.get('status'), 'errors': result.get('errors')}), flush=True)
                    elif event['tool'] == 'inventory':
                        print(json.dumps({'checkpoints': result.get('checkpoints'),
                                          'adapter': result.get('adapter', {}).get('path')}), flush=True)
                    elif event['tool'] == 'models':
                        print(json.dumps([{'id': m['id'], 'root': m.get('root')}
                                          for m in result.get('data', [])]), flush=True)
                    else:
                        print(json.dumps(event), flush=True)
                    if 'error' in event:
                        print('ERROR: ' + event['error'], flush=True)
                cursor = len(lines)
            if agent.poll() is not None:
                break
            if time.monotonic() > deadline:
                raise TimeoutError('OpenClaw exceeded the notebook time limit')
            if time.monotonic() > next_progress:
                print('OpenClaw is running; waiting for the next tool result or final answer…', flush=True)
                next_progress = time.monotonic() + 15
            time.sleep(.5)
    raw = (directory / 'openclaw-output.txt').read_text()
    try:
        start = raw.index('{\n  "payloads"')
        reply, _ = json.JSONDecoder().raw_decode(raw[start:])
        for payload in reply.get('payloads', []):
            print('AGENT SUMMARY (validation follows): ' + payload.get('text', ''), flush=True)
        print('Agent duration (seconds):', reply.get('meta', {}).get('durationMs', 0) / 1000, flush=True)
    except (ValueError, KeyError):
        print('OpenClaw did not return a normal reply. See openclaw-output.txt.', flush=True)
    trace = subprocess.run(
        ['openclaw', 'sessions', 'tail', '--session-key', 'agent:main:explicit:' + directory.name,
         '--tail', '200'], capture_output=True, text=True, timeout=30)
    (directory / 'agent-session.txt').write_text(trace.stdout + trace.stderr)
    print('SESSION TRACE\n' + trace.stdout, flush=True)
    export = subprocess.run(
        ['openclaw', 'sessions', 'export-trajectory',
         '--session-key', 'agent:main:explicit:' + directory.name,
         '--workspace', str(directory), '--output', 'trace', '--json'],
        capture_output=True, text=True, timeout=30)
    if export.returncode:
        print('Could not export detailed trajectory: ' + export.stderr, flush=True)
    sys.exit(agent.returncode)
finally:
    if agent is not None and agent.poll() is None:
        agent.terminate()
        try:
            agent.wait(timeout=10)
        except subprocess.TimeoutExpired:
            agent.kill()
            agent.wait()
    bridge.terminate()
    bridge.wait(timeout=10)
