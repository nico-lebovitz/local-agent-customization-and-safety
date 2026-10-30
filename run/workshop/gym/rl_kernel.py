"""Load exact pinned upstream functions without the distributed training stack.

Only the named FunctionDef nodes are compiled, unchanged, from complete upstream
files. This demo uses NeMo RL's loss kernel, not its full trainer or LLM rollout
engine. SHA256 checks bind the functions to the recorded source manifest.
"""
import ast
import hashlib
import json
from pathlib import Path
from typing import Optional
import torch

VENDOR = Path(__file__).parent / "vendor"


def load_kernels():
    manifest = json.loads((VENDOR / "manifest.json").read_text())
    namespace = {"torch": torch, "Optional": Optional}
    for filename, names in [("utils.py", ["masked_mean", "calculate_baseline_and_std_per_prompt"]),
                            ("clipped_pg.py", ["clipped_pg_actor_objective"])]:
        source = (VENDOR / filename).read_bytes()
        if hashlib.sha256(source).hexdigest() != manifest["files"][filename]["sha256"]:
            raise RuntimeError("Pinned upstream source checksum changed: " + filename)
        parsed = ast.parse(source, filename=filename)
        selected = [node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name in names]
        if {node.name for node in selected} != set(names):
            raise RuntimeError("Missing expected upstream functions")
        exec(compile(ast.Module(body=selected, type_ignores=[]), filename, "exec"), namespace)
    return namespace, manifest
