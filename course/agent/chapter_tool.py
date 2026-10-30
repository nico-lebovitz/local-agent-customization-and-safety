"""Sandbox-side client for the notebook's fixed chapter actions."""
import argparse
import fcntl
import json
from pathlib import Path
import time
import uuid


def main():
    directory = Path(__file__).resolve().parent
    spec = json.loads((directory / 'chapter.json').read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=spec['actions'])
    action = parser.parse_args().action
    with (directory / 'tools.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        events = directory / 'events.jsonl'
        if events.exists() and len(events.read_text().splitlines()) >= 6:
            raise SystemExit('Chapter tool budget exhausted (six calls).')
        request_id = uuid.uuid4().hex
        requests = directory / 'requests'
        requests.mkdir(exist_ok=True)
        payload = {'id': request_id, 'action': action}
        tmp = requests / (request_id + '.tmp')
        tmp.write_text(json.dumps(payload))
        tmp.replace(requests / (request_id + '.json'))
        response = directory / 'responses' / (request_id + '.json')
        deadline = time.monotonic() + 180
        while not response.exists():
            if time.monotonic() > deadline:
                raise SystemExit('The notebook did not return a tool result within 180 seconds.')
            time.sleep(.2)
        result = json.loads(response.read_text())
        event = {'tool': action, 'time': time.time(), **result}
        with events.open('a') as stream:
            stream.write(json.dumps(event) + '\n')
        print(json.dumps({'completed':'error' not in result,'action':action,**result}, indent=2), flush=True)
        raise SystemExit(1 if 'error' in result else 0)


if __name__ == '__main__':
    main()
