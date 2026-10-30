"""Interactive chapter handoff with a bounded host worker for fixed actions."""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import uuid

from course.common import ROOT
from course.agent.notebook_agent import SANDBOX, SOURCES, command, put_file
from course.agent.chapter_agent import CHAPTERS, LessonActions, prepare, finish


def prepare_chapter_terminal(chapter):
    if os.environ.get('COURSE_LIVE', '1') != '1':
        raise RuntimeError('Terminal preparation requires live mode.')
    if chapter not in CHAPTERS:
        raise ValueError('Unknown chapter.')
    from urllib.request import urlopen
    with urlopen('http://127.0.0.1:30081/v1/models', timeout=5) as response:
        models = json.load(response)
    if not any(m['id'] == 'nvidia/NVIDIA-Nemotron-Nano-9B-v2-FP8' for m in models['data']):
        raise RuntimeError('Nano controller unavailable.')
    # Terminal demos consume verified agent artifacts, never silently fall back
    # to a manual/legacy output folder from a different experiment.
    for relative, previous in CHAPTERS[chapter]['inputs'].items():
        latest = ROOT / 'course/outputs/agent-demos' / previous / 'latest.json'
        if not latest.is_file():
            raise FileNotFoundError('Complete the OpenClaw demo for ' + previous + ' first.')
        record = json.loads(latest.read_text())
        if record.get('status') != 'PASS' or not (Path(record['directory']) / 'work' / relative).exists():
            raise FileNotFoundError('Missing verified agent input ' + relative + '; rerun ' + previous)
    directory, spec = prepare(chapter, 'openclaw')
    remote = '/home/sandbox/course-runs/' + directory.name
    session = 'agent:main:notebook' + chapter[:2] + '-' + directory.name
    config = json.loads((ROOT / 'run/claw/terminal/openclaw.json').read_text())
    config['agents']['defaults']['workspace'] = remote + '/workspace'
    config['skills']['allowBundled'] = [spec['skill']] + spec.get('supporting_skills', [])
    bridge = (ROOT / 'run/claw/terminal/bridge.mjs').read_text().replace(
        'body.stream = false;',
        'body.stream = false; body.temperature = 0; body.messages = body.messages?.map(normalizeToolMessage);')
    bridge = "import {normalizeToolMessage} from './normalize_tool_output.mjs';\n" + bridge
    entry = (ROOT / 'run/claw/terminal/entry.sh').read_text().replace(
        '/home/sandbox/.openclaw/openclaw.json', remote + '/openclaw.json').replace(
        '/opt/workshop/run/claw/terminal/bridge.mjs', remote + '/bridge.mjs')
    files = {
        'chapter_tool.py': (SOURCES / 'chapter_tool.py').read_text(),
        'chapter.json': json.dumps(spec),
        'openclaw.json': json.dumps(config, indent=2),
        'bridge.mjs': bridge,
        'normalize_tool_output.mjs': (SOURCES / 'normalize_tool_output.mjs').read_text(),
        'terminal.sh': entry,
        'workspace/AGENTS.md': 'Read the selected skill first. Run only its three fixed tool actions. '
            'Report actual results; stop on genuine errors. The tool path is ' + remote + '/chapter_tool.py.',
    }
    for skill in ['workshop-model-inventory'] + [s['skill'] for name, s in CHAPTERS.items() if name <= chapter] + sorted({skill for name,s in CHAPTERS.items() if name <= chapter for skill in s.get('supporting_skills', [])}):
        files['workspace/skills/' + skill + '/SKILL.md'] = (SOURCES / 'skills' / skill / 'SKILL.md').read_text()
    for name, content in files.items():
        put_file(remote + '/' + name, content)
    prompt = (f"Use the {spec['skill']} skill. First read {remote}/workspace/skills/{spec['skill']}/SKILL.md. " +
              "".join(f"Then read {remote}/workspace/skills/{name}/SKILL.md before any exec. " for name in spec.get("supporting_skills", [])) +
              f"The tool path is {remote}/chapter_tool.py. "
              f"Task: {spec['task']} {spec['note']} "
              f"Run {', then '.join(spec['actions'])} individually with exec elevated=false, yieldMs=10000, timeoutSeconds=180. "
              'If a command is still running, poll with process before continuing. '
              'A launcher oom_score_adj warning alone is harmless if the tool returns a JSON result. '
              'Report the actual check status and measured results. '
              'Stop on a genuine error. Do not edit files or run other commands. /no_think')
    launcher = directory / 'open-terminal.sh'
    launcher.write_text('#!/usr/bin/env bash\nset -euo pipefail\n' + shlex.join([
        'openshell', 'sandbox', 'exec', '--name', SANDBOX, '--tty', '--', 'bash',
        remote + '/terminal.sh', 'tui', '--local', '--session', session, '--thinking', 'off']) + '\n')
    run = {'chapter': chapter, 'directory': str(directory), 'remote': remote, 'session': session,
           'prompt': prompt, 'launcher': str(launcher), 'title': f'Notebook {chapter[:2]} · OpenClaw'}
    path = directory / 'terminal-run.json'
    path.write_text(json.dumps(run, indent=2))
    with (directory / 'host-worker.log').open('w') as log:
        subprocess.Popen([sys.executable, '-m', 'course.agent.chapter_terminal', 'serve', str(path)],
                         cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    return run


def serve(run):
    """Receive fixed action names; stop after completion or a 15-minute window."""
    directory = Path(run['directory'])
    spec = json.loads((directory / 'chapter.json').read_text())
    actions = LessonActions(directory, spec)
    watcher = '''import json,pathlib,sys,time
root=pathlib.Path(sys.argv[1]); seen=set(); deadline=time.monotonic()+900
while time.monotonic()<deadline:
    if (root/'stop-host-worker').exists(): break
    for path in sorted((root/'requests').glob('*.json')):
        if path.name not in seen:
            print(path.read_text(),flush=True); seen.add(path.name)
    time.sleep(.3)
'''
    proc = subprocess.Popen(['openshell', 'sandbox', 'exec', '--name', SANDBOX, '--',
                             'python3', '-u', '-c', watcher, run['remote']],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    errors = []
    try:
        for line in proc.stdout:
            req = json.loads(line)
            if not re.fullmatch('[0-9a-f]{32}', req.get('id', '')):
                raise ValueError('Invalid request identifier')
            try:
                reply = {'result': actions.perform(req['action'])}
            except Exception as exc:
                reply = {'error': str(exc)}
                errors.append(str(exc))
            put_file(run['remote'] + '/responses/' + req['id'] + '.json', json.dumps(reply))
            if errors or req['action'] == spec['actions'][-1]:
                break
        if set(actions.results) != set(spec['actions']) and not errors:
            errors.append('Host worker stopped before all actions completed (15-minute window or manual stop).')
    except Exception as exc:
        errors.append(str(exc))
    finally:
        # Signal the remote watcher too: terminating SSH alone need not stop it.
        try:
            put_file(run['remote'] + '/stop-host-worker', 'done')
        except Exception as exc:
            errors.append(str(exc))
        if proc.poll() is None:
            proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.wait()
        (directory / 'host-worker-status.json').write_text(json.dumps({'errors': errors}))


def collect_chapter_terminal(run):
    directory = Path(run['directory'])
    status = directory / 'host-worker-status.json'
    if not status.exists():
        raise RuntimeError('The host worker is still waiting or running. Finish the TUI task, then retry this cell.')
    errors = json.loads(status.read_text())['errors']
    spec = json.loads((directory / 'chapter.json').read_text())
    actions = LessonActions(directory, spec)
    if (directory / 'tool-results.json').exists():
        actions.results = json.loads((directory / 'tool-results.json').read_text())
    prefix = ['openshell', 'sandbox', 'exec', '--name', SANDBOX, '--']
    export_name = 'trace-' + uuid.uuid4().hex
    command(prefix + ['env', 'OPENCLAW_STATE_DIR=/home/sandbox/.openclaw-live',
                     'OPENCLAW_CONFIG_PATH=' + run['remote'] + '/openclaw.json',
                     'openclaw', 'sessions', 'export-trajectory', '--session-key', run['session'],
                     '--workspace', run['remote'], '--output', export_name, '--json'])
    trace = command(prefix + ['cat', run['remote'] + '/.openclaw/trajectory-exports/' + export_name + '/session-branch.json'])
    (directory / 'trajectory').mkdir(exist_ok=True)
    (directory / 'trajectory/session-branch.json').write_text(trace)
    (directory / 'events.jsonl').write_text(command(prefix + ['cat', run['remote'] + '/events.jsonl']))
    return finish(directory, spec, 'openclaw', actions, errors)


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] != 'serve':
        raise SystemExit('Usage: python -m course.agent.chapter_terminal serve RUN_JSON')
    serve(json.loads(Path(sys.argv[2]).read_text()))
