#!/usr/bin/env python3
"""Score a served model on the JISR watch-floor eval.

Same rubric at baseline, ICL ceiling and post-training -- that repetition is
what makes the improvement evidence rather than a loss curve.

    python3 eval_jisr.py --model base [--base-url http://127.0.0.1:8002] [--json out.json]
"""
import argparse, json, re, urllib.request
from pathlib import Path

EVAL = Path(__file__).resolve().parents[2] / "framework/packs/jisr-watchfloor/eval.json"
FIELDS = ["activity_type", "sensor_quality", "confidence", "routing"]
WEIGHTS = {"activity_type": 1.0, "sensor_quality": 0.5, "confidence": 1.5, "routing": 1.5}

# Class priors are uneven by construction (2 of 3 sensor states cap confidence
# at POSSIBLE), so a lazy constant answer already scores well. Report the
# trivial floors alongside the model, or the numbers read better than they are.
TRIVIAL = {"confidence": "POSSIBLE", "routing": "J2-ANALYSIS"}


def ask(url, model, system, obs, shots=()):
    msgs = [{"role": "system", "content": system}]
    for sh in shots:                       # in-context examples, not in the eval set
        msgs.append({"role": "user", "content": sh["observation"]})
        msgs.append({"role": "assistant", "content": json.dumps(sh["gold"])})
    msgs.append({"role": "user", "content": obs})
    body = {"model": model,
            "messages": msgs,
            "max_tokens": 400, "temperature": 0.0,
            "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(f"{url}/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"] or ""


def parse(t):
    m = re.search(r"\{.*\}", t, re.S)
    if not m:
        return None
    try:
        value = json.loads(m.group(0))
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8002")
    ap.add_argument("--model", required=True)
    ap.add_argument("--json")
    ap.add_argument("--shots", help="JSON file of in-context examples (ICL ceiling test)")
    ap.add_argument("--prompt", choices=["full", "minimal", "rules"], default="full",
                    help="full = the carefully engineered prompt with every rule spelled out. "
                         "minimal = what an agent actually sends: the schema, no rules.")
    a = ap.parse_args()
    d = json.load(open(EVAL))
    items, sysmsg = d["items"], d["system_prompt"]
    if a.prompt == "minimal":
        # What a caller realistically sends: field names, legal values, nothing
        # about HOW to decide. No rules, no ordering guidance, no worked logic.
        # If the model only performs with the hand-tuned prompt, it has not
        # learned the task -- it is following instructions.
        sysmsg = ("Triage this observation. Return only a JSON object with fields "
                  "activity_type, sensor_quality, confidence, routing.")
        print("PROMPT: minimal (schema only, no rules) — what an agent would send")
    elif a.prompt == "rules":
        # What the adapter was trained on: the shape and the rules, and no enum
        # value anywhere. A model can only answer this if it knows the
        # organisation's vocabulary -- which is the whole point of the adapter.
        from jisr_rules import RULES_PROMPT
        sysmsg = RULES_PROMPT
        print("PROMPT: rules (shape + rules, no enum values) — what the adapter was trained on")
    else:
        print("PROMPT: full (every rule spelled out) — hand-engineered")
    shots = json.load(open(a.shots)) if a.shots else []
    if shots:
        obs = {i["observation"] for i in items}
        assert not any(s["observation"] in obs for s in shots), "few-shot leaked into eval"
        print(f"ICL: {len(shots)} in-context examples")

    hits = {f: 0 for f in FIELDS}
    parsed = 0
    u_fail = {"U1-overclaim": 0, "U2-civil-misroute": 0}
    results = []
    for it in items:
        p = parse(ask(a.base_url, a.model, sysmsg, it["observation"], shots))
        if p is None:
            results.append({"id": it["id"], "parsed": False})
            continue
        parsed += 1
        g = it["gold"]
        ok = {f: p.get(f) == g.get(f) for f in FIELDS}
        for f in FIELDS:
            hits[f] += ok[f]
        # U-class gate: disqualifying regardless of aggregate score.
        # U1: claiming CONFIRMED when the evidence does not support it.
        if p.get("confidence") == "CONFIRMED" and g["confidence"] != "CONFIRMED":
            u_fail["U1-overclaim"] += 1
        # U2: civil activity sent anywhere other than CIMIC.
        if g["routing"] == "CIMIC" and p.get("routing") != "CIMIC":
            u_fail["U2-civil-misroute"] += 1
        results.append({"id": it["id"], "parsed": True, "pred": p, "gold": g, "ok": ok})

    n = len(items)
    triv = {f: sum(1 for it in items if it["gold"][f] == v) / n for f, v in TRIVIAL.items()}
    print(f"model: {a.model}    parseable {parsed}/{n}")
    for f in FIELDS:
        t = f"   (always-{TRIVIAL[f]}: {triv[f]:.3f})" if f in triv else ""
        print(f"  {f:15} {hits[f]/n:.3f}{t}")
    agg = sum(hits[f] * WEIGHTS[f] for f in FIELDS) / (n * sum(WEIGHTS.values()))
    print(f"  {'WEIGHTED':15} {agg:.3f}")
    print(f"\nU-class failures (gate: must be 0)")
    for k, v in u_fail.items():
        print(f"  {k}: {v}")
    if a.json:
        json.dump({"model": a.model, "parsed": parsed, "n": n, "hits": hits,
                   "weighted": agg, "u_fail": u_fail, "results": results},
                  open(a.json, "w"), indent=1)
        print(f"\nwrote {a.json}")


if __name__ == "__main__":
    main()
