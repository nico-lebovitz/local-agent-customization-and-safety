# Agentic workshop walkthrough

An interactive visual walkthrough, backed by real NAT functions, local Lightning calls
through Switchyard, and NeMo Relay lifecycle events. This application uses **127.0.0.1:7861**.
For the original provisioned Spark, see [the lifecycle guide](../../scripts/README.md).

## Run

From the repository root:

~~~bash
bash scripts/install.sh demo
bash scripts/start-demo.sh
~~~

Open http://127.0.0.1:7861. Keep the process running in your terminal or session manager.
Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first.
The installer uses the root `requirements.txt`, which includes this directory's
`requirements.lock`. It installs Python dependencies; it does not provision models.
For a remote Spark, forward port 7861 over SSH. Models must already be running for live inference; VSS is needed only for live perception;
this application does not start, stop, or reconfigure those containers.

Required local services:
- Lightning :8002, model names **base** and **specialist**, existing LoRA loaded.
- VSS :8000 only for live perception. Recorded perception never silently calls VSS.
- Local clips in run/chain/clips/ for video playback (excluded from Git).

Switchyard runs as an embedded native loopback server on an automatically allocated port.
It uses explicit task routes. It does not yet classify arbitrary requests automatically.
Relay wraps application model/tool boundaries; its native plugin for Switchyard is not used.
The trace shows app-owned routing marks, provider usage, and real Relay scope events.

## Workshop flow

The default page is the visual demo. The footer links to the original detailed
presentation at `/static/classic.html`.

1. **Choose a task:** scroll through scene cards, play the local video, and select
   Describe, Classify, or Draft. Run makes actual model calls using recorded VSS
   observations by default; live VSS remains an explicit choice.
2. **Follow the agent:** see the last recorded model route, scroll or scrub through
   the execution, and click a step for its input/output and related Relay evidence.
   Model-node clicks are labeled route previews; they do not change backend routing.
3. **Find the failure:** compare the original triage-before-evidence failure with
   the corrected constrained workflow. These are saved real runs, not injected
   tests or evidence of an RL update.
4. **Watch it learn:** scrub or play the 40 recorded CPU training updates, switch
   task intent, and inspect rewarded/rejected sampled attempts. The probabilities
   and reward curve come from the existing Gym/RL artifact. No training launches
   when viewing the UI; Lightning weights remain unchanged.

Live execution, recorded execution, and recorded training have separate visible
labels. Full JSON is in expandable panels. Rule validation and the controller's
review decision remain separate, so a controller hold cannot imply that a valid
classification failed its checks.

Local card thumbnails are generated from existing clips and excluded from Git:

```bash
python3 run/workshop/scripts/build_posters.py
```

A missing clip or thumbnail does not block recorded-description inference. The UI
has responsive layouts, keyboard-accessible controls, and reduced-motion styles.
There are no runtime CDN or JavaScript framework dependencies.

UI behavior tests use a simulated DOM and the real recorded fixture data:

```bash
npm ci --prefix run/workshop/ui-tests
npm test --prefix run/workshop/ui-tests
```

The controller is a NAT custom workflow making bounded JSON action decisions (maximum
8 steps), not NAT's stock ReAct agent. Each available tool is a registered NAT function.
The specialist prompt is imported unchanged from train/scripts/jisr_rules.py. It only
receives one observation, never the controller's conversation. Both targets share weights.

All outputs remain drafts. JSON/schema checks and R1/R2 confidence checks run in code;
the destination is assigned by lookup. Unsupported categories and failures hold for review.
The report header comes from the validated item. The base model supplies only a short
summary with a source reference. **Prose factuality is not automatically verified.**

## Verification and baseline

~~~bash
cd run/workshop
.venv/bin/python -m pytest -q tests
.venv/bin/python eval/run_baseline.py
.venv/bin/python -m workshop_agent.evaluation outputs/RUN_ID.json --episode report-market
~~~

The baseline runner makes live model calls with recorded VSS descriptions. Its four
starter episodes are **development smoke tests**, not independent held-out evidence.
Tests use explicitly scripted fixtures and make no live model calls.
Execution records are local JSON under outputs/ and excluded from Git. Download a run
from the UI for its event record, model/tool payloads, result and source labels.

## Recorded development evidence

The first four-case live check passed 2/4 workflow contracts. After adding explicit
current-state information and constraining the allowed action schema, the same four
development cases passed 4/4. This was a harness correction, **not training or held-out
evidence**. Both summaries and the original Relay traces are preserved in eval/.
The UI can replay these records without calling a model. Trace replay is clearly labeled.

