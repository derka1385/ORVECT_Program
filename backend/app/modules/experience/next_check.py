"""Choose the next most useful diagnostic check.

This is a transparent deterministic heuristic, not an information-gain
computation. It does not claim to be optimal, and the rationale it returns
names every term that contributed, so a technician can overrule it knowingly.

It costs no model call: it re-ranks the plan the reasoning layer already
produced, using cost, time, discriminating power and what the workshop has
already done.
"""

import re

from app.modules.experience import signature

SELECTION_METHOD = "deterministic_heuristic_v1"

DIFFICULTY_SCORE = {"easy": 3, "intermediate": 2, "advanced": 1}
DIFFICULTY_WEIGHT = 2
DURATION_WEIGHT = 2
DISCRIMINATION_WEIGHT = 3
TOOLING_WEIGHT = 1
FIELD_EVIDENCE_WEIGHT = 3
# A check that can no longer separate any live hypothesis is not the next best
# action, whatever it costs. It stays in the plan but sinks below every check
# that still discriminates, so rejecting a hypothesis really does re-order the
# work rather than leaving a now-pointless test recommended.
IRRELEVANT_PENALTY = 20

# Matches the duration the reasoning layer puts at the head of `objective`,
# in any of the four report languages.
DURATION = re.compile(
    r"(?:Dur[ée]e estim[ée]e|Estimated duration|Uppskattad tid|Gesch[äa]tzte Dauer)\s*:\s*(\d+)",
    re.IGNORECASE,
)


def parse_minutes(objective: str) -> int | None:
    """Estimated duration the reasoning layer put at the head of `objective`."""
    found = DURATION.search(str(objective or ""))
    return int(found.group(1)) if found else None


def _duration_score(check: dict) -> tuple[int, int | None]:
    # Prefer the value persisted with the step; fall back to the plan text.
    minutes = check.get("estimatedMinutes") or parse_minutes(check.get("objective"))
    if not minutes:
        return 2, None
    return (3 if minutes <= 10 else 2 if minutes <= 30 else 1), minutes


def _discrimination(check: dict, hypotheses: list[dict]) -> int:
    """How many distinct hypotheses this check can actually separate.

    Measured by component and label overlap between the check and the ranked
    hypotheses. Crude but honest: a check that mentions only one hypothesis
    cannot depart the field, whatever it promises about itself.
    """
    haystack = signature.normalize(
        " ".join(
            [
                check.get("title", ""),
                check.get("objective", ""),
                " ".join(
                    f"{item.get('outcome', '')} {item.get('interpretation', '')}"
                    for item in check.get("expectedResults", []) or []
                ),
            ]
        )
    )
    touched = 0
    for hypothesis in hypotheses:
        tokens = [
            token
            for token in signature.normalize(
                f"{hypothesis.get('component') or ''} {hypothesis.get('label') or ''}"
            ).split()
            if len(token) >= 4
        ]
        if any(token in haystack for token in tokens):
            touched += 1
    # Two separable hypotheses is already a discriminating check; beyond three
    # the extra breadth usually means the check is vague, not powerful.
    return min(touched, 3)


def _field_support(check: dict, evidence: list[dict]) -> int:
    """Checks that ORVECT has actually seen discriminate in the field."""
    if not evidence:
        return 0
    title = signature.normalize(check.get("title", ""))
    if not title:
        return 0
    for item in evidence:
        for test in item.get("field_evidence", {}).get("discriminating_tests", []):
            known = signature.normalize(test.get("title", ""))
            if known and (known in title or title in known):
                return 1
    return 0


def rank(checks: list[dict], hypotheses: list[dict], completed_titles: set[str], evidence: list[dict] | None = None) -> list[dict]:
    """Score every outstanding check, best first, with its reasoning attached.

    `hypotheses` must be the LIVE ones only. Feeding rejected hypotheses back in
    would keep recommending the test that was supposed to eliminate them.
    """
    evidence = evidence or []
    done = {signature.normalize(title) for title in completed_titles}
    scored = []
    for position, check in enumerate(checks or []):
        if signature.normalize(check.get("title", "")) in done:
            continue
        difficulty = DIFFICULTY_SCORE.get(check.get("estimatedDifficulty"), 2)
        duration_score, minutes = _duration_score(check)
        discrimination = _discrimination(check, hypotheses)
        tools = len(check.get("requiredTools") or [])
        tooling_score = 3 if tools <= 1 else 2 if tools <= 3 else 1
        field = _field_support(check, evidence)
        score = (
            difficulty * DIFFICULTY_WEIGHT
            + duration_score * DURATION_WEIGHT
            + discrimination * DISCRIMINATION_WEIGHT
            + tooling_score * TOOLING_WEIGHT
            + field * FIELD_EVIDENCE_WEIGHT
        )
        rationale = [
            f"difficulté {check.get('estimatedDifficulty') or 'inconnue'}",
            f"durée {minutes} min" if minutes else "durée non précisée",
            f"départage {discrimination} hypothèse(s)",
            f"{tools} outil(s) requis",
        ]
        if field:
            rationale.append("contrôle discriminant déjà observé en atelier")
        if hypotheses and not discrimination:
            score -= IRRELEVANT_PENALTY
            rationale.append("ne départage plus aucune hypothèse restante")
        scored.append(
            {
                "check": check,
                "plan_order": check.get("order", position + 1),
                "score": score,
                "rationale": rationale,
                "selectionMethod": SELECTION_METHOD,
            }
        )
    # Ties fall back to the reasoning layer's own ordering, so the result stays
    # stable across identical runs.
    scored.sort(key=lambda item: (-item["score"], item["plan_order"]))
    return scored


def best(checks: list[dict], hypotheses: list[dict], completed_titles: set[str], evidence: list[dict] | None = None) -> dict | None:
    ranked = rank(checks, hypotheses, completed_titles, evidence)
    return ranked[0] if ranked else None
