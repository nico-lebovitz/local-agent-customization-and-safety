"""Small presentation helpers for the notebook 02.

Dataset definitions mirror the existing lesson; OpenClaw uses that lesson's fixed worker.
"""
import json
from pathlib import Path
from html import escape
from course.common import ROOT

ROUTES = {'civil_gathering':'CIMIC', 'bridge_damage':'J3-CURRENT-OPS',
          'humanitarian_convoy':'CIMIC'}
SYSTEM = ('Classify the observation. Return JSON with activity_type, sensor_quality, '
          'confidence, and routing. One source cannot establish CONFIRMED. '
          'DEGRADED or UNKNOWN sensor quality requires POSSIBLE.')
def make_label(activity, quality):
    return {'activity_type':activity, 'sensor_quality':quality,
            'confidence':'PROBABLE' if quality=='CLEAR' else 'POSSIBLE',
            'routing':ROUTES[activity]}
def make_record(observation, activity, quality):
    return {'messages':[{'role':'system','content':SYSTEM},
                        {'role':'user','content':observation},
                        {'role':'assistant','content':json.dumps(make_label(activity,quality))}]}


def build_examples():
    events = {
     'civil_gathering':['People gather around market stalls.', 'Residents queue beside food stalls.', 'Civilians browse an outdoor market.', 'Shoppers meet in the town square.'],
     'bridge_damage':['A bridge deck is visibly collapsed.', 'The bridge has a broken support.', 'A span of the bridge has fallen.', 'The bridge roadway has a large structural break.'],
     'humanitarian_convoy':['Aid trucks carry food to a relief camp.', 'Relief vehicles deliver blankets to a shelter.', 'Trucks marked for humanitarian aid transport drinking water.', 'Aid vehicles bring medical supplies to a relief centre.'],
    }
    training = []
    for activity, descriptions in events.items():
        for description in descriptions:
            for quality, wording in [('CLEAR','The image is clear.'),('DEGRADED','The image is degraded by fog.')]:
                observation = f'{description} {wording} Only one camera reports this; there is no independent corroboration.'
                training.append(make_record(observation,activity,quality))
    validation = [
     make_record('One clear camera shows families shopping among produce stalls. No second source is available.','civil_gathering','CLEAR'),
     make_record('A fog-degraded single camera shows a fractured bridge deck with a missing section. There is no corroboration.','bridge_damage','DEGRADED'),
     make_record('One clear camera observes aid lorries unloading food at an emergency shelter. No independent report corroborates this.','humanitarian_convoy','CLEAR'),
    ]
    return training, validation


def validate_example(row):
    messages = row['messages']
    assert [m['role'] for m in messages] == ['system','user','assistant']
    label = json.loads(messages[-1]['content'])
    assert label == make_label(label['activity_type'],label['sensor_quality'])


def save_examples(training, validation, directory):
    for row in training + validation:
        validate_example(row)
    train_text = [r['messages'][1]['content'] for r in training]
    val_text = [r['messages'][1]['content'] for r in validation]
    assert len(set(train_text)) == len(train_text), 'Duplicate training observations'
    assert not set(train_text) & set(val_text), 'Training/validation overlap'
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name, records in [('train', training), ('validation', validation)]:
        (directory / f'{name}.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
    return {'training_examples': len(training), 'validation_examples': len(validation),
            'duplicate_training_observations': 0, 'train_validation_overlap': 0,
            'label_checks': 'PASS', 'directory': str(directory)}


def show_pair(record):
    from IPython.display import HTML, display
    observation = escape(record['messages'][1]['content'])
    answer = escape(json.dumps(json.loads(record['messages'][2]['content']), indent=2))
    display(HTML('<div style="display:flex;gap:16px;flex-wrap:wrap">'
                 '<div style="flex:1;min-width:250px;padding:20px;background:#edf2ee;color:#25392c;border-radius:12px">'
                 '<b>Observation</b><p>'+observation+'</p></div>'
                 '<div style="flex:1;min-width:250px;padding:20px;background:#e2f1db;color:#25392c;border-radius:12px">'
                 '<b>Expected answer</b><pre>'+answer+'</pre></div></div>'))


def show_loss_mask(record):
    from IPython.display import HTML, display
    from transformers import AutoTokenizer
    from huggingface_hub import snapshot_download
    path = snapshot_download('nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4', local_files_only=True)
    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True, trust_remote_code=True)
    messages = record['messages']
    prefix = tokenizer.apply_chat_template(messages[:-1], tokenize=False, add_generation_prompt=True, enable_thinking=False)
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
    assert text.startswith(prefix)
    encoded = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
    labels = [token if end > len(prefix) else -100
              for token, (_,end) in zip(encoded['input_ids'],encoded['offset_mapping'])]
    display(HTML('<p><b>Gray: context, ignored by loss (−100).</b> '
                 '<b style="color:#327225">Green: answer, scored during training.</b></p>'
                 '<div style="white-space:pre-wrap;font:13px/1.8 monospace;padding:16px;border:1px solid #ccd8cc;border-radius:12px">'
                 '<span style="background:#eee;color:#555">'+escape(prefix)+'</span>'
                 '<span style="background:#d7edc9;color:#173f1b">'+escape(text[len(prefix):])+'</span></div>'))
    return {'context_tokens_ignored': labels.count(-100),
            'answer_tokens_scored': sum(x != -100 for x in labels)}
