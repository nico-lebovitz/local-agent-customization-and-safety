"""Execute a fixed notebook lesson in a fresh CPU process and collect evidence.

The agent supplies an action name, never Python or shell source. The notebook
sources and prerequisites are copied by the host before OpenClaw starts.
"""
import hashlib
import json
import linecache
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def policy_probes(directory):
    """Test the existing policy, including a canary writable without Landlock."""
    from urllib.request import urlopen
    from course.common import BASE_URL
    with urlopen(BASE_URL + '/health', timeout=10) as response:
        assert response.status == 200
    def cmd(args):
        return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=30)
    ids = cmd(['docker', 'ps', '-q', '--filter',
               'label=openshell.ai/sandbox-name=nato-openclaw-demo']).split()
    if len(ids) != 1:
        raise RuntimeError('Expected one running nato-openclaw-demo sandbox')
    # A new, dedicated canary owned by sandbox makes the filesystem test meaningful.
    canary = '/opt/course-policy-canary-' + directory.parent.name
    setup = ('import os,pwd,pathlib,sys; p=pathlib.Path(sys.argv[1]); '
             'p.write_text("course policy probe\\n"); u=pwd.getpwnam("sandbox"); '
             'os.chown(p,u.pw_uid,u.pw_gid); p.chmod(0o600)')
    cmd(['docker', 'exec', '--user', 'root', ids[0], 'python3', '-c', setup, canary])
    try:
        cmd(['docker', 'exec', '--user', 'sandbox', ids[0], 'python3', '-c',
             'import sys; open(sys.argv[1],"r+").close(); print("Unix permissions allow writes")', canary])
        probe = '''import json,sys,tempfile
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError
base="http://host.openshell.internal:8002"
with urlopen(base+"/v1/models",timeout=10) as r:
    models=json.load(r)
assert {"base","specialist"} <= {m["id"] for m in models["data"]}
try:
    urlopen(base+"/health",timeout=10)
except HTTPError as exc:
    assert exc.code==403, exc.code
else:
    raise AssertionError("Expected policy denial for /health")
try:
    open(sys.argv[1],"r+").close()
except PermissionError:
    pass
else:
    raise AssertionError("Source write was not denied")
with tempfile.NamedTemporaryFile(dir="/tmp",mode="w+") as scratch:
    scratch.write("allowed"); scratch.flush(); scratch.seek(0)
    assert scratch.read()=="allowed"
print(json.dumps({"sandbox":"nato-openclaw-demo","allowed_models":True,
"host_health_status":200,"sandbox_health_status":403,
"unix_canary_writable":True,"readonly_write_denied":True,"scratch_write_allowed":True,
"tested_policy":"existing demo policy; student policy not deployed","landlock":"best_effort"}))
'''
        raw = cmd(['openshell', 'sandbox', 'exec', '--name', 'nato-openclaw-demo', '--',
                   'python3', '-c', probe, canary])
        result = json.loads(raw)
        (directory / 'policy-probes.json').write_text(json.dumps(result, indent=2))
        return result
    finally:
        # Remove only this run's canary, created above; never touch course source.
        cmd(['docker', 'exec', '--user', 'root', ids[0], 'python3', '-c',
             'import pathlib,sys; pathlib.Path(sys.argv[1]).unlink()', canary])


