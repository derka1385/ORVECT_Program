import re

from app.modules.diagnostic_ai.schemas import SafetyAssessment


SAFETY_RULE_VERSION = "safety-rules-v1"
STOP_CODES = {
    "P0217": "Engine over-temperature condition is reported.",
    "P0524": "Engine oil pressure is reported too low.",
}
DO_NOT_DRIVE_TERMS = {
    "brake failure",
    "no brakes",
    "fire",
    "flames",
    "fumée importante",
    "freins inopérants",
    "incendie",
}


def _contains_reported_term(text: str, term: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text))


class SafetyEngine:
    """Small deterministic safety boundary. It never calls an LLM."""

    def assess(self, context: dict) -> SafetyAssessment:
        codes = {
            item.get("code")
            for item in context.get("fault_codes", [])
            if item.get("status") in {"active", "confirmed", "permanent"}
        }
        matched = sorted(code for code in codes if code in STOP_CODES)
        text = " ".join(
            str(value).lower()
            for value in context.get("untrusted_user_data", {}).values()
            if value
        )
        symptom_matches = sorted(term for term in DO_NOT_DRIVE_TERMS if _contains_reported_term(text, term))
        if symptom_matches:
            return SafetyAssessment(
                status="DO_NOT_DRIVE",
                riskLevel="critical",
                drivingRecommendation="do_not_drive",
                explanation="A conservative safety rule matched a reported critical symptom. Human assessment is required.",
                humanReviewRequired=True,
                ruleIds=[f"{SAFETY_RULE_VERSION}:critical-symptom"],
                decisionSource="safety_engine",
            )
        if matched:
            return SafetyAssessment(
                status="STOP_AS_SOON_AS_SAFE",
                riskLevel="high",
                drivingRecommendation="stop_as_soon_as_safe",
                explanation="A conservative safety rule matched an active standardized fault code. Human assessment is required before further use.",
                humanReviewRequired=True,
                ruleIds=[f"{SAFETY_RULE_VERSION}:{code}" for code in matched],
                decisionSource="safety_engine",
            )
        return SafetyAssessment(
            status="UNKNOWN",
            riskLevel="unknown",
            drivingRecommendation="unknown",
            explanation="No reliable deterministic rule covers this case. The system does not infer safety from an LLM response.",
            humanReviewRequired=True,
            ruleIds=[f"{SAFETY_RULE_VERSION}:no-matching-rule"],
            decisionSource="safety_engine",
        )
