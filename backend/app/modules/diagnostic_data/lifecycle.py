from sqlalchemy.orm import Session
from sqlalchemy import or_, select

from app.database.models import (
    DiagnosticAliasReview,
    DiagnosticCodeAlias,
    DiagnosticDataset,
    DiagnosticDatasetEvent,
    DiagnosticDataConflict,
    DiagnosticDefinitionReview,
    DiagnosticDefinitionVariant,
    DiagnosticIdentifier,
    KnowledgeSource,
)
from .admission import admission_error, source_is_usable
from .conflicts import open_conflicts


STAGE_SEQUENCE = ("quarantined", "source_matched", "verified", "production")


class PromotionError(ValueError):
    pass


def _validate_next_stage(current: str, target: str):
    try:
        expected = STAGE_SEQUENCE[STAGE_SEQUENCE.index(current) + 1]
    except (ValueError, IndexError) as exc:
        raise PromotionError("Entry is not in a promotable lifecycle state") from exc
    if target != expected:
        raise PromotionError(f"Promotion must follow {current} -> {expected}; stages cannot be skipped")


def _validate_provenance(provenance: dict):
    required = {"record_id", "document_reference", "retrieved_at"}
    if not required.issubset(provenance) or any(not provenance.get(field) for field in required):
        raise PromotionError("Complete source provenance is required for promotion")


def promote_definition(
    db: Session,
    definition: DiagnosticDefinitionVariant,
    target_stage: str,
    reviewer_user_id: str,
    reason: str,
) -> DiagnosticDefinitionVariant:
    _validate_next_stage(definition.promotion_stage, target_stage)
    if definition.is_generated:
        raise PromotionError("Generated or approximate definitions can never be promoted")
    source = db.get(KnowledgeSource, definition.source_id)
    dataset = db.get(DiagnosticDataset, definition.dataset_id)
    identifier = db.get(DiagnosticIdentifier, definition.identifier_id)
    if (
        not dataset
        or not identifier
        or not dataset.legal_use_confirmed
        or dataset.status == "revoked"
        or dataset.source_id != definition.source_id
        or dataset.namespace_id != identifier.namespace_id
    ):
        raise PromotionError("The definition is not attached to a legally confirmed source dataset")
    if not source_is_usable(db, source) or definition.source_version != source.version:
        raise PromotionError("Source metadata or source version is not eligible for promotion")
    _validate_provenance(definition.provenance or {})
    if target_stage in {"verified", "production"} and source.review_status != "reviewed":
        raise PromotionError("Human-reviewed source metadata is required for verification and production")
    if target_stage == "production" and definition.verification_status != "verified":
        raise PromotionError("Only a verified definition can enter production")
    if target_stage in {"verified", "production"}:
        error = admission_error(db, definition)
        if error:
            raise PromotionError(error)
        if open_conflicts(db, definition.identifier_id):
            raise PromotionError("Unresolved source conflict blocks verification and production")

    previous = definition.promotion_stage
    definition.promotion_stage = target_stage
    definition.verification_status = "verified" if target_stage in {"verified", "production"} else "source_matched"
    if target_stage == "production":
        dataset.status = "active"
    db.add(
        DiagnosticDefinitionReview(
            definition_id=definition.id,
            from_stage=previous,
            to_stage=target_stage,
            reviewer_user_id=reviewer_user_id,
            source_id=definition.source_id,
            reason=reason,
        )
    )
    db.commit()
    return definition


def promote_alias(
    db: Session,
    alias: DiagnosticCodeAlias,
    target_stage: str,
    reviewer_user_id: str,
    reason: str,
) -> DiagnosticCodeAlias:
    _validate_next_stage(alias.promotion_stage, target_stage)
    if alias.is_generated:
        raise PromotionError("Generated or approximate aliases can never be promoted")
    source = db.get(KnowledgeSource, alias.source_id)
    dataset = db.get(DiagnosticDataset, alias.dataset_id)
    source_identifier = db.get(DiagnosticIdentifier, alias.source_identifier_id)
    if (
        not dataset
        or not source_identifier
        or not dataset.legal_use_confirmed
        or dataset.status == "revoked"
        or dataset.source_id != alias.source_id
        or dataset.namespace_id != source_identifier.namespace_id
    ):
        raise PromotionError("The alias is not attached to a legally confirmed source dataset")
    if not source_is_usable(db, source) or alias.source_version != source.version:
        raise PromotionError("Alias source metadata or source version is not eligible for promotion")
    _validate_provenance(alias.provenance or {})
    if target_stage in {"verified", "production"} and source.review_status != "reviewed":
        raise PromotionError("Human-reviewed source metadata is required for verification and production")
    if target_stage == "production" and alias.verification_status != "verified":
        raise PromotionError("Only a verified alias can enter production")
    if target_stage in {"verified", "production"}:
        error = admission_error(db, alias)
        if error:
            raise PromotionError(error)

    previous = alias.promotion_stage
    alias.promotion_stage = target_stage
    alias.verification_status = "verified" if target_stage in {"verified", "production"} else "source_matched"
    if target_stage == "production":
        dataset.status = "active"
    db.add(
        DiagnosticAliasReview(
            alias_id=alias.id,
            from_stage=previous,
            to_stage=target_stage,
            reviewer_user_id=reviewer_user_id,
            source_id=alias.source_id,
            reason=reason,
        )
    )
    db.commit()
    return alias


def revoke_dataset(db: Session, dataset: DiagnosticDataset, actor: str, reason: str):
    """Logical rollback preserves all source records/reviews and cannot be undone by re-import."""
    if dataset.status != "revoked":
        previous = dataset.status
        dataset.status = "revoked"
        db.add(DiagnosticDatasetEvent(dataset_id=dataset.id, action="revoked", actor_user_id=actor,
            reason=reason, details={"previous_status": previous}))
        db.commit()
    return dataset


def restore_dataset(db: Session, dataset: DiagnosticDataset, actor: str, reason: str):
    if dataset.status != "revoked":
        raise PromotionError("Only a revoked dataset can be restored")
    if not source_is_usable(db, db.get(KnowledgeSource, dataset.source_id)):
        raise PromotionError("Source rights must still be approved before restoration")
    rows = db.scalars(select(DiagnosticDefinitionVariant).where(DiagnosticDefinitionVariant.dataset_id == dataset.id)).all()
    ids = [row.id for row in rows]
    if db.scalar(select(DiagnosticDataConflict.id).where(
        DiagnosticDataConflict.status == "resolved_by_revocation",
        or_(DiagnosticDataConflict.left_definition_id.in_(ids), DiagnosticDataConflict.right_definition_id.in_(ids)),
    ).limit(1)):
        raise PromotionError("Restoration would reintroduce a conflict resolved by revocation; register a corrected version")
    aliases = db.scalars(select(DiagnosticCodeAlias).where(DiagnosticCodeAlias.dataset_id == dataset.id)).all()
    for row in [*rows, *aliases]:
        if row.promotion_stage == "production":
            error = admission_error(db, row)
            if error:
                raise PromotionError(error)
            identifier_id = row.identifier_id if isinstance(row, DiagnosticDefinitionVariant) else row.source_identifier_id
            if open_conflicts(db, identifier_id):
                raise PromotionError("An unresolved conflict blocks restoration")
    dataset.status = "active" if any(row.promotion_stage == "production" for row in [*rows, *aliases]) else "staged"
    db.add(DiagnosticDatasetEvent(dataset_id=dataset.id, action="restored", actor_user_id=actor, reason=reason))
    db.commit()
    return dataset
