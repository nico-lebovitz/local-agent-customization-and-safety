# Workshop notebooks

**CPU training is for demonstration purposes only.** The tiny adapter and 12-parameter RL policy teach optimization mechanics; they do not train Lightning. Follow [train_lightning.py](scripts/train_lightning.py) and the optional GPU commands in [04](04-train-adapter.ipynb) for actual Lightning LoRA training. The optional section in [11](11-trace-and-improve.ipynb) explains how to build the full Gym/NeMo RL exercise. It identifies the environment, task/verifier implementation, trainer setup and evaluation still required; full GPU RL is not bundled or launched by Run All.

These eleven notebooks are the current course. Run the executable teaching cells in order, then paste the generated task into the OpenClaw TUI when prompted.

| Notebook | Walkthrough |
|---|---|
| [01 · Local models](01-local-model.ipynb) | Discover model IDs and send live API requests |
| [02 · Training data](02-training-data.ipynb) | Build examples, review model-generated wording, see the loss mask |
| [03 · Build LoRA](03-build-lora.ipynb) | Attach an adapter and compare ranks |
| [04 · Train](04-train-adapter.ipynb) | Train the small CPU adapter and inspect loss |
| [05 · Reload](05-attach-and-serve.ipynb) | Reload it and compare live Lightning answers |
| [06 · Evaluate](06-evaluate.ipynb) | Score actual answers, including poor results |
| [07 · Specialist tool](07-specialist-tool.ipynb) | Switchyard routes and application checks |
| [08 · Skills](08-agent-skills.ipynb) | Write and load task instructions |
| [09 · Agent loop](09-agent-loop.ipynb) | Example video, live decisions, Relay events and injected failure |
| [10 · Policy](10-openshell-policy.ipynb) | Test the existing sandbox’s access boundaries |
| [11 · Improve](11-trace-and-improve.ipynb) | Use Gym and RL to train a tiny plan-selection policy |

## Running the course

On a new machine, first follow the [fresh-Spark setup guide](../SPARK-SETUP.md). This course targets Linux ARM64 on a 128 GB DGX Spark. Then follow the environment and service prerequisites in the [repository README](../README.md). Use the **NATO course (PyTorch + PEFT)** Jupyter kernel. The video in 09 uses Jupyter’s file endpoint with the repository root as its root directory (the workshop server on port 8890).

Run each notebook’s manual steps first. At the terminal step, exit the previous TUI with `/exit`, run the preparation and launch cells, then paste only the generated task into OpenClaw. The terminal opens on the workshop computer’s desktop. After the agent finishes, return to Jupyter and run the results cell. Run All cannot complete that interactive handoff for you.

Manual and agent runs are separate experiments. Later manual lessons use the previous successful manual outputs; later TUI demos require earlier successful agent outputs. Preparation prints the run location, and the agent’s inspect tool reports its inputs. Existing output locations are retained so work completed during preview continues to be available.

OpenClaw uses Nano for lightweight orchestration. Tools call Lightning when needed. In 09, the tool runs a separate teaching loop whose controller is Lightning base. In 11, RL updates a 12-parameter CPU plan policy, not Lightning. The CPU adapter in 03–06 is distinct from the deployed specialist.

## Supporting implementation

The notebooks are the authored course files. `agent/`, `common.py`, `openshell/`, and the existing environments provide their runtime support; do not remove them. The manual notebooks contain the teaching implementation. JSON specifications under `agent/lessons/` remain the fixed agent recipes; editing manual cells does not modify those recipes. They are not duplicate notebooks in the course listing.

Output folders retain datasets, adapters, traces, and validation results needed by later lessons. They are not disposable preview material.

### Helper responsibilities

