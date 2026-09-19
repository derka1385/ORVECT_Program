"""Deterministic identity of a diagnostic situation and of its outcome.

Everything the Experience Engine learns is keyed by these functions. They are
pure, reproducible and free of any model call: two identical workshop
situations must always produce the same keys, on any machine, forever.
"""

import hashlib
import json
import re
import unicodedata

# Vehicle scope levels, most specific first. A case produces one signature per
# level whose dimensions it can fill, so the specificity hierarchy is derived
# from the data rather than hardcoded at retrieval time.
#
# There is deliberately no cross-manufacturer level: "same generic DTC" alone
# is not a defensible reason to carry a Golf finding onto an unrelated vehicle.
SCOPE_LEVELS: tuple[tuple[str, tuple[str, ...], int], ...] = (
    ("engine_ecu", ("brand", "engine_code", "ecu_model"), 100),
    ("engine", ("brand", "engine_code"), 80),
    ("platform", ("brand", "platform", "fuel_type"), 60),
    ("model", ("brand", "model"), 50),
    ("brand", ("brand",), 30),
)
LEVEL_WEIGHT = {name: weight for name, _, weight in SCOPE_LEVELS}
LEVEL_DIMENSIONS = {name: dimensions for name, dimensions, _ in SCOPE_LEVELS}

# Beyond this, listing more individual codes adds pattern rows without adding
# diagnostic value: the set-level signature already carries the combination.
MAX_SINGLE_CODE_SIGNATURES = 5


def normalize(value) -> str:
    """Casefolded, accent-free, whitespace-collapsed form used for every key."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip().casefold()


def dimensions(source: dict) -> dict:
    """Normalized vehicle dimensions, absent keys left out rather than empty."""
    mapping = {
        # Brand, not corporate group: "Volkswagen Group" would wrongly merge
        # Audi, Seat and Škoda findings under one key, and the two names do not
        # even agree between a stored case and a live context.
        "brand": source.get("make") or source.get("brand") or source.get("manufacturer"),
        "manufacturer_group": source.get("manufacturer"),
        "make": source.get("make"),
        "model": source.get("model"),
        "generation": source.get("generation"),
        "platform": source.get("platform") or source.get("vehicle_platform"),
        "engine_code": source.get("engine_code"),
        "engine_family": source.get("engine_family"),
        "fuel_type": source.get("fuel_type"),
        "transmission_type": source.get("transmission_type"),
        "drivetrain": source.get("drivetrain"),
        "ecu_manufacturer": source.get("ecu_manufacturer") or source.get("engine_ecu_manufacturer"),
        "ecu_model": source.get("ecu_model") or source.get("engine_ecu_model"),
    }
    return {key: normalize(value) for key, value in mapping.items() if normalize(value)}


def dtc_signature(codes) -> str:
    """Sorted, namespaced, de-duplicated code set. Order of entry never matters."""
    entries = set()
    for item in codes or []:
        if isinstance(item, dict):
            code, namespace = item.get("code"), item.get("namespace") or "sae_obd2"
        else:
            # Idempotent: an already-namespaced entry must not be prefixed twice,
            # otherwise a stored signature stops matching a freshly computed one.
            text = str(item or "")
            namespace, _, code = text.rpartition(":")
            namespace = namespace or "sae_obd2"
        code = normalize(code).upper()
        if code:
            entries.add(f"{normalize(namespace)}:{code}")
    return "|".join(sorted(entries))


def dtc_variants(codes) -> list[tuple[str, str]]:
    """(dtc_scope, signature) pairs a case should be learned under.

    The full set captures a shared-root-cause combination; each individual code
    lets a later single-code case still find the evidence.
    """
    full = dtc_signature(codes)
    if not full:
        return []
    variants = [("set", full)]
    singles = full.split("|")
    if len(singles) > 1:
        variants += [("single", code) for code in singles[:MAX_SINGLE_CODE_SIGNATURES]]
    return variants


def scope_signatures(vehicle_dimensions: dict) -> list[tuple[str, dict, int]]:
    """Every (level, scope, weight) this vehicle can legitimately support."""
    found = []
    for level, required, weight in SCOPE_LEVELS:
        if all(vehicle_dimensions.get(key) for key in required):
            found.append((level, {key: vehicle_dimensions[key] for key in required}, weight))
    return found


def outcome_key(root_cause_component: str, repair_action_type: str) -> tuple[str, str]:
    return normalize(root_cause_component), normalize(repair_action_type) or "other"


def pattern_key(
    level: str,
    scope: dict,
    dtc_scope: str,
    signature: str,
    root_cause_component: str,
    repair_action_type: str,
) -> str:
    payload = {
        "level": level,
        "scope": {key: scope[key] for key in sorted(scope)},
        "dtc_scope": dtc_scope,
        "dtc": signature,
        "cause": normalize(root_cause_component),
        "repair": normalize(repair_action_type),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def field_source_id(key: str) -> str:
    """Stable citable identifier for an ORVECT field-evidence item."""
    return "orvect:" + hashlib.sha1(key.encode()).hexdigest()[:16]
