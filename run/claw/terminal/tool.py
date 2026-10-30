"""Narrow workshop CLI tool: recorded observation and validated specialist output."""
import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from course.common import chat
from run.workshop.workshop_agent.contracts import RULES_PROMPT,validate_item
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('action',choices=['describe','triage'])
parser.add_argument('clip',choices=['civil-market','sample-drone-bridge','degraded-mountain-fog'])
args=parser.parse_args()
observation=(ROOT/'run/chain/descriptions'/f'{args.clip}.txt').read_text()
result={'clip':args.clip,'source':'recorded VSS observation','source_count':1,'observation':observation,'released':False}
if args.action=='triage':
    item=json.loads(chat('specialist',[{'role':'system','content':RULES_PROMPT},
                                     {'role':'user','content':observation}],json_output=True))
    result.update(item=item,gate=validate_item(item,source_count=1))
print(json.dumps(result,indent=2))
