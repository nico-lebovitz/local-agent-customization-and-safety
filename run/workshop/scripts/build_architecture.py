"""Workshop adaptation of OpenShell Customer Deck (September 2026), slides 6/8.
Run from repo root: python3 run/workshop/scripts/build_architecture.py
Named boundary ports produce straight, aligned connectors with no box crossings.
"""
from pathlib import Path
from html import escape
OUT=Path(__file__).resolve().parents[1]/'static/architecture.svg'
nodes={
 'learning':(1120,120,295,110,'Learning tools + skills',['Evaluate behavior · NeMo Gym','Improve policy · NeMo RL','Target skills · gated training jobs'],'planned'),
 'input':(45,35,175,90,'Inputs',['Prompt / CLI'],'input'),
 'gateway':(45,410,175,90,'Gateway',['Session + lifecycle'],'trusted'),
 'agent':(310,275,260,360,'Agent harness',[],'core'),
 'tool_policy':(685,290,310,90,'Tool access',['Supervisor: endpoint + process','Allowed API methods / paths'],'trusted'),
 'model_policy':(685,410,310,90,'Model access',['Supervisor: inference endpoint','Provider permissions'],'trusted'),
 'file_policy':(685,530,310,90,'Filesystem access',['Read-only inputs / configuration','Write: outputs + temporary files'],'trusted'),
 'tools':(1120,265,295,140,'Agent tools',['perceive · observation','triage · specialist + validation','draft · prepare report','request_review · hold'],''),
 'models':(1120,410,295,90,'Models',['Switchyard task routing','Lightning base / Lightning + LoRA'],''),
 'data':(1120,530,295,90,'Mounted data',['Observations · rules · configuration','Captured execution records'],''),
 'prover':(685,670,310,70,'Policy Prover',['Check proposed policy changes'],'trusted'),
}
edges=[('tools','top','learning','bottom','planned-edge'),('input','bottom','gateway','top','flow'),('gateway','right','agent','left','flow'),
 ('agent','tool','tool_policy','left','flow'),('agent','model','model_policy','left','flow'),('agent','data','file_policy','left','flow'),
 ('tool_policy','right','tools','left','network'),('model_policy','right','models','left','network'),('file_policy','right','data','left','network')]
def port(name,side):
 x,y,w,h,*_=nodes[name]
 ports={'left':(x,y+h/2),'right':(x+w,y+h/2),'top':(x+w/2,y),'bottom':(x+w/2,y+h)}
 if name=='agent':ports.update(tool=(x+w,335),model=(x+w,455),data=(x+w,575))
 return ports[side]
