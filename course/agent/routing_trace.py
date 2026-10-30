"""Notebook plumbing: real Switchyard routes and managed NeMo Relay calls."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import time
import uuid
from urllib.request import Request, urlopen

import nemo_relay as relay
os.environ.setdefault("RUST_LOG", "warn")
from switchyard_rust.server import Server

from course.common import ROOT, BASE_URL


def wait(factory):
    """Use managed async APIs from either a plain Python process or Jupyter."""
    async def resolve():
        return await factory()
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(resolve())
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, resolve()).result()


class Trace:
    def __init__(self, path, name="notebook-agent"):
        self.path = Path(path)
        self.name = name
        self.events = []
        self.subscriber = "course-" + uuid.uuid4().hex

    def __enter__(self):
        relay.subscribers.register(self.subscriber, lambda e: self.events.append(e.to_dict()))
        self.scope = relay.scope.scope(self.name, relay.ScopeType.Agent)
        self.handle = self.scope.__enter__()
        return self

    def __exit__(self, *exc):
        try:
            self.scope.__exit__(*exc)
        finally:
            try:
                wait(relay.subscribers.flush_async)
            finally:
                relay.subscribers.deregister(self.subscriber)
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(self.events, indent=2) + "\n")

    def tool(self, action, invoke):
        original_error = None
        async def call(args):
            nonlocal original_error
            try:
                return relay.ToolExecutionResult(invoke(args))
            except Exception as exc:
                original_error = exc
                raise
        try:
            return wait(lambda: relay.tools.execute(action["tool"], action, call,
                                           handle=self.handle)).result
        except RuntimeError:
            if original_error is not None:
                raise original_error
            raise

    def model(self, model, messages, invoke, **kwargs):
        """Also records injected model responses, explicitly named as fixtures."""
        async def call(request):
            return invoke(model, request.content["messages"], **kwargs)
        return wait(lambda: relay.llm.execute("injected-controller", relay.LLMRequest(
            {}, {"model": model, "messages": messages}), call, handle=self.handle))


@contextmanager
def model_router():
    """Reuse the browser demo's fixed routes, with the notebook endpoint override."""
    config = (ROOT / "run/workshop/configs/switchyard.toml").read_text()
    config = config.replace('http://127.0.0.1:8002/v1', BASE_URL.rstrip("/") + "/v1")
    with tempfile.TemporaryDirectory(prefix="course-switchyard-") as tmp:
        path = Path(tmp) / "routes.toml"
        path.write_text(config)
        with Server(path) as server:
            yield RoutedChat(server.base_url)


class RoutedChat:
    routes = {"base": "workshop-reason", "specialist": "workshop-triage"}

    def __init__(self, base_url, trace=None):
        self.base_url, self.trace = base_url, trace
        self.calls = []

    def __call__(self, model, messages, max_tokens=512, json_output=False):
        route = self.routes[model]
        payload = dict(model=route, messages=messages, temperature=0, max_tokens=max_tokens)
        if json_output:
            payload["response_format"] = {"type": "json_object"}
        start = time.monotonic()

        async def invoke(request):
            req = Request(self.base_url + "/v1/chat/completions",
                          data=json.dumps(request.content).encode(),
                          headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=120) as response:
                return json.load(response)

        if self.trace:
            out = wait(lambda: relay.llm.execute("switchyard", relay.LLMRequest({}, payload),
                       invoke, handle=self.trace.handle, model_name=model))
        else:
            out = wait(lambda: invoke(relay.LLMRequest({}, payload)))
        choice = out["choices"][0]
        row = {"route": route, "expected_model": model, "model": out.get("model"),
               "finish_reason": choice["finish_reason"],
               "seconds": round(time.monotonic() - start, 3),
               "answer": choice["message"].get("content")}
        self.calls.append(row)
        if out.get("model") != model:
            raise ValueError(f"Route {route} returned {out.get('model')}, expected {model}")
        if choice["finish_reason"] != "stop" or not row["answer"]:
            raise ValueError(f"Incomplete {route} response: {choice['finish_reason']}")
        return row["answer"]


def timeline(events):
    """Small readable view; the adjacent JSON retains full request/response evidence."""
    starts = {e["uuid"]: e for e in events if e.get("scope_category") == "start"}
    rows = []
    for event in events:
        if event.get("scope_category") != "end" or event.get("category") not in ("tool", "llm"):
            continue
        start = starts.get(event["uuid"], {})
        data = event.get("data") or {}
        row = {"kind": event["category"], "name": event["name"],
               "status": (event.get("metadata") or {}).get("otel.status_code", "unknown"),
               "event_id": event["uuid"]}
        if isinstance(data, dict) and "choices" in data:
            row.update(model=data.get("model"), finish_reason=data["choices"][0].get("finish_reason"))
        row["started"] = start.get("timestamp")
        rows.append(row)
    return rows


def print_timeline(events):
    for row in timeline(events):
        print(f"{row['kind']:4} | {row['name']:20} | {row['status']:7} | "
              f"{row.get('model', '')} {row.get('finish_reason', '')}")
