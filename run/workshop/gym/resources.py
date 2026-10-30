"""A real NeMo Gym Resources server for a tiny, offline tool-plan task.

The policy selects a plan; this verifier executes its state transitions. It never
accepts a policy-supplied reward or claimed tool result. No production tools run.
"""
import json
import secrets
from typing import ClassVar
from nemo_gym.base_resources_server import (
    BaseResourcesServerConfig, BaseVerifyRequest, BaseVerifyResponse,
    SimpleResourcesServer, ReverifyMode,
)
from nemo_gym.server_utils import ServerClient
from nemo_gym.config_types import BaseServerConfig
from omegaconf import OmegaConf
from pydantic import PrivateAttr

INTENTS = ["describe", "triage", "draft"]
PLANS = [
    {"id": "observe", "label": "Observe → finish", "tools": ["perceive", "finish"]},
    {"id": "classify", "label": "Observe → triage → finish", "tools": ["perceive", "triage", "finish"]},
    {"id": "report", "label": "Observe → triage → draft → review", "tools": ["perceive", "triage", "draft", "request_review"]},
    {"id": "skip_evidence", "label": "Triage → draft → review", "tools": ["triage", "draft", "request_review"]},
]
EXPECTED = {"describe": ["perceive", "finish"], "triage": ["perceive", "triage", "finish"],
            "draft": ["perceive", "triage", "draft", "request_review"]}


class Config(BaseResourcesServerConfig):
    REVERIFY_MODE: ClassVar[ReverifyMode] = ReverifyMode.STATELESS


class VerifyResponse(BaseVerifyResponse):
    intent: str
    plan_id: str
    transitions: list[dict]
    failures: list[str]
    released: bool = False


class WorkshopResources(SimpleResourcesServer):
    config: Config
    _session_secret: str = PrivateAttr(default_factory=lambda: secrets.token_urlsafe(32))

    def get_session_middleware_key(self):
        return self._session_secret

    async def verify(self, body: BaseVerifyRequest) -> VerifyResponse:
        # The task is provided by the training harness, never by generated output.
        intent = body.responses_create_params.input
        if intent not in EXPECTED:
            raise ValueError("Unknown task intent")
        failures, transitions, plan_id = [], [], "invalid"
        observed = classified = drafted = False
        try:
            output = body.response.output
            if len(output) != 1 or output[0].type != "message":
                raise ValueError("Expected one policy action")
            text = output[0].content[0].text
            action = json.loads(text)
            if set(action) != {"plan_id"}:
                raise ValueError("Only plan_id is allowed")
            plan_id = action["plan_id"]
            tools = next(plan["tools"] for plan in PLANS if plan["id"] == plan_id)
            for tool in tools:
                allowed = ((tool == "perceive" and not observed)
                           or (tool == "triage" and observed and not classified)
                           or (tool == "draft" and classified and not drafted)
                           or (tool == "request_review" and drafted)
                           or (tool == "finish" and observed))
                transitions.append({"tool": tool, "allowed": allowed})
                if not allowed:
                    failures.append("Evidence dependency failed: " + tool)
                    break
                observed |= tool == "perceive"
                classified |= tool == "triage"
                drafted |= tool == "draft"
            if tools != EXPECTED[intent]:
                failures.append("Plan does not match task's required tool sequence")
        except (ValueError, TypeError, AttributeError, IndexError, KeyError, StopIteration):
            failures.append("Invalid policy action")
        return VerifyResponse(**body.model_dump(), reward=float(not failures),
            intent=intent, plan_id=plan_id, transitions=transitions, failures=failures)


def create_app():
    config = Config(host="127.0.0.1", port=7862, entrypoint="resources.py", name="workshop_plan")
    client = ServerClient(head_server_config=BaseServerConfig(host="127.0.0.1", port=7862),
                          global_config_dict=OmegaConf.create({}))
    return WorkshopResources(config=config, server_client=client).setup_webserver()


app = create_app()


def request_payload(intent, plan_id):
    return {"responses_create_params": {"input": intent}, "response": {
        "id": "offline-policy-action", "created_at": 0, "model": "tiny-categorical-controller",
        "object": "response", "parallel_tool_calls": False, "tool_choice": "none", "tools": [],
        "output": [{"id": "action", "type": "message", "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "annotations": [],
                                 "text": json.dumps({"plan_id": plan_id})}]}]}}
