"""Service provisioning checks with no Docker mutation or model downloads."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / 'model_services.py'
spec = importlib.util.spec_from_file_location('model_services', PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ModelServiceTests(unittest.TestCase):
    def test_plan_needs_no_docker_or_assets(self):
        result = subprocess.run([sys.executable, str(PATH), 'plan', '--cache', '/missing cache'],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('workshop-lightning', result.stdout)
        self.assertIn('workshop-nano', result.stdout)
        self.assertIn('127.0.0.1:8002:8000', result.stdout)

    def test_launch_contract_and_space_preservation(self):
        cmd = m.command('lightning', Path('/cache with spaces'), Path('/parser'), '0.0.0.0')
        self.assertIn('type=bind,src=/cache with spaces,dst=/hf/hub', cmd)
        self.assertIn('specialist=/adapter', cmd)
        self.assertIn('HF_HUB_OFFLINE=1', cmd)
        self.assertNotIn('--privileged', cmd)
        nano = m.command('nano', Path('/cache'), Path('/parser with spaces.py'), '127.0.0.1')
        self.assertIn('nemotron_json', nano)
        self.assertIn('type=bind,src=/parser with spaces.py,dst=/opt/parser.py,readonly', nano)

    def test_unsupported_platform_fails_before_docker(self):
        with patch.object(m.platform, 'machine', return_value='x86_64'), patch.object(m.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'ARM64'):
                m.preflight(['nano'], Path('/cache'), Path('/parser'))
            run.assert_not_called()

    def test_existing_container_is_not_replaced(self):
        with patch.object(m.platform, 'system', return_value='Linux'), \
             patch.object(m.platform, 'machine', return_value='aarch64'), \
             patch.object(m.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            with self.assertRaisesRegex(ValueError, 'already exists'):
                m.preflight(['nano'], Path('/cache'), Path('/parser'))
            self.assertFalse(any('start' in c.args[0] or 'rm' in c.args[0] for c in run.call_args_list))

    def test_discovery_alone_cannot_pass(self):
        with patch.object(m, 'api', side_effect=[{'data': [{'id': 'base'}, {'id': 'specialist'}]},
             {'choices': [{'finish_reason': 'length', 'message': {'content': 'partial'}}]}]):
            with self.assertRaisesRegex(ValueError, 'truncated'):
                m.check('lightning')

    def test_nano_requires_structured_tool_call(self):
        with patch.object(m, 'api', side_effect=[{'data': [{'id': m.NANO}]},
             {'choices': [{'message': {'content': 'I would call workshop_ping'}}]}]):
            with self.assertRaisesRegex(ValueError, 'structured tool call'):
                m.check('nano')

    def test_valid_tool_call_passes_without_execution(self):
        with patch.object(m, 'api', side_effect=[{'data': [{'id': m.NANO}]},
             {'choices': [{'message': {'tool_calls': [{'function': {'name': 'workshop_ping',
                'arguments': '{"text":"hello"}'}}]}}]}]):
            m.check('nano')


if __name__ == '__main__':
    unittest.main()
