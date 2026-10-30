"""Validate canonical notebooks; optionally execute their manual walkthroughs.

OpenClaw TUI cells require presenter interaction and are never auto-launched here.
"""
import argparse
import json
import os
from pathlib import Path
import nbformat


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--notebook',help='Notebook filename, e.g. 04-train-adapter.ipynb')
    parser.add_argument('--execute-manual',action='store_true',help='Run manual cells against local services; skip TUI handoff')
    parser.add_argument('--offline',action='store_true',help='Structural checks only (no model or tool calls)')
    args=parser.parse_args()
    if args.offline and args.execute_manual:parser.error('--offline cannot execute live manual cells')
    root=Path(__file__).resolve().parents[2]
    kernel_paths=[str(root/'.workshop/jupyter/share/jupyter'), str(root/'demo/.venv/share/jupyter')]
    if os.environ.get('JUPYTER_PATH'):kernel_paths.append(os.environ['JUPYTER_PATH'])
    os.environ['JUPYTER_PATH']=os.pathsep.join(kernel_paths)
    paths=[root/'course'/args.notebook] if args.notebook else sorted((root/'course').glob('*.ipynb'))
    destination=root/'course/outputs/validation';destination.mkdir(parents=True,exist_ok=True)
    results=[]
    for path in paths:
        result={'notebook':path.name,'mode':'manual' if args.execute_manual else 'structural',
                'agent_execution':'not tested by this command; use the interactive TUI'}
        try:
            notebook=nbformat.read(path,as_version=4);nbformat.validate(notebook)
            for cell in notebook.cells:
                if cell.cell_type=='code':compile(cell.source,str(path),'exec')
            if not notebook.metadata.get('course_walkthrough'):raise ValueError('Expected promoted course walkthrough')
            if args.execute_manual:
                from nbclient import NotebookClient
                os.environ['COURSE_LIVE']='1'
                notebook.cells=[c for c in notebook.cells if 'openclaw-tui' not in c.metadata.get('tags',[])]
                number=path.name[:2]
                checks={
                    '01':"assert base_response['model']=='base' and specialist_response['model']=='specialist'\nassert all(r['choices'][0]['finish_reason']=='stop' for r in (base_response,specialist_response))",
                    '02':"assert report['label_checks']=='PASS' and report['train_validation_overlap']==0",
                    '03':"assert saved['base_weights_unchanged'] and report['only_lora_trainable']",
                }
                notebook.cells.append(nbformat.v4.new_code_cell(checks.get(number,"assert isinstance(manual_result,dict) and manual_result"),metadata={'tags':['qa-only']}))
                NotebookClient(notebook,timeout=360,kernel_name=notebook.metadata.kernelspec.name,
                    resources={'metadata':{'path':str(path.parent)}}).execute()
                nbformat.write(notebook,destination/path.name)
            result['status']='PASS'
        except Exception as exc:result.update(status='FAIL',error=str(exc))
        results.append(result)
        print(path.name,result['status'],result.get('error','')[-1500:],flush=True)
    name=('manual' if args.execute_manual else 'structural')+('-'+Path(args.notebook).stem if args.notebook else '')+'.json'
    (destination/name).write_text(json.dumps(results,indent=2)+'\n')
    return 0 if all(r['status']=='PASS' for r in results) else 1


if __name__=='__main__':raise SystemExit(main())
