"""Prepare notebook 01's interactive OpenClaw session without sending a task."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import uuid

from course.agent.notebook_agent import (
    ROOT, SANDBOX, SKILL, SOURCES, prepare, put_file, command, check_result,
)


def prepare_terminal():
    """Install a per-run workspace and return a prompt and terminal launcher."""
    from urllib.request import urlopen
    with urlopen('http://127.0.0.1:30081/v1/models', timeout=5) as response:
        models = json.load(response)
    if not any(m['id'] == 'nvidia/NVIDIA-Nemotron-Nano-9B-v2-FP8' for m in models['data']):
        raise RuntimeError('The Nano controller is unavailable.')
    directory = prepare('openclaw')
    remote = '/home/sandbox/course-runs/' + directory.name
    session = 'agent:main:notebook01-' + directory.name
    config = json.loads((ROOT / 'run/claw/terminal/openclaw.json').read_text())
    config['agents']['defaults']['workspace'] = remote + '/workspace'
    config['skills']['allowBundled'] = ['workshop-model-inventory']
    prompt = (
        'Use the workshop-model-inventory skill to check the local models.\n'
        f'Read {remote}/workspace/skills/workshop-model-inventory/SKILL.md first.\n'
        f'The tool path is {remote}/inventory_tool.py.\n'
        'Read the host-exported inventory, discover the models, probe base and specialist, '
        'then save the endpoint manifest. Run each of the five actions individually with '
        'exec elevated=false. Report the actual validation status, response times and finish reasons. '
        'Stop on errors. Do not download weights, restart services or edit files. /no_think'
    )
    files = {
        'inventory_tool.py': (SOURCES / 'inventory_tool.py').read_text(),
        'host-inventory.json': (directory / 'host-inventory.json').read_text(),
        'openclaw.json': json.dumps(config, indent=2),
        'bridge.mjs': (ROOT / 'run/claw/terminal/bridge.mjs').read_text(),
        'workspace/skills/workshop-model-inventory/SKILL.md': SKILL.read_text(),
        'workspace/AGENTS.md': 'Read the workshop-model-inventory skill first. Use only its tool commands. Report actual evidence and stop on errors.',
    }
    # Reuse the existing TUI's lock, bridge readiness check and cleanup.
    entry = (ROOT / 'run/claw/terminal/entry.sh').read_text()
    entry = entry.replace('/home/sandbox/.openclaw/openclaw.json', remote + '/openclaw.json')
    entry = entry.replace('/opt/workshop/run/claw/terminal/bridge.mjs', remote + '/bridge.mjs')
    files['terminal.sh'] = entry
    for name, content in files.items():
        put_file(remote + '/' + name, content)
    run = {'directory': str(directory), 'remote': remote, 'session': session, 'prompt': prompt}
    args = ['openshell', 'sandbox', 'exec', '--name', SANDBOX, '--tty', '--',
            'bash', remote + '/terminal.sh', 'tui', '--local', '--session', session,
            '--thinking', 'off']
    launcher = directory / 'open-terminal.sh'
    launcher.write_text('#!/usr/bin/env bash\nset -euo pipefail\n' + shlex.join(args) + '\n')
    run['launcher'] = str(launcher)
    (directory / 'terminal-run.json').write_text(json.dumps(run, indent=2) + '\n')
    return run


def open_terminal(run):
    """Open the local desktop TUI; never submit the prompt automatically."""
    if not os.environ.get('DISPLAY') or not shutil.which('gnome-terminal'):
        print('In a Jupyter terminal run: bash ' + shlex.quote(run['launcher']))
        return
    # Jupyter may outlive the terminal screen from which it was started.
    env = os.environ.copy()
    for key in ('GNOME_TERMINAL_SCREEN', 'GNOME_TERMINAL_SERVICE'):
        env.pop(key, None)
    fallback = 'In a Jupyter terminal run: bash ' + shlex.quote(run['launcher'])
    try:
        result = subprocess.run(
            ['gnome-terminal', '--window', '--title=' + run.get('title', 'Notebook 01 · OpenClaw'),
             '--', 'bash', run['launcher']],
            env=env, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print('Desktop terminal launch failed: ' + str(exc))
        print(fallback)
        return
    if result.returncode or 'Error creating terminal' in result.stderr:
        print('Desktop terminal launch failed: ' + (result.stderr.strip() or str(result.returncode)))
        print(fallback)
        return
    print('Requested an OpenClaw terminal on the workshop computer’s desktop. '
          'When its TUI is ready, paste the task below.')
    print('If no window appears, ' + fallback[0].lower() + fallback[1:])


def collect_terminal(run):
    """Fetch only this run's evidence and export its actual OpenClaw trajectory."""
    directory = Path(run['directory'])
    remote = run['remote']
    prefix = ['openshell', 'sandbox', 'exec', '--name', SANDBOX, '--']
    try:
        manifest = command(prefix + ['cat', remote + '/endpoint-manifest.json'])
    except RuntimeError as exc:
        raise RuntimeError('No manifest yet. Wait for the TUI task to finish, then run this cell again.') from exc
    (directory / 'endpoint-manifest.json').write_text(manifest)
    export_name = 'trace-' + uuid.uuid4().hex
    command(prefix + ['env', 'OPENCLAW_STATE_DIR=/home/sandbox/.openclaw-live',
                     'OPENCLAW_CONFIG_PATH=' + remote + '/openclaw.json',
                     'openclaw', 'sessions', 'export-trajectory', '--session-key', run['session'],
                     '--workspace', remote, '--output', export_name, '--json'])
    trajectory = directory / 'trajectory'
    trajectory.mkdir(exist_ok=True)
    for name in ('session-branch.json',):
        data = command(prefix + ['cat', remote + '/.openclaw/trajectory-exports/' + export_name + '/' + name])
        (trajectory / name).write_text(data)
    (directory / 'events.jsonl').write_text(command(prefix + ['cat', remote + '/events.jsonl']))
    return check_result(directory, 'openclaw')
