# Agentic AI workshop

**Built for NVIDIA DGX Spark: Linux ARM64 (aarch64), GB10, 128 GB unified memory.** Other hardware is not validated for the full workshop. Start with the [fresh-Spark setup guide](SPARK-SETUP.md) for hardware/storage requirements, Docker/GPU setup, model downloads, Lightning specialist provisioning, Nano tool calling, OpenShell, UI and Jupyter. The [model-service launcher](scripts/model_services.py) provides `plan`, `preflight`, `start` and `check` commands. This fresh-machine path still needs an end-to-end qualification on a clean Spark.

**Training scope:** CPU training in notebooks 03–04 and 11 is for demonstration purposes only. Actual Lightning GPU fine-tuning follows [train_lightning.py](course/scripts/train_lightning.py), with environment requirements and commands in [notebook 04](course/04-train-adapter.ipynb). [Notebook 11](course/11-trace-and-improve.ipynb) documents the optional full Gym/NeMo RL exercise, including tasks, verifiers, trainer integration and held-out evaluation. These GPU paths are opt-in; they do not run with Run All.

Participant materials for the browser demo and eleven [course notebooks](course/README.md).
The manual notebooks expose executable API, training, evaluation, routing, and agent-loop code.
Notebook 05 also includes an optional, documented [NIM LoRA serving example](course/05-attach-and-serve.ipynb); it is not executed by Run All.
The examples use fictional observations to teach model specialization, tools, skills,
agent loops, sandbox policy, tracing, and a small CPU reinforcement-learning exercise.

## Quick start: browser demo

This release includes the newer workshop UI on **port 7861**.
Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run
from the repository root:

```bash
bash scripts/install.sh demo
bash scripts/start-demo.sh
```

Open **http://127.0.0.1:7861**. Recorded traces and training results can be explored
without model servers. The Run action makes live inference calls and needs the
Lightning service described below. Video playback requires separately supplied clips.
Stop the server with Ctrl-C. On a remote machine, forward port 7861 over SSH.

The root [requirements.txt](requirements.txt) includes the demo's pinned dependency
lock. The installer creates a Python 3.12 environment, syncs it, checks dependencies,
and verifies that the server imports. It can download Python and packages through uv.
Rerunning it synchronizes these project environments, removing packages outside
their locks. Preview commands without installing anything:

```bash
bash scripts/install.sh all --dry-run
```

## Install the course too

```bash
bash scripts/install.sh all
.workshop/jupyter/bin/python -m jupyterlab --config=scripts/jupyter_config.py \
  --ip=127.0.0.1 --port=8890 --ServerApp.port_retries=0 --ServerApp.root_dir="$PWD"
```

`all` installs the demo, course, Jupyter, and Gym environments and registers the
course kernel. `course` installs only the latter three. Open the printed Jupyter
login link, select **NATO course (PyTorch + PEFT)**, and start with notebook 01.
Live notebook sections require the services and model assets listed below.

## Start the existing workshop Spark

On the original, already-provisioned machine, use its original checkout:

```bash
bash scripts/workshop.sh preflight
bash scripts/workshop.sh up
bash scripts/workshop.sh links
```

`up` starts the existing Nano controller, Lightning base/specialist service,
OpenShell gateway, saved workshop sandboxes, UI on 7861, and Jupyter on 8890.
`up --live-video` additionally starts the configured VSS/Cosmos stack.
It does not install dependencies, create model containers, or open an OpenClaw TUI.
The launcher expects the original container identities, model adapter, and clips,
even when using recorded observations. Do not use it as a fresh-clone installer.
See the [lifecycle guide](scripts/README.md).

## Choose a starting point

- **Explore the browser demo:** follow [run/workshop/README.md](run/workshop/README.md).
  Recorded traces and training results are included; live task execution requires a model server.
