"""Fail-closed, field-by-field admission. No LLM or licence-name inference."""
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import (
    DiagnosticCodeAlias, DiagnosticDefinitionVariant, DiagnosticIdentifier,
    DiagnosticNamespace, DiagnosticSourceAssessment, KnowledgeSource,
)

ALLOWED_CATEGORIES = {"licensed_oem", "licensed_standard", "open_data"}


def assessment_for(db: Session, source_id: str):
    return db.scalar(select(DiagnosticSourceAssessment).where(DiagnosticSourceAssessment.source_id == source_id))


def source_is_usable(db: Session, source: KnowledgeSource | None) -> bool:
    if not source or source.review_status != "reviewed":
        return False
    assessment = assessment_for(db, source.id)
    return bool(
        assessment and assessment.source_version == source.version
        and assessment.status == "approved" and assessment.category in ALLOWED_CATEGORIES
        and assessment.content_rights_confirmed and assessment.commercial_use == "allowed"
        and assessment.redistribution in {"allowed", "attribution", "share_alike"}
        and assessment.licence_evidence and assessment.independent_origin
    )


def assertion_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def identifier_claim(db: Session, identifier_id: str) -> dict:
    identifier = db.get(DiagnosticIdentifier, identifier_id)
    namespace = db.get(DiagnosticNamespace, identifier.namespace_id)
    return {"namespace": namespace.key, "code": identifier.normalized_code}


def required_claims(db: Session, row) -> dict:
    if isinstance(row, DiagnosticCodeAlias):
        relation = {
            "source": identifier_claim(db, row.source_identifier_id),
            "target": identifier_claim(db, row.target_identifier_id),
            "relationship_type": row.relationship_type,
        }
        claims = {"alias_relationship": relation}
        if row.relationship_type == "generic_obd_equivalent":
            claims["generic_equivalence"] = relation
        return claims
    claims = {
        "code_existence": identifier_claim(db, row.identifier_id),
        "normalized_description": row.description,
    }
    if row.failure_mode or row.subtype:
        claims["failure_subtype"] = {"failure_mode": row.failure_mode, "subtype": row.subtype}
    ecu = {"ecu_module": row.ecu_module, "ecu_identifiers": row.ecu_identifiers or []}
    if ecu["ecu_module"] or ecu["ecu_identifiers"]:
        claims["ecu_applicability"] = ecu
    scope = {key: getattr(row, key) for key in (
        "manufacturer", "brand", "vehicle_platform", "model", "model_year_from", "model_year_to",
        "engine_code", "transmission_code",
    ) if getattr(row, key) is not None}
    if scope:
        claims["vehicle_applicability"] = scope
    return claims


def admission_error(db: Session, row) -> str | None:
    if row.is_generated:
        return "Generated or approximate records are permanently ineligible"
    if not source_is_usable(db, db.get(KnowledgeSource, row.source_id)):
        return "Source content rights have not been approved for commercial reuse and redistribution"
    provenance = row.provenance or {}
    tier = provenance.get("admission_tier")
    if tier not in {"A", "B"}:
        return "Tier A or B evidence is required; Tier C awaits an independently attested vehicle-observation workflow"
    for claim, value in required_claims(db, row).items():
        valid = []
        for evidence in provenance.get("claims", {}).get(claim, []):
            source = db.get(KnowledgeSource, evidence.get("source_id"))
            if (not source or evidence.get("source_version") != source.version
                    or evidence.get("confidence") != "supported"
                    or evidence.get("assertion_sha256") != assertion_hash(value)
                    or not evidence.get("document_reference") or not source_is_usable(db, source)):
                continue
            assessment = assessment_for(db, source.id)
            if assessment.authority_level in {"authoritative", "credible"}:
                valid.append(assessment)
        if tier == "A" and not any(a.authority_level == "authoritative" for a in valid):
            return f"Claim {claim} lacks authoritative, independently rights-cleared evidence"
        if tier == "B" and len({a.independent_origin.strip().casefold() for a in valid}) < 2:
            return f"Claim {claim} requires two technically independent reusable origins"
    return None


def rights_payload(db: Session, source: KnowledgeSource) -> dict:
    assessment = assessment_for(db, source.id)
    return {
        "content_rights_confirmed": source_is_usable(db, source),
        "source_category": assessment.category if assessment else "unknown_licence",
        "commercial_use": assessment.commercial_use if assessment else "uncertain",
        "redistribution": assessment.redistribution if assessment else "uncertain",
        "attribution_requirements": assessment.attribution_requirements if assessment else None,
        "assessment_id": assessment.id if assessment else None,
    }
