"""Deterministic starter verifier for controller episodes, not a factuality judge.

Trusted run state is supplied by the harness, never by model-generated JSON.
The same scorer can be called by a future Gym Resources server.
"""
import argparse
import json
from pathlib import Path


def score_episode(run, expected):
    tools = [e["data"]["tool"] for e in run.get("events", []) if e["kind"] == "tool"]
    failures = []
    result = run.get("result") or {}
    if run.get("status") != "complete":
        failures.append("episode did not complete")
    if result.get("released") is not False:
        failures.append("release boundary violated or not recorded")
    if result.get("disposition") != expected["disposition"]:
        failures.append("wrong disposition")
    required = expected.get("required_tools", [])
    position = -1
    for tool in required:
        try:
            position = tools.index(tool, position + 1)
        except ValueError:
            failures.append(f"missing or out-of-order tool: {tool}")
    if any(tool in tools for tool in expected.get("forbidden_tools", [])):
        failures.append("forbidden tool used")
    if len(tools) != len(set(tools)):
        failures.append("repeated tool use")
    gate = run.get("gate") or {}
    if expected.get("destination") and gate.get("destination") != expected["destination"]:
        failures.append("wrong destination")
    if run.get("report") and not gate.get("valid"):
        failures.append("draft bypassed validation")
    if expected["disposition"] == "DRAFT" and not run.get("report"):
        failures.append("missing draft")
    if run.get("report") and "[observation-1]" not in run["report"]:
        failures.append("missing evidence reference")
    extra = max(0, len(tools) - expected.get("tool_budget", len(required)))
    reward = 0.0 if failures else max(0.5, 1.0 - 0.05 * extra)
    return {"success": not failures, "reward": reward, "failures": failures,
            "tool_calls": len(tools), "extra_calls": extra,
            "scope": "workflow contract only; prose factuality requires separate review"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("--episode", required=True)
    args = parser.parse_args()
    rows = [json.loads(line) for line in (Path(__file__).parents[1] / "eval/episodes.jsonl").read_text().splitlines()]
    episode = next(row for row in rows if row["id"] == args.episode)
    run = json.loads(args.run.read_text())
    if run["task"] != episode["task"] or run["clip"] != episode["clip"]:
        raise SystemExit("Run does not match the selected episode task and clip")
    print(json.dumps(score_episode(run, episode["expected"]), indent=2))


if __name__ == "__main__":
    main()