### Architecture and trace presentation

Section 3 contains an SVG connection diagram and a policy inspector.
`configs/openshell-design.yaml` is a deployment design excerpt, not an applied
policy. Complete the sandbox image, mounts, runtime file permissions and binary
identity before validating and deploying it. The existing Claw preset uses older
ports and is displayed only for comparison. Neither view proves enforcement.
The policy text in the static HTML mirrors the design file; update both together.

Section 4 renders recorded workflow events as a decision sequence and timing
waterfall. Model bars use reported latency; other events are point markers.
Select an event for its payload, filter by event type, or load a saved execution
without inference. Original Relay lifecycle events remain expandable below.

Rebuild `static/architecture.svg` with
`python3 run/workshop/scripts/build_architecture.py` from the repository root.
The builder derives connector endpoints from centered box edges or labeled harness ports and rejects
bent connectors or paths crossing unrelated boxes. The sandbox encloses the
harness and agent loop. Three logical access lanes connect it through tool, model
and filesystem policy to external capability boxes. These boxes represent access
domains, not a claim that every registered function runs in a separate process.
Network policy is enforced by the trusted supervisor; mounted data uses filesystem
controls. Relay instruments the harness. The nested boundary layout illustrates the sandbox and its controlled access domains.

Section 5 replays `gym/artifacts/demo.json`: 40 real CPU optimizer updates driven by
Gym verification and pinned NeMo RL loss functions. Expected reward moves from 0.25
to 0.994 over this finite teaching environment. This is not held-out performance or
a Lightning weight update. Sliders and replay controls only read captured results.

### What the diagram represents

The four registered tools are `perceive`, `triage`, `draft`, and `request_review`.
The browser has no `SKILL.md` loader. Relay records execution; the Gym/RL panel
replays a separate CPU training run. Dashed learning connections show a proposed
integration, not callable training or deployment tools.

For an agent running under an applied policy, use the
[OpenClaw sandbox exercise](../claw/terminal/README.md).

## NVIDIA video blueprint and deployment evidence

Official starting points are the [VSS blueprint card](https://build.nvidia.com/nvidia/video-search-and-summarization/blueprintcard), [DGX Spark VSS guide](https://build.nvidia.com/spark/vss), and [NVIDIA VSS architecture and component documentation](https://docs.nvidia.com/vss). Browse related agent instructions in the [NVIDIA skills catalog](https://build.nvidia.com/skills). The browser workflow has no skill loader; notebook 09 separately loads the pinned Relay skill.

The UI illustrates the original workshop path: Nano 9B v2 plans video-tool calls, VST supplies clip access, and Cosmos Reason2 interprets frames. These are external deployment descriptions, not a container manifest included in this clone. The current blueprint card lists newer models; its defaults must not be substituted silently for the workshop model IDs. NIM is an upstream serving option; the Python client only verifies the configured HTTP API, not the serving engine.

Before claiming the live stack is reproduced, record:

- VSS release or Git commit, deployment profile, Compose configuration, container image tags/digests, and VST version.
- Nano/Cosmos model IDs, revisions, precision, serving engine, and the separate Lightning checkpoint and adapter hashes.
- The deployed OpenAPI schema: this client calls `POST /generate` with `input_message` and accepts a JSON string or a string-valued `value` field. This contract is specific to the configured deployment.
- A clip-name-to-video-ID mapping and a saved successful response for the selected clip. The client asks by clip name; a healthy endpoint alone does not prove the agent selected the correct footage.

Use [runtime.py](workshop_agent/runtime.py) for the exact request/response handling and [the lifecycle script](../../scripts/workshop.py) for expected original-machine container names. No release/digest is invented when the deployment record is unavailable. Recorded mode reads local descriptions and calls none of these video services.

For the agent layer, [NVIDIA’s Switchyard TOML reference](https://nvidia-nemo.github.io/Switchyard/reference/toml_schema/) describes our passthrough routes, [Relay 0.9.4](https://docs.nvidia.com/nemo/relay/v0.9.4/instrument-applications/instrument-tool-call) describes managed tool calls, and the [NAT migration notice](https://docs.nvidia.com/nemo/agent-toolkit/latest/resources/migration-guide.html) records its deprecation. This pinned NAT demo is not a new-project framework recommendation.
