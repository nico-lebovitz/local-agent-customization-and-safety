"""Lifecycle safety tests use simulated Docker/process operations only."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace

spec=importlib.util.spec_from_file_location('workshop_lifecycle',Path(__file__).parents[1]/'workshop.py')
w=importlib.util.module_from_spec(spec); spec.loader.exec_module(w)

class LifecycleTests(unittest.TestCase):
    def item(self,name): return {'name':name,'id':name+'-id'}
    def test_replaced_container_is_rejected(self):
        data={'root':str(w.ROOT),'containers':[self.item('spec')]}
        with patch.object(w,'inspect',return_value={'Id':'different'}):
            with self.assertRaisesRegex(RuntimeError,'identity changed'): w.verified(data)
    def test_moved_repository_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'Repository moved'):
            w.verified({'root':'/somewhere/else','containers':[]})
    def test_model_requires_both_aliases(self):
        with patch.object(w,'http',return_value={'data':[{'id':'base'}]}):
            self.assertFalse(w.model_ready())
        with patch.object(w,'http',return_value={'data':[{'id':'base'},{'id':'specialist'}]}):
            self.assertTrue(w.model_ready())
    def test_start_waits_for_each_model_before_next(self):
        events=[]; items=[self.item(n) for n in ['cosmos','nano','spec']]
        def cmd(args,**kwargs): events.append(tuple(args)); return SimpleNamespace(stdout='')
        def wait(check,label,timeout): events.append(('ready',label))
        with patch.object(w,'verified',return_value=items),patch.object(w,'check_assets'),patch.object(w,'check_video_network'),patch.object(w,'warm_models'),patch.object(w,'command',side_effect=cmd),patch.object(w,'inspect',return_value={'State':{'Running':False}}),patch.object(w,'wait_until',side_effect=wait),patch.object(w,'owned_sandboxes',return_value=([],[])),patch.object(w,'start_app'),patch.object(w,'links'):
            w.up({},1,live_video=True)
        self.assertLess(events.index(('ready','cosmos')),events.index(('docker','start','nano')))
        self.assertLess(events.index(('ready','nano')),events.index(('docker','start','spec')))
        self.assertIn(('ready','base and specialist model aliases'),events)
    def test_readiness_failure_prevents_later_model(self):
        calls=[]
        with patch.object(w,'verified',return_value=[self.item('cosmos'),self.item('spec')]),patch.object(w,'check_assets'),patch.object(w,'check_video_network'),patch.object(w,'warm_models'),patch.object(w,'command',side_effect=lambda args: calls.append(args)),patch.object(w,'inspect',return_value={'State':{'Running':False}}),patch.object(w,'wait_until',side_effect=RuntimeError('unhealthy')):
            with self.assertRaisesRegex(RuntimeError,'unhealthy'): w.up({},1,live_video=True)
        self.assertNotIn(['docker','start','spec'],calls)
    def test_shutdown_preserves_data_and_unrelated_gateway(self):
        running={'vss':True,'spec':True}; calls=[]
        def cmd(args,**kwargs):
            calls.append(args)
            if args[:2]==['docker','stop']: running[args[-1]]=False
            return SimpleNamespace(stdout='unrelated-container\n')
        with patch.object(w,'verified',return_value=[self.item('vss'),self.item('spec')]),patch.object(w,'processes',return_value=[]),patch.object(w,'jupyter_servers',return_value=iter([])),patch.object(w,'owned_sandboxes',return_value=([],[{'State':{'Running':True}}])),patch.object(w,'command',side_effect=cmd),patch.object(w,'inspect',side_effect=lambda name:{'State':{'Running':running[name]}}):
            w.down({})
        stops=[c[-1] for c in calls if c[:2]==['docker','stop']]
        self.assertEqual(stops,['spec','vss'])
        self.assertFalse(any('systemctl' in c for c in calls))
        self.assertFalse(any(x in c for c in calls for x in ['rm','prune','down','poweroff','--volumes']))
    def test_foreign_port_not_replaced(self):
        with patch.object(w,'processes',return_value=[]),patch.object(w,'port_open',return_value=True):
            with self.assertRaisesRegex(RuntimeError,'unrecognized'): w.start_app('ui')
    def test_default_start_does_not_start_video_stack(self):
        calls=[]
        with patch.object(w,'verified',return_value=[self.item('vss-agent'),self.item('spec')]),patch.object(w,'check_assets'),patch.object(w,'warm_models'),patch.object(w,'command',side_effect=lambda args:calls.append(args)),patch.object(w,'inspect',return_value={'State':{'Running':False}}),patch.object(w,'wait_until'),patch.object(w,'owned_sandboxes',return_value=([],[])),patch.object(w,'start_app'),patch.object(w,'links'):
            w.up({},1)
        self.assertIn(['docker','start','spec'],calls)
        self.assertNotIn(['docker','start','vss-agent'],calls)
    def test_cold_video_start_rejects_loaded_lightning(self):
        with patch.object(w,'verified',return_value=[self.item('spec')]),patch.object(w,'check_assets'),patch.object(w,'check_video_network'),patch.object(w,'inspect',side_effect=lambda name:{'State':{'Running':name=='spec'}}),patch.object(w,'command') as cmd:
            with self.assertRaisesRegex(RuntimeError,'already loaded Lightning'):
                w.up({},1,live_video=True)
            cmd.assert_not_called()
    def test_changed_venue_address_rejected(self):
        with patch.object(w,'inspect',return_value={'Config':{'Env':['LLM_BASE_URL=http://192.168.4.71:30081/v1']}}),patch.object(w,'command',return_value=SimpleNamespace(stdout='[{"addr_info":[{"local":"10.0.0.2"}]}]')):
            with self.assertRaisesRegex(RuntimeError,'not assigned'):
                w.check_video_network()
    def test_failed_initializer_is_not_healthy(self):
        with patch.object(w,'inspect',return_value={'State':{'Status':'exited','ExitCode':1}}):
            with self.assertRaisesRegex(RuntimeError,'initialization failed'): w.container_ready(w.INIT)

if __name__=='__main__': unittest.main()
