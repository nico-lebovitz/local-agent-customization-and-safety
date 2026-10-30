"""Turn the notebook's deliberately failed attempt into a bounded Gym/RL demo."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from course.common import ROOT


def run_learning(output):
    output = Path(output)
    trace = output / "failed-agent-run.json"
    relay_path = output / "failed-relay-events.json"
    record = json.loads(trace.read_text())
    events = json.loads(relay_path.read_text())
    first = record["events"][0]
    if (record.get("test_type") != "injected missing-evidence action"
            or first["action"]["tool"] != "triage" or "error" not in first
            or "observation" in record["state"]):
        raise ValueError("Expected the explicitly injected triage-before-evidence attempt from 09")
    failed_calls = [e for e in events if e.get("category") == "tool"
                    and e.get("name") == "triage" and e.get("scope_category") == "end"
                    and (e.get("metadata") or {}).get("otel.status_code") == "ERROR"]
    if not failed_calls:
        raise ValueError("The failed action needs an actual Relay error event")
    case = {
        "task": "draft", "plan_id": "skip_evidence",
        "rule": "Collect evidence before classification",
        "source_trace_sha256": hashlib.sha256(trace.read_bytes()).hexdigest(),
        "relay_event_id": failed_calls[0]["uuid"],
        "relay_sha256": hashlib.sha256(relay_path.read_bytes()).hexdigest(),
        "mapping": "The failed triage prefix maps to Gym's existing skip_evidence plan.",
        "training_data": "Fresh on-policy plan samples; the trace is not ingested as training tensors.",
    }
    destination = output / "gym-rl"
    destination.mkdir(exist_ok=True)
    (destination / "failure-case.json").write_text(json.dumps(case, indent=2) + "\n")
    python = ROOT / "run/workshop/gym/.venv/bin/python"
    if not python.is_file():
        raise RuntimeError("Set up the Gym CPU environment using run/workshop/gym/README.md")
    completed = subprocess.run([str(python), "-m", "course.agent.learning", "--train",
                                str(destination)], cwd=ROOT, capture_output=True,
                               text=True, timeout=120)
    (destination / "training.log").write_text(completed.stdout + completed.stderr)
    if completed.returncode:
        raise RuntimeError("Gym/RL exercise failed: " + completed.stderr[-2000:])
    return json.loads((destination / "comparison.json").read_text())


def train_and_compare(destination):
    # Keep Gym's dependencies isolated from the Jupyter and inference environments.
    sys.path.insert(0, str(ROOT / "run/workshop/gym"))
    from fastapi.testclient import TestClient
    from resources import INTENTS, PLANS, app, request_payload
    from train_demo import train

    artifact = train(destination, steps=40, group_size=16, seed=42)
    intent_index = INTENTS.index("draft")
    probabilities = artifact["after"]["probabilities"][intent_index]
    chosen = PLANS[max(range(len(PLANS)), key=probabilities.__getitem__)]["id"]
    with TestClient(app) as client:
        def verify(plan):
            response = client.post("/verify", json=request_payload("draft", plan))
            response.raise_for_status()
            return response.json()
        failed, replay = verify("skip_evidence"), verify(chosen)
    bad = next(i for i, p in enumerate(PLANS) if p["id"] == "skip_evidence")
    good = next(i for i, p in enumerate(PLANS) if p["id"] == "report")
    result = {
        "failed_plan_reward": failed["reward"],
        "failed_plan_reason": failed["failures"],
        "before_correct_plan_probability": artifact["before"]["probabilities"][intent_index][good],
        "after_correct_plan_probability": probabilities[good],
        "before_skip_evidence_probability": artifact["before"]["probabilities"][intent_index][bad],
        "after_skip_evidence_probability": probabilities[bad],
        "before_expected_reward": artifact["before"]["expected_reward"],
        "after_expected_reward": artifact["after"]["expected_reward"],
        "replayed_plan": chosen, "replay_reward": replay["reward"],
        "replay_transitions": replay["transitions"],
        "optimizer_steps": artifact["optimizer_steps"], "fresh_rollouts": artifact["rollout_count"],
        "weights_changed": artifact["weight_update"],
        "before_checkpoint_sha256": artifact["before"]["checkpoint"]["sha256"],
        "after_checkpoint_sha256": artifact["after"]["checkpoint"]["sha256"],
        "trained_model": "12-parameter CPU plan-selection policy",
        "lightning_weights_changed": False,
        "evaluation": "Same tiny Gym environment; not a held-out LLM benchmark",
    }
    if not result["weights_changed"] or failed["reward"] != 0:
        raise AssertionError("Expected real weight updates and rejection of the missing-evidence plan")
    (destination / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--train":
        raise SystemExit("Usage: learning.py --train OUTPUT")
    train_and_compare(Path(sys.argv[2]))
