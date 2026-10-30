"""Short notebook controls around the existing, fixed lesson implementations.

A step executes explicit cell indices from a captured original notebook. Agent
requests never supply these indices or Python source; their fixed tools remain separate.
"""
import contextlib
import hashlib
from html import escape
import io
import json
import linecache
from pathlib import Path
import shutil
import time
import uuid

from course.common import ROOT, chat, request, rows
from course.agent.chapter_agent import CHAPTERS

# Public step names keep teaching code in the notebook readable.
STEPS = {
 '04': {'load':[2], 'batch':[4], 'baseline':[6], 'train':[7,8]},
 '05': {'reload':[3,4], 'deployed':[6], 'compare':[8]},
 '06': {'candidate':[3], 'endpoints':[4,5], 'manifest':[7]},
 '07': {'route':[2], 'gate':[4], 'order':[6]},
 '08': {'write':[2], 'discover':[3]},
 '09': {'tools':[2,4,6,7,9], 'run':[10,11], 'fail':[14]},
 '10': {'prepare':[2,3], 'probe':[]},
 '11': {'trace':[2,4], 'case':[6], 'learn':[9,11]},
}


class LessonWalkthrough:
    def __init__(self, chapter):
        self.chapter = chapter
        self.number = chapter[:2]
        self.parent = ROOT / 'course/outputs/previews' / chapter
        self.directory = self.parent / uuid.uuid4().hex
        self.work = self.directory / 'work'
        self.work.mkdir(parents=True)
        source = ROOT / 'course/agent/lessons' / (chapter+'.json')
        shutil.copy2(source, self.directory/'lesson.ipynb')
        self.notebook=json.loads(source.read_text())
        self.inputs={}
        for relative,previous in CHAPTERS[chapter]['inputs'].items():
            if previous[:2] in ('02','03'):
                origin=ROOT / ('course/outputs/preview'+previous[:2]) / relative
            else:
                latest=ROOT/'course/outputs/previews'/previous/'latest.json'
                if not latest.exists():raise FileNotFoundError('Finish the manual walkthrough for '+previous+' first.')
                origin=Path(json.loads(latest.read_text())['work'])/relative
            if not origin.exists():raise FileNotFoundError('Run notebook '+previous+' first: '+str(origin))
            dest=self.work/relative
            dest.parent.mkdir(parents=True,exist_ok=True)
            if origin.is_dir():shutil.copytree(origin,dest)
            else:shutil.copy2(origin,dest)
            self.inputs[relative]=str(origin)
        self.ns={'__name__':'lesson_walkthrough','ROOT':ROOT,'OUTPUT':self.work,'LIVE':True,
                 'Path':Path,'json':json,'chat':chat,'request':request,'rows':rows}
        import os,sys
        self.ns.update(os=os,sys=sys)
        self.endpoint_calls=[]
        if self.number=='05':
            def traced_chat(model,messages,**kwargs):
                started=time.perf_counter();answer=chat(model,messages,**kwargs)
                self.endpoint_calls.append({'model':model,'answer':answer,'seconds':round(time.perf_counter()-started,3)})
                return answer
            self.ns['chat']=traced_chat
            self.ns['endpoint_calls']=self.endpoint_calls
        self.completed=[]
        print('Fresh manual run:',self.directory)
        if self.inputs:print('Inputs:',json.dumps(self.inputs,indent=2))

    def step(self,name):
        names=list(STEPS[self.number])
        if name not in names:raise ValueError('Unknown step')
        index=names.index(name)
        if index and names[index-1] not in self.completed:raise ValueError('Run '+names[index-1]+' first')
        if name in self.completed:raise ValueError('Step already completed. Rerun setup for a fresh experiment.')
        buffer=io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer):
                for i in STEPS[self.number][name]:
                    source=''.join(self.notebook['cells'][i]['source'])
                    filename=str(self.directory/f'cell_{i}.py')
                    linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
                    exec(compile(source,filename,'exec'),self.ns)
                if self.number=='10' and name=='probe':
                    from course.agent.chapter_worker import policy_probes
                    self.ns['policy_results']=policy_probes(self.work)
            self.completed.append(name)
        finally:
            text=buffer.getvalue()
            (self.directory/(name+'.log')).write_text(text)
            from IPython.display import HTML,display
            if text:display(HTML('<details><summary>Execution details · '+escape(name)+'</summary><pre style="white-space:pre-wrap">'+escape(text)+'</pre></details>'))
        print('Completed:',name)

    def finish(self):
        if self.completed!=list(STEPS[self.number]):raise ValueError('Complete every step first.')
        from course.agent.chapter_worker import summarize
        result=self.ns['policy_results'] if self.number=='10' else summarize(self.chapter,self.ns,self.work)
        (self.work/'lesson-summary.json').write_text(json.dumps(result,indent=2))
        missing=[p for p in CHAPTERS[self.chapter]['outputs'] if not (self.work/p).is_file()]
        if missing:raise ValueError('Missing artifacts: '+str(missing))
        self.parent.mkdir(parents=True,exist_ok=True)
        (self.parent/'latest.json').write_text(json.dumps({'work':str(self.work),'chapter':self.chapter,'status':'PASS'}))
        return result

    def read(self,name):
        return json.loads((self.work/name).read_text())


