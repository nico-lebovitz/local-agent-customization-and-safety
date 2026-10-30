"""Filesystem and HTTP plumbing shared by notebooks and lesson implementations."""
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get('COURSE_MODEL_URL', 'http://127.0.0.1:8002').rstrip('/')

def request(path, payload=None, timeout=120):
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(BASE_URL + path, data=data, headers={'Content-Type': 'application/json'})
    with urlopen(req, timeout=timeout) as response:
        return json.load(response)

def chat(model, messages, max_tokens=512, json_output=False):
    payload = dict(model=model, messages=messages, temperature=0, max_tokens=max_tokens,
                   chat_template_kwargs={'enable_thinking': False})
    if json_output:
        payload['response_format'] = {'type': 'json_object'}
    result = request('/v1/chat/completions', payload)
    if result.get('model') != model:
        raise ValueError(f"Requested {model}, received {result.get('model')}")
    choice = result['choices'][0]
    if choice['finish_reason'] != 'stop':
        raise ValueError(f"Incomplete generation: {choice['finish_reason']}")
    text = choice['message'].get('content')
    if not text:
        raise ValueError('Model returned no visible content')
    return text

def rows(relative):
    return [json.loads(line) for line in (ROOT / relative).read_text().splitlines() if line.strip()]
