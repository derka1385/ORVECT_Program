"""Deterministic compatibility between a live case and historical evidence.

Compatibility is not a similarity guess: a pattern is only considered when the
vehicle actually matches on every dimension of its scope level. The score then
orders the surviving matches, and the explanation says exactly which dimensions
matched, so a technician can disagree with the machine on the facts.
"""

from dataclasses import dataclass, field

from . import signature, trust

# Corroboration adds to the ordering of field evidence. It is capped well below
# the weight of a specific vehicle match: many weakly-matched cases must never
# outrank one case on the same engine and ECU.
SUPPORT_BONUS = {trust.EMERGING: 0, trust.CORROBORATED: 8, trust.ESTABLISHED: 16}
MAX_SUPPORT_BONUS = max(SUPPORT_BONUS.values())

# A set-level DTC match means the same combination of codes was present, which
# is a stronger situational match than sharing one code.
DTC_SCOPE_BONUS = {"set": 10, "single": 0}

# Below this, evidence is not worth putting in front of a technician.
MIN_SCORE = 30


@dataclass
class Match:
    """Why a historical pattern was considered applicable to this case."""
    level: str
    score: int
    matched_on: list[str]
    dtc_scope: str
    dtc_signature: str
    support_label: str
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "level": self.level,
            "score": self.score,
            "matched_on": self.matched_on,
            "dtc_scope": self.dtc_scope,
            "dtc_signature": self.dtc_signature,
            "support_label": self.support_label,
            "notes": self.notes,
        }


def evaluate(case_dimensions: dict, case_codes, pattern) -> Match | None:
    """Score one pattern against the live case, or reject it outright.

    Returns None when the vehicle does not satisfy every dimension of the
    pattern's scope, or when the codes do not overlap as the pattern requires.
    A partial vehicle match is not a weak match: it is not a match.
    """
    required = signature.LEVEL_DIMENSIONS.get(pattern.scope_level)
    if required is None:
        return None
    scope = pattern.scope or {}
    matched_on = []
    for key in required:
        expected, actual = scope.get(key), case_dimensions.get(key)
        if not expected or not actual or expected != actual:
            return None
        matched_on.append(key)

    variants = dict(signature.dtc_variants(case_codes))
    live_set = variants.get("set", "")
    live_singles = set(live_set.split("|")) if live_set else set()
    if pattern.dtc_scope == "set":
        if pattern.dtc_signature != live_set:
            return None
    elif pattern.dtc_signature not in live_singles:
        return None
    matched_on.append("dtc_set" if pattern.dtc_scope == "set" else "dtc_code")

    score = signature.LEVEL_WEIGHT[pattern.scope_level]
    score += DTC_SCOPE_BONUS.get(pattern.dtc_scope, 0)
    score += SUPPORT_BONUS.get(pattern.support_label, 0)

    notes = []
    if pattern.contradicting_count:
        # Surfaced rather than silently folded into the score: a contradicted
        # pattern is exactly the situation a technician must see.
        notes.append("contradicted_cases_present")
    if pattern.dtc_scope == "single" and len(live_singles) > 1:
        notes.append("matched_on_one_code_of_several")
    return Match(
        level=pattern.scope_level,
        score=min(score, signature.LEVEL_WEIGHT["engine_ecu"] + DTC_SCOPE_BONUS["set"] + MAX_SUPPORT_BONUS),
        matched_on=matched_on,
        dtc_scope=pattern.dtc_scope,
        dtc_signature=pattern.dtc_signature,
        support_label=pattern.support_label,
        notes=notes,
    )


def acceptable(match: Match | None) -> bool:
    return bool(match and match.score >= MIN_SCORE)
