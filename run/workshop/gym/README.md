# Gym + RL teaching experiment

**CPU training is for demonstration purposes only.** For actual Lightning supervised LoRA training, follow [train_lightning.py](../../../course/scripts/train_lightning.py) and [notebook 04](../../../course/04-train-adapter.ipynb). For the full Gym/NeMo RL exercise, follow the optional setup walkthrough in [notebook 11](../../../course/11-trace-and-improve.ipynb): task splits, Agent and Resources servers, trainer integration, GPU allocation and held-out evaluation. This requires additional implementation and a separate training environment; the twelve-logit CPU checkpoint cannot be loaded into Lightning.

This exercise trains a small CPU policy: 12 trainable logits choose one of four fixed tool plans for three request intents. It teaches the reward → group advantage → policy update loop. It does not train the Lightning adapter, production agent, or a language model.

## What runs

- **NeMo Gym 0.6.0**: an actual `SimpleResourcesServer` exposes `/verify`. Its verifier executes offline tool-state transitions, checks evidence dependencies and task-specific plan order, and returns reward 0 or 1. Calls use HTTP semantics through an in-process ASGI client; no separate daemon or Ray cluster is needed.
- **NeMo RL source kernels**: unchanged `calculate_baseline_and_std_per_prompt`, `masked_mean`, and `clipped_pg_actor_objective` functions from the commit in [vendor/manifest.json](vendor/manifest.json). Full upstream source and Apache license are retained. The loader extracts only those function definitions and verifies file hashes to avoid importing the distributed trainer's GPU dependencies.
- **PyTorch CPU**: samples fresh on-policy action groups, backpropagates the official policy-gradient loss and applies Adam updates. One update per sampled group means the importance ratio is initially one; clipping is inactive in this small run.

The local loop uses selected NeMo RL loss functions. It does not launch the distributed trainer.

## Reproduce

From `run/workshop/gym` (separate from the browser's Python 3.12 environment):

```bash
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python torch==2.14.1+cpu --index-url https://download.pytorch.org/whl/cpu
uv pip install --python .venv/bin/python -r requirements.lock --extra-index-url https://download.pytorch.org/whl/cpu
.venv/bin/python -m pytest -q test_demo.py
.venv/bin/python train_demo.py
```

The recorded seed-42 run performs 40 updates and 1,920 sampled episodes. `artifacts/demo.json` contains before/after policy probabilities, every training step, representative real rollouts from each step, package versions, source commit, checkpoint hashes, and limitations. `rollouts.jsonl` contains every sampled action, verifier transition, reward and advantage. `checkpoint.json` contains all trained weights. The workshop reads these through `GET /api/training-demo`; viewing the page never starts a training job.

Expected reward is computed by enumerating all 12 intent/plan combinations in this tiny environment. It is not a held-out performance claim. The environment has no visual perception, generative reasoning, text-quality judging, production tool execution, or OpenShell enforcement.

## Move from teaching to the production controller

1. Wrap the existing harness as a Gym Agent server and expose trusted task verification through a Resources server. Keep the trained Lightning specialist frozen while training the base controller.
2. Collect complete on-policy model conversations with response token IDs, sampled log probabilities, action masks and tool feedback. Current workshop traces alone are not sufficient training tensors.
3. Run the full NeMo RL training stack on an isolated GPU worker/checkpoint; budget room for training state and rollout generation. The CPU exercise adds no GPU workload.
4. Evaluate held-out tasks and review reward exploits before replacing the production controller. A successful finite teaching task does not validate the production workflow.

Official references: [Gym Resources servers](https://docs.nvidia.com/nemo/gym/v0.6.0/environment-tutorials/), [Gym external agents](https://docs.nvidia.com/nemo/gym/v0.6.0/agent-server/), [NeMo RL + Gym integration](https://docs.nvidia.com/nemo/rl/nightly/design-docs/nemo-gym-integration.html).

## How Relay supports the learning story

Section 5 links the real Relay failure in run
`dddb5bc4073b4d649ce1a1719abacd69` (triage before perception) to the
verifier's evidence-dependency rule. It then opens a separately sampled, rewarded
`skip_evidence` plan from the captured training run. The display reads the Relay
event UUID, actual Gym reward/advantage and policy probabilities directly from
the existing records.

This mapping is an engineering explanation of how observations inform test and
reward design. The captured CPU run did **not** ingest Relay logs or use them as
on-policy training data. Relay captures diagnostic evidence; Gym owns verification;
NeMo RL's numerical kernels drive the policy update. Production training still
requires policy token IDs, log probabilities and masks in addition to traces.

The notebook agent uses the workshop-authored `workshop-review-trace` skill to run this exercise. NeMo Skills is a separate project and is not part of this training path; see the [course skill map](../../../course/README.md#skills-and-training).
