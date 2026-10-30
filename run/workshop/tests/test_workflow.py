import asyncio
import json

from fastapi.testclient import TestClient
import pytest

from workshop_agent.contracts import validate_item
from workshop_agent.evaluation import score_episode
from workshop_agent.runtime import CURRENT, Run, draft, parse_object
from workshop_agent import server
from unittest.mock import AsyncMock

@pytest.fixture(autouse=True)
def isolate_run_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "RUNS_DIR", tmp_path)


VALID = {"activity_type": "civil_gathering", "sensor_quality": "UNKNOWN",
         "confidence": "POSSIBLE", "routing": "CIMIC"}


@pytest.mark.parametrize("choices", [
    [],
    [{"finish_reason": "length", "message": {"content": "partial"}}],
    [{"finish_reason": "content_filter", "message": {"content": "partial"}}],
    [{"finish_reason": "stop", "message": {"content": " "}}],
])
def test_gateway_rejects_incomplete_or_empty_responses(monkeypatch, choices):
    from workshop_agent.runtime import Gateway
    import nemo_relay as relay
    monkeypatch.setattr(relay.llm, "execute", AsyncMock(return_value={
        "model": "base", "choices": choices}))

    async def scenario():
        token = CURRENT.set(Run(task="Describe", clip="civil-market"))
        try:
            with pytest.raises(ValueError):
                await Gateway("http://unused").call("controller", [])
        finally:
            CURRENT.reset(token)
    asyncio.run(scenario())


@pytest.mark.parametrize("item", [None, [], {}, {**VALID, "activity_type": "invented"},
    {**VALID, "confidence": "CONFIRMED"}, {**VALID, "sensor_quality": "CLEAR", "confidence": "CONFIRMED"},
    {**VALID, "routing": ["CIMIC"]}, {**VALID, "sensor_quality": []},
    {**VALID, "sensor_quality": {}}, {**VALID, "extra": True}])
def test_invalid_output_holds(item):
    result = validate_item(item)
    assert not result["valid"]
    assert result["destination"] is None


def test_routing_is_owned_by_table():
    result = validate_item({**VALID, "routing": "J2-ANALYSIS"})
    assert result["valid"] and result["routing_overridden"]
    assert result["destination"] == "CIMIC"


@pytest.mark.parametrize("text", ['[]', 'not json', 'null'])
def test_parser_rejects_non_objects(text):
    with pytest.raises(ValueError):
        parse_object(text)


class ScriptedGateway:
    """Test fixture only. Never used by the live application."""
    def __init__(self, actions, item=None):
        self.actions = iter(actions)
        self.item = VALID if item is None else item
        self.calls = []

    async def call(self, purpose, messages, max_tokens=700, response_schema=None):
        self.calls.append((purpose, messages))
        if purpose == "controller":
            return json.dumps({"action": next(self.actions), "reason": "test fixture"})
        if purpose == "triage":
            return json.dumps(self.item)
        return json.dumps({"summary": "People are shopping at an outdoor market.", "source_ids": ["observation-1"]})


def test_nat_workflow_and_real_relay_capture():
    with TestClient(server.app) as client:
        gateway = ScriptedGateway(["perceive", "triage", "draft", "finish"])
        server.app.state.gateway = gateway
        response = client.post("/api/runs", json={"task": "Inspect and draft a report", "clip": "civil-market"})
        run_id = response.json()["id"]
        # Scripted calls complete without network; flush Relay before assertions.
        async def settle():
            await asyncio.gather(*list(server.TASKS))
        client.portal.call(settle)
        data = client.get("/api/runs/" + run_id).json()
        assert data["status"] == "complete", data["error"]
        assert data["result"]["released"] is False
        assert "Confidence: POSSIBLE" in data["report"]
        assert "[observation-1]" in data["report"]
        assert data["relay_events"]
        assert any(e.get("category") == "tool" for e in data["relay_events"])
        assert [c[0] for c in gateway.calls].count("triage") == 1
        assert client.get("/api/runs/" + run_id + "/download").status_code == 200


