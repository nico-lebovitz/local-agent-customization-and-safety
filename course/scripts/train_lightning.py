"""Dedicated-GPU reproduction recipe. Never launched by notebook Run All.

Uses the repo's ChatDataset pre-shifted label contract, with explicit verification.
Requires the existing nemo-automodel:26.04 training environment and a local BF16 snapshot.
"""
import argparse
import json
import random
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--train', type=Path, required=True)
    parser.add_argument('--validation', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--steps', type=int, default=20)
    parser.add_argument('--accumulation', type=int, default=8)
    parser.add_argument('--lr', type=float, default=2e-4)
    parser.add_argument('--seed', type=int, default=1111)
    parser.add_argument('--check-data-only', action='store_true', help='Validate cached tokenizer and label alignment without loading weights')
    args = parser.parse_args()
    if not args.base.is_dir():
        parser.error('--base must be an existing local BF16 snapshot')
    if args.output.exists():
        parser.error('Choose a new output directory; existing adapters are never overwritten')
    if args.steps < 1 or args.accumulation < 1:
        parser.error('steps and accumulation must be positive')
    import torch
    import torch.nn.functional as F
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import LoraConfig, get_peft_model
    from nemo_automodel.components.datasets.llm.chat_dataset import ChatDataset
    torch.manual_seed(args.seed)
    random.seed(args.seed)
    tokenizer = AutoTokenizer.from_pretrained(args.base, local_files_only=True, trust_remote_code=True)
    train = ChatDataset(path_or_dataset_id=str(args.train), tokenizer=tokenizer)
    validation = ChatDataset(path_or_dataset_id=str(args.validation), tokenizer=tokenizer)
    def tensors(example):
        ids = torch.tensor(example['input_ids'], device='cuda').unsqueeze(0)
        labels = torch.tensor(example['labels'], device='cuda').unsqueeze(0)
        if not (labels != -100).any():
            raise ValueError('Example has no supervised tokens')
        return ids, labels
    # Fail before loading weights if this dataset implementation changes its contract.
    for dataset in (train, validation):
        if not len(dataset):
            raise ValueError('Empty dataset')
        for index in range(min(12, len(dataset))):
            sample = dataset[index]
            ids, labels = list(sample['input_ids']), list(sample['labels'])
            positions = [i for i, label in enumerate(labels) if label != -100 and i+1 < len(ids)]
            if not positions or sum(labels[i] == ids[i+1] for i in positions)/len(positions) < 0.9:
                raise ValueError('Expected pre-shifted ChatDataset labels; inspect alignment')
    if args.check_data_only:
        print(json.dumps({'training_records':len(train),'validation_records':len(validation),
                          'pre_shifted_alignment':'PASS','weights_loaded':False}))
        return
    model = AutoModelForCausalLM.from_pretrained(args.base, local_files_only=True,
        trust_remote_code=True, dtype=torch.bfloat16, device_map='cuda')
    config = LoraConfig(r=32, lora_alpha=64, lora_dropout=0.05, bias='none',
        task_type='CAUSAL_LM', target_modules=['q_proj','k_proj','v_proj','o_proj','in_proj','out_proj'])
    model = get_peft_model(model, config)
    model.print_trainable_parameters()
    parameters = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(parameters, lr=args.lr, weight_decay=0.01)
    def loss_for(example):
        ids, labels = tensors(example)
        logits = model(ids).logits.float()
        # ChatDataset already shifted labels; do NOT shift logits/labels again.
        return F.cross_entropy(logits[0], labels[0], ignore_index=-100)
    def evaluate():
        model.eval()
        with torch.no_grad():
            values = [loss_for(validation[i]).item() for i in range(min(12,len(validation)))]
        return sum(values)/len(values)
    before = evaluate()
    args.output.mkdir(parents=True)
    with (args.output/'training.jsonl').open('w') as log:
        model.train()
        for step in range(args.steps):
            optimizer.zero_grad()
            losses = []
            for _ in range(args.accumulation):
                loss = loss_for(train[random.randrange(len(train))])
                (loss/args.accumulation).backward()
                losses.append(loss.item())
            norm = torch.nn.utils.clip_grad_norm_(parameters, 1.0)
            if not torch.isfinite(norm):
                raise ValueError('Non-finite gradient norm')
            optimizer.step()
            row = {'step': step, 'loss': sum(losses)/len(losses), 'gradient_norm': norm.item()}
            log.write(json.dumps(row)+'\n'); log.flush()
            print(row, flush=True)
    after = evaluate()
    model.save_pretrained(args.output)
    tokenizer.save_pretrained(args.output/'tokenizer')
    generations = []
    for i in range(min(3, len(validation))):
        example = validation[i]
        first = next(j for j,l in enumerate(example['labels']) if l != -100)
        prompt = torch.tensor(example['input_ids'][:first+1], device='cuda').unsqueeze(0)
        with torch.no_grad():
            output = model.generate(prompt, attention_mask=torch.ones_like(prompt),
                max_new_tokens=128, do_sample=False, pad_token_id=tokenizer.eos_token_id)
        generations.append(tokenizer.decode(output[0,prompt.shape[1]:], skip_special_tokens=True))
    import hashlib
    manifest = {k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()}
    manifest.update(validation_loss_before=before, validation_loss_after=after,
        validation_measure='mean example loss on first 12 validation records; diagnostic only',
        generations=generations, torch_version=torch.__version__)
    for key in ('train','validation'):
        manifest[key+'_sha256'] = hashlib.sha256(getattr(args,key).read_bytes()).hexdigest()
    (args.output/'run.json').write_text(json.dumps(manifest,indent=2)+'\n')

if __name__ == '__main__':
    main()
