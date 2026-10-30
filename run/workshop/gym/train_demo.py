"""CPU-only RL demonstration: Gym rewards + official NeMo RL PG loss kernel."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import time

from fastapi.testclient import TestClient
import torch
from resources import INTENTS, PLANS, app, request_payload
from rl_kernel import load_kernels

HERE = Path(__file__).parent


def checkpoint(logits):
    weights = logits.detach().tolist()
    return {"model": "tiny-categorical-controller", "parameters": 12,
            "intents": INTENTS, "plan_ids": [x["id"] for x in PLANS], "logits": weights,
            "sha256": hashlib.sha256(json.dumps(weights).encode()).hexdigest()}


def summarize(logits, reward_matrix):
    probabilities = logits.detach().softmax(-1)
    return {"expected_reward": float((probabilities * reward_matrix).sum(-1).mean()),
            "greedy_success": float(reward_matrix.gather(1, probabilities.argmax(-1, keepdim=True)).mean()),
            "probabilities": probabilities.tolist(), "checkpoint": checkpoint(logits)}


def train(output, steps=40, group_size=16, seed=42):
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    kernels, manifest = load_kernels()
    logits = torch.nn.Parameter(torch.zeros((len(INTENTS), len(PLANS)), device="cpu"))
    optimizer = torch.optim.Adam([logits], lr=0.12)
    rows, history = [], []
    started = time.time()
    with TestClient(app) as client:
        def verify(intent, action):
            response = client.post("/verify", json=request_payload(intent, PLANS[action]["id"]))
            response.raise_for_status()
            result = response.json()
            if result.get("failure_kind") or result.get("mask_sample") or result.get("failure_reason"):
                raise RuntimeError("Gym verifier infrastructure failure: " + str(result))
            return result

        reward_matrix = torch.tensor([[verify(intent, j)["reward"] for j in range(len(PLANS))]
                                      for intent in INTENTS], device="cpu")
        before = summarize(logits, reward_matrix)
        for step in range(1, steps + 1):
            # Fresh on-policy samples per task group at every optimization step.
            actions = torch.distributions.Categorical(logits=logits.detach()).sample((group_size,)).T
            previous = logits.detach().log_softmax(-1).gather(1, actions).reshape(-1, 1)
            reward_rows = []
            for task_index, intent in enumerate(INTENTS):
                group_rewards = []
                for sample_index, action in enumerate(actions[task_index].tolist()):
                    verification = verify(intent, action)
                    group_rewards.append(verification["reward"])
                    rows.append({"step": step, "sample": sample_index, "intent": intent,
                                 "plan_id": PLANS[action]["id"], "reward": verification["reward"],
                                 "transitions": verification["transitions"], "failures": verification["failures"],
                                 "released": verification["released"],
                                 "old_log_probability": float(previous[task_index * group_size + sample_index, 0])})
                reward_rows.extend(group_rewards)
            rewards = torch.tensor(reward_rows)
            prompt_ids = torch.arange(len(INTENTS)).repeat_interleave(group_size).unsqueeze(-1)
            baseline, std, trivial = kernels["calculate_baseline_and_std_per_prompt"](
                prompt_ids, rewards, torch.ones_like(rewards), leave_one_out_baseline=False)
            advantages = torch.where(trivial, 0, (rewards - baseline) / std.clamp_min(1e-8)).unsqueeze(-1)
            current = logits.log_softmax(-1).gather(1, actions).reshape(-1, 1)
            mask = torch.ones_like(current)
            loss, _, _ = kernels["clipped_pg_actor_objective"](
                current, prev_logprobs=previous, advantages=advantages,
                token_mask=mask, mask=mask, sample_mask=mask[:, 0], importance_weights=None,
                global_valid_toks=mask.sum(), global_valid_seqs=mask.sum(),
                ratio_clip_min=0.2, ratio_clip_max=0.2, ratio_clip_c=0.0,
                disable_ppo_ratio=False, force_on_policy_ratio=False,
                sequence_level_importance_ratios=False, use_cispo=False, token_level_loss=True)
            optimizer.zero_grad()
            loss.backward()
            gradient_norm = float(logits.grad.norm())
            optimizer.step()
            state = summarize(logits, reward_matrix)
            history.append({"step": step, "mean_reward": float(rewards.mean()),
                            "expected_reward": state["expected_reward"], "loss": float(loss.detach()),
                            "gradient_norm": gradient_norm, "probabilities": state["probabilities"]})
            for i, row in enumerate(rows[-len(rewards):]):
                row["advantage"] = float(advantages[i, 0])
    after = summarize(logits, reward_matrix)
    output.mkdir(parents=True, exist_ok=True)
    rollout_path = output / "rollouts.jsonl"
    rollout_path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    (output / "checkpoint.json").write_text(json.dumps(after["checkpoint"], indent=2) + "\n")
    sample_rows = []
    for step in range(1, steps + 1):
        for intent in INTENTS:
            for reward in [0, 1]:
                sample_rows.extend(next(([r] for r in rows if r["step"] == step and r["intent"] == intent and r["reward"] == reward), []))
    artifact = {
        "schema_version": 1, "kind": "CPU teaching experiment: NeMo Gym + NeMo RL loss kernel",
        "created_at": datetime.now(timezone.utc).isoformat(), "seed": seed,
        "gym_version": importlib.metadata.version("nemo-gym"),
        "torch_version": torch.__version__, "python_version": platform.python_version(),
        "device": "cpu", "parameters": logits.numel(), "optimizer": "Adam", "learning_rate": 0.12,
        "group_size": group_size, "optimizer_steps": steps, "rollout_count": len(rows),
        "duration_s": round(time.time() - started, 3),
        "weight_update": before["checkpoint"]["sha256"] != after["checkpoint"]["sha256"],
        "production_weights_changed": False, "full_nemo_rl_trainer": False,
        "rl_source": {"commit": manifest["commit"], "function": "clipped_pg_actor_objective",
                      "url": manifest["repository"] + "/blob/" + manifest["commit"] + "/nemo_rl/algorithms/loss/clipped_pg.py"},
        "gym_transport": "Real Gym SimpleResourcesServer /verify via in-process ASGI TestClient",
        "intents": INTENTS, "actions": PLANS, "before": before, "after": after,
        "steps": history, "sample_rollouts": sample_rows,
        "rollouts_sha256": hashlib.sha256(rollout_path.read_bytes()).hexdigest(),
        "checkpoint": "gym/artifacts/checkpoint.json", "rollouts": "gym/artifacts/rollouts.jsonl",
        "limitations": [
            "A 12-parameter categorical controller chooses among four fixed tool plans; no LLM or Lightning adapter is trained.",
            "Gym verifies offline state transitions; this experiment does not execute VSS, Lightning, OpenShell, or the production agent.",
            "Uses pinned NeMo RL loss and group-baseline functions, not its full distributed trainer or model rollout stack.",
            "Expected reward is calculated over all 12 task/plan pairs in this teaching environment, not a held-out benchmark.",
            "One optimizer update per fresh sample group makes the PPO ratio initially one; clipping is supported by the upstream function but inactive in this run.",
        ],
    }
    (output / "demo.json").write_text(json.dumps(artifact, indent=2) + "\n")
    print(json.dumps({"before": before["expected_reward"], "after": after["expected_reward"],
                      "steps": steps, "rollouts": len(rows), "weight_update": artifact["weight_update"],
                      "duration_s": artifact["duration_s"]}))
    return artifact


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=HERE / "artifacts")
    parser.add_argument("--steps", type=int, default=40)
    parser.add_argument("--group-size", type=int, default=16)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.steps < 1 or args.group_size < 2:
        parser.error("steps >= 1 and group-size >= 2 are required")
    train(args.output, args.steps, args.group_size, args.seed)
