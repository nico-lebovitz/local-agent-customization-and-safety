# Set up the workshop on a fresh DGX Spark

This workshop is built for **Linux ARM64 (aarch64) on NVIDIA DGX Spark**. The reference deployment uses GB10 and 128 GB unified memory. Use a 128 GB Spark for reproducing this two-model setup; 64 GB variants, x86 PCs, Windows and macOS have not been validated for this workshop. A laptop can connect to the Spark through SSH and a browser.

The existing deployment has run the course successfully. The fresh-machine procedure and launcher below have been checked against its configuration, but have **not yet been tested end to end on a wiped Spark**. Model download access and a compatible specialist adapter are required; a Git clone alone does not supply them.

## Hardware and software requirements

| Requirement | Workshop target |
|---|---|
| Host | DGX Spark, GB10, ARM64, 128 GB unified memory, supported DGX OS |
| Storage | Plan for at least 200 GB free SSD space for inference models, container layers and environments; allow more for the BF16 training checkpoint, checkpoints and optional VSS. This is a planning allowance, not a measured minimum. |
| GPU software | Working NVIDIA driver, Docker Engine and NVIDIA Container Toolkit configured for Docker |
| Host utilities | Git, curl, Python 3, uv; the installer downloads Python 3.12/3.14 environments |
| Access | Internet access to GitHub, package indexes, Hugging Face and NVIDIA NGC; accounts/tokens if an artifact requires authentication |
| Optional assets | Authorized video clips; VSS deployment only for live video analysis |

See NVIDIA's [Spark serving playbook](https://build.nvidia.com/spark/vllm) for hardware-specific inference guidance and [Container Toolkit installation](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) for the Docker GPU runtime. CPU training in the notebooks is for demonstration purposes only; GPU training needs its own memory budget and environment.

## 1. Prepare the host and clone

Run the Spark's first-boot/OS setup and install available supported driver updates. Install Git, curl and Python 3 through the OS package manager if absent:

```bash
sudo apt-get update
sudo apt-get install -y git curl python3
```

Install Docker Engine using the [Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/), selecting ARM64 packages. Follow NVIDIA's Container Toolkit guide above, including runtime configuration and the Docker restart. If Docker is already supplied by DGX OS, verify it before reinstalling. Configure Docker access for your user, then log in again if group membership changed. Check:

```bash
uname -m                         # aarch64
nvidia-smi                      # the GB10 is visible
docker info                    # must work as the current user
```

