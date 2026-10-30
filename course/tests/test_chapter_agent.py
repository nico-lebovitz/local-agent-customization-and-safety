import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from course.agent.chapter_agent import CHAPTERS, LessonActions, finish, run_chapter
from course.agent.notebook_agent import validate_trajectory


class ChapterAgentTests(unittest.TestCase):
    def test_offline_does_not_start_process_or_prepare_files(self):
        with patch.dict(os.environ, {'COURSE_LIVE':'0'}), patch('course.agent.chapter_agent.prepare') as prepare:
            with patch('course.agent.chapter_agent.subprocess.Popen') as process:
                self.assertEqual(run_chapter('04-train-adapter')['status'],'SKIPPED')
                process.assert_not_called();prepare.assert_not_called()

    def test_action_allowlist_and_preconditions(self):
        with tempfile.TemporaryDirectory() as tmp:
            actions=LessonActions(Path(tmp),CHAPTERS['04-train-adapter'])
            for action in ('arbitrary-shell','train-adapter','check-training'):
                with self.assertRaises(ValueError):actions.perform(action)

    def test_repeated_work_reuses_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            actions=LessonActions(Path(tmp),CHAPTERS['04-train-adapter'])
            actions.results['train-adapter']={'steps':40}
            with patch('course.agent.chapter_agent.subprocess.run') as run:
                result=actions.perform('train-adapter')
                self.assertTrue(result['reused']);run.assert_not_called()

    def test_missing_outputs_do_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec={**CHAPTERS['04-train-adapter'],'chapter':'04-train-adapter'}
            actions=LessonActions(Path(tmp),spec)
            actions.results={name:{} for name in spec['actions'][:2]}
            with self.assertRaisesRegex(ValueError,'Missing results'):
                actions.perform('check-training')

    def test_failed_run_does_not_replace_latest_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp);directory=parent/'failed';directory.mkdir()
            previous={'status':'PASS','directory':'previous-good-run'}
            (parent/'latest.json').write_text(json.dumps(previous))
            spec={**CHAPTERS['04-train-adapter'],'chapter':'04-train-adapter'}
            result=finish(directory,spec,'direct',LessonActions(directory,spec),['timeout'])
            self.assertEqual(result['status'],'FAIL')
            self.assertEqual(json.loads((parent/'latest.json').read_text()),previous)

    def test_trace_must_read_the_current_chapter_skill(self):
        def trace(name):
            return {'entries':[
                {'message':{'content':[{'type':'toolCall','name':'read','id':'r','arguments':
                    {'path':'/workspace/skills/'+name+'/SKILL.md'}}]}},
                {'message':{'role':'toolResult','toolCallId':'r','isError':False}},
                {'message':{'content':[{'type':'toolCall','name':'exec','id':'e'}]}}]}
        self.assertEqual(validate_trajectory(trace('workshop-train-adapter'),'workshop-train-adapter'),[])
        self.assertTrue(validate_trajectory(trace('workshop-model-inventory'),'workshop-train-adapter'))


if __name__=='__main__':unittest.main()
