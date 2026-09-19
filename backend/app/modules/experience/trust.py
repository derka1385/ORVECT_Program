"""Knowledge trust classes.

ORVECT keeps four kinds of evidence apart, in storage, in the diagnostic
context and in the report. The separation exists so that accumulated field
observation can never quietly become manufacturer truth, however often it is
observed. Volume changes how well corroborated a field pattern is; it never
changes its class.
"""

# Ordered from most to least authoritative. The order is informational: it is
# what the prompt and the UI display, not a licence to average classes together.
AUTHORITATIVE = "authoritative_knowledge"
TECHNICAL_EXTERNAL = "technical_external_evidence"
ORVECT_FIELD = "orvect_field_evidence"
WEB_FIELD_SIGNAL = "web_field_signal"

TRUST_CLASSES = (AUTHORITATIVE, TECHNICAL_EXTERNAL, ORVECT_FIELD, WEB_FIELD_SIGNAL)

# Source type -> trust class. Any unknown type falls back to the weakest class:
# an unclassified source must never be promoted by accident.
SOURCE_TYPE_TRUST = {
    "orvect_catalog": AUTHORITATIVE,
    "oem_manufacturer": AUTHORITATIVE,
    "safety_authority": AUTHORITATIVE,
    "technical_documentation": TECHNICAL_EXTERNAL,
    "repair_technical_resource": TECHNICAL_EXTERNAL,
    "orvect_field_evidence": ORVECT_FIELD,
    "specialist_community": WEB_FIELD_SIGNAL,
    "general_web": WEB_FIELD_SIGNAL,
}

FIELD_EVIDENCE_SOURCE_TYPE = "orvect_field_evidence"

# Support tiers for an aggregated field pattern. Only `corroborated` and above
# may leave the workshop that produced the cases.
EMERGING = "emerging"
CORROBORATED = "corroborated"
ESTABLISHED = "established"
SUPPORT_ORDER = {EMERGING: 1, CORROBORATED: 2, ESTABLISHED: 3}

# Deliberately conservative. One workshop fixing one car establishes nothing,
# and a pattern with as many contradictions as confirmations is not evidence.
CORROBORATED_MIN_CONFIRMED = 2
CORROBORATED_MIN_GARAGES = 2
ESTABLISHED_MIN_CONFIRMED = 5
ESTABLISHED_MIN_GARAGES = 3
ESTABLISHED_MAX_CONTRADICTION_RATIO = 1 / 3


def trust_class(source_type: str) -> str:
    return SOURCE_TYPE_TRUST.get(str(source_type or ""), WEB_FIELD_SIGNAL)


def support_label(confirmed: int, garages: int, contradicting: int) -> str:
    """Tier of an aggregated pattern. Contradictions can only ever demote."""
    if confirmed <= 0:
        return EMERGING
    if (
        confirmed >= ESTABLISHED_MIN_CONFIRMED
        and garages >= ESTABLISHED_MIN_GARAGES
        and contradicting <= confirmed * ESTABLISHED_MAX_CONTRADICTION_RATIO
    ):
        return ESTABLISHED
    if (
        confirmed >= CORROBORATED_MIN_CONFIRMED
        and garages >= CORROBORATED_MIN_GARAGES
        and contradicting < confirmed
    ):
        return CORROBORATED
    return EMERGING


def shareable_support(label: str) -> bool:
    return SUPPORT_ORDER.get(label, 0) >= SUPPORT_ORDER[CORROBORATED]
