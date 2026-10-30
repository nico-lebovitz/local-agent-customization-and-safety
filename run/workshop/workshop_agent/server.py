"""Local presenter UI. Runs are serialized to protect Spark memory headroom."""
import asyncio
from contextlib import asynccontextmanager
import importlib.metadata
import json
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import httpx
import nemo_relay as relay
from pydantic import BaseModel, Field
from typing import Literal
import yaml
from switchyard_rust.server import Server
from nat.builder.workflow_builder import WorkflowBuilder
from nat.data_models.config import Config

from . import nat_workflow  # registers our NAT components
from .contracts import ROOT
from .runtime import CLIPS, CURRENT, Gateway, Run

HERE = Path(__file__).resolve().parent.parent
RUNS_DIR = HERE / "outputs"
RUNS = {}
TASKS = set()
ACTIVE = None


@asynccontextmanager
async def lifespan(app):
    global ACTIVE
    with Server(HERE / "configs/switchyard.toml") as router:
        app.state.gateway = Gateway(router.base_url)
        config = Config.model_validate(yaml.safe_load((HERE / "configs/workflow.yml").read_text()))
        async with WorkflowBuilder.from_config(config) as builder:
            app.state.workflow = builder.get_workflow()
            try:
                yield
            finally:
                for task in list(TASKS):
                    task.cancel()
                await asyncio.gather(*TASKS, return_exceptions=True)
                ACTIVE = None


