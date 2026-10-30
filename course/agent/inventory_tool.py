"""Small evidence tools used by OpenClaw and the explicit direct fallback."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import time
from urllib.request import Request, urlopen


def request(endpoint, path, payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    req = Request(endpoint + path, data=body, headers={'Content-Type': 'application/json'})
    with urlopen(req, timeout=90) as response:
        return json.load(response)


def validate(evidence):
    errors = []
    inventory = evidence.get('inventory', {})
    if not inventory.get('adapter', {}).get('config_sha256'):
        errors.append('Missing adapter identity')
    if not inventory.get('adapter', {}).get('weights'):
        errors.append('Missing adapter weight identity')
    for kind in ('BF16', 'NVFP4'):
        if not inventory.get('checkpoints', {}).get(kind):
            errors.append(f'Missing visible {kind} checkpoint snapshot')
    models = {m['id']: m for m in evidence.get('models', {}).get('data', [])}
    for alias in ('base', 'specialist'):
        if alias not in models or not models[alias].get('root'):
            errors.append(f'Missing discovered alias: {alias}')
        probe = evidence.get('probe-' + alias, {})
        if probe.get('request', {}).get('model') != alias:
            errors.append(f'Missing or mismatched request model: {alias}')
        result = probe.get('response', {})
        choices = result.get('choices', [])
        if result.get('model') != alias:
            errors.append(f'Missing or mismatched response model: {alias}')
        if not choices or choices[0].get('finish_reason') != 'stop':
            errors.append(f'Incomplete response: {alias}')
        if not choices or not choices[0].get('message', {}).get('content'):
            errors.append(f'No visible response: {alias}')
        if not isinstance(probe.get('seconds'), (float, int)) or probe['seconds'] <= 0:
            errors.append(f'Missing measured latency: {alias}')
    return errors


def perform(directory, action, endpoint=None):
    directory = Path(directory)
    endpoint = endpoint or os.environ.get('COURSE_MODEL_URL', 'http://host.openshell.internal:8002')
    evidence_path = directory / 'evidence.json'
    evidence = json.loads(evidence_path.read_text()) if evidence_path.exists() else {}
    if action in evidence:
        return {'cached': True, 'result': evidence[action]}
    if action == 'inventory':
        result = json.loads((directory / 'host-inventory.json').read_text())
    elif action == 'models':
        result = request(endpoint, '/v1/models')
    elif action in ('probe-base', 'probe-specialist'):
        alias = action.removeprefix('probe-')
        if alias not in {m['id'] for m in evidence.get('models', {}).get('data', [])}:
            raise ValueError('Discover models before probing this alias')
        payload = {
            'model': alias,
            'messages': [{'role': 'user', 'content': 'Reply with one short sentence acknowledging this endpoint probe.'}],
            'max_tokens': 128, 'temperature': 0,
            'chat_template_kwargs': {'enable_thinking': False},
        }
        started = time.perf_counter()
        response = request(endpoint, '/v1/chat/completions', payload)
        result = {'request': payload, 'response': response,
                  'seconds': round(time.perf_counter() - started, 6)}
    elif action == 'manifest':
        errors = validate(evidence)
        result = {'status': 'FAIL' if errors else 'PASS', 'errors': errors,
                  'endpoint': endpoint, 'evidence': evidence}
        (directory / 'endpoint-manifest.json').write_text(json.dumps(result, indent=2) + '\n')
        return result
    else:
        raise ValueError('Unknown inventory action')
    evidence[action] = result
    evidence_path.write_text(json.dumps(evidence, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['inventory', 'models', 'probe-base', 'probe-specialist', 'manifest'])
    args = parser.parse_args()
    directory = Path(__file__).resolve().parent
    lock = (directory / 'tools.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX)
    event = {'tool': args.action, 'time': time.time()}
    try:
        events = directory / 'events.jsonl'
        if events.exists() and len(events.read_text().splitlines()) >= 8:
            raise RuntimeError('Inventory tool budget exhausted (eight calls)')
        result = perform(directory, args.action)
        event['result'] = result
    except Exception as exc:
        event['error'] = str(exc)
    with (directory / 'events.jsonl').open('a') as stream:
        stream.write(json.dumps(event) + '\n')
    print(json.dumps(event, indent=2), flush=True)
    raise SystemExit(1 if 'error' in event else 0)


if __name__ == '__main__':
    main()