def table(headers, rows):
    from IPython.display import HTML,display
    header=''.join('<th style="padding:10px;text-align:left">'+escape(str(h))+'</th>' for h in headers)
    body=''.join('<tr>'+''.join('<td style="padding:10px;border-top:1px solid #dce5df;vertical-align:top;overflow-wrap:anywhere">'+escape(str(v))+'</td>' for v in row)+'</tr>' for row in rows)
    display(HTML('<table style="width:100%;table-layout:fixed;border-collapse:collapse;background:#f5f8f5;color:#25392c"><thead><tr>'+header+'</tr></thead><tbody>'+body+'</tbody></table>'))


def bars(values, maximum=None):
    from IPython.display import HTML,display
    maximum=maximum or max(values.values()) or 1
    html=''
    for label,value in values.items():
        html+='<div style="margin:14px 0"><b>'+escape(str(label))+f' · {value:.3f}</b><div style="height:24px;background:#e2e8e2;border-radius:5px"><div style="height:100%;background:#76b900;width:{max(0,min(100,100*value/maximum))}%"></div></div></div>'
    display(HTML(html))


def loss_chart(history):
    from IPython.display import HTML,display
    vals=[r['loss'] for r in history];low=min(vals);high=max(vals);span=high-low or 1
    points=' '.join(f'{40+600*i/max(1,len(vals)-1):.1f},{180-140*(v-low)/span:.1f}' for i,v in enumerate(vals))
    display(HTML('<svg viewBox="0 0 700 230" role="img" aria-label="Measured training loss by update" style="max-width:800px;background:#f5f8f5">'
        '<path d="M40 25 V180 H650" fill="none" stroke="#52675b"/>'
        f'<polyline points="{points}" fill="none" stroke="#5e9700" stroke-width="3"/>'
        f'<text x="45" y="20">Training loss: {high:.3f} to {low:.3f} (axis range)</text>'
        f'<text x="40" y="210">Update 1</text><text x="570" y="210">Update {len(vals)}</text></svg>'))


def show_skill_library(chapter):
    from IPython.display import HTML,display
    names=['workshop-model-inventory']+[s['skill'] for name,s in CHAPTERS.items() if name<=chapter]
    table(['Notebook','Skill'],[(i+1,name) for i,name in enumerate(names)])
    spec=CHAPTERS[chapter]
    for name in [spec['skill']]+spec.get('supporting_skills',[]):
        text=(ROOT/'course/agent/skills'/name/'SKILL.md').read_text()
        display(HTML('<details><summary>Read '+escape(name)+'/SKILL.md</summary><pre style="white-space:pre-wrap">'+escape(text)+'</pre></details>'))