- **Work through the notebooks:** follow [course/README.md](course/README.md) in order.
- **Operate the original workshop Spark:** see [scripts/README.md](scripts/README.md).
  Its lifecycle launcher manages an existing deployment and is not an installer.

## NVIDIA documentation, skills, and blueprints

The [course source map](course/README.md#nvidia-source-map) connects each integration to NVIDIA documentation and the exact local implementation. Browse [official NVIDIA agent skills](https://build.nvidia.com/skills); notebook 09 includes `nemo-relay-instrument-calls`, while `nemo-automodel-recipe-development` is an optional review reference. Workshop-specific skills are authored in this repository.

For video, see the [VSS blueprint on build.nvidia.com](https://build.nvidia.com/nvidia/video-search-and-summarization/blueprintcard), [DGX Spark VSS playbook](https://build.nvidia.com/spark/vss), and [NVIDIA VSS documentation](https://docs.nvidia.com/vss). Those pages describe upstream options, not proof of the installed workshop profile. The [demo deployment evidence guide](run/workshop/README.md#nvidia-video-blueprint-and-deployment-evidence) explains the required version and API records.

Model references: [Lightning NVFP4](https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b/modelcard), [Lightning BF16](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16), and [Nano 9B v2 FP8](https://huggingface.co/nvidia/NVIDIA-Nemotron-Nano-9B-v2-FP8). Record the deployed checkpoint revision and adapter hash separately from API model aliases. The course’s CPU adapter belongs to a different practice model.

## Services and assets

A clone contains source, synthetic datasets, recorded observations, and demo evidence.
It does not contain model weights, the deployed specialist adapter, video clips,
Python environments, credentials, or Docker/OpenShell state.

| Capability | Prerequisite |
|---|---|
| Recorded browser replay | Browser demo Python environment; no inference needed |
| Live demo and notebook API calls | OpenAI-compatible API at `127.0.0.1:8002`, exposing `base` and `specialist` |
| Notebook 02 token inspection | Cached tokenizer for `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4` |
| Notebooks 03–06 CPU adapter | Course environment; the tiny base is constructed locally |
| Deployed-adapter inspection and notebook 01 agent inventory | Local `train/adapters/jisr-lightning/`, BF16 and NVFP4 checkpoint cache metadata |
| OpenClaw handoffs and notebook 10 | Docker, OpenShell, Nano controller on `30081`, and the [terminal sandbox](run/claw/terminal/README.md) |
| Notebook 11 | Separate [Gym CPU environment](run/workshop/gym/README.md) |
| Optional live video | Configured VSS service on `8000` with the selected clips registered |

The serving model used in the workshop was NVIDIA Nemotron 3.5 Lightning 30B-A3B;
`specialist` is its deployed JISR LoRA adapter. Serving infrastructure and that
adapter must be provisioned separately. The CPU adapter built in the course cannot
be loaded into Lightning. A dedicated-GPU reproduction recipe is provided at
`course/scripts/train_lightning.py`; it requires a separate NeMo AutoModel environment.
The [fresh-Spark guide](SPARK-SETUP.md) and `scripts/model_services.py` now provide model-serving launch instructions. VSS remains an optional separate deployment.

The tested environments were Linux ARM64 on a Spark, Python 3.12 for the browser
server, and Python 3.14 for the CPU course and Gym environments. Lock files capture
those environments; installation on other platforms has not been verified.

## Provision services before running the course

The environment setup below installs notebook dependencies. Provision these
external services using the [fresh-Spark setup guide](SPARK-SETUP.md) before attempting the live exercises. The following summarizes their contracts:

1. Obtain the Lightning model/tokenizer and a compatible JISR adapter. Review the
   [vLLM LoRA serving guide](https://docs.vllm.ai/en/latest/features/lora/) for a
   serving implementation, including adapter compatibility and model aliases.
   Configure an OpenAI-compatible service on port 8002 with `base` and `specialist`.
   The optional [GPU training recipe](course/scripts/train_lightning.py) is a
   starting point for producing an adapter; it is not a tested fresh deployment
   installer. The tiny notebook adapter cannot replace this deployed adapter.
2. For agent handoffs, serve
   `nvidia/NVIDIA-Nemotron-Nano-9B-v2-FP8` on port 30081, then follow the
   [terminal sandbox setup](run/claw/terminal/README.md). It documents the Docker,
   OpenShell, OpenClaw, and host-bridge requirements. Compare upstream
   [OpenShell architecture](https://docs.nvidia.com/openshell/about/architecture)
   with the workshop's pinned configuration before upgrading.
3. Install the [separate Gym environment](run/workshop/gym/README.md) before 11.
   Install the [browser environment](run/workshop/README.md) only if using the
   browser demo. VSS and video clips are optional for the recorded-text course path.
4. Check the live API contract before opening notebook 01:

   ```bash
   curl --fail http://127.0.0.1:8002/v1/models
   curl --fail http://127.0.0.1:30081/v1/models
   ```

The first response must list both configured aliases; the second must list the
Nano controller ID. These discovery checks do not validate generation, adapter
quality, or sandbox access. Notebook 01 performs live requests, and notebook 10
checks sandbox boundaries. Inventory exercises also require the local checkpoint
metadata and deployed adapter paths listed above.

`COURSE_MODEL_URL` controls the course HTTP helper. Browser routing configuration
and sandbox host addresses are separate; changing this variable does not migrate
the whole system. See the [concept SDK map](course/README.md#concept-sdks-and-documentation)
for the versions and API scope used here.
The original-Spark lifecycle script starts an existing installation; a fresh
machine still needs the provisioning steps above. Fresh deployment on other
hardware has not been verified.

## Set up Jupyter and the course

With `uv` installed, run from the repository root:

```bash
uv venv course/.venv --python 3.14
uv pip sync --python course/.venv/bin/python course/requirements.lock --extra-index-url https://download.pytorch.org/whl/cpu
uv venv .workshop/jupyter --python 3.12
uv pip sync --python .workshop/jupyter/bin/python scripts/jupyter-requirements.lock
course/.venv/bin/python -m ipykernel install --prefix .workshop/jupyter \
  --name nato-course --display-name 'NATO course (PyTorch + PEFT)'
.workshop/jupyter/bin/python -m jupyterlab --config=scripts/jupyter_config.py \
  --ip=127.0.0.1 --port=8890 --ServerApp.port_retries=0 --ServerApp.root_dir="$PWD"
```

Select **NATO course (PyTorch + PEFT)** and open `course/01-local-model.ipynb`.
Keep the Jupyter login token private. For remote access, forward the ports:

```bash
ssh -L 7861:127.0.0.1:7861 -L 8890:127.0.0.1:8890 USER@WORKSHOP_HOST
```

Run the OpenClaw launcher printed by each notebook in a Jupyter terminal when no
local desktop is available. Paste the task manually, wait for completion, and then
collect the evidence in the notebook. Run All cannot perform that interaction.

## Repository map

| Path | Purpose |
|---|---|
| `course/*.ipynb` | Participant exercises |
| `course/agent/` | Lesson implementations, displays, skills, and OpenClaw transport |
| `course/openshell/` | Policy exercise image and probes |
| `run/workshop/` | Browser UI, NAT workflow, Switchyard routing, Relay traces, Gym exercise |
| `run/claw/terminal/` | OpenClaw sandbox image, policy, and terminal bridge |
| `run/chain/descriptions/` | Recorded observations used by demo and course |
| `train/data/`, `train/eval/`, `framework/` | Specialist datasets, contract, and recorded comparison evidence |
| `scripts/` | Jupyter configuration and original-Spark lifecycle helper |

Tests are retained beside their implementation. Notebook and runtime outputs are
ignored; included evaluation records are deliberate replay fixtures, not fresh-run results.
Third-party RL code and the Relay skill retain their licenses and pinned provenance.
