"""CPU LoRA demonstration and compact visual summaries; no model download."""
from html import escape
from pathlib import Path
import torch
from transformers import GPT2Config, GPT2LMHeadModel
from peft import LoraConfig, get_peft_model

TARGETS = ['c_attn', 'c_proj', 'c_fc']


def make_base():
    torch.set_num_threads(2)
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(17)
        return GPT2LMHeadModel(GPT2Config(
            vocab_size=258, n_positions=768, n_embd=48, n_layer=1, n_head=2,
            bos_token_id=1, eos_token_id=1, pad_token_id=0))


def attach_adapter(base, rank=8):
    config = LoraConfig(r=rank, lora_alpha=rank*2, lora_dropout=0.0,
                        bias='none', task_type='CAUSAL_LM', target_modules=TARGETS,
                        fan_in_fan_out=True)
    return get_peft_model(base, config)


def parameter_report(model):
    named = list(model.named_parameters())
    trainable = [(n,p) for n,p in named if p.requires_grad]
    assert trainable and all('lora_' in n for n,p in trainable)
    total = sum(p.numel() for _,p in named)
    count = sum(p.numel() for _,p in trainable)
    return {'total_parameters': total, 'frozen_parameters': total-count,
            'trainable_adapter_parameters': count, 'trainable_percent': round(100*count/total,2),
            'only_lora_trainable': True,
            'adapter_matrices': [{'name': n, 'shape': list(p.shape), 'parameters': p.numel()}
                                 for n,p in trainable]}


def show_parameters(model):
    from IPython.display import HTML, display
    report = parameter_report(model)
    percent = report['trainable_percent']
    display(HTML('<div style="padding:20px;border:1px solid #cbd8cd;border-radius:12px;color:#25392c;background:#f5f8f5">'
        f'<b>Frozen base: {report["frozen_parameters"]:,}</b> &nbsp; | &nbsp; '
        f'<b>Trainable adapter: {report["trainable_adapter_parameters"]:,} ({percent}%)</b>'
        '<div style="display:flex;height:28px;margin:16px 0;background:#ccc;border-radius:6px;overflow:hidden">'
        f'<div style="width:{100-percent}%;background:#a8b4ae"></div>'
        f'<div style="width:{percent}%;background:#76b900"></div></div>'
        '<span>Gray = frozen weights. Green = weights training can update.</span></div>'))
    return report


def compare_ranks(ranks=(4,8,16)):
    from IPython.display import HTML, display
    rows=[]
    for rank in ranks:
        report=parameter_report(attach_adapter(make_base(), rank))
        rows.append({'rank': rank, 'trainable_parameters': report['trainable_adapter_parameters'],
                     'trainable_percent': report['trainable_percent']})
    maximum=max(row['trainable_parameters'] for row in rows)
    body=''
    for row in rows:
        body+=f'<tr><td style="padding:12px">Rank {row["rank"]}</td><td style="padding:12px">{row["trainable_parameters"]:,}</td>'
        body+=f'<td style="width:55%"><div style="height:22px;background:#76b900;width:{100*row["trainable_parameters"]/maximum}%"></div></td></tr>'
    display(HTML('<table style="width:100%;text-align:left"><tr><th>Rank</th><th>Trainable parameters</th><th>Relative adapter size</th></tr>'+body+'</table>'))
    return rows


def save_setup(model, directory):
    """Save a matching unadapted base and adapter recipe; no training performed."""
    directory=Path(directory)
    base=make_base()
    underlying=model.get_base_model()
    for name,value in base.state_dict().items():
        adapted_name=name
        for target in TARGETS:
            for suffix in ('weight','bias'):
                if name.endswith('.'+target+'.'+suffix):
                    adapted_name=name[:-len(suffix)]+'base_layer.'+suffix
        assert torch.equal(value,underlying.state_dict()[adapted_name]), 'Base weights changed: '+name
    base.save_pretrained(directory/'base')
    model.peft_config['default'].save_pretrained(directory/'adapter-config')
    return {'base':str(directory/'base'), 'adapter_config':str(directory/'adapter-config/adapter_config.json'),
            'base_weights_unchanged':True, 'training_performed':False}
