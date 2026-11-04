#!/usr/bin/env python3
"""Launch the inspected Spark model recipes; never replace existing containers."""
import argparse
import json
import os
from pathlib import Path
import platform
import shlex
import socket
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LIGHTNING = 'nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4'
NANO = 'nvidia/NVIDIA-Nemotron-Nano-9B-v2-FP8'
IMAGES = {'lightning': 'vllm/vllm-openai:v0.27.1', 'nano': 'nvcr.io/nvidia/vllm:25.12.post1-py3'}
PORTS = {'lightning': 8002, 'nano': 30081}


def command(service, cache, parser, bind):
    name = 'workshop-' + service
    cmd = ['docker', 'run', '-d', '--name', name, '--label', 'workshop.participant=true',
           '--gpus', 'all', '--ipc=host', '-p', f'{bind}:{PORTS[service]}:8000',
           '--mount', f'type=bind,src={cache},dst=/hf/hub',
           '-e', 'HF_HOME=/hf', '-e', 'HF_HUB_OFFLINE=1']
    if service == 'lightning':
        cmd += ['--mount', f'type=bind,src={ROOT / "train/adapters/jisr-lightning"},dst=/adapter,readonly',
                IMAGES[service], '--model', LIGHTNING, '--served-model-name', 'base',
                '--enable-lora', '--lora-modules', 'specialist=/adapter', '--max-lora-rank', '32',
                '--trust-remote-code', '--max-model-len', '8192', '--max-num-seqs', '16',
                '--gpu-memory-utilization', '0.22', '--kv-cache-memory=5368709120']
    else:
        cmd += ['--mount', f'type=bind,src={parser},dst=/opt/parser.py,readonly', IMAGES[service],
                'python3', '-m', 'vllm.entrypoints.openai.api_server', '--model', NANO,
                '--trust-remote-code', '--tensor-parallel-size', '1', '--gpu-memory-utilization', '0.15',
                '--port', '8000', '--mamba_ssm_cache_dtype', 'float32', '--enable-auto-tool-choice',
                '--tool-parser-plugin', '/opt/parser.py', '--tool-call-parser', 'nemotron_json']
    return cmd


def preflight(services, cache, parser):
    if platform.system() != 'Linux' or platform.machine() not in ('aarch64', 'arm64'):
        raise ValueError('This launcher targets Linux ARM64 on DGX Spark; other hardware is unvalidated.')
    subprocess.run(['docker', 'info'], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(['nvidia-smi'], check=True)
    for service in services:
        name = 'workshop-' + service
        existing = subprocess.run(['docker', 'container', 'inspect', name], capture_output=True)
        if existing.returncode == 0:
            raise ValueError(f'{name} already exists. Inspect it and use docker start explicitly; no replacement attempted.')
        try:
            with socket.socket() as sock:
                sock.bind(('0.0.0.0', PORTS[service]))
        except OSError as exc:
            raise ValueError(f'{service}: port {PORTS[service]} is unavailable ({exc}); no existing service will be stopped.') from exc
        model = LIGHTNING if service == 'lightning' else NANO
        folder = cache / ('models--' + model.replace('/', '--')) / 'snapshots'
        if not any(folder.glob('*/config.json')):
            raise ValueError(f'Missing cached {model}; follow SPARK-SETUP.md downloads.')
    if 'nano' in services and not parser.is_file():
        raise ValueError(f'Missing NVIDIA Nano tool-call parser: {parser}')
    if 'lightning' in services:
        adapter = ROOT / 'train/adapters/jisr-lightning'
        config = json.loads((adapter / 'adapter_config.json').read_text())
        if not (adapter / 'adapter_model.safetensors').is_file():
            raise ValueError('Missing trained Lightning adapter weights; the CPU practice adapter is incompatible.')
        if config.get('peft_type') != 'LORA' or not 0 < config.get('r', 0) <= 32:
            raise ValueError('Expected a Lightning LoRA adapter with rank <= 32.')
        print('Adapter base recorded as:', config.get('base_model_name_or_path'))
        print('Confirm its Lightning checkpoint provenance; file checks do not prove compatibility.')


def api(port, path, payload=None):
    req = urllib.request.Request(f'http://127.0.0.1:{port}{path}',
        data=None if payload is None else json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=180) as response:
        return json.load(response)


def check(service):
    port = PORTS[service]
    expected = ['base', 'specialist'] if service == 'lightning' else [NANO]
    ids = {m['id'] for m in api(port, '/v1/models')['data']}
    if not set(expected) <= ids:
        raise ValueError(f'{service}: expected aliases {expected}; found {sorted(ids)}')
    for model in expected:
        payload = {'model': model, 'messages': [{'role': 'user', 'content': 'Reply with one short greeting.'}],
                   'max_tokens': 256, 'temperature': 0, 'chat_template_kwargs': {'enable_thinking': False}}
        if service == 'nano':
            payload['messages'][0]['content'] = 'Call workshop_ping with text hello. Do not answer in prose.'
            payload['tools'] = [{'type': 'function', 'function': {'name': 'workshop_ping',
                'description': 'Return a test greeting', 'parameters': {'type': 'object',
                'properties': {'text': {'type': 'string'}}, 'required': ['text']}}}]
            payload['tool_choice'] = 'auto'
        result = api(port, '/v1/chat/completions', payload)
        choice = result['choices'][0]
        message = choice['message']
        if service == 'nano':
            calls = message.get('tool_calls', [])
            if not calls or calls[0]['function']['name'] != 'workshop_ping':
                raise ValueError('Nano did not produce a structured tool call; inspect parser and generation logs.')
            args = json.loads(calls[0]['function']['arguments'])
            if not isinstance(args.get('text'), str):
                raise ValueError('Nano tool arguments failed the smoke-test schema.')
        elif not message.get('content') or choice.get('finish_reason') != 'stop':
            raise ValueError(f'{model}: missing or truncated visible response.')
        print(f'PASS {model}: discovery and live ' + ('tool-call generation' if service == 'nano' else 'generation'))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=['plan', 'preflight', 'start', 'check'])
    ap.add_argument('--service', choices=['all', 'lightning', 'nano'], default='all')
    ap.add_argument('--cache', type=Path, default=Path(os.environ.get('HF_HUB_CACHE',
        str(Path(os.environ.get('HF_HOME', str(Path.home() / '.cache/huggingface'))) / 'hub'))))
    ap.add_argument('--parser', type=Path, default=ROOT / '.workshop/models/nemotron_toolcall_parser_no_streaming.py')
    ap.add_argument('--bind', choices=['127.0.0.1', '0.0.0.0'], default='127.0.0.1',
                    help='Use 0.0.0.0 only on a protected host when OpenShell needs host access; see setup guide.')
    args = ap.parse_args()
    services = ['lightning', 'nano'] if args.service == 'all' else [args.service]
    cache, parser = args.cache.expanduser().resolve(), args.parser.expanduser().resolve()
    if args.action == 'check':
        for service in services:
            check(service)
        return
    if args.action in ('preflight', 'start'):
        preflight(services, cache, parser)
    if args.action == 'preflight':
        print('Preflight passed. Snapshot presence is not a full download or GPU capacity check.')
        return
    for service in services:
        cmd = command(service, cache, parser, args.bind)
        print(shlex.join(cmd), flush=True)
        if args.action == 'start':
            subprocess.run(cmd, check=True)
    if args.action == 'start':
        print('Containers launched, not yet ready. Follow docker logs, then run this script with check.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