| Files | Responsibility |
|---|---|
| `common.py` | Repository paths, dataset reads, and checked model HTTP calls |
| `agent/training_data.py`, `lora_walkthrough.py` | Bulk dataset/display utilities and retained reference helpers; manual token masks and LoRA operations are in cells |
| `agent/notebook_support.py` | Manual artifact bookkeeping and isolated Gym process transport; no teaching algorithm dispatch |
| `agent/lesson_walkthrough.py`, `lessons/*.json` | Display utilities and retained fixed reference implementations |
| `agent/chapters.json`, `chapter_worker.py` | Chapter inputs/outputs, fixed lesson execution, and evidence checks |
| `agent/chapter_agent.py`, `chapter_terminal.py` | Host preparation, bounded action dispatch, and result collection |
| `agent/chapter_tool.py` | Sandbox-side action requests; sends action names to the host worker |
| `agent/notebook_agent.py`, `notebook_terminal.py`, `inventory_tool.py` | Notebook 01 model inventory, terminal setup, probes, and validation |
| `agent/run_remote.py`, `normalize_tool_output.mjs` | Noninteractive OpenClaw transport and normalization of a known launcher warning |
| `agent/runtime.py`, `routing_trace.py` | Bounded teaching loop, Switchyard calls, and Relay evidence |
| `agent/learning.py` | Launch the isolated Gym CPU training exercise and compare checkpoints |
| `openshell/launch.py`, `probe.py` | Require access probes before running the companion image's teaching loop |
| `scripts/train_lightning.py` | Optional dedicated-GPU training recipe; never runs through notebook Run All |
| `scripts/validate_notebooks.py`, `tests/` | Structural/manual validation and offline regression checks |

The OpenClaw process runs inside OpenShell. Chapter tools 02–11 request predefined
actions from a host worker; the CPU lesson itself runs on the host, outside the
sandbox. Notebook 10 probes the existing sandbox and prepares a student image;
it does not deploy that image. Both boundaries are explicit teaching choices.

Lesson JSON contains fixed executable code, not model-provided instructions. The manual notebook code is independently editable. Keep the fixed agent recipes and their artifact contracts stable when experimenting in manual cells.

## Concept SDKs and documentation

The versions below describe the checked-in environments, not the newest releases.
Use the lock files to reproduce this workshop. Links marked “current” can describe
newer APIs; the local configuration and locked packages describe the workshop implementation. Current documentation is conceptual background where its API differs; the Switchyard quickstart now teaches a development Rust API.

