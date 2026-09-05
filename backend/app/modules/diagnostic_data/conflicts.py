"""Conservative conflict detection; wording differences require human review."""
from sqlalchemy import select
from app.database.models import (
    DiagnosticDataConflict, DiagnosticDefinitionVariant, DiagnosticDataset,
    KnowledgeSource,
)
from .admission import assessment_for, source_is_usable


def overlapping_scope(left, right):
    if left.subtype and right.subtype and left.subtype != right.subtype:
        return False
    for key in ("manufacturer", "brand", "vehicle_platform", "model", "engine_code", "transmission_code", "ecu_module"):
        a, b = getattr(left, key), getattr(right, key)
        if a and b and a.strip().casefold() != b.strip().casefold():
            return False
    if left.ecu_identifiers and right.ecu_identifiers:
        if {x.casefold() for x in left.ecu_identifiers}.isdisjoint(x.casefold() for x in right.ecu_identifiers):
            return False
    return max(left.model_year_from or 0, right.model_year_from or 0) <= min(left.model_year_to or 9999, right.model_year_to or 9999)


def detect_conflicts(db, incoming):
    if incoming.is_generated or not source_is_usable(db, db.get(KnowledgeSource, incoming.source_id)):
        return
    others = db.scalars(select(DiagnosticDefinitionVariant).where(
        DiagnosticDefinitionVariant.identifier_id == incoming.identifier_id,
        DiagnosticDefinitionVariant.id != incoming.id,
        DiagnosticDefinitionVariant.is_generated.is_(False),
    )).all()
    for other in others:
        dataset = db.get(DiagnosticDataset, other.dataset_id)
        if dataset.status == "revoked" or not source_is_usable(db, db.get(KnowledgeSource, other.source_id)):
            continue
        if not overlapping_scope(other, incoming):
            continue
        if (" ".join(other.description.casefold().split()), other.failure_mode) == (" ".join(incoming.description.casefold().split()), incoming.failure_mode):
            continue
        def snapshot(row):
            source = db.get(KnowledgeSource, row.source_id)
            assessment = assessment_for(db, source.id)
            return {"definition_id": row.id, "description": row.description, "source_id": source.id,
                    "source_version": row.source_version, "authority": assessment.authority_level,
                    "admission_tier": (row.provenance or {}).get("admission_tier"),
                    "applicability": {key: getattr(row, key) for key in (
                        "manufacturer", "brand", "vehicle_platform", "model", "model_year_from", "model_year_to",
                        "engine_code", "transmission_code", "ecu_module", "ecu_identifiers", "subtype")}}
        db.add(DiagnosticDataConflict(identifier_id=incoming.identifier_id,
            left_definition_id=other.id, right_definition_id=incoming.id,
            competing_claims={"left": snapshot(other), "right": snapshot(incoming)}))


def open_conflicts(db, identifier_id):
    return db.scalars(select(DiagnosticDataConflict).where(
        DiagnosticDataConflict.identifier_id == identifier_id,
        DiagnosticDataConflict.status == "open",
    ).order_by(DiagnosticDataConflict.id)).all()
