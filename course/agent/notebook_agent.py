"""Jupyter adapter for the existing OpenClaw/OpenShell workshop deployment."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

from course.common import ROOT, BASE_URL
from course.agent.inventory_tool import perform, validate

SANDBOX = 'nato-openclaw-demo'
SKILL = ROOT / 'course/agent/skills/workshop-model-inventory/SKILL.md'
SOURCES = ROOT / 'course/agent'
OUTPUT = ROOT / 'course/outputs/01-local-model'


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot():
    cache = Path(os.environ.get('HF_HUB_CACHE',
        str(Path(os.environ.get('HF_HOME', str(Path.home() / '.cache/huggingface'))) / 'hub')))
    checkpoints = {}
    for kind in ('BF16', 'NVFP4'):
        folder = cache / f'models--nvidia--NVIDIA-Nemotron-3.5-Lightning-30B-A3B-{kind}'
        checkpoints[kind] = [
            {'path': str(p), 'revision': p.name,
             'config_sha256': sha256(p / 'config.json') if (p / 'config.json').is_file() else None}
            for p in sorted((folder / 'snapshots').glob('*')) if p.is_dir()]
    adapter = ROOT / 'train/adapters/jisr-lightning'
    return {
        'captured_at': time.time(), 'source': 'host-exported filesystem metadata; no weights copied',
        'checkpoints': checkpoints,
        'adapter': {'path': str(adapter), 'config': json.loads((adapter / 'adapter_config.json').read_text()),
                    'config_sha256': sha256(adapter / 'adapter_config.json'),
                    'weights': [{'file': p.name, 'bytes': p.stat().st_size, 'sha256': sha256(p)}
                                for p in sorted(adapter.glob('*.safetensors'))]},
        'nat_packages_in_notebook_environment': [
            {'name': d.metadata['Name'], 'version': d.version}
            for d in importlib.metadata.distributions()
            if d.metadata.get('Name', '').lower().startswith(('nvidia-nat', 'nvidia-nemo-agent-toolkit'))],
        'identity_note': 'Cached revisions and API model roots are separate observations; '
                         'they do not attest which checkpoint revision is loaded by the server.',
    }


def command(args, timeout=60):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return result.stdout


def put_file(remote, text):
    result = subprocess.run(
        ['openshell', 'sandbox', 'exec', '--name', SANDBOX, '--', 'python3', '-c',
         'import pathlib,sys; p=pathlib.Path(sys.argv[1]); p.parent.mkdir(parents=True,exist_ok=True); t=p.with_suffix(p.suffix+".tmp"); t.write_text(sys.stdin.read()); t.replace(p)',
         remote], input=text, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)


def prepare(mode):
    if os.environ.get('COURSE_LIVE', '1') != '1':
        raise RuntimeError('Agent and direct probes are disabled in offline mode.')
    directory = OUTPUT / (mode + '-' + uuid.uuid4().hex)
    directory.mkdir(parents=True)
    (directory / 'host-inventory.json').write_text(json.dumps(snapshot(), indent=2) + '\n')
    return directory


def check_result(directory, mode):
    path = directory / 'endpoint-manifest.json'
    if not path.exists():
        return {'mode': mode, 'status': 'FAIL', 'errors': ['Agent did not produce a manifest'],
                'directory': str(directory)}
    manifest = json.loads(path.read_text())
    errors = validate(manifest.get('evidence', {}))
    original = json.loads((directory / 'host-inventory.json').read_text())
    if manifest.get('evidence', {}).get('inventory') != original:
        errors.append('Manifest inventory differs from the host snapshot')
    if mode == 'openclaw':
        trace = directory / 'trajectory/session-branch.json'
        if not trace.exists():
            errors.append('Missing OpenClaw trajectory')
        else:
            errors.extend(validate_trajectory(json.loads(trace.read_text())))
    result = {'mode': mode, 'status': 'FAIL' if errors else 'PASS', 'errors': errors,
              'directory': str(directory), 'manifest': str(path)}
    (directory / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def validate_trajectory(trace, skill_name="workshop-model-inventory"):
    """Require a successful skill read before the first inventory command."""
    calls = {}
    loaded = False
    executed = False
    errors = []
    for entry in trace.get('entries', []):
        # OpenClaw's redacted export may replace large trailing entries with
        # literal "[Truncated]" markers. Tool evidence is saved separately.
        if not isinstance(entry, dict):
            continue
        message = entry.get('message', {})
        content = message.get('content', [])
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get('type') == 'toolCall':
                    calls[block['id']] = block
                    if block.get('name') == 'exec':
                        executed = True
                        if not loaded:
                            errors.append('Agent executed a command before loading the skill')
        if message.get('role') == 'toolResult':
            call = calls.get(message.get('toolCallId'), {})
            path = call.get('arguments', {}).get('path', '')
            if (call.get('name') == 'read' and
                    path.endswith('/skills/' + skill_name + '/SKILL.md') and
                    not message.get('isError')):
                loaded = True
            if message.get('isError'):
                errors.append('OpenClaw reported a failed tool call')
    if not loaded:
        errors.append('No successful skill read in the OpenClaw trace')
    if not executed:
        errors.append('No agent tool execution in the OpenClaw trace')
    return errors


def run_direct():
    """Explicit fallback; this does not invoke an agent."""
    directory = prepare('direct')
    print('DIRECT CHECKS — no agent execution', flush=True)
    for action in ('inventory', 'models', 'probe-base', 'probe-specialist', 'manifest'):
        print('Running:', action, flush=True)
        perform(directory, action, BASE_URL)
    result = check_result(directory, 'direct')
    print(json.dumps(result, indent=2))
    return result


def run_agent():
    """Run a fresh OpenClaw session and stream tool evidence into Jupyter."""
    # Check prerequisites before creating/uploading a run.
    if os.environ.get('COURSE_LIVE', '1') != '1':
        raise RuntimeError('Agent execution is disabled in offline mode.')
    if not shutil.which('openshell'):
        raise RuntimeError('openshell is not on PATH in the notebook environment.')
    from urllib.request import urlopen
    try:
        with urlopen('http://127.0.0.1:30081/v1/models', timeout=5) as response:
            models = json.load(response)
        if not any(m['id'] == 'nvidia/NVIDIA-Nemotron-Nano-9B-v2-FP8' for m in models['data']):
            raise ValueError('Expected Nano controller alias is missing')
    except Exception as exc:
        raise RuntimeError('OpenClaw requires the Nano controller on port 30081. '
                           'Ask the presenter to start/check it; this cell does not restart services. '
                           'The direct-check fallback needs only port 8002.') from exc
    directory = prepare('openclaw')
    remote = '/home/sandbox/course-runs/' + directory.name
    bundle = directory / 'bundle'
    bundle.mkdir()
    shutil.copy2(SOURCES / 'inventory_tool.py', bundle / 'inventory_tool.py')
    shutil.copy2(SOURCES / 'run_remote.py', bundle / 'run_remote.py')
    shutil.copy2(directory / 'host-inventory.json', bundle / 'host-inventory.json')
    config = json.loads((ROOT / 'run/claw/terminal/openclaw.json').read_text())
    config['agents']['defaults']['workspace'] = remote + '/workspace'
    # allowBundled=[] means no filtering in this installed version. Use the
    # explicit course skill name to exclude unrelated bundled skill catalogs.
    config['skills']['allowBundled'] = ['workshop-model-inventory']
    (bundle / 'openclaw.json').write_text(json.dumps(config, indent=2))
    bridge = (ROOT / 'run/claw/terminal/bridge.mjs').read_text()
    (bundle / 'bridge.mjs').write_text(bridge)
    prompt = (
        'Use the workshop-model-inventory skill for notebook 01. '
        f'Read {remote}/workspace/skills/workshop-model-inventory/SKILL.md first. '
        f'The inventory tool path is {remote}/inventory_tool.py. '
        'Inspect the host-exported checkpoint and adapter metadata, discover endpoint models, '
        'probe base and specialist once each, then produce the endpoint manifest. '
        'Run the five actions individually, using exec elevated=false. '
        'Stop after the manifest and report its actual validation status. '
        'Do not modify files or run other shell commands. /no_think')
    (bundle / 'task.txt').write_text(prompt + '\n')
    print('Harness: OpenClaw | controller: Nano | probes: base + specialist', flush=True)
    print('Task:', prompt, flush=True)
    print('Run directory:', directory, flush=True)
    try:
        put_file(remote + '/workspace/skills/workshop-model-inventory/SKILL.md', SKILL.read_text())
        put_file(remote + '/workspace/AGENTS.md',
                 'Follow the workshop-model-inventory skill. Use only its tool commands. '
                 'Report actual evidence, and stop on errors. Keep the final answer short.')
        for path in bundle.iterdir():
            put_file(remote + '/' + path.name, path.read_text())
        process = subprocess.Popen(['openshell', 'sandbox', 'exec', '--name', SANDBOX, '--',
                                    'python3', remote + '/run_remote.py'],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            with (directory / 'console.txt').open('w') as log:
                for line in process.stdout:
                    print(line, end='', flush=True)
                    log.write(line)
            code = process.wait(timeout=10)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
        for name in ('endpoint-manifest.json', 'events.jsonl', 'openclaw-output.txt', 'agent-session.txt'):
            try:
                text = command(['openshell', 'sandbox', 'exec', '--name', SANDBOX, '--',
                                'cat', remote + '/' + name])
                (directory / name).write_text(text)
            except RuntimeError as exc:
                print(f'Could not retrieve {name}: {exc}', flush=True)
        trajectory = directory / 'trajectory'
        trajectory.mkdir()
        for name in ('manifest.json', 'events.jsonl', 'session-branch.json', 'system-prompt.txt',
                     'tools.json', 'metadata.json', 'artifacts.json', 'prompts.json'):
            try:
                text = command(['openshell', 'sandbox', 'exec', '--name', SANDBOX, '--', 'cat',
                                remote + '/.openclaw/trajectory-exports/trace/' + name])
                (trajectory / name).write_text(text)
            except RuntimeError as exc:
                print(f'Could not retrieve trajectory/{name}: {exc}', flush=True)
        result = check_result(directory, 'openclaw')
        if code:
            result['status'] = 'FAIL'
            result['errors'].append(f'OpenClaw exited with code {code}')
    except Exception as exc:
        result = {'mode': 'openclaw', 'status': 'FAIL', 'errors': [str(exc)], 'directory': str(directory)}
    (directory / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2), flush=True)
    return result
