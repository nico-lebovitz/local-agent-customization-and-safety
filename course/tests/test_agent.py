import json
import unittest
from course.agent.runtime import run, execute, allowed_actions, load_skill

VALID = {'activity_type':'civil_gathering','sensor_quality':'UNKNOWN',
         'confidence':'POSSIBLE','routing':'CIMIC'}

def fixture(actions, item=VALID):
    actions = iter(actions)
    def call(model, messages, **kwargs):
        if model == 'specialist': return json.dumps(item)
        if 'Write one short factual summary' in messages[0]['content']:
            return 'People gather at market stalls.'
        return json.dumps({'tool':next(actions),'reason':'scripted test decision'})
    return call

class AgentTests(unittest.TestCase):
    def test_complete_draft_preserves_source_and_gate(self):
        record=run(model_call=fixture(['perceive','triage','draft','finish']))
        self.assertEqual(record['status'],'COMPLETE')
        self.assertEqual(record['state']['draft']['source_id'],'civil-market')
        self.assertEqual(record['state']['draft']['destination'],'CIMIC')
        self.assertFalse(record['released'])
    def test_invalid_specialist_holds_without_draft(self):
        record=run(model_call=fixture(['perceive','triage','request_review','finish'],
            {**VALID,'confidence':'CONFIRMED'}))
        self.assertEqual(record['status'],'HOLD')
        self.assertNotIn('draft',record['state'])
    def test_skill_cannot_skip_preconditions(self):
        record=run(model_call=fixture(['draft']))
        self.assertEqual(record['status'],'ERROR')
        self.assertNotIn('draft',record['state'])
    def test_malformed_action_stops(self):
        record=run(model_call=lambda *a,**kw: '[]')
        self.assertEqual(record['status'],'ERROR')
    def test_timeout_stops(self):
        def timeout(*a,**kw): raise TimeoutError('injected timeout')
        self.assertEqual(run(model_call=timeout)['status'],'ERROR')
    def test_budget_is_enforced(self):
        record=run(model_call=fixture(['perceive']),max_steps=1)
        self.assertEqual(record['status'],'STEP_LIMIT')
    def test_describe_needs_no_model_classification(self):
        record=run(skill='describe-observation',model_call=fixture(['perceive','finish']))
        self.assertEqual(record['status'],'COMPLETE')
        self.assertNotIn('triage',record['state'])
    def test_skill_path_cannot_escape_catalog(self):
        with self.assertRaises(KeyError):load_skill('../../README')
    def test_invalid_clip(self):
        with self.assertRaises(ValueError):run(clip='../../etc/passwd')
    def test_changed_routing_is_overridden(self):
        record=run(model_call=fixture(['perceive','triage','draft','finish'],{**VALID,'routing':'J2-ANALYSIS'}))
        self.assertEqual(record['state']['draft']['destination'],'CIMIC')

if __name__ == '__main__': unittest.main()