parts=['''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1460 880" role="img" aria-labelledby="title desc">
<title id="title">NVIDIA OpenShell: workshop architecture, adapted from Customer Deck slides 6 and 8</title>
<desc id="desc">Inputs enter the OpenShell gateway, then the agent harness inside its own sandbox. Three independent outward access lanes connect the harness to tools and skills, models, and mounted data through OpenShell policy controls outside the agent sandbox. The outer OpenShell boundary contains the gateway, sandbox, enforcement layer and policy prover. This is an intended logical access design, not a claim of deployed sandbox enforcement.</desc>
<rect width="1460" height="880" fill="#10171a"/>
<defs><marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L10 5L0 10Z" fill="#b8eb59"/></marker><marker id="blue" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L10 5L0 10Z" fill="#88c9f1"/></marker></defs>
<style>svg{background:#10171a;font-family:Arial,sans-serif}.box{fill:#182328;stroke:#44544e;stroke-width:1.5}.core{fill:#23331c;stroke:#8db95c}.trusted{fill:#162b38;stroke:#6999b5}.input{fill:#29261b;stroke:#b4a05b}.title{fill:#eef3ed;font-size:20px;font-weight:600}.sub{fill:#b1bdb7;font-size:14px}.label{fill:#b8eb59;font-size:13px;letter-spacing:1.1px}.note{fill:#b1bdb7;font-size:13px}.flow,.network{fill:none;stroke:#b8eb59;stroke-width:2;marker-end:url(#arrow)}.network{stroke:#88c9f1;marker-end:url(#blue)}.planned{stroke:#88c9f1;stroke-dasharray:5 4}.planned-edge{fill:none;stroke:#88c9f1;stroke-width:2;stroke-dasharray:5 4;marker-end:url(#blue)}.port{fill:#b8eb59;font-size:12px}</style>
<text x="310" y="64" class="label">NVIDIA AGENT TOOLKIT / WORKSHOP ARCHITECTURE</text>
<text x="310" y="97" class="title">Govern the agent. Connect its capabilities.</text>
<rect x="20" y="175" width="1030" height="620" rx="18" fill="#142018" stroke="#8db95c" stroke-width="2"/>
<text x="280" y="215" class="label">NVIDIA OPENSHELL / SECURE RUNTIME BOUNDARY</text>
<rect x="280" y="240" width="320" height="430" rx="14" fill="none" stroke="#b1bdb7" stroke-dasharray="7 6"/>
<text x="305" y="263" class="label">AGENT SANDBOX</text>
<text x="685" y="263" class="label">PRIVILEGED POLICY CONTROLS</text>
<text x="1120" y="105" class="label">CONNECTED CAPABILITIES</text>
<text x="305" y="705" class="note">Relay instruments the agent loop.</text>
<text x="305" y="730" class="note">Traces are captured as run records.</text>
<rect x="21" y="755" width="1028" height="39" rx="12" fill="#b8eb59"/>
<text x="535" y="782" text-anchor="middle" fill="#172011" font-size="19" font-weight="600">NVIDIA OpenShell</text>
<text x="20" y="832" class="note">Based on Customer Deck slides 6 + 8. Network access is supervisor-mediated; mounted files use filesystem controls.</text>
<text x="20" y="858" class="note">Target architecture · recorded training example. Dashed learning skills are proposed; four operational tools are registered.</text>
''']
for a,sa,b,sb,kind in edges:
 p,q=port(a,sa),port(b,sb)
 assert p[0]==q[0] or p[1]==q[1],(a,b,'connector must be straight')
 for name,(x,y,w,h,*_) in nodes.items():
  if name in (a,b):continue
  if p[0]==q[0]:assert not(x<p[0]<x+w and max(min(p[1],q[1]),y)<min(max(p[1],q[1]),y+h)),(a,b,name)
  else:assert not(y<p[1]<y+h and max(min(p[0],q[0]),x)<min(max(p[0],q[0]),x+w)),(a,b,name)
 parts.append(f'<path class="{kind}" data-from="{a}" data-to="{b}" d="M{p[0]} {p[1]} L{q[0]} {q[1]}"/>')
for name,(x,y,w,h,title,lines,kind) in nodes.items():
 parts.append(f'<g id="{name}"><rect class="box {kind}" x="{x}" y="{y}" width="{w}" height="{h}" rx="9"/>')
 if name=='agent':
  parts.append('''<text x="334" y="385" class="title">Agent harness</text><text x="334" y="413" class="sub">Observe → reason → act</text><text x="334" y="497" class="sub">Prompt + working state</text><text x="334" y="523" class="sub">Evidence + tool results</text><text x="547" y="328" text-anchor="end" class="port">TOOLS</text><text x="547" y="448" text-anchor="end" class="port">INFERENCE</text><text x="547" y="568" text-anchor="end" class="port">FILES</text>''')
 else:
  parts.append(f'<text class="title" x="{x+17}" y="{y+28}">{escape(title)}</text>')
  for i,line in enumerate(lines):parts.append(f'<text class="sub" x="{x+17}" y="{y+53+i*20}">{escape(line)}</text>')
 parts.append('</g>')
parts.append('</svg>');OUT.write_text('\n'.join(parts))
print(f'Built {OUT.name}: {len(nodes)} nodes, {len(edges)} aligned connectors; no box crossings')
