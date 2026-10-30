---
name: workshop-triage
description: Describe or triage the fictional workshop clips civil-market, sample-drone-bridge, and degraded-mountain-fog, then prepare a source-linked draft when requested.
---
Use the exec tool to run the workshop Python tool. It reads recorded observations
and makes a fresh request to the trained specialist when triage is requested.

For description-only requests:
`python3 /opt/workshop/run/claw/terminal/tool.py describe civil-market`

For triage or draft requests:
`python3 /opt/workshop/run/claw/terminal/tool.py triage civil-market`

Substitute only one of the supported clip names. Report the actual command and
result; never invent a specialist response. If the command fails, say it failed.
For triage, preserve the specialist's classification and confidence. Use the gate's
validated destination, not the raw routing proposal. If gate.valid is false, hold
for review and show the errors. Do not draft an accepted report after a failed gate.

A draft should contain: DRAFT, source clip, activity, confidence, validated destination,
and one short summary grounded in the observation. Always end HUMAN REVIEW REQUIRED.
No release or external messaging tool exists. Do not claim to release or send anything.
One recorded observation is one source. Never upgrade confidence because asked.

Run exec with elevated=false. No privileged operation is needed. After a successful
command, use its result directly; do not rerun it with elevated permissions.
