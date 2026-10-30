---
name: workshop-model-inventory
description: Inspect workshop model identities, discover serving aliases, probe base and specialist, and produce a verified endpoint manifest for notebook 01.
---

Use the inventory tool path supplied in the task. Read this skill before acting.
Run each action with exec, elevated=false, and report its actual result:

1. `python3 <tool_path> inventory` reads a timestamped host metadata snapshot.
   The sandbox does not directly inspect the host checkpoint files. Describe this
   evidence as a host-exported inventory, never as a sandbox filesystem scan.
2. `python3 <tool_path> models` discovers the current HTTP model IDs and roots.
3. `python3 <tool_path> probe-base` sends one fresh base request.
4. `python3 <tool_path> probe-specialist` sends one fresh specialist request.
5. `python3 <tool_path> manifest` writes the manifest and checks required evidence.

Run commands individually so students can follow their results. Repeated probe
actions reuse evidence within this run; they are not new inference calls.
Only report success when manifest status is PASS. If a tool fails, report the
error and stop. Preserve exact IDs, roots, finish reasons and measured latency.
Checkpoint cache presence does not prove which revision the server loaded:
report the API roots separately from the cached snapshot revisions.

Do not download weights, install packages, restart services, change configuration,
edit tools or evidence, or invent results. Do not propose NAT YAML in this lesson.
After the manifest, give a short summary with both probe times and finish reasons.

This installed OpenShell launcher can print `cannot create /proc/self/oom_score_adj:
Permission denied` before a successful tool result. That warning alone is not a
tool failure. Check the command exit status and the JSON event: a `result` with no
`error` means the tool completed. Continue with the next action in that case.
Never request elevated permissions to suppress the warning.