app = FastAPI(title="The observation workshop", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


class Request(BaseModel):
    task: str = Field(min_length=5, max_length=1500)
    clip: str
    perception: Literal["recorded", "live"] = "recorded"


@app.get("/")
async def index():
    return FileResponse(HERE / "static/index.html")


@app.get("/api/info")
async def info():
    scores = []
    for label, filename, prompt, precision in [
        ("Base", "nvfp4-base-rules.json", "Rules only", "NVFP4"),
        ("Specialist", "nvfp4-spec-rules.json", "Rules only", "NVFP4"),
        ("Base", "lightning-base-full.json", "Full taxonomy", "BF16"),
        ("Specialist", "lightning-spec-full.json", "Full taxonomy", "BF16")]:
        data = json.loads((ROOT / "train/eval" / filename).read_text())
        scores.append({"label": label, "prompt": prompt, "precision": precision,
            "weighted": data["weighted"], "n": data["n"],
            "exact": sum(bool(r.get("ok")) and all(r["ok"].values()) for r in data["results"]),
            "failures": data["u_fail"], "source": "train/eval/" + filename})
    versions = {name: importlib.metadata.version(name) for name in ["nvidia-nat", "nemo-relay", "nemo-switchyard"]}
    baselines = [json.loads((HERE / "eval" / name).read_text())
                 for name in ["baseline-initial.json", "baseline-constrained.json"]]
    return {"clips": CLIPS, "scores": scores, "versions": versions, "baselines": baselines,
            "routing": "Switchyard explicit task routes; adaptive classifier not enabled",
            "training": "CPU teaching controller trained with Gym rewards and NeMo RL loss kernels; production Lightning weights unchanged."}


async def vss_connection():
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get("http://127.0.0.1:8000/openapi.json")
            response.raise_for_status()
            if "/generate" not in response.json().get("paths", {}):
                raise ValueError("VSS generate endpoint missing")
        return {"ready": True}
    except Exception as error:
        return {"ready": False, "error": type(error).__name__}


@app.get("/api/health")
async def health():
    async def check(url):
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                r = await client.get(url)
                r.raise_for_status()
                return {"ready": True}
        except Exception as e:
            return {"ready": False, "error": type(e).__name__}
    model, vss, perception = await asyncio.gather(check("http://127.0.0.1:8002/v1/models"),
                                    check("http://127.0.0.1:3000"), vss_connection())
    return {"lightning": model, "vss_ui": vss, "vss_perception": perception,
            "active_run": ACTIVE, "nat": True, "relay": True, "switchyard": True}


@app.get("/api/clips/{clip}")
async def clip_video(clip: str):
    if clip not in CLIPS:
        raise HTTPException(404)
    path = ROOT / "run/chain/clips" / (clip + ".mp4")
    if not path.is_file():
        raise HTTPException(404, "Video remains a local asset and is not included in Git")
    return FileResponse(path, media_type="video/mp4")


async def execute(run):
    global ACTIVE
    token = CURRENT.set(run)
    subscriber = "workshop-" + run.id
    relay.subscribers.register(subscriber, lambda event: run.relay_events.append(event.to_dict()))
    try:
        with relay.scope.scope("observation-workshop", relay.ScopeType.Agent) as handle:
            run.handle = handle
            run.emit("start", "Run started", task=run.task, perception=run.perception,
                     models="live", routing="explicit Switchyard routes", training="untrained controller")
            try:
                async with asyncio.timeout(run.deadline_seconds):
                    run.result = await app.state.workflow.ainvoke(run.task)
                run.status = "complete"
                run.emit("complete", "Run complete", result=run.result)
            except asyncio.CancelledError:
                run.status = "cancelled"
                run.result = {"disposition": "HOLD", "released": False}
                run.emit("error", "Run cancelled", result=run.result)
                raise
            except Exception as e:
                run.status, run.error = "failed", str(e) or type(e).__name__
                run.result = {"disposition": "HOLD", "released": False}
                run.emit("error", "Run held", error=run.error, result=run.result)
    finally:
        run.handle = None
        await relay.subscribers.flush_async()
        relay.subscribers.deregister(subscriber)
        CURRENT.reset(token)
        RUNS_DIR.mkdir(exist_ok=True)
        (RUNS_DIR / (run.id + ".json")).write_text(json.dumps(run.public(), indent=2, default=str))
        ACTIVE = None


@app.post("/api/runs", status_code=202)
async def start_run(request: Request):
    global ACTIVE
    if ACTIVE:
        raise HTTPException(409, "One run is already active; wait before starting another")
    if request.clip not in CLIPS:
        raise HTTPException(422, "Unknown clip")
    if request.perception == "live" and not (await vss_connection())["ready"]:
        raise HTTPException(503, "Live VSS is unavailable on port 8000. Use recorded descriptions or start the workshop live-video stack.")
    # The availability probe yields; recheck serialization before creating a run.
    if ACTIVE:
        raise HTTPException(409, "One run is already active; wait before starting another")
    run = Run(**request.model_dump())
    run.gateway = app.state.gateway
    RUNS[run.id] = run
    ACTIVE = run.id
    task = asyncio.create_task(execute(run))
    TASKS.add(task)
    task.add_done_callback(TASKS.discard)
    return {"id": run.id}


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    if run_id in RUNS:
        return RUNS[run_id].public()
    return json.loads(stored_path(run_id).read_text())


@app.get("/api/runs/{run_id}/download")
async def download(run_id: str):
    if run_id in RUNS and RUNS[run_id].status == "running":
        raise HTTPException(404, "Completed run not found")
    path = stored_path(run_id)
    return FileResponse(path, media_type="application/json", filename=f"workshop-run-{run_id}.json")


def stored_path(run_id):
    if not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise HTTPException(404)
    for directory in [RUNS_DIR, HERE / "eval/records"]:
        path = directory / (run_id + ".json")
        if path.is_file():
            return path
    raise HTTPException(404, "Recorded run not found")


@app.get("/api/training-demo")
async def training_demo():
    """Recorded CPU experiment; this endpoint never launches training."""
    path = HERE / "gym/artifacts/demo.json"
    if not path.is_file():
        raise HTTPException(404, "Run gym/train_demo.py to capture the teaching experiment")
    return json.loads(path.read_text())


@app.get("/api/training-demo/download")
async def training_demo_download():
    path = HERE / "gym/artifacts/demo.json"
    if not path.is_file():
        raise HTTPException(404, "Training demonstration artifact not found")
    return FileResponse(path, media_type="application/json", filename="workshop-gym-rl-demo.json")
