"""Shared output contract and deterministic policy gates."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("workshop_jisr_rules", ROOT / "train/scripts/jisr_rules.py")
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)
RULES_PROMPT, ROUTING = rules.RULES_PROMPT, rules.ROUTING
PERMITTED = {
    "activity_type": set(rules.ACTIVITY_TYPES),
    "sensor_quality": {"CLEAR", "DEGRADED", "UNKNOWN"},
    "confidence": {"CONFIRMED", "PROBABLE", "POSSIBLE"},
    "routing": set(ROUTING.values()),
}


def validate_item(item, source_count=1):
    errors = []
    if not isinstance(item, dict):
        return {"valid": False, "errors": ["Output is not a JSON object"], "destination": None}
    if set(item) != set(PERMITTED):
        errors.append("Expected exactly four specified fields")
    for field, values in PERMITTED.items():
        value = item.get(field)
        if not isinstance(value, str) or value not in values:
            errors.append(f"Invalid {field}")
    if item.get("confidence") == "CONFIRMED" and source_count < 2:
        errors.append("R1: one source cannot establish corroboration")
    sensor = item.get("sensor_quality")
    if isinstance(sensor, str) and sensor in {"DEGRADED", "UNKNOWN"} and item.get("confidence") != "POSSIBLE":
        errors.append("R2: degraded or unknown feed requires POSSIBLE")
    activity = item.get("activity_type")
    destination = ROUTING.get(activity) if isinstance(activity, str) else None
    return {"valid": not errors, "errors": errors,
            "destination": destination if not errors else None,
            "model_proposed": item.get("routing"),
            "routing_overridden": not errors and item.get("routing") != destination,
            "release": "HUMAN_REVIEW_REQUIRED"}