Install uv using its [official installer](https://docs.astral.sh/uv/getting-started/installation/), then open a new shell:

```bash
curl -LsSf https://astral.sh/uv/install.sh -o /tmp/workshop-install-uv.sh
sh /tmp/workshop-install-uv.sh
```

```bash
git clone https://github.com/nico-lebovitz/agent-customization-and-safety.git
cd agent-customization-and-safety
bash scripts/install.sh all --dry-run
bash scripts/install.sh all
uv tool install huggingface_hub
uv tool update-shell
```

Reopen the shell if `hf` is not found. These commands install the browser, course, Jupyter and CPU Gym environments. They do not provision GPU services. Use a repository revision containing this guide and `scripts/model_services.py`; unpublished local changes are not available to another clone.

## 2. Download model assets

Use the same user and Hugging Face cache for downloads, the launcher and Jupyter. The default is `~/.cache/huggingface/hub`; if you change it, export `HF_HUB_CACHE` consistently. Do not use `--local-dir` for model snapshots: notebook 01 inspects the normal cache layout. Run `hf auth login` if access requires it and accept any applicable model terms. Never put tokens in committed files.

```bash
hf download nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4
hf download nvidia/NVIDIA-Nemotron-Nano-9B-v2-FP8
# Notebook 01 also inspects BF16 checkpoint metadata; this does not download weights.
hf download nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16 --include config.json
hf download nvidia/NVIDIA-Nemotron-Nano-9B-v2 \
  nemotron_toolcall_parser_no_streaming.py --local-dir .workshop/models
sha256sum .workshop/models/nemotron_toolcall_parser_no_streaming.py
```

Record the resolved snapshot revisions printed by `hf` and the parser hash. For repeatable distribution, add `--revision COMMIT` to each command using the recorded revision; `main` can change. The Nano parser is Python code loaded by vLLM: use the NVIDIA source linked above and review/version it with the deployment. Model references: [Lightning](https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b/modelcard), [Nano FP8](https://huggingface.co/nvidia/NVIDIA-Nemotron-Nano-9B-v2-FP8), [NVIDIA parser source](https://huggingface.co/nvidia/NVIDIA-Nemotron-Nano-9B-v2/blob/main/nemotron_toolcall_parser_no_streaming.py).

## 3. Supply or train the Lightning specialist adapter

The `specialist` endpoint must load a real Lightning-compatible LoRA adapter. Obtain the workshop adapter from your organizer, with checkpoint provenance and a checksum, and place its files at:

```text
train/adapters/jisr-lightning/adapter_config.json
train/adapters/jisr-lightning/adapter_model.safetensors
```

No public download for this workshop adapter is bundled. Do not create the `specialist` alias as another name for the base model or use the CPU GPT-2 practice adapter: either would invalidate the exercise. The serving recipe supports LoRA rank up to 32. Check the adapter's base checkpoint, target modules and provenance; rank alone does not establish compatibility.

If you do not have the adapter, reproduce a candidate with [train_lightning.py](course/scripts/train_lightning.py) and [notebook 04](course/04-train-adapter.ipynb). This trains actual Lightning; it is separate from CPU Run All. Download the full BF16 snapshot first:

```bash
hf download nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16
docker pull nvcr.io/nvidia/nemo-automodel:26.04
```

Use `docker login nvcr.io` if NGC requires authentication, following [NVIDIA NGC guidance](https://docs.nvidia.com/ngc/gpu-cloud/ngc-user-guide/index.html). Allocate the GPU to training before starting the inference containers. Set the resolved BF16 snapshot path **inside** the mounted cache, replacing `REVISION`:

```bash
export LIGHTNING_BASE=/hf/hub/models--nvidia--NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16/snapshots/REVISION
export WORKSHOP_HUB_CACHE="${HF_HUB_CACHE:-${HF_HOME:-$HOME/.cache/huggingface}/hub}"
docker run --rm --gpus all --ipc=host \
  --mount "type=bind,src=$WORKSHOP_HUB_CACHE,dst=/hf/hub" \
  --mount "type=bind,src=$PWD,dst=/workspace" \
  -w /workspace -e HF_HOME=/hf --entrypoint python \
  nvcr.io/nvidia/nemo-automodel:26.04 course/scripts/train_lightning.py \
  --base "$LIGHTNING_BASE" --train train/data/jisr/train.jsonl \
  --validation train/data/jisr/val.jsonl \
  --output train/adapters/jisr-lightning --check-data-only
```

After the data check passes, rerun that command replacing `--check-data-only` with `--steps 20 --accumulation 8 --lr 2e-4 --seed 1111`. The output directory must not already exist. The recipe requires compatible Transformers, PEFT and NeMo AutoModel packages in the image; inspect any import/model compatibility failure rather than substituting the course CPU environment. This is the reference training image, not a newly validated clean training deployment. Inspect `run.json`, losses and generations, then evaluate the candidate with notebook 06. A short reproduction run need not match the organizer's trained adapter quality.

## 4. Start the model services

The new launcher uses distinct names, `workshop-lightning` and `workshop-nano`, and the inspected reference image tags. It does not replace or stop any existing service. It checks ARM64, Docker/GPU visibility, occupied ports, model snapshot presence and adapter/parser files before starting either container. Snapshot presence alone cannot prove every shard was downloaded; complete step 2 and inspect startup logs.

```bash
python3 scripts/model_services.py plan
python3 scripts/model_services.py preflight
# Pull ahead of time to catch registry/authentication problems.
docker pull vllm/vllm-openai:v0.27.1
docker pull nvcr.io/nvidia/vllm:25.12.post1-py3
```

For a notebook-only host, the default binds APIs to loopback. For the full OpenShell exercise, sandbox traffic must reach the host ports through `host.openshell.internal`. Use the following on a trusted, network-restricted Spark:

```bash
python3 scripts/model_services.py start --bind 0.0.0.0
```

Binding all interfaces exposes unauthenticated model APIs on 8002 and 30081. Restrict access at the host/network boundary while allowing OpenShell's bridge traffic; Docker-published ports need Docker-aware firewall rules, not just an assumed UFW default. Do not expose these ports to the public Internet. Loopback-only startup is `python3 scripts/model_services.py start`; it may not be reachable from the sandbox.

Wait for both servers to finish loading (initial compilation can take time). In separate terminals:

```bash
docker logs -f workshop-lightning
docker logs -f workshop-nano
```

Exit log following with Ctrl-C; containers continue running. Then:

```bash
python3 scripts/model_services.py check
```

This checks `base` and `specialist` discovery and actual Chat Completions responses, plus a structured Nano tool call. It does not execute the test tool or claim model quality. Startup is not readiness. If the test fails, inspect logs, cache completeness, available unified memory and parser compatibility. Model requests are offline with respect to Hugging Face inside the containers; a missing download is reported rather than silently fetched.

The launcher mirrors the current memory settings, not universal tuning advice. Concurrent VSS or training can exhaust memory. Inspect `docker inspect` image IDs and record digests once qualified. To restart these containers later, use `docker start workshop-lightning workshop-nano`; to stop them, use `docker stop workshop-lightning workshop-nano`. Do not use the original-machine `workshop.sh up` on this fresh deployment.

## 5. Install OpenShell and prepare OpenClaw

The course policy was tested with OpenShell **0.0.85** and OpenClaw **2026.9.7**. Follow the [versioned OpenShell source](https://github.com/NVIDIA/OpenShell/tree/v0.0.85) and [NVIDIA installation guide](https://docs.nvidia.com/openshell/latest/about/installation). Download and inspect the installer, then request the tested version:

```bash
curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh \
  -o /tmp/workshop-install-openshell.sh
OPENSHELL_VERSION=v0.0.85 sh /tmp/workshop-install-openshell.sh
openshell --version
openshell gateway list
openshell status
```

Confirm a matching CLI/gateway release and a reachable local gateway. The current installation guide targets a newer release; if old artifacts are unavailable, use the versioned release instructions or explicitly qualify an upgrade with the policy tests. Installing only the CLI via uv does not establish a working gateway.

```bash
bash run/claw/terminal/demo.sh build
bash run/claw/terminal/demo.sh setup
bash run/claw/terminal/demo.sh policy
```

The Dockerfile installs pinned Node/OpenClaw dependencies; no separate host Node installation is needed. Follow the [terminal guide](run/claw/terminal/README.md#change-and-test-access) to test allowed model discovery and denied `/health` from inside the sandbox. A host API success is not sufficient to prove sandbox connectivity. Notebook 10 adds policy/filesystem checks. Notebook host workers start from the notebook preparation cells; they are not another server to install globally.

## 6. Start the UI and Jupyter

Run these in separate terminals from the repository root:

```bash
bash scripts/start-demo.sh
```

```bash
.workshop/jupyter/bin/python -m jupyterlab --config=scripts/jupyter_config.py \
  --ip=127.0.0.1 --port=8890 --ServerApp.port_retries=0 --ServerApp.root_dir="$PWD"
```

From a laptop, forward the UI ports and use the printed Jupyter login link:

```bash
ssh -L 7861:127.0.0.1:7861 -L 8890:127.0.0.1:8890 USER@SPARK_HOST
```

Open `http://127.0.0.1:7861` and Jupyter on 8890. Select **NATO course (PyTorch + PEFT)**. Run manual notebooks in order; agent handoffs require pasting the generated task into the TUI and waiting before collecting results. Use a Jupyter terminal for printed launcher commands when the Spark has no desktop.

## 7. Video, GPU RL and final checks

Recorded observation text is included. Optional video playback needs separately supplied, authorized clips at `run/chain/clips/`, including `civil-market.mp4` for notebook 09. Missing clips affect playback; do not describe recorded text as fresh video inference. For live video, provision the [NVIDIA VSS blueprint](https://build.nvidia.com/nvidia/video-search-and-summarization/blueprintcard) using the [Spark playbook](https://build.nvidia.com/spark/vss), configure port 8000 and register the clips. Record the selected blueprint version/API as described in [the demo guide](run/workshop/README.md#nvidia-video-blueprint-and-deployment-evidence). VSS is optional and is not installed by the model launcher.

Notebook 11's CPU Gym exercise is installed by `install.sh all`. Full Lightning Gym/RL training requires the additional task/verifier/trainer implementation documented in [notebook 11](course/11-trace-and-improve.ipynb); it is not provisioned by starting inference servers. NVIDIA skills and blueprint discovery links are in the [course source map](course/README.md#nvidia-source-map).

```bash
python3 scripts/model_services.py check
course/.venv/bin/python course/scripts/validate_notebooks.py --offline
# Requires running services, cached assets and the configured sandbox:
course/.venv/bin/python course/scripts/validate_notebooks.py --execute-manual
```

The last command executes manual cells and records results; it skips interactive TUI handoffs. Complete those separately to validate OpenClaw. Keep the resolved software/model versions, adapter hashes and validation outputs with your deployment record. A clean-machine deployment is qualified only after these checks and the agent handoffs pass on that machine.

## Validation of this setup tooling

The launcher passed the repository's 22 provisioning/lifecycle tests, and the setup shell examples passed syntax checks. Its live `check` command passed base and specialist generation and Nano structured tool calling against the existing Spark services. Its preflight rejected the occupied Lightning port without changing services. These checks do not substitute for downloading and starting both containers on a clean Spark.
