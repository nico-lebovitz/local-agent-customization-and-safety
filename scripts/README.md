# Setup and startup scripts

For a fresh participant checkout:

```bash
bash scripts/install.sh demo       # Python environment for the 7861 UI
bash scripts/start-demo.sh         # foreground server; Ctrl-C stops it
bash scripts/install.sh all        # also install course, Jupyter, and Gym
```

Install uv first. `install.sh all --dry-run` previews every command. These scripts
work from any current directory and keep environments inside the checkout.
The installer checks Python versions before syncing an existing environment.
For model serving, GPU drivers, Docker, OpenShell, model downloads and clip requirements, follow the [fresh-Spark setup guide](../SPARK-SETUP.md).

```bash
python3 scripts/model_services.py plan       # prints commands; no changes
python3 scripts/model_services.py preflight  # requires assets and free ports
python3 scripts/model_services.py start      # loopback APIs; see guide for sandbox access
python3 scripts/model_services.py check      # discovery, generation and Nano tool-call probes
```

The launcher targets Linux ARM64 on a 128 GB DGX Spark. It uses separate `workshop-lightning` and `workshop-nano` containers and refuses existing names/occupied ports. It does not install drivers, download models, train an adapter or provision OpenShell. The guide supplies those stages. No fresh-machine end-to-end validation has yet been performed.

## Original Spark lifecycle

`workshop.sh` manages the already-provisioned workshop Spark. It expects the named
containers in `workshop.py`, cached models, local clips, the specialist adapter,
OpenShell's user service, and the course/UI/Jupyter environments. It deliberately
refuses missing or replaced containers. It cannot provision a fresh machine.

```bash
bash scripts/workshop.sh preflight
bash scripts/workshop.sh up
bash scripts/workshop.sh links
bash scripts/workshop.sh status
```

Default startup uses recorded observations with live model inference. `up --live-video`
also restores VSS and its GPU services; use it only after checking their configured
host address. `plan` prints the managed inventory. `down` waits for active UI work,
then stops the workshop processes and registered containers without removing data.
Save notebooks and exit OpenClaw before stopping. The script never powers off the host.

Default `up` restores Nano on 30081, Lightning base/specialist on 8002, the
OpenShell user service and saved workshop sandboxes, the UI on 7861, and Jupyter
on 8890. It warms the model endpoints before starting the UI. It does not run
`install.sh`, build images, download weights, create missing sandboxes, or launch
the TUI. Even default startup requires the recorded deployment's complete container
inventory and the clips checked by `check_assets()`.

Private machine identities, restart policies, logs, and tokens live under ignored
`.workshop/`. Do not redistribute that directory. The Jupyter launcher prefers
`.workshop/jupyter`; `demo/.venv` is a compatibility fallback on the original machine.

The lifecycle test suite uses mocks and does not operate real services:

```bash
python3 -m unittest discover -s scripts/tests -v
```
