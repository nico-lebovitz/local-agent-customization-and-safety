# Original Spark lifecycle

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

Private machine identities, restart policies, logs, and tokens live under ignored
`.workshop/`. Do not redistribute that directory. The Jupyter launcher prefers
`.workshop/jupyter`; `demo/.venv` is a compatibility fallback on the original machine.

The lifecycle test suite uses mocks and does not operate real services:

```bash
python3 -m unittest discover -s scripts/tests -v
```
