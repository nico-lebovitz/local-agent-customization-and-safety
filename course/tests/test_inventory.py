import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from course.agent.inventory_tool import perform, validate
from course.agent.notebook_agent import prepare, run_agent, validate_trajectory


def evidence():
    result = {
        'inventory': {
            'adapter': {'config_sha256': 'abc', 'weights': [{'sha256': 'weights'}]},
            'checkpoints': {'BF16': [{'revision': 'b'}], 'NVFP4': [{'revision': 'n'}]}},
        'models': {'data': [{'id': 'base', 'root': 'checkpoint'},
                            {'id': 'specialist', 'root': 'adapter'}]},
    }
    for alias in ('base', 'specialist'):
        result['probe-' + alias] = {
            'request': {'model': alias}, 'seconds': .1,
            'response': {'model': alias, 'choices': [
                {'finish_reason': 'stop', 'message': {'content': 'Ready'}}]}}
    return result


class InventoryTests(unittest.TestCase):
    def test_complete_evidence_passes(self):
        self.assertEqual(validate(evidence()), [])

    def test_missing_and_truncated_probe_fail(self):
        item = evidence()
        del item['probe-specialist']
        self.assertTrue(validate(item))
        item = evidence()
        item['probe-base']['response']['choices'][0]['finish_reason'] = 'length'
        self.assertIn('Incomplete response: base', validate(item))

    def test_wrong_model_and_blank_output_fail(self):
        item = evidence()
        item['probe-specialist']['response']['model'] = 'base'
        item['probe-base']['response']['choices'][0]['message']['content'] = ''
        self.assertIn('Missing or mismatched response model: specialist', validate(item))
        self.assertIn('No visible response: base', validate(item))

    def test_probe_requires_discovery_and_deduplicates_within_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            with self.assertRaises(ValueError):
                perform(path, 'probe-base')
            (path / 'evidence.json').write_text(json.dumps({'models': evidence()['models']}))
            with patch('course.agent.inventory_tool.request',
                       return_value=evidence()['probe-base']['response']) as call:
                perform(path, 'probe-base')
                second = perform(path, 'probe-base')
                self.assertTrue(second['cached'])
                self.assertEqual(call.call_count, 1)

    def test_manifest_refuses_incomplete_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = perform(tmp, 'manifest')
            self.assertEqual(manifest['status'], 'FAIL')
            self.assertTrue(manifest['errors'])

    def test_offline_never_starts_agent_or_creates_run(self):
        with patch.dict(os.environ, {'COURSE_LIVE': '0'}):
            with patch('course.agent.notebook_agent.subprocess.run') as call:
                with self.assertRaises(RuntimeError):
                    run_agent()
                with self.assertRaises(RuntimeError):
                    prepare('direct')
                call.assert_not_called()

    def test_trace_requires_skill_read_before_execution(self):
        read = {'message': {'content': [{'type': 'toolCall', 'id': 'r', 'name': 'read',
                'arguments': {'path': '/workspace/skills/workshop-model-inventory/SKILL.md'}}]}}
        loaded = {'message': {'role': 'toolResult', 'toolCallId': 'r', 'isError': False}}
        run = {'message': {'content': [{'type': 'toolCall', 'id': 'e', 'name': 'exec'}]}}
        self.assertEqual(validate_trajectory({'entries': [read, loaded, run]}), [])
        self.assertEqual(validate_trajectory({'entries': [read, loaded, run, '[Truncated]']}), [])
        self.assertTrue(validate_trajectory({'entries': [run, read, loaded]}))
        self.assertTrue(validate_trajectory({'entries': []}))


if __name__ == '__main__':
    unittest.main()
