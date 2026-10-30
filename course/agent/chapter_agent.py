"""One notebook interface for the chapter-specific OpenClaw demonstrations."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid
from urllib.request import urlopen

from course.common import ROOT
from course.agent.notebook_agent import command, put_file, validate_trajectory, SANDBOX, SOURCES

CHAPTERS=json.loads((SOURCES/'chapters.json').read_text())
OUTPUT=ROOT/'course/outputs/agent-demos'


def show_skill(chapter):
    from IPython.display import Markdown, display
    spec=CHAPTERS[chapter]
    path=SOURCES/'skills'/spec['skill']/'SKILL.md'
    learned=['workshop-model-inventory']+[s['skill'] for name,s in CHAPTERS.items() if name<=chapter]
    learned+=sorted({skill for name,s in CHAPTERS.items() if name<=chapter
                     for skill in s.get('supporting_skills',[])})
    print('Skills so far:', ' → '.join(name.removeprefix('workshop-') for name in learned))
    display(Markdown('<details><summary>Read this chapter’s skill</summary>\n\n'+path.read_text()+'\n</details>'))
    for name in spec.get('supporting_skills', []):
        upstream=json.loads((SOURCES/'nvidia-skills.json').read_text())[name]
        print('NVIDIA skill:',name,'| pinned commit:',upstream['commit'][:12])
        display(Markdown('<details><summary>Read the NVIDIA skill</summary>\n\n'+
                        (SOURCES/'skills'/name/'SKILL.md').read_text()+'\n</details>'))


def prerequisite(relative, chapter):
    latest=OUTPUT/chapter/'latest.json'
    if latest.exists():
        record=json.loads(latest.read_text())
        candidate=Path(record['directory'])/'work'/relative
        if record.get('status')=='PASS' and candidate.exists():
            return candidate
    candidate=ROOT/'course/outputs'/relative
    if not candidate.exists():
        raise FileNotFoundError(f'Run {chapter} first: missing {relative}')
    return candidate


def prepare(chapter, mode):
    spec={**CHAPTERS[chapter],'chapter':chapter}
    directory=OUTPUT/chapter/(mode+'-'+uuid.uuid4().hex)
    work=directory/'work'
    work.mkdir(parents=True)
    (directory/'chapter.json').write_text(json.dumps(spec,indent=2))
    # Capture the exact lesson this run uses; its agent section is excluded by the worker.
    shutil.copy2(SOURCES/'lessons'/f'{chapter}.json',directory/'lesson.ipynb')
    inputs={}
    for relative,previous in spec['inputs'].items():
        source=prerequisite(relative,previous)
        destination=work/relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        if source.is_dir(): shutil.copytree(source,destination)
        else: shutil.copy2(source,destination)
        files=sorted(destination.rglob('*')) if destination.is_dir() else [destination]
        inputs[relative]={'source':str(source),'files':{
            str(f.relative_to(work)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files if f.is_file()}}
    (directory/'inputs.json').write_text(json.dumps(inputs,indent=2))
    upstream=json.loads((SOURCES/'nvidia-skills.json').read_text())
    provenance={}
    for name in [spec['skill']]+spec.get('supporting_skills',[]):
        text=(SOURCES/'skills'/name/'SKILL.md').read_bytes()
        sha=hashlib.sha256(text).hexdigest()
        if name in upstream and sha != upstream[name]['sha256']:
            raise ValueError('Pinned NVIDIA skill has changed: '+name)
        provenance[name]={**upstream.get(name,{'author':'workshop'}),'sha256':sha}
    (directory/'skills.json').write_text(json.dumps(provenance,indent=2))
    return directory,spec


class LessonActions:
    def __init__(self,directory,spec):
        self.directory,self.spec=directory,spec
        self.results={}

    def perform(self,action):
        actions=self.spec['actions']
        if action not in actions: raise ValueError('Unknown chapter action')
        if action in self.results: return {**self.results[action],'reused':True}
        index=actions.index(action)
        if index and actions[index-1] not in self.results:
            raise ValueError('Run '+actions[index-1]+' first')
        if index==0:
            result={'chapter':self.spec['chapter'],'task':self.spec['task'],
                    'inputs':json.loads((self.directory/'inputs.json').read_text()),
                    'execution':'Fixed lesson code on the host CPU; OpenClaw chooses the tool calls',
                    'note':self.spec['note']}
        elif index==1:
            print('Running the lesson tool…',flush=True)
            env={**os.environ,'COURSE_LIVE':'1','CUDA_VISIBLE_DEVICES':'',
                 'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','OMP_NUM_THREADS':'2'}
            with (self.directory/'lesson.log').open('w') as log:
                completed=subprocess.run([sys.executable,str(SOURCES/'chapter_worker.py'),str(self.directory)],
                                         cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=150)
            if completed.returncode:
                raise RuntimeError('Lesson tool failed. '+(self.directory/'lesson.log').read_text()[-2000:])
            result=json.loads((self.directory/'work/lesson-summary.json').read_text())
        else:
            work=self.directory/'work'
            paths=[work/p for p in self.spec['outputs']]
            missing=[str(p.relative_to(work)) for p in paths if not p.is_file() or not p.stat().st_size]
            if missing: raise ValueError('Missing results: '+', '.join(missing))
            result={'status':'PASS','summary':json.loads((work/'lesson-summary.json').read_text()),
                    'artifacts':{str(p.relative_to(work)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
            (self.directory/'result.json').write_text(json.dumps(result,indent=2))
        self.results[action]=result
        (self.directory/'tool-results.json').write_text(json.dumps(self.results,indent=2))
        return result


def finish(directory,spec,mode,actions,extra_errors=()):
    errors=list(extra_errors)
    if set(actions.results)!=set(spec['actions']): errors.append('The three chapter tools did not all complete')
    if mode=='openclaw':
        trace=directory/'trajectory/session-branch.json'
        if not trace.exists(): errors.append('No OpenClaw skill-read trace was saved')
        else:
            trajectory=json.loads(trace.read_text())
            for name in [spec['skill']]+spec.get('supporting_skills',[]):
                errors.extend(validate_trajectory(trajectory,name))
    result={'status':'FAIL' if errors else 'PASS','mode':mode,'chapter':spec['chapter'],
            'errors':errors,'directory':str(directory)}
    if (directory/'result.json').exists():
        result.update(json.loads((directory/'result.json').read_text()))
        result['status']='FAIL' if errors else 'PASS'
    (directory/'validation.json').write_text(json.dumps(result,indent=2))
    if result['status']=='PASS':
        (directory.parent/'latest.json').write_text(json.dumps(result,indent=2))
    print('CHECK:',result['status'],flush=True)
    if errors: print('\n'.join(errors),flush=True)
    else: print(json.dumps(result['summary'],indent=2),flush=True)
    print('Saved:',directory,flush=True)
    return result


def run_chapter(chapter, agent=True):
    if chapter not in CHAPTERS: raise ValueError('Unknown chapter')
    if os.environ.get('COURSE_LIVE','1')!='1':
        return {'status':'SKIPPED','reason':'Offline mode; no agent or live lesson repeat'}
    mode='openclaw' if agent else 'direct'
    if agent:
        with urlopen('http://127.0.0.1:30081/v1/models',timeout=5) as r:
            assert json.load(r)['data'],'Nano controller is not ready'
    directory,spec=prepare(chapter,mode)
    actions=LessonActions(directory,spec)
    if not agent:
        print('DIRECT CHECKS — no OpenClaw agent',flush=True)
        try:
            for action in spec['actions']:
                print('TOOL:',action,flush=True)
                actions.perform(action)
            return finish(directory,spec,mode,actions)
        except Exception as exc:
            return finish(directory,spec,mode,actions,[str(exc)])
    remote='/home/sandbox/course-runs/'+directory.name
    bundle=directory/'bundle';bundle.mkdir()
    for name in ('chapter_tool.py','run_remote.py'):
        shutil.copy2(SOURCES/name,bundle/name)
    shutil.copy2(directory/'chapter.json',bundle/'chapter.json')
    bridge=(ROOT/'run/claw/terminal/bridge.mjs').read_text().replace(
        'body.stream = false;',
        'body.stream = false; body.temperature = 0; body.messages = body.messages?.map(normalizeToolMessage);')
    (bundle/'bridge.mjs').write_text("import {normalizeToolMessage} from './normalize_tool_output.mjs';\n"+bridge)
    shutil.copy2(SOURCES/'normalize_tool_output.mjs',bundle/'normalize_tool_output.mjs')
    config=json.loads((ROOT/'run/claw/terminal/openclaw.json').read_text())
    config['agents']['defaults']['workspace']=remote+'/workspace'
    config['skills']['allowBundled']=[spec['skill']]+spec.get('supporting_skills',[])
    (bundle/'openclaw.json').write_text(json.dumps(config,indent=2))
    commands='; then '.join(f'python3 {remote}/chapter_tool.py {action}' for action in spec['actions'])
    prompt=(f"Use the {spec['skill']} skill for notebook {chapter[:2]}. "
            f"First use read on {remote}/workspace/skills/{spec['skill']}/SKILL.md. "
            + ''.join(f"Then use read on {remote}/workspace/skills/{name}/SKILL.md before any exec. "
                      for name in spec.get('supporting_skills',[])) +
            f"Task: {spec['task']} "
            f"Then run these three complete commands individually: {commands}. "
            'Use exec elevated=false, yieldMs=10000, timeout=180. '
            'If a command is still running, poll it with process before the next action. '
            'The known oom_score_adj launcher warning is harmless when JSON contains result; '
            'in that case continue to the next command without asking. '
            'Stop only for an actual error result or after the final check. '
            'Report the final check status briefly. Do not edit files or run other commands. /no_think')
    (bundle/'task.txt').write_text(prompt)
    print('OpenClaw task:',spec['task'],flush=True)
    print('Tools:', ' → '.join(spec['actions']),flush=True)
    errors=[]
    try:
        # The skill library grows with the course, but the task selects this chapter's skill.
        names=['workshop-model-inventory']+[s['skill'] for name,s in CHAPTERS.items() if name<=chapter]
        names+=sorted({skill for name,s in CHAPTERS.items() if name<=chapter
                       for skill in s.get('supporting_skills',[])})
        for name in names:
            put_file(remote+'/workspace/skills/'+name+'/SKILL.md',(SOURCES/'skills'/name/'SKILL.md').read_text())
        put_file(remote+'/workspace/AGENTS.md',
                 'Read the selected workshop skill and any NVIDIA supporting skill named in the task. '
                 'The implementation is already prepared; use the skills to run and check its evidence. '
                 'Execute only the workshop skill’s three actions. '
                 'Report actual results and stop on a genuine tool error. Keep your final answer short.')
        for path in bundle.iterdir(): put_file(remote+'/'+path.name,path.read_text())
        proc=subprocess.Popen(['openshell','sandbox','exec','--name',SANDBOX,'--',
                               'python3',remote+'/run_remote.py'],stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT,text=True)
        try:
            with (directory/'console.txt').open('w') as log:
                for line in proc.stdout:
                    log.write(line); log.flush()
                    if line.startswith('COURSE_REQUEST '):
                        req=json.loads(line.removeprefix('COURSE_REQUEST '))
                        if not re.fullmatch('[0-9a-f]{32}',req.get('id','')):
                            raise ValueError('Invalid tool request identifier')
                        try:
                            print('TOOL:',req['action'],flush=True)
                            result=actions.perform(req['action'])
                            reply={'result':result}
                            if req['action']==spec['actions'][0]:
                                print('Inputs ready:',list(result['inputs']) or 'no prior artifacts needed',flush=True)
                            else:
                                print(json.dumps(result.get('summary',result),indent=2),flush=True)
                        except Exception as exc:
                            reply={'error':str(exc)}
                            errors.append(str(exc))
                        put_file(remote+'/responses/'+req['id']+'.json',json.dumps(reply))
                    elif not line.startswith('{"tool":'):
                        print(line,end='',flush=True)
            if proc.wait(timeout=10): errors.append('OpenClaw command failed')
        finally:
            if proc.poll() is None:
                proc.terminate();proc.wait(timeout=10)
        trajectory=directory/'trajectory';trajectory.mkdir()
        for name in ('session-branch.json','events.jsonl','manifest.json'):
            try:
                text=command(['openshell','sandbox','exec','--name',SANDBOX,'--','cat',
                              remote+'/.openclaw/trajectory-exports/trace/'+name])
                (trajectory/name).write_text(text)
            except RuntimeError as exc: errors.append(str(exc))
        for name in ('openclaw-output.txt','agent-session.txt','events.jsonl'):
            try:
                text=command(['openshell','sandbox','exec','--name',SANDBOX,'--','cat',remote+'/'+name])
                (directory/name).write_text(text)
            except RuntimeError as exc: errors.append(str(exc))
    except Exception as exc:
        errors.append(str(exc))
    return finish(directory,spec,mode,actions,errors)
