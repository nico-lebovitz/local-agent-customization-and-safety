# OpenClaw inside OpenShell

This exercise runs OpenClaw in a sandbox, lets it call two local model services,
and checks the access rules from inside that sandbox. Run commands from the
repository root on the machine hosting the services.

## Before you start

Install Docker and OpenShell using the [upstream installation instructions](https://github.com/NVIDIA/OpenShell#installation).
Follow the gateway setup for that release, then check:

```bash
docker info
openshell --version
openshell gateway list
openshell status
```

The workshop was tested with OpenShell **0.0.85**; use [NVIDIA’s v0.0.85 source](https://github.com/NVIDIA/OpenShell/tree/v0.0.85) as the release reference alongside [policy.yaml](policy.yaml). Current upstream instructions
describe a newer release; use a matching CLI/gateway pair and review policy schema
changes before upgrading. A CLI installation alone does not provide a running
gateway. If no gateway is registered, follow the upstream setup before continuing.
This repository supplies the sandbox image and policy, not a gateway installer.

The host must already serve Nano on port 30081 and Lightning on port 8002, as
described in [service provisioning](../../../README.md#provision-services-before-running-the-course).
The sandbox reaches them through `host.openshell.internal`. OpenClaw's controller
configuration is in [openclaw.json](openclaw.json).

Build the image and create the sandbox once:

```bash
bash run/claw/terminal/demo.sh build
bash run/claw/terminal/demo.sh setup
bash run/claw/terminal/demo.sh policy
```

`setup` assigns [policy.yaml](policy.yaml) with `openshell sandbox create --policy`.
It also disables automatic provider injection with `--no-auto-providers`, so the
access rules come from this policy. An existing sandbox is not overwritten.

## Run the agent

From the repository root, run:

```bash
bash run/claw/terminal/demo.sh tui
```

This opens the actual OpenClaw terminal interface inside the `nato-openclaw-demo`
OpenShell sandbox. It runs the embedded agent (`--local`); no messaging channel or
OpenClaw Gateway service is needed. The OpenShell gateway is still required.

Paste these prompts one at a time:

1. **Use the workshop-triage skill to triage civil-market and prepare a short draft. Show the specialist classification, confidence, and validated destination. Keep it for human review.**
2. **Now triage degraded-mountain-fog using the specialist tool. Can we call this CONFIRMED and release it? Explain using the actual tool result.**

The loop is OpenClaw → local Nemotron Nano controller → skill → Python tool →
local `specialist` model (base plus loaded adapter) → deterministic validation →
OpenClaw answer. Observations are prerecorded; model inference is live. The skill
instructs the agent to hold drafts for human review, and no delivery tools are enabled.

For a second terminal showing the enforcement layer:

```bash
bash run/claw/terminal/demo.sh policy
bash run/claw/terminal/demo.sh logs
```

`setup` creates a new sandbox; if it already exists, use the running sandbox or
explicitly delete this demo sandbox before recreating it. Its local conversation
history will be lost on deletion. The launcher rejects duplicate starts before opening the bridge. Exit with `/exit`
in the original terminal (including any Jupyter terminal) before reopening elsewhere.
Closing a browser tab does not stop its terminal process.

Run only one OpenClaw session at a time against
its state directory. Exit the TUI before running CLI rehearsals.

## Change and test access

Read the applied policy before editing it. The main rules are:

| Process or resource | Access |
|---|---|
| `/usr/local/bin/node` | Nano on port 30081: GET `/v1/models`, POST `/v1/chat/completions` |
| `/usr/local/bin/python3.12` | Lightning on port 8002: the same two API paths |
| `/usr`, `/lib`, `/etc`, `/opt` | Read-only source and system files |
| `/home/sandbox`, `/tmp`, `/dev` | Writable sandbox paths |
| User/group | `sandbox`; the host working directory is not automatically included |

Network access depends on the executable, destination, port, HTTP method, and
path. A skill's instructions do not grant any of these permissions.

Check allowed and denied paths with the same Python executable used by the tool:

```bash
openshell sandbox exec --name nato-openclaw-demo -- /usr/local/bin/python3.12 -c '
import urllib.request, urllib.error
for path in ("/v1/models", "/health"):
    try:
        with urllib.request.urlopen("http://host.openshell.internal:8002" + path, timeout=10) as response:
            print(path, response.status)
    except urllib.error.HTTPError as error:
        print(path, error.code)
'
```

With the original policy, expect `/v1/models` to succeed and `/health` to return
403. A timeout or connection refusal is a service/reachability problem, not proof
of a policy denial. Inspect `bash run/claw/terminal/demo.sh logs` as well.

To practice granting access, exit the agent TUI and copy the policy:

```bash
cp run/claw/terminal/policy.yaml /tmp/workshop-policy.yaml
```

In the copy, add this rule to **specialist → endpoints → rules**, alongside the
existing GET and POST rules. Keep the host, port, and Python binary restriction:

```yaml
          - allow: {method: GET, path: /health}
```

Apply the complete copied policy to this sandbox and rerun the probe:

```bash
openshell policy set nato-openclaw-demo --policy /tmp/workshop-policy.yaml --wait
openshell policy get nato-openclaw-demo
```

The health request should now reach the server; its response depends on whether
that server implements `/health`. Compare it with a host-side request to
`http://127.0.0.1:8002/health`. Restore the original policy and confirm the sandbox
request is denied again:

```bash
openshell policy set nato-openclaw-demo --policy run/claw/terminal/policy.yaml --wait
```

These commands change the network policy of one sandbox. Filesystem and process
policy changes may require recreating it; consult the
[policy documentation](https://docs.nvidia.com/openshell/how-it-works/policies/overview)
for your installed version. Do not use a global policy for this exercise.

Notebook 10 adds filesystem probes and records the results. Its generated student
image is a separate exercise and is not deployed automatically. The chapter
training tools run their fixed CPU jobs in a host worker; OpenShell constrains
OpenClaw, not those host jobs.

## Compatibility details

Pinned OpenClaw: 2026.9.7, Node 24. Debian trixie supplies the system libraries
required by the installed OpenShell supervisor. SQLite temporary files use `/tmp`.

The existing Nano server does not stream tool calls. `bridge.mjs` listens only on
sandbox loopback and converts native non-streaming JSON responses into SSE for
OpenClaw. It preserves structured tool calls; it never interprets model prose as
commands. No model server restart or download is required.

The policy permits Node to call the controller and Python to call the specialist,
only on `/v1/models` and `/v1/chat/completions`. Source files are read-only and
sandbox home and temporary storage are writable. Installed OpenShell 0.0.85 uses
`best_effort` Landlock compatibility here; this is a workshop policy example, not
a claim that every kernel enforces every Landlock feature.

## Rehearsal observations

Both prompts were run against the live local models. The market example returned
`civil_gathering`, `POSSIBLE`, and validated destination `CIMIC`. The fog example
returned an unsupported `activity_type`; validation rejected it and OpenClaw
held it for review instead of claiming confirmation or release. These are model
outputs, not fixed expected answers. Each exchange took roughly two minutes.

OpenClaw's process launcher may print a permission warning when attempting to
adjust `/proc/self/oom_score_adj`. OpenShell denies that write; the Python tool
still runs and returns its result. Do not grant elevated execution to hide it.
An explicit Python request to the unapproved specialist `/health` path returned
HTTP 403 during policy verification.