| Concept | Workshop version / implementation | Documentation and first exercise |
|---|---|---|
| Tokenization and causal language models | Transformers 5.19.0 | [Chat templates (current)](https://huggingface.co/docs/transformers/main/en/chat_templating); notebook 02 renders the actual model template |
| Low-rank adaptation | PEFT 0.21.2 | [Quick tour (current)](https://huggingface.co/docs/peft/main/en/quicktour); notebook 03 constructs `LoraConfig` and `get_peft_model` |
| Gradient-based training | PyTorch 2.14.1+cpu | [Optimization tutorial (current)](https://docs.pytorch.org/tutorials/beginner/basics/optimization_tutorial.html); notebook 04 updates only trainable adapter parameters |
| Adapter loading / serving | PEFT locally; separately provisioned compatible server | [vLLM LoRA serving (current)](https://docs.vllm.ai/en/latest/features/lora/); notebook 05 distinguishes local reload from the deployed specialist |
| Routing | Switchyard 0.3.0 | [TOML schema](https://nvidia-nemo.github.io/Switchyard/reference/toml_schema/) and [local Python wrapper](agent/routing_trace.py); notebook 07 uses fixed routes, not learned routing |
| Agent tracing | NeMo Relay 0.9.4 | [Versioned overview](https://docs.nvidia.com/nemo/relay/v0.9.4/about-nemo-relay/overview), [tool instrumentation](https://docs.nvidia.com/nemo/relay/v0.9.4/instrument-applications/instrument-tool-call); notebook 09 wraps tool calls |
| Agent skills | OpenClaw 2026.9.7; separate workshop Python skill consumer | [OpenClaw skills (current)](https://docs.openclaw.ai/tools/skills); notebook 08 creates Markdown task instructions |
| Sandbox policy | OpenShell 0.0.85 in the workshop deployment | [v0.0.85 source](https://github.com/NVIDIA/OpenShell/tree/v0.0.85) and [architecture (current)](https://docs.nvidia.com/openshell/about/architecture); notebook 10 tests the existing sandbox |
| Reward environment | NeMo Gym 0.6.0, isolated environment | [Versioned environment tutorials](https://docs.nvidia.com/nemo/gym/v0.6.0/environment-tutorials/); notebook 11 uses the local resource implementation |
| Policy optimization | Selected NeMo RL kernels at commit `9046a59790697d2779a4ead2d8394b4cbb74dca0` | [Full Gym/RL integration (nightly)](https://docs.nvidia.com/nemo/rl/nightly/design-docs/nemo-gym-integration.html); this course trains 12 logits, not the full upstream stack |
| Optional GPU training | Separate NeMo AutoModel 26.04 recipe | [26.04 ChatDataset API](https://docs.nvidia.com/nemo/automodel/v0.4/nemo-automodel/nemo_automodel/components/datasets/llm/chat_dataset); see [train_lightning.py](scripts/train_lightning.py), outside notebook Run All |
| Browser workflow | NeMo Agent Toolkit 1.9.0, browser environment only | [Migration notice](https://docs.nvidia.com/nemo/agent-toolkit/latest/resources/migration-guide.html); deprecated October 2026, end of life at the end of 2026 |

Environment pins: [course](requirements.lock), [browser](../run/workshop/requirements.lock).
The notebooks use raw HTTP for their OpenAI-compatible model calls; they do not
currently use the OpenAI Python SDK or OpenAI-hosted models.

## How the notebook helpers execute

Manual notebooks execute their model requests, masks, LoRA setup, optimizer updates, scoring, routes, skills, agent loop, probes, and rewards in visible code cells. Notebook 01 uses standard-library HTTP directly. Later lessons can reuse the already-taught HTTP helper while exposing the new operation being taught.

`NotebookRun` in [notebook_support.py](agent/notebook_support.py) copies prerequisites into a fresh `lesson.work` directory and publishes results only after the notebook's visible checks and required artifacts are present. It does not select lesson JSON cells or execute training/scoring logic. `finish(summary)` is artifact bookkeeping, not a model-quality score.

Notebook 11 defines `plan_library`, `verify_plan`, and `train_policy` in cells. `run_in_gym` exports those exact function definitions, records their parameters, and launches the isolated Gym interpreter. The saved `notebook-experiment.py` and `training.log` show what ran. Edits to those functions or the learning rate affect that manual experiment. NVIDIA's pinned numerical loss kernels remain imported.

**Manual edits do not change the agent reference run.** The OpenClaw task invokes a fixed recipe; it does not ingest edited notebook cells or reuse manual artifacts. Manual outputs feed later manual lessons, and verified agent outputs feed later agent lessons. Restart the kernel and run in order when comparing experiments.

The agent path is separate: OpenClaw receives the notebook's task, calls the
sandbox-side [chapter tool](agent/chapter_tool.py), and requests named actions.
The [host dispatcher](agent/chapter_agent.py) validates the action sequence and
launches the [worker](agent/chapter_worker.py). That worker runs fixed lesson code
and returns artifacts through the file transport. The model does not provide
arbitrary Python for execution. The chapter work runs **on the host**, outside
OpenShell; notebook 01 instead performs model-inventory probes from its sandbox.

Inspect, run, and check are prescribed stages. A successful artifact check means
the required evidence exists and meets its checks; it does not establish model
accuracy. Inspect raw responses, traces, and evaluation scores as well. Keep manual
and agent outputs separate when comparing experiments.

## NVIDIA source map

Start with [NVIDIA’s skills catalog](https://build.nvidia.com/skills), the [VSS blueprint card](https://build.nvidia.com/nvidia/video-search-and-summarization/blueprintcard), and the [DGX Spark VSS deployment guide](https://build.nvidia.com/spark/vss). These are discovery and deployment references; opening a catalog page does not install a skill or blueprint.

| Reference | What this course actually uses |
|---|---|
| [Lightning model card](https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b/modelcard) | NVFP4 tokenizer and separately provisioned base/specialist endpoints; optional [BF16 training checkpoint](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16) |
| [Nano FP8 model card](https://huggingface.co/nvidia/NVIDIA-Nemotron-Nano-9B-v2-FP8) | OpenClaw orchestration, separate from Lightning reasoning |
| [Pinned Relay skill](https://github.com/NVIDIA/skills/blob/ce1024dcf2de005dd7482c4ce95be5238d9db56c/skills/nemo-relay-instrument-calls/SKILL.md) | Copied into notebook 09’s workspace; provenance and checksum in [nvidia-skills.json](agent/nvidia-skills.json) |
| `nemo-automodel-recipe-development` in the [skills catalog](https://build.nvidia.com/skills) | Optional GPU-recipe review reference; not bundled or run by the CPU notebooks |
| [VSS documentation](https://docs.nvidia.com/vss) | Recorded descriptions in the course; optional external live service in the browser demo |

The current VSS blueprint card can name newer models than the workshop. Use the [deployment evidence checklist](../run/workshop/README.md#nvidia-video-blueprint-and-deployment-evidence) to identify the installed stack. Record checkpoint revisions, precision, server images, adapter hashes, and tokenizer revision; API aliases and cached metadata alone do not attest deployed weights. Workshop temperature 0 is a controlled comparison setting, not a claim to reproduce model-card benchmarks.

## Skills and training

The course uses three different things with similar names:

| Item | Where you use it |
|---|---|
| Workshop agent skills (`SKILL.md`) | OpenClaw follows the data, LoRA, training, evaluation, and trace-review instructions in `agent/skills/`. These are workshop-authored skills. |
| NVIDIA agent skills | Notebook 09 includes the upstream Relay instrumentation skill, pinned in [nvidia-skills.json](agent/nvidia-skills.json). No upstream NVIDIA training skill is bundled. |
| NeMo Skills | NVIDIA's [data generation, evaluation, and training project](https://github.com/NVIDIA-NeMo/Skills). This is a separate software pipeline, not the Markdown skill loader. It is not used by the current notebook training runs. |

In notebook 04, ask OpenClaw to use `workshop-train-adapter` with the task printed
by the notebook. Follow its three tool calls: inspect inputs, train the adapter,
and check the saved results. The skill directs the work; PEFT and PyTorch perform
the 40 CPU updates in the host worker. Inspect the loss and saved adapter before
accepting the agent's summary.

Notebook 11 uses `workshop-review-trace` to inspect a failure and run the small
Gym/RL experiment. Gym supplies rewards and the selected NeMo RL kernels compute
the loss. This does not invoke the NeMo Skills training pipeline.

For a separate GPU exercise, review NVIDIA's
[AutoModel recipe-development skill](https://github.com/NVIDIA/skills/blob/main/skills/nemo-automodel-recipe-development/SKILL.md)
alongside [train_lightning.py](scripts/train_lightning.py). The script uses
AutoModel's `ChatDataset` with a local Transformers/PEFT loop; it does not launch
the full AutoModel distributed trainer. An appropriate agent task is:

> Review this training script and its dataset contract using the AutoModel
> recipe-development skill. Identify the model checkpoint, label alignment,
> adapter targets, validation split, and hardware requirements. Propose a recipe
> and a data-only check. Do not start training or alter the serving deployment.

This is an optional review exercise, not an installed training integration.
Select and record the upstream skill revision and a compatible AutoModel release
before running it. The course's working CPU exercise remains available without
GPU training infrastructure.

## Optional NIM adapter serving

[Notebook 05](05-attach-and-serve.ipynb) includes a Markdown-only NIM deployment example: adapter directory layout, profile selection, `NIM_PEFT_SOURCE`, model discovery, and a Chat Completions request. It cites [NVIDIA NIM 2.1.4 LoRA documentation](https://docs.nvidia.com/nim/large-language-models/2.1.4/advanced-use-cases/finetune-lora.html). Run All never starts NIM. Use an adapter matching a supported base model and profile; the CPU GPT-2 adapter cannot be attached to Lightning. NIM support for the workshop Lightning adapter is not asserted or tested.

## Evaluation references

Notebook 06 shows the scoring and evaluation loops as executable cells. Its [fixed agent recipe](agent/lessons/06-evaluate.json) remains separate.
For a larger benchmark, see NeMo Evaluator's
[custom benchmark tutorial](https://docs.nvidia.com/nemo/evaluator/tutorials/byob).
The three course cases are smoke tests, not enough to establish model quality.

## Validation

From the repository root:

```bash
# No inference or tool execution:
course/.venv/bin/python course/scripts/validate_notebooks.py

# Execute manual walkthroughs in order, without launching TUI windows:
course/.venv/bin/python course/scripts/validate_notebooks.py --execute-manual

# Check a single notebook:
course/.venv/bin/python course/scripts/validate_notebooks.py --notebook 09-agent-loop.ipynb
```

The validator does not claim agent execution passed. Run the TUI handoff and its evidence check to validate the agent. `--offline` means structural validation only. Lesson JSON files remain fixed agent reference recipes; manual checks execute the notebook cells themselves. Saved outputs and obsolete agent appendices are excluded.
