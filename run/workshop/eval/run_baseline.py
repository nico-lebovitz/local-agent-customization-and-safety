"""Run the development episodes against the live workshop, sequentially.

No weights are updated. Requires the UI server and local Lightning endpoint.
"""
import argparse
import json
from pathlib import Path
import sys
import time

import httpx

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from workshop_agent.evaluation import score_episode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:7861")
    parser.add_argument("--output", type=Path, default=HERE / "outputs/baseline-summary.json")
    args = parser.parse_args()
    rows = [json.loads(line) for line in (HERE / "eval/episodes.jsonl").read_text().splitlines()]
    results = []
    with httpx.Client(base_url=args.url, timeout=15) as client:
        versions = client.get("/api/info").json()["versions"]
        for episode in rows:
            start = client.post("/api/runs", json={"task": episode["task"], "clip": episode["clip"], "perception": "recorded"})
            start.raise_for_status()
            run_id = start.json()["id"]
            deadline = time.monotonic() + 620
            while time.monotonic() < deadline:
                response = client.get("/api/runs/" + run_id)
                response.raise_for_status()
                run = response.json()
                if run["status"] != "running":
                    break
                time.sleep(0.25)
            else:
                raise TimeoutError("Workshop episode did not finish")
            score = score_episode(run, episode["expected"])
            results.append({"episode": episode["id"], "run_id": run_id, **score,
                            "latency_s": run["events"][-1]["elapsed_s"],
                            "model_calls": sum(e["kind"] == "model" for e in run["events"]),
                            "relay_events": len(run["relay_events"])})
            print(episode["id"], json.dumps(score), flush=True)
            # The server persists and flushes the final trace before releasing its single-run slot.
            while client.get("/api/health").json()["active_run"]:
                if time.monotonic() > deadline:
                    raise TimeoutError("Trace flush did not finish")
                time.sleep(0.1)
    summary = {"kind": "development smoke baseline, not a held-out benchmark",
               "perception": "recorded", "models": "live", "versions": versions,
               "rl_training": False, "results": results,
               "successes": sum(r["success"] for r in results), "episodes": len(results)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
