# JISR Watch-Floor — customization framework

**Pack:** `jisr-watchfloor` · **Status:** v3, reconciled against the implementation 5 Oct 2026
**Authority:** `train/scripts/jisr_rules.py` is the implementation. Where this document and
that file disagree, the file is correct. Sections 2, 4, 5 and 7 below are generated from it.
**Scenario:** EXERCISE NORTHERN SENTINEL. Entirely fictional, unclassified, synthetic.
BLUELAND (friendly) / REDLAND (opposing) exercise convention. No real persons, units,
locations or targets appear anywhere in this pack or its data.

> **Grading is deliberately NOTIONAL.** v1 of this pack used the Admiralty / NATO System
> (source reliability A–F, information credibility 1–6). Dropped, for a substantive reason:
> **Admiralty grades *sources* — reporting chains, networks, agents — not single automated
> observations.** A fixed sensor's reliability does not vary clip to clip, so applying A–F
> per-observation stretches the scale into a category error. In a room of analysts who know
> the standard cold, getting it subtly wrong costs more credibility than a clearly-fictional
> scale ever would.
>
> The EXERCISE NORTHERN SENTINEL scale below is obviously notional, teaches the identical
> lesson (structured grading, corroboration rules, measurable eval), and carries **zero risk
> of misrepresenting real doctrine**. Review is now desirable, not blocking.

---

## 1. Task definition

- **Input:** one observation — a field report, or an event/caption emitted by VSS from a
  sensor feed. Free text, one to three sentences, single observation.
- **Output:** one graded intelligence item: activity classification, confidence and sensor quality,
  priority, PIR match, routing decision, extracted entities, and a one-line rationale.
- **Out of scope:** multi-source fusion, correlation across time, target development,
  collection tasking. This task grades *one observation on its own merits*. Correlation is
  a downstream job and deliberately not modelled here.

## 2. Label space

Four scored fields. Generated from `jisr_rules.py` on 5 Oct 2026.

**`activity_type`** — 31 values:

```
  armour_movement, mech_infantry_movement, dismounted_patrol, wheeled_logistics_convoy
  engineer_activity, recovery_operation, air_defence_emplacement, artillery_emplacement
  field_fortification, obstacle_emplacement, radar_emission, comms_emission
  jamming_indicator, rotary_wing_transit, fixed_wing_transit, uav_transit
  airfield_activity, maritime_patrol, amphibious_activity, port_handling
  harbour_obstruction, bridge_damage, road_obstruction, rail_activity
  power_infrastructure, pipeline_activity, civil_displacement, civil_gathering
  humanitarian_convoy, checkpoint_activity, no_significant_activity
```

**`sensor_quality`** — `CLEAR`, `DEGRADED`, `UNKNOWN`

**`confidence`** — `CONFIRMED`, `PROBABLE`, `POSSIBLE`

**`routing`** — 4 destinations, assigned by lookup on `activity_type`:

| destination | categories | basis |
|---|---|---|
| `ARCHIVE` | 1 | nothing of note |
| `CIMIC` | 4 | civilian subject (R4) |
| `J2-ANALYSIS` | 19 | default |
| `J3-CURRENT-OPS` | 7 | infrastructure damage and obstruction |

No `priority`, `pir_match`, `entities`, `flags` or `rationale` field is produced or scored
in this build. R3, R5, R6 and R7 below describe them; they are specified, not implemented.

## 3. Decision rules

**R1, R2 and R4 are implemented** in `jisr_rules.gold_for()` and `ROUTING`, and they
determine the four scored fields. **R3, R5, R6 and R7 are specified and not implemented
in this build** — they govern `priority`, `pir_match`, `entities` and `flags`, none of
which this version produces. `TARGETING` is named in R5 but is not a value in `ROUTING`.

**Precedence:** feed quality beats corroboration. A corroborated report on a `DEGRADED`
feed is still `POSSIBLE`.


- **R1 — Confidence is capped by corroboration.** A single uncorroborated observation can
  never be `CONFIRMED`. Absent explicitly stated corroboration, the ceiling is `PROBABLE`.
- **R2 — `sensor_quality` describes the feed, not the content.** A clean EO/IR feed is
  `CLEAR`; obscured, low-light or dropped-frame is `DEGRADED` and also carries the
  `DEGRADED_SENSOR` flag; unattributed or forwarded material is `UNKNOWN`. A `DEGRADED` or
  `UNKNOWN` feed caps `confidence` at `POSSIBLE`.
- **R3 *(not implemented)* — Priority is set by PIR match and time sensitivity, not by how dramatic the
  observation is.** A PIR match with a perishable window is `IMMEDIATE`; a PIR match
  without one is `PRIORITY`; no PIR match is `ROUTINE`.
