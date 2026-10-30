---
name: workshop-evaluate
description: Run the small evaluation and report actual scores, including malformed or incorrect answers.
---

Read this skill before using tools. The task supplies the absolute tool path.
Run these three actions individually with exec, elevated=false:

1. `python3 <tool_path> inspect-cases` — inspect the task and prerequisites.
2. `python3 <tool_path> evaluate` — execute the lesson and collect new results.
3. `python3 <tool_path> check-results` — check the results and save a report.

PASS means the evaluation ran and recorded its results, not that the model is accurate.

The tool asks the host notebook to run fixed lesson code. It cannot accept arbitrary
code or shell commands. Keep its reported results separate from your interpretation.
If exec returns a running session, poll it with process until it completes before
starting the next action. Repeated actions reuse this run's results.
Only report success after the final tool returns PASS. A genuine tool error means
stop and explain the error. Never invent an artifact or hide a failed check.

The OpenShell launcher may print a permission warning for `/proc/self/oom_score_adj`.
That warning alone is not failure: a JSON `result` and exit code 0 mean success. Continue to the next action without asking for permission. Do not treat the launcher warning as a host failure.
Never elevate permissions to suppress it. Do not install packages, download weights,
restart services, or change policies. End with the actual result in two short sentences.
