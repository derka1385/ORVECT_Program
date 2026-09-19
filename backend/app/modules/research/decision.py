"""Knowledge-first research gate.

Orvect does not query the web for every diagnosis. External research is only
worth its cost and latency when internal knowledge cannot carry the case. The
decision and the queries are both deterministic: no LLM round-trip is spent
deciding whether to spend an LLM round-trip.
"""

import re
from dataclasses import asdict, dataclass

from app.core.config import settings

# Enough compatible internal excerpts to answer without going outside.
INTERNAL_SUFFICIENCY_THRESHOLD = 3

# When ORVECT has already seen this situation resolved on compatible vehicles,
# by independent workshops, without contradiction, an external search adds cost
# and latency for evidence the platform already holds. The thresholds are
# deliberately strict: this is the one place where accumulated experience is
# allowed to *replace* looking something up, so it must be well supported.
FIELD_EVIDENCE_SUFFICIENT_LEVELS = {"engine_ecu", "engine"}
FIELD_EVIDENCE_MIN_CONFIRMED = 3
FIELD_EVIDENCE_MIN_GARAGES = 2
STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "et", "ou", "a", "au", "aux", "en",
    "the", "and", "with", "when", "that", "this", "for", "est", "sur", "dans", "par", "pas",
    "plus", "tres", "very", "quand", "avec", "mais", "son", "ses", "qui", "que",
}


@dataclass(frozen=True)
class ResearchPlan:
    needed: bool
    reasons: list[str]
    queries: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def keywords(text: str, limit: int) -> list[str]:
    """Stable content words. Shared with the Experience Engine so a symptom is
    keyed identically whether it is being searched for or being learned from."""
    words = re.findall(r"[a-zA-ZÀ-ÿ]{4,}", str(text or "").casefold())
    return list(dict.fromkeys(word for word in words if word not in STOPWORDS))[:limit]


def _vehicle_label(vehicle: dict) -> str:
    parts = [
        str(vehicle.get("model_year") or "").strip(),
        vehicle.get("make"),
        vehicle.get("model"),
        vehicle.get("engine_name") or vehicle.get("engine_code"),
    ]
    return " ".join(part for part in parts if part)


def build_queries(context: dict) -> list[str]:
    """Vehicle-specific queries. Never the bare fault code on its own."""
    vehicle = context.get("vehicle", {})
    label = _vehicle_label(vehicle)
    codes = [item.get("code") for item in context.get("fault_codes", []) if item.get("code")]
    if not codes:
        return []
    primary = codes[0]
    engine = vehicle.get("engine_code") or vehicle.get("engine_family") or ""
    symptoms = " ".join(
        keywords(context.get("untrusted_user_data", {}).get("symptoms"), 5)
    )
    queries = [f"{label} {' '.join(codes[:3])} common causes diagnosis".strip()]
    if engine:
        queries.append(
            f"{vehicle.get('make') or ''} {engine} {primary} {symptoms} technical service bulletin".strip()
        )
    elif symptoms:
        queries.append(f"{label} {primary} {symptoms} diagnosis".strip())
    if len(codes) > 1:
        queries.append(f"{label} {' '.join(codes[:3])} shared root cause".strip())
    elif label:
        queries.append(f"{label} {primary} recall technical service bulletin".strip())
    return [re.sub(r"\s+", " ", query) for query in queries][: settings.tavily_max_queries]


def _field_evidence_is_sufficient(field: dict) -> bool:
    """Does ORVECT's own evidence already answer this case convincingly?

    Requires a close vehicle match, several confirmed outcomes, more than one
    workshop, one consistent root cause and no contradiction. Anything less
    still goes out to search.
    """
    return bool(
        field.get("available")
        and field.get("network_backed")
        and field.get("best_level") in FIELD_EVIDENCE_SUFFICIENT_LEVELS
        and field.get("confirmed_cases", 0) >= FIELD_EVIDENCE_MIN_CONFIRMED
        and field.get("independent_garages", 0) >= FIELD_EVIDENCE_MIN_GARAGES
        and field.get("distinct_root_causes", 0) == 1
        and not field.get("contradicted")
    )


def decide_research(context: dict) -> ResearchPlan:
    """Decide whether external evidence would materially improve this diagnosis."""
    if not settings.research_enabled or not settings.tavily_api_key:
        return ResearchPlan(False, ["research_disabled"], [])

    definitions = context.get("technical_definitions", [])
    fault_codes = context.get("fault_codes", [])
    internal = context.get("internal_excerpts", context.get("technical_excerpts", []))
    vehicle = context.get("vehicle", {})
    reasons: list[str] = []

    if any(item.get("definition_type") == "manufacturer_specific" for item in definitions):
        reasons.append("manufacturer_specific_code")
    if any(not item.get("documented") for item in definitions):
        reasons.append("internal_definition_missing")
    if len(fault_codes) > 1:
        reasons.append("multiple_codes_need_shared_cause_evidence")
    if len(internal) < INTERNAL_SUFFICIENCY_THRESHOLD:
        reasons.append("internal_evidence_insufficient")
    if vehicle.get("engine_code") and not internal:
        reasons.append("engine_specific_failure_pattern_relevant")
    if str(context.get("untrusted_user_data", {}).get("symptoms") or "").strip() and not internal:
        reasons.append("symptoms_need_vehicle_specific_evidence")

    field = context.get("field_evidence_summary") or {}
    if field.get("contradicted"):
        # Conflicting field outcomes are exactly when an external source is
        # worth its cost, even if the rest of the case looks well covered.
        reasons.append("field_evidence_contradictory")
    elif field.get("available") and field.get("distinct_root_causes", 0) > 1:
        reasons.append("field_evidence_diverges_on_root_cause")

    if not reasons:
        return ResearchPlan(False, ["internal_knowledge_sufficient"], [])

    # Experience can only suppress the weaker triggers. A manufacturer-specific
    # code or a missing definition still needs authoritative confirmation:
    # accumulated observation never substitutes for a definition ORVECT lacks.
    blocking = {
        "manufacturer_specific_code", "internal_definition_missing",
        "field_evidence_contradictory", "field_evidence_diverges_on_root_cause",
    }
    if _field_evidence_is_sufficient(field) and not (set(reasons) & blocking):
        return ResearchPlan(False, ["orvect_field_evidence_sufficient", *reasons], [])
    queries = build_queries(context)
    if not queries:
        return ResearchPlan(False, ["no_query_could_be_built"], [])
    return ResearchPlan(True, reasons, queries)
