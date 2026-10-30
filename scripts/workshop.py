#!/usr/bin/env python3
"""Preserve and operate this Spark's existing workshop services; never remove data."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.workshop'
MANIFEST = STATE / 'machine.json'
# Dependency order from this Spark's VSS Compose labels. GPU models load serially.
ORDER = ['mdx-redis', 'centralizedb-dev', 'phoenix',
         'streamprocessing-ms-dev', 'envoy-streamprocessing', 'sdr-streamprocessing',
         'sensor-ms-dev', 'vst-ingress-dev', 'vst-mcp-dev',
         'cosmos-reason2-8b-shared-gpu',
         'nvidia-nemotron-nano-9b-v2-fp8-toolcall-init',
         'nvidia-nemotron-nano-9b-v2-fp8-shared-gpu',
         'vss-agent', 'metropolis-vss-ui', 'spec']
INIT = 'nvidia-nemotron-nano-9b-v2-fp8-toolcall-init'
CONTROLLER = 'nvidia-nemotron-nano-9b-v2-fp8-shared-gpu'
CONTROLLER_MODEL = 'nvidia/NVIDIA-Nemotron-Nano-9B-v2-FP8'
GATEWAY = 'nemoclaw-openshell-gateway.service'


def command(args, check=True):
    return subprocess.run(args, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=check)


def inspect(name):
    result = command(['docker', 'inspect', name], check=False)
    if result.returncode:
        return None
    return json.loads(result.stdout)[0]


def owned_sandboxes():
    ids = command(['docker', 'ps', '-aq', '--filter', 'label=openshell.ai/managed-by=openshell']).stdout.split()
    all_boxes = [inspect(cid) for cid in ids]
    own = [c for c in all_boxes if c and (c['Config'].get('Labels') or {}).get(
        'openshell.ai/sandbox-name', '').startswith('nato-')]
    return own, [c for c in all_boxes if c and c not in own]


def capture():
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    containers = []
    for name in ORDER:
        c = inspect(name)
        if c is None:
            raise RuntimeError(f'Missing existing container {name}; restore the original deployment first. No image pull or replacement attempted.')
        containers.append({'name': name, 'id': c['Id'], 'image': c['Config']['Image'],
                           'restart_policy': c['HostConfig']['RestartPolicy'],
                           'mounts': [{'source': m['Source'], 'destination': m['Destination'],
                                       'type': m['Type']} for m in c['Mounts']]})
    data = {'root': str(ROOT), 'containers': containers, 'created': time.time()}
    MANIFEST.write_text(json.dumps(data, indent=2)+'\n')
    MANIFEST.chmod(0o600)
    print(f'Recorded existing container identities and mounts: {MANIFEST}')
    return data


def verified(data):
    if data['root'] != str(ROOT):
        raise RuntimeError('Repository moved: review machine.json and the spec bind mount before starting.')
    for item in data['containers']:
        c = inspect(item['name'])
        if not c or c['Id'] != item['id']:
            raise RuntimeError(f"Container identity changed: {item['name']}. Review the deployment; do not blindly reuse the manifest.")
    return data['containers']


def http(url, method=None, headers=None):
    req = urllib.request.Request(url, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=5) as response:
        body = response.read()
        return json.loads(body) if body else None


def wait_until(check, label, timeout):
    end = time.monotonic() + timeout
    next_report = 0
    while time.monotonic() < end:
        if check():
            print(f'Ready: {label}', flush=True)
            return
        if time.monotonic() >= next_report:
            print(f'Waiting: {label}', flush=True)
            next_report = time.monotonic() + 30
        time.sleep(2)
    raise RuntimeError(f'Timed out waiting for {label}. Existing services/data are retained; inspect logs and retry.')


def container_ready(name):
    c = inspect(name)
    if not c:
        return False
    state = c['State']
    if name == INIT:
        if state['Status'] == 'exited' and state['ExitCode'] != 0:
            raise RuntimeError('VSS tool-call initialization failed; inspect its container log.')
        return state['Status'] == 'exited' and state['ExitCode'] == 0
    if state['Status'] in ('exited', 'dead'):
        raise RuntimeError(f'{name} exited; inspect docker logs {name}.')
    return state['Running'] and state.get('Health', {}).get('Status', 'healthy') == 'healthy'


def model_ready():
    try:
        ids = {m['id'] for m in http('http://127.0.0.1:8002/v1/models')['data']}
        return {'base', 'specialist'} <= ids
    except (OSError, ValueError, KeyError):
        return False


def controller_ready():
    try:
        return CONTROLLER_MODEL in {m['id'] for m in http('http://127.0.0.1:30081/v1/models')['data']}
    except (OSError, ValueError, KeyError):
        return False


def port_open(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=.5):
            return True
    except OSError:
        return False


def jupyter_servers():
    for p in (Path.home()/'.local/share/jupyter/runtime').glob('*server-*.json'):
        try:
            c = json.loads(p.read_text())
            if c.get('port') == 8890 and Path(c.get('root_dir', '/')).resolve() == ROOT:
                os.kill(c['pid'], 0)
                yield c
        except (OSError, ValueError, KeyError):
            pass


def processes(kind):
    found = []
    for p in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            args = p.read_bytes().decode().split('\0')
            cwd = (p.parent/'cwd').resolve()
            match = (kind == 'ui' and 'workshop_agent.server:app' in args and cwd == ROOT/'run/workshop')
            match |= (kind == 'legacy' and 'run/app/app.py' in args and cwd == ROOT)
            if match:
                found.append(int(p.parent.name))
        except (OSError, UnicodeError):
            pass
    return found


def stop_pid(pid, label):
    # Capture the process start-time to avoid signaling a recycled PID.
    stat = Path(f'/proc/{pid}/stat')
    try:
        identity = stat.read_text().split(') ', 1)[1].split()[19]
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except FileNotFoundError:
        return
    def stopped():
        try:
            fields = stat.read_text().split(') ', 1)[1].split()
            return fields[0] == 'Z' or fields[19] != identity
        except FileNotFoundError:
            return True
    wait_until(stopped, f'{label} stopped', 60)


def notebook_python():
    for path in [STATE/'jupyter/bin/python', ROOT/'demo/.venv/bin/python']:
        if path.exists():
            return path
    raise RuntimeError('Missing Jupyter environment; see README setup. No automatic installation attempted.')


def start_app(kind):
    port = 7861 if kind == 'ui' else 8890
    matches = processes('ui') if kind == 'ui' else list(jupyter_servers())
    if port_open(port):
        if not matches:
            raise RuntimeError(f'Port {port} belongs to an unrecognized process; refusing to replace it.')
        print(f'{kind} is already running')
        return
    if kind == 'ui':
        args = [str(ROOT/'run/workshop/.venv/bin/python'), '-m', 'uvicorn',
                'workshop_agent.server:app', '--host', '127.0.0.1', '--port', '7861']
        cwd = ROOT/'run/workshop'
    else:
        args = [str(notebook_python()), '-m', 'jupyterlab', f'--config={ROOT / "scripts/jupyter_config.py"}', '--ip=127.0.0.1', '--port=8890',
                '--ServerApp.port_retries=0', '--no-browser', f'--ServerApp.root_dir={ROOT}',
                f'--FileContentsManager.preferred_dir={ROOT / "course"}']
        cwd = ROOT
    with (STATE/f'{kind}.log').open('a') as log:
        p = subprocess.Popen(args, cwd=cwd, stdin=subprocess.DEVNULL, stdout=log,
                             stderr=subprocess.STDOUT, start_new_session=True)
    def ready():
        if p.poll() is not None:
            raise RuntimeError(f'{kind} exited. See {STATE}/{kind}.log')
        return port_open(port)
    wait_until(ready, kind, 90)


def check_assets():
    required = ['course/.venv/bin/python', 'run/workshop/.venv/bin/python',
                'train/adapters/jisr-lightning/adapter_config.json',
                'train/adapters/jisr-lightning/adapter_model.safetensors',
                'run/workshop/gym/artifacts/demo.json']
    required += ['run/chain/clips/'+n+'.mp4' for n in ['civil-market','sample-drone-bridge',
                    'degraded-mountain-fog','convoy-truck-road','port-containers-cranes']]
    missing = [p for p in required if not (ROOT/p).exists()]
    if missing:
        raise RuntimeError('Missing local assets: '+', '.join(missing))
    python = notebook_python()
    kernel_path = python.parent.parent/'share/jupyter/kernels/nato-course/kernel.json'
    if not kernel_path.exists():
        raise RuntimeError('The Jupyter environment is missing the nato-course kernel. Register it using the README setup command.')
    argv = json.loads(kernel_path.read_text())['argv']
    if Path(argv[0]).absolute() != ROOT/'course/.venv/bin/python':
        raise RuntimeError('The nato-course kernelspec points at a different environment; reinstall it for this checkout.')
    command([str(ROOT/'course/.venv/bin/python'), '-c', 'import torch, peft, nbformat, nbclient'])


def links():
    print('UI: http://localhost:7861')
    servers = list(jupyter_servers())
    token = servers[0].get('token') if servers else None
    suffix = '?token='+urllib.parse.quote(token, safe='') if token else ''
    print('Notebooks: http://localhost:8890/lab/tree/course/01-local-model.ipynb'+suffix)
    if token:
        print('The notebook link contains a login token; keep it private.')


def check_video_network():
    # Host-network VSS services embed the provisioning-time Spark address.
    c = inspect('vss-agent')
    env = dict(e.split('=', 1) for e in c['Config'].get('Env', []) if '=' in e)
    host = urllib.parse.urlparse(env.get('LLM_BASE_URL', '')).hostname
    addresses = json.loads(command(['ip', '-j', '-4', 'address', 'show']).stdout)
    local = {a['local'] for interface in addresses for a in interface.get('addr_info', [])}
    if host not in local and host not in ('localhost', '127.0.0.1'):
        raise RuntimeError(f'VSS expects Spark address {host}, which is not assigned here. Use default up with recorded observations; reconfigure the original VSS deployment before --live-video.')


def warm_models():
    for model in ('base', 'specialist'):
        payload = json.dumps({'model': model, 'messages': [{'role': 'user', 'content': 'Reply ready.'}],
                              'max_tokens': 8, 'temperature': 0,
                              'chat_template_kwargs': {'enable_thinking': False}}).encode()
        req = urllib.request.Request('http://127.0.0.1:8002/v1/chat/completions', data=payload,
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=180) as response:
            result = json.load(response)
        if not result.get('choices'):
            raise RuntimeError(f'Warmup returned no choices for {model}')
        print(f'Live inference warmed: {model}', flush=True)


def up(data, timeout, live_video=False):
    all_items = verified(data)
    items = all_items if live_video else [i for i in all_items if i['name'] in (INIT, CONTROLLER, 'spec')]
    check_assets()
    if live_video:
        check_video_network()
        spec = inspect('spec')
        cold = any(not inspect(n)['State']['Running'] for n in
                   ['cosmos-reason2-8b-shared-gpu', 'nvidia-nemotron-nano-9b-v2-fp8-shared-gpu'])
        if spec and spec['State']['Running'] and cold:
            raise RuntimeError('Save your notebooks, run workshop.sh down, then up --live-video. Refusing to initialize VSS GPU models alongside an already loaded Lightning model.')
    # Persist unless-stopped so an intentional transport shutdown stays stopped at boot.
    for item in items:
        name = item['name']
        if name != INIT:
            command(['docker', 'update', '--restart', 'unless-stopped', name])
        c = inspect(name)
        if name == INIT and c['State']['Status'] == 'exited' and c['State']['ExitCode'] == 0:
            continue
        if not c['State']['Running']:
            print(f'Starting {name}', flush=True)
            command(['docker', 'start', name])
        wait_until(lambda n=name: container_ready(n), name, timeout)
        if name == CONTROLLER:
            wait_until(controller_ready, 'Nano notebook controller on port 30081', timeout)
        if name == 'spec':
            wait_until(model_ready, 'base and specialist model aliases', timeout)
    warm_models()
    command(['systemctl', '--user', 'start', GATEWAY])
    # Restore saved notebook sandboxes without opening a TUI or sending a task.
    own, _ = owned_sandboxes()
    for c in own:
        if not c['State']['Running']:
            command(['docker', 'start', c['Id']])
    start_app('ui')
    start_app('jupyter')
    links()


def down(data):
    items = verified(data)
    # Finish in-flight UI work rather than silently interrupt it.
    if processes('ui'):
        def idle():
            return http('http://127.0.0.1:7861/api/health').get('active_run') is None
        wait_until(idle, 'current UI run finished', 360)
    for pid in processes('ui')+processes('legacy'):
        stop_pid(pid, 'workshop application')
    for server in jupyter_servers():
        # Jupyter SIGTERM handles kernel shutdown. Save browser edits before down.
        stop_pid(server['pid'], 'Jupyter and its kernels')
    own, other = owned_sandboxes()
    if not any(c['State']['Running'] for c in other):
        command(['systemctl', '--user', 'stop', GATEWAY])
    else:
        print('Other OpenShell sandboxes exist; leaving their gateway running.')
    for c in own:
        command(['docker', 'update', '--restart', 'unless-stopped', c['Id']])
        if c['State']['Running']:
            command(['docker', 'stop', '--time', '60', c['Id']])
    for item in reversed(items):
        name = item['name']
        if name != INIT:
            command(['docker', 'update', '--restart', 'unless-stopped', name])
        if inspect(name)['State']['Running']:
            print(f'Stopping {name}', flush=True)
            command(['docker', 'stop', '--time', '120', name])
    remaining = [i['name'] for i in items if inspect(i['name'])['State']['Running']]
    if remaining:
        raise RuntimeError('Still running: '+', '.join(remaining))
    print('Workshop stopped. Containers, volumes, caches, adapters and notebook files are preserved.')
    extra = command(['docker','ps','--format','{{.Names}}']).stdout.strip()
    if extra:
        print('Other containers remain running (not stopped by this script):\n'+extra)
    print('After saving all other work, power off the Spark with: sudo systemctl poweroff')


def status(data):
    for item in verified(data):
        c = inspect(item['name'])
        print(f"{item['name']}: {c['State']['Status']} / {c['State'].get('Health',{}).get('Status','no healthcheck')}")
    print('Model aliases:', 'ready' if model_ready() else 'not ready')
    print('Nano notebook controller :30081:', 'ready' if controller_ready() else 'not ready')
    print('UI:', 'running' if processes('ui') else 'stopped')
    print('Jupyter:', 'running' if list(jupyter_servers()) else 'stopped')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['up','down','status','links','plan','preflight'])
    parser.add_argument('--live-video', action='store_true', help='Also start the full VSS/Cosmos stack; requires its configured host IP')
    parser.add_argument('--timeout', type=int, default=1200, help='Readiness timeout per container, seconds')
    args = parser.parse_args()
    STATE.mkdir(mode=0o700, exist_ok=True)
    STATE.chmod(0o700)
    with (STATE/'lifecycle.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another workshop lifecycle command is running.')
        if args.action == 'links':
            links()
            return
        data = capture()
        if args.action == 'plan':
            verified(data)
            print('Default UP: Nano initializer/controller :30081, spec (base + specialist), OpenShell gateway/saved workshop sandboxes, UI :7861, Jupyter :8890.')
            print('UP --live-video: readiness-gated starts in this order:')
            print('\n'.join(i['name'] for i in data['containers']))
            print('Then model warmup, OpenShell gateway/saved workshop sandboxes, UI and Jupyter.')
            print('DOWN: UI (wait for idle), Jupyter/kernels, workshop sandboxes, reverse container order.')
            print('Restart policy becomes unless-stopped. No deletion, pruning, compose down, build, pull or host poweroff.')
        elif args.action == 'preflight':
            verified(data)
            check_assets()
            if args.live_video:
                check_video_network()
            print('Local environments, clips, adapter, teaching artifact and existing container IDs verified.')
        elif args.action == 'up':
            up(data,args.timeout,args.live_video)
        elif args.action == 'down':
            down(data)
        else:
            status(data)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
