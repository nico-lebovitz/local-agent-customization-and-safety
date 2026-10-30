---
name: triage-observation
description: Classify a recorded observation with the local specialist and return its validated destination; use when classification is requested without a report.
---
Obtain the selected clip's observation with `perceive`. Call `triage` on that evidence.
The tool sends the training prompt to the specialist and applies the Python contract.
If the gate rejects the proposal, use `request_review` with the reason, then `finish`.
Otherwise finish with the validated result. Do not call `draft` for this skill.
Use the gate's destination, even when it differs from the model's proposed routing.
The clip is one source; do not treat repeated descriptions as independent corroboration.