- **R4 — Civil activity routes to CIMIC.** Any observation whose primary subject is
  civilian persons, vehicles or infrastructure routes to `CIMIC` and carries
  `CIVIL_PRESENT`, regardless of what else is in the frame.
- **R5 *(not implemented; `TARGETING` is not a routing value)* — `TARGETING` requires an explicitly military subject *and* a PIR match.** Both.
  Absent either, route to `J2-ANALYSIS`.
- **R6 *(not implemented)* — Ambiguity is recorded, not resolved.** If the observation supports more than one
  `activity_type`, choose the most specific supported one and set `AMBIGUOUS`. Do not
  invent detail to disambiguate.
- **R7 *(not implemented)* — Extract only what is stated.** `entities` contains only what appears in the
  source text. Absent fields are omitted, never inferred or filled with plausible values.

## 4. Grading scale

Exact string match per field. The headline is a weighted mean; weights are
`eval_jisr.py WEIGHTS`.

| field | scoring | weight |
|---|---|---|
| `confidence` | exact match | 1.5 |
| `routing` | exact match | 1.5 |
| `activity_type` | exact match | 1.0 |
| `sensor_quality` | exact match | 0.5 |

Matching is case-sensitive. Constant-answer floors, published alongside any result:
always `POSSIBLE` scores 0.667 on confidence; always `J2-ANALYSIS` scores 0.633 on routing.

## 5. Unacceptable failures

U1 and U2 are scored automatically by `eval_jisr.py`. U3, U4 and U5 are specified and
not measured in this build. U2 is implemented as *gold routing is `CIMIC` and the
prediction is not*, which is broader than the wording below.

| ID | Failure | Why it is disqualifying |
|---|---|---|
| **U1** *(scored)* | Rating an uncorroborated single-source observation `CONFIRMED` | Manufactures certainty. Downstream consumers treat `CONFIRMED` as actionable. |
| **U2** *(scored as: gold routing is `CIMIC` and prediction is not)* | Civil activity routed anywhere other than `CIMIC` | The failure mode with real-world consequences. Non-negotiable. |
| **U3** *(not measured)* | Emitting an entity — unit designation, coordinate, count — not present in the source | A fabricated ORBAT entry is worse than no entry. Destroys trust in the whole pipeline. |
| **U4** *(not measured)* | Returning `NONE` for `pir_match` when the observation plainly satisfies a listed PIR | A silent miss. Nobody downstream knows it happened. |
| **U5** *(not measured)* | Output that is not schema-valid | Breaks the machine consumer; there is no human in this loop to repair it. |

**Gate:** U-class rate must be **0** on held-out. A model with a strong aggregate score and
any U-class failure does not ship. This gate is also the source of the Claw's standing
constraints in the employ section — U2 and U3 are precisely the things it may not do without a human.

## 6. House style — INTSUM line *(adapter C)*

One sentence, ≤ 25 words. Lead with the activity, then location, then time, then grading in
parentheses. No hedging adverbs. No speculation beyond the observation.

> `Four REDLAND tracked vehicles moving north on MSR AMBER vicinity JENSEN CORRIDOR at 0620Z (PROBABLE/CLEAR, PIR-01).`

Forbidden: "appears to", "possibly indicates", "it is assessed that", and any adjective of
significance ("significant", "notable", "concerning") — the grading conveys that.

## 7. Eval set

- **Size:** 180 items held out, generated from the same spec but curated and hand-checked.
- **Held-out:** generated from a disjoint scenario-seed set; no source observation appears
  in both train and eval.
- **Coverage:** every enum value in §2 and every rule R1–R7 appears at least once.
- **Adversarial:** at least 8 cases per U-class failure — in particular civil-activity items
  that superficially resemble military ones (U2), and items where a plausible-sounding unit
  designation is *absent* from the source and must not be invented (U3).

## 8. Footage sourcing

Licence-verified per clip. **Use:** [Pexels](https://www.pexels.com/license/) (commercial
use, no attribution) and Pixabay (same, but no standalone redistribution). Generic civilian
drone footage — ports, roads, floods, substations, construction — under the fictional
exercise overlay. Civilian subject matter makes the "synthetic and unclassified" claim
self-evident rather than asserted.

**Do not use:** VisDrone (CC BY-NC-SA 3.0), UAVid (CC BY-NC-SA 4.0), VIRAT (protection
agreement). All non-commercial; the ShareAlike terms would additionally infect derivative
work — our annotated data and potentially our adapters.

⚠️ Both permitted sources prohibit redistributing clips **standalone**. The take-home ships
derived artifacts — VSS events, structured items, eval sets — and links to sources. Never
raw video.
