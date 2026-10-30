"""JISR watch-floor task definition. Single source of truth.

The eval set and the SDG pipeline both import this, so training labels and eval
labels cannot drift apart.

DESIGN NOTE — why the taxonomy is the point
-------------------------------------------
Earlier versions used 10 generic categories (vehicle_movement, logistics, ...)
and leaned on derived rules for the rest. Measured outcome: a well-prompted base
model matched the customized one, because the categories were guessable and every
rule was stated in the prompt. There was nothing left for training to teach.

The categories below are deliberately specific to THIS organisation's reporting
scheme. A base model has never seen them and cannot guess them — asked without a
prompt listing every value, it invents its own vocabulary ("radar_pulse",
"earthworks") and returns output nothing downstream can consume.

That is the case customization actually solves: the knowledge lives in the
weights, so the caller does not have to carry it.
"""

# 31 categories, including an explicit no-significant-activity outcome.
# Specific to this fictional reporting vocabulary and recognizable enough
# that an analyst would recognise them.
ACTIVITY_TYPES = [
    # ground manoeuvre
    "armour_movement", "mech_infantry_movement", "dismounted_patrol",
    "wheeled_logistics_convoy", "engineer_activity", "recovery_operation",
    # emplacement
    "air_defence_emplacement", "artillery_emplacement", "field_fortification",
    "obstacle_emplacement",
    # emissions
    "radar_emission", "comms_emission", "jamming_indicator",
    # air
    "rotary_wing_transit", "fixed_wing_transit", "uav_transit", "airfield_activity",
    # maritime
    "maritime_patrol", "amphibious_activity", "port_handling", "harbour_obstruction",
    # infrastructure
    "bridge_damage", "road_obstruction", "rail_activity", "power_infrastructure",
    "pipeline_activity",
    # civil
    "civil_displacement", "civil_gathering", "humanitarian_convoy", "checkpoint_activity",
    # nothing of note. WITHOUT this the model is forced to pick one of the 29
    # above even when the feed shows nothing -- and it does, confidently. An
    # empty frame produced "airfield_activity" during testing, which is a
    # fabricated report reaching a watch floor from no evidence at all.
    "no_significant_activity",
]

# Which cell owns each category. A lookup, not a rule -- the model learns the
# association the same way it learns the vocabulary.
ROUTING = {
    **{a: "J2-ANALYSIS" for a in [
        "armour_movement", "mech_infantry_movement", "dismounted_patrol",
        "wheeled_logistics_convoy", "engineer_activity", "recovery_operation",
        "air_defence_emplacement", "artillery_emplacement", "field_fortification",
        "obstacle_emplacement", "radar_emission", "comms_emission", "jamming_indicator",
        "rotary_wing_transit", "fixed_wing_transit", "uav_transit", "airfield_activity",
        "maritime_patrol", "amphibious_activity"]},
    **{a: "J3-CURRENT-OPS" for a in [
        "bridge_damage", "road_obstruction", "rail_activity", "power_infrastructure",
        "pipeline_activity", "port_handling", "harbour_obstruction"]},
    **{a: "CIMIC" for a in [
        "civil_displacement", "civil_gathering", "humanitarian_convoy", "checkpoint_activity"]},
    "no_significant_activity": "ARCHIVE",
}

PLACES = ["MSR AMBER", "JENSEN CORRIDOR", "PORT KALDA", "HILL 412", "KESTREL BRIDGE",
          "the NORTHGATE substation", "VYRNA RIDGE", "the DELTA rail junction",
          "the CORMORANT coastal strip", "WAYPOINT SIERRA"]


def gold_for(activity_type, corroborated, sensor):
    """Derive the label. activity_type is the classification; the rest follows."""
    # R1 a single uncorroborated source can never be CONFIRMED
    # R2 a DEGRADED or UNKNOWN feed caps confidence at POSSIBLE
    if sensor in ("DEGRADED", "UNKNOWN"):
        confidence = "POSSIBLE"
    elif corroborated:
        confidence = "CONFIRMED"
    else:
        confidence = "PROBABLE"
    return {"activity_type": activity_type,
            "sensor_quality": sensor,
            "confidence": confidence,
            "routing": ROUTING[activity_type]}


SYSTEM_PROMPT = (
    "You are a JISR watch-floor triage assistant for EXERCISE NORTHERN SENTINEL. "
    "For each observation return a JSON object with exactly these fields:\n"
    "- activity_type: one of " + ", ".join(ACTIVITY_TYPES) + "\n"
    "- sensor_quality: one of CLEAR, DEGRADED, UNKNOWN\n"
    "- confidence: one of CONFIRMED, PROBABLE, POSSIBLE\n"
    "- routing: one of J2-ANALYSIS, J3-CURRENT-OPS, CIMIC, ARCHIVE\n"
    "Rules: a single uncorroborated source can never be CONFIRMED. A degraded or "
    "unclear feed caps confidence at POSSIBLE. If the observation reports nothing of "
    "note, use no_significant_activity and route to ARCHIVE - do not invent an "
    "activity that is not described.\n"
    "Return only the JSON object, no other text."
)

assert set(ROUTING) == set(ACTIVITY_TYPES), "every category needs a routing cell"

# The prompt used for training, evaluation and the demo app. It states the
# output shape and the rules, and deliberately names NO enum value -- not a
# category, not a confidence grade, not a destination. Those come from the
# adapter.
#
# It lives here beside ROUTING because the first adapter failed from prompt
# drift: training mixed four prompt styles while the app sent a fifth, so the
# comparison measured prompts rather than weights.
RULES_PROMPT = "Triage this observation and return only a JSON object with the fields activity_type, sensor_quality, confidence and routing.\nRules: a single uncorroborated source cannot be given the highest confidence grade. A degraded or unclear feed caps the confidence grade. If the observation reports nothing of note, classify it as such and send it to the archive. Use this organisation's standard terms for every field."
