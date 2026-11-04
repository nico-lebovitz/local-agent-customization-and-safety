"""Artifact bookkeeping and isolated-process transport for executable notebooks.

Teaching code lives in notebook cells. This module does not select lesson JSON
cells, compute rewards, train models, or decide whether generated answers pass.
"""
import inspect
import json
from pathlib import Path
import shutil
import subprocess
import textwrap
import uuid

from course.common import ROOT
from course.agent.chapter_agent import CHAPTERS


class NotebookRun:
    """Copy prerequisites and publish artifacts after notebook-owned checks pass."""
    def __init__(self, chapter):
        self.chapter = chapter
        self.parent = ROOT / 'course/outputs/previews' / chapter
        self.directory = self.parent / uuid.uuid4().hex
        self.work = self.directory / 'work'
        self.work.mkdir(parents=True)
        self.inputs = {}
        for relative, previous in CHAPTERS[chapter]['inputs'].items():
            if previous[:2] in ('02', '03'):
                origin = ROOT / ('course/outputs/preview' + previous[:2]) / relative
            else:
                pointer = ROOT / 'course/outputs/previews' / previous / 'latest.json'
                if not pointer.is_file():
                    raise FileNotFoundError('Finish manual notebook ' + previous + ' first')
                origin = Path(json.loads(pointer.read_text())['work']) / relative
            if not origin.exists():
                raise FileNotFoundError('Missing manual prerequisite: ' + str(origin))
            dest = self.work / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            if origin.is_dir():
                shutil.copytree(origin, dest)
            else:
                shutil.copy2(origin, dest)
            self.inputs[relative] = str(origin)
        print('Fresh manual artifacts:', self.work)

    def read(self, name):
        return json.loads((self.work / name).read_text())

    def finish(self, summary):
        # Semantic assertions run visibly in the notebook before this call.
        if not isinstance(summary, dict) or not summary:
            raise ValueError('Supply the notebook’s checked summary')
        (self.work / 'lesson-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        missing = [name for name in CHAPTERS[self.chapter]['outputs']
                   if not (self.work / name).is_file() or not (self.work / name).stat().st_size]
        if missing:
            raise ValueError('Missing artifacts: ' + ', '.join(missing))
        (self.parent / 'latest.json').write_text(json.dumps({
            'work': str(self.work), 'chapter': self.chapter, 'status': 'PASS',
            'execution_source': 'editable manual notebook cells',
        }, indent=2) + '\n')
        return summary


def run_in_gym(functions, entrypoint, output, **parameters):
    """Run the exact functions defined in cells in the isolated Gym interpreter.

Functions must import their dependencies locally and receive experiment settings
as arguments. Source, arguments, stdout, and stderr remain with the artifacts.
    """
    names = {function.__name__ for function in functions}
    if entrypoint not in names:
        raise ValueError('Entrypoint must be one of the supplied functions')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    source = '\n\n'.join(textwrap.dedent(inspect.getsource(fn)) for fn in functions)
    script = output / 'notebook-experiment.py'
    script.write_text(source + '\n\nif __name__ == "__main__":\n'
                      '    import json, sys\n'
                      f'    {entrypoint}(**json.loads(sys.argv[1]))\n')
    arguments = {'output': str(output), **parameters}
    (output / 'parameters.json').write_text(json.dumps(arguments, indent=2) + '\n')
    python = ROOT / 'run/workshop/gym/.venv/bin/python'
    if not python.is_file():
        raise RuntimeError('Install the Gym environment: bash scripts/install.sh course')
    completed = subprocess.run([str(python), str(script), json.dumps(arguments)],
                               cwd=ROOT, text=True, capture_output=True, timeout=180)
    (output / 'training.log').write_text(completed.stdout + completed.stderr)
    print(completed.stdout)
    if completed.returncode:
        raise RuntimeError('Notebook Gym experiment failed:\n' + completed.stderr[-4000:])
