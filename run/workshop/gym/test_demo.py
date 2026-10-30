import json
import pytest
import torch
from fastapi.testclient import TestClient
from resources import INTENTS, PLANS, app, request_payload
from rl_kernel import load_kernels
from train_demo import train


@pytest.mark.parametrize("intent_index", range(3))
@pytest.mark.parametrize("plan_index", range(4))
def test_gym_rewards_only_exact_task_plan(intent_index, plan_index):
    with TestClient(app) as client:
        response = client.post("/verify", json=request_payload(INTENTS[intent_index], PLANS[plan_index]["id"]))
        assert response.status_code == 200
        body = response.json()
        assert body["reward"] == float(intent_index == plan_index)
        assert body["released"] is False
        if plan_index == 3:
            assert body["transitions"][0] == {"tool": "triage", "allowed": False}


@pytest.mark.parametrize("action", [{"plan_id": "report", "reward": 1}, {"plan_id": "release"}, {"released": False}, []])
def test_policy_cannot_supply_its_own_reward(action):
    payload = request_payload("draft", "report")
    payload["response"]["output"][0]["content"][0]["text"] = json.dumps(action)
    with TestClient(app) as client:
        body = client.post("/verify", json=payload).json()
    assert body["reward"] == 0
    assert body["failures"]


def test_exact_upstream_loss_has_correct_gradient_direction():
    kernels, _ = load_kernels()
    logits = torch.zeros(2, requires_grad=True)
    current = logits.log_softmax(0).reshape(2, 1)
    mask = torch.ones_like(current)
    loss, _, _ = kernels["clipped_pg_actor_objective"](current,
        prev_logprobs=current.detach(), advantages=torch.tensor([[-1.], [1.]]),
        token_mask=mask, mask=mask, sample_mask=mask[:, 0], importance_weights=None,
        global_valid_toks=mask.sum(), global_valid_seqs=mask.sum(),
        ratio_clip_min=.2, ratio_clip_max=.2, ratio_clip_c=0.,
        disable_ppo_ratio=False, force_on_policy_ratio=False,
        sequence_level_importance_ratios=False, use_cispo=False, token_level_loss=True)
    loss.backward()
    assert logits.grad[0] > 0 and logits.grad[1] < 0


def test_cpu_training_reproducible_weight_update(tmp_path):
    a = train(tmp_path / "a", steps=3, group_size=8)
    b = train(tmp_path / "b", steps=3, group_size=8)
    assert a["weight_update"] and not a["production_weights_changed"]
    assert a["after"]["expected_reward"] > a["before"]["expected_reward"]
    assert a["after"]["checkpoint"] == b["after"]["checkpoint"]
    assert a["rollouts_sha256"] == b["rollouts_sha256"]
    assert a["rollout_count"] == 3 * 3 * 8