def summarize(chapter, ns, output):
    number = chapter[:2]
    if number == '02':
        train, val = ns['training'], ns['validation']
        train_text = [r['messages'][1]['content'] for r in train]
        val_text = [r['messages'][1]['content'] for r in val]
        assert len(set(train_text)) == len(train_text)
        assert not set(train_text) & set(val_text)
        for row in train + val:
            ns['validate_example'](row)
        if ns.get('proposed'):
            (output / 'teacher-candidate.txt').write_text(ns['proposed'])
        return {'training_examples':len(train),'validation_examples':len(val),
                'duplicate_observations':0,'train_validation_overlap':0,
                'supervised_tokens':sum(x != -100 for x in ns['labels']),
                'teacher_suggestion':ns.get('proposed'),
                'review_status':'Not added to training; human review required'}
    if number == '03':
        named = list(ns['model'].named_parameters())
        trainable = [(name,p) for name,p in named if p.requires_grad]
        assert trainable and all('lora_' in name for name,p in trainable)
        return {'profile':'cpu','rank':ns['adapter_config'].r,
                'trainable_parameters':sum(p.numel() for _,p in trainable),
                'frozen_parameters':sum(p.numel() for _,p in named if not p.requires_grad),
                'only_lora_trainable':True}
    if number == '04':
        metrics = json.loads((output/'cpu/training-metrics.json').read_text())
        assert metrics['steps']==40 and len(metrics['history'])==40
        assert metrics['base_frozen']
        return {'profile':'cpu','steps':40,'loss_before':metrics['validation_before'],
                'loss_after':metrics['validation_after'],'frozen_sample_unchanged':True,
                'adapter_sha256':digest(output/'cpu/student-adapter/adapter_model.safetensors')}
    if number == '05':
        assert ns['difference'] > 0
        return {'cpu_adapter_reloaded':True,'mean_logit_change':ns['difference'],
                'existing_endpoint_answers':ns['endpoint_calls'],
                'note':'Neither serving alias is the CPU candidate'}
    if number == '06':
        rows = ns['student_results']; results=ns['results']
        assert len(rows)==3 and len(results)==9
        return {'candidate_exact_match':sum(r['exact_match'] for r in rows),'candidate_examples':len(rows),
                'endpoint_scores':{arm:sum(all(r['correct'].values()) for r in results if r['arm']==arm)
                                   for _,arm,_ in ns['arms']},
                'endpoint_cases_per_arm':3,'recorded_errors':sum('error' in r for r in results),
                'meaning':'Evaluation completed; PASS is not an accuracy claim'}
    if number == '07':
        assert [r['model'] for r in ns['routing_results']]==['base','specialist']
        assert not ns['validate_item'](ns['invalid'],1)['valid']
        # Confirm a real dependency timeout propagates rather than fabricating a classification.
        original=ns['chat']
        def timeout(*args,**kwargs): raise TimeoutError('injected endpoint timeout')
        ns['chat']=timeout
        try:
            try: ns['classify_observation']('test')
            except TimeoutError: pass
            else: raise AssertionError('Timeout was hidden')
        finally: ns['chat']=original
        return {'classification':ns['result']['item'],'live_specialist_gate':ns['result']['gate'],
                'switchyard_routes':ns['routing_results'],
                'invalid_confidence_rejected':True,'premature_draft_rejected':True,
                'injected_timeout_propagated':True}
    if number == '08':
        skills = ns['discover_skills'](output/'student-skills')
        assert {'draft-report','describe-observation'} <= set(skills)
        return {'skills':{name:{'description':item['description'],'sha256':digest(item['path'])}
                          for name,item in skills.items()},'loaded_skill':'draft-report'}
    if number == '09':
        from course.agent.routing_trace import timeline
        record=ns['record']
        assert record['status'] in ('COMPLETE','HOLD'), record
        assert not record['released']
        compile((output/'student-agent.py').read_text(),'student-agent.py','exec')
        rows=timeline(ns['trace'].events)
        assert any(r['kind']=='llm' and r.get('model')=='base' for r in rows)
        assert any(r['kind']=='tool' for r in rows)
        failure_rows=timeline(ns['failure_trace'].events)
        assert any(r['name']=='triage' and r['status']=='ERROR' for r in failure_rows)
        return {'outcome':record['status'],'actions':[e.get('action',{}).get('tool') for e in record['events']],
                'released':False,'skill_sha256':record['skill_sha256'],
                'relay_events':len(ns['trace'].events),
                'injected_failure':ns['failed_record']['events'][0]['error'],
                'draft':record['state'].get('draft'),'hold_reason':record['state'].get('hold')}
    if number == '10':
        return policy_probes(output)
    if number == '11':
        assert ns['record'] is not None, 'Run notebook 09 first'
        # Execute the notebook-exported implementation, with the skills copied from 08.
        tested={'__name__':'course_regression'}
        exec(compile((output/'student-agent.py').read_text(),'student-agent.py','exec'),tested)
        tested['SKILLS']=output/'student-skills'
        run=tested['run']
        invalid=ns['case']['injected_specialist']
        actions=iter(['perceive','triage','request_review','finish'])
        def fixture(model,messages,**kwargs):
            if model=='specialist': return json.dumps(invalid)
            return json.dumps({'tool':next(actions),'reason':'Injected invalid classification must hold'})
        record=run(model_call=fixture)
        assert record['status']=='HOLD' and 'draft' not in record['state']
        observed=ns['check_trace'](ns['record'])
        result={'test_type':'injected regression, not an observed model failure',
                'saved_run_outcome':ns['record']['status'],'saved_run_contract_failures':observed,
                'regression_outcome':record['status'],'draft_created':False,'released':False,
                'gym_rl':ns['learning_result']}
        (output/'regression-result.json').write_text(json.dumps(result,indent=2))
        return result
    raise ValueError('Unknown chapter')


def run(directory):
    directory=Path(directory)
    chapter=json.loads((directory/'chapter.json').read_text())['chapter']
    notebook=json.loads((directory/'lesson.ipynb').read_text())
    output=directory/'work'
    output.mkdir(exist_ok=True)
    os.environ.update(CUDA_VISIBLE_DEVICES='',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    ns={'__name__':'course_lesson_run'}
    for index,cell in enumerate(notebook['cells']):
        source=''.join(cell['source'])
        if cell.get('metadata',{}).get('course_agent_section') or '## Have an agent' in source:
            break
        if cell['cell_type']!='code': continue
        # The optional saved reference policy record is not fresh evidence.
        if chapter.startswith('10-') and 'openshell-validation.json' in source: continue
        filename=str(directory/f'cell_{index}.py')
        linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
        exec(compile(source,filename,'exec'),ns)
        if index==1:
            ns['OUTPUT']=output
            if chapter.startswith('05-'):
                original_chat=ns['chat']
                calls=[]
                def traced_chat(model,messages,**kwargs):
                    start=time.perf_counter()
                    answer=original_chat(model,messages,**kwargs)
                    calls.append({'model':model,'answer':answer,
                                  'seconds':round(time.perf_counter()-start,3)})
                    return answer
                ns['chat']=traced_chat
                ns['endpoint_calls']=calls
        if ns.get('PROFILE','cpu')!='cpu':
            raise RuntimeError('Agent lessons use only the CPU profile')
    summary=summarize(chapter,ns,output)
    (output/'lesson-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('LESSON RESULT:',json.dumps(summary),flush=True)


if __name__=='__main__':
    run(sys.argv[1])
