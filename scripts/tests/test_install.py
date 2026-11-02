"""Installer contract checks without downloading packages or changing services."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='participant setup ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'scripts').mkdir()
        for name in ('install.sh', 'start-demo.sh'):
            shutil.copy2(SOURCE / name, self.root / 'scripts' / name)

    def run_script(self, name, *args, env=None):
        return subprocess.run(['bash', str(self.root / 'scripts' / name), *args],
                              cwd='/tmp', env=env, text=True, capture_output=True)

    def test_dry_run_all_creates_nothing(self):
        result = self.run_script('install.sh', 'all', '--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        for text in ('requirements.txt', 'course/requirements.lock',
                     'gym/requirements.lock', 'jupyter-requirements.lock',
                     'ipykernel', '--offline'):
            self.assertIn(text, result.stdout)
        self.assertEqual(list(self.root.iterdir()), [self.root / 'scripts'])

    def test_invalid_profiles_fail_before_work(self):
        for args in [('demo', 'all'), ('--typo',)]:
            self.assertEqual(self.run_script('install.sh', *args).returncode, 2)
        self.assertFalse((self.root / 'run').exists())

    def test_uv_failure_is_not_reported_as_success(self):
        binary = self.root / 'bin'
        binary.mkdir()
        uv = binary / 'uv'
        uv.write_text('#!/bin/sh\nexit 23\n')
        uv.chmod(0o755)
        env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ['PATH'])
        result = self.run_script('install.sh', 'demo', env=env)
        self.assertEqual(result.returncode, 23)
        self.assertNotIn('Installation complete', result.stdout)

    def test_start_without_environment_explains_install(self):
        result = self.run_script('start-demo.sh')
        self.assertEqual(result.returncode, 1)
        self.assertIn('bash scripts/install.sh demo', result.stderr)


if __name__ == '__main__':
    unittest.main()