def test_failed_gate_cannot_be_drafted():
    async def scenario():
        run = Run(task="test", clip="civil-market")
        run.gateway = ScriptedGateway([])
        run.gate = {"valid": False}
        token = CURRENT.set(run)
        try:
            with pytest.raises(ValueError, match="validated"):
                await draft()
            assert not run.gateway.calls
        finally:
            CURRENT.reset(token)
    asyncio.run(scenario())


def test_unknown_clip_rejected():
    with TestClient(server.app) as client:
        assert client.post("/api/runs", json={"task": "inspect", "clip": "../secrets"}).status_code == 422
        assert client.get("/api/clips/unknown").status_code == 404


def test_reward_does_not_pay_for_abstaining_on_every_task():
    run = {"status": "complete", "events": [], "result": {"disposition": "HOLD", "released": False}}
    score = score_episode(run, {"disposition": "DRAFT", "required_tools": ["perceive", "triage", "draft"]})
    assert score["reward"] == 0 and not score["success"]


def test_reward_rejects_release_and_wrong_order():
    run = {"status": "complete", "events": [{"kind": "tool", "data": {"tool": t}} for t in ["triage", "perceive"]],
           "result": {"disposition": "REVIEW", "released": True}}
    score = score_episode(run, {"disposition": "REVIEW", "required_tools": ["perceive", "triage"]})
    assert score["reward"] == 0
    assert "release boundary violated or not recorded" in score["failures"]


def test_all_evidence_scores_are_loaded_from_artifacts():
    with TestClient(server.app) as client:
        scores = client.get("/api/info").json()["scores"]
        assert scores[1]["exact"] == 154 and scores[1]["n"] == 180
        assert scores[1]["weighted"] == pytest.approx(0.9524691358)


def test_nat_stops_for_unknown_specialist_category():
    with TestClient(server.app) as client:
        server.app.state.gateway = ScriptedGateway(
            ["perceive", "triage", "request_review"], {**VALID, "activity_type": "unknown_bridge"})
        run_id = client.post("/api/runs", json={"task": "Inspect and draft a report", "clip": "sample-drone-bridge"}).json()["id"]
        async def settle():
            await asyncio.gather(*list(server.TASKS))
        client.portal.call(settle)
        data = client.get("/api/runs/" + run_id).json()
        assert data["status"] == "complete"
        assert data["result"]["disposition"] == "HOLD"
        assert data["gate"]["destination"] is None
        assert data["report"] is None


def test_repeated_tool_does_not_loop_forever():
    with TestClient(server.app) as client:
        server.app.state.gateway = ScriptedGateway(["perceive", "perceive"])
        run_id = client.post("/api/runs", json={"task": "Describe the scene", "clip": "civil-market"}).json()["id"]
        async def settle():
            await asyncio.gather(*list(server.TASKS))
        client.portal.call(settle)
        data = client.get("/api/runs/" + run_id).json()
        assert data["status"] == "failed"
        assert data["result"]["disposition"] == "HOLD"
        assert "Repeated action" in data["error"]


def test_concurrent_live_requests_are_rejected():
    class SlowGateway(ScriptedGateway):
        async def call(self, *args, **kwargs):
            await asyncio.sleep(0.1)
            return await super().call(*args, **kwargs)
    with TestClient(server.app) as client:
        server.app.state.gateway = SlowGateway(["perceive", "finish"])
        payload = {"task": "Describe the scene only", "clip": "civil-market"}
        assert client.post("/api/runs", json=payload).status_code == 202
        assert client.post("/api/runs", json=payload).status_code == 409
        async def settle():
            await asyncio.gather(*list(server.TASKS))
        client.portal.call(settle)


def test_missing_source_reference_cannot_be_published_as_draft():
    class BadDraft(ScriptedGateway):
        async def call(self, *args, **kwargs):
            return json.dumps({"summary": "An unsupported report", "source_ids": []})
    async def scenario():
        run = Run(task="test", clip="civil-market")
        run.gateway = BadDraft([])
        run.evidence = {"id": "observation-1", "description": "People at a market"}
        run.item = VALID
        run.gate = validate_item(VALID)
        token = CURRENT.set(run)
        try:
            with pytest.raises(ValueError, match="evidence reference"):
                await draft()
            assert run.report is None
        finally:
            CURRENT.reset(token)
    asyncio.run(scenario())
