from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import AuthContext, active_garage_id, require_admin
from app.core.config import settings
from app.database.models import (
    DiagnosticCodeAlias,
    DiagnosticDataset,
    DiagnosticDefinitionVariant,
    DiagnosticSourceAssessment, DiagnosticDataConflict, DiagnosticDatasetEvent, KnowledgeSource,
    now,
    VehicleProfile,
)
from app.database.session import get_db

from .coverage import coverage_report
from .ingestion import DatasetAdapterUnavailable, DatasetIngestionError, ingest_dataset
from .lifecycle import PromotionError, promote_alias, promote_definition, revoke_dataset, restore_dataset
from .resolver import DiagnosticDataResolver, build_vehicle_context
from .schemas import (DiagnosticDatasetImport, DiagnosticResolveRequest, PromotionInput,
    SourceAssessmentInput, DatasetActionInput, ConflictResolutionInput)


router = APIRouter(prefix="/api/diagnostic-data", tags=["diagnostic-data"])
resolver = DiagnosticDataResolver()


def _serialize(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


@router.post("/resolve")
def resolve_diagnostic_identifier(
    data: DiagnosticResolveRequest,
    db: Session = Depends(get_db),
    garage_id: str = Depends(active_garage_id),
):
    context = {"ecu_module": data.ecu_module, "ecu_identifiers": data.ecu_identifiers}
    if data.vehicle_id:
        vehicle = db.scalar(
            select(VehicleProfile).where(
                VehicleProfile.id == data.vehicle_id,
                VehicleProfile.garage_id == garage_id,
            )
        )
        if not vehicle:
            raise HTTPException(404, "Vehicle not found for the active garage")
        context = build_vehicle_context(db, vehicle, data.ecu_module, data.ecu_identifiers)
    context["failure_type"] = data.failure_type
    return resolver.resolve(db, data.namespace, data.code, context)


@router.post("/sources/{source_id}/assessment", status_code=201)
def assess_source(source_id: str, data: SourceAssessmentInput, db: Session = Depends(get_db), auth: AuthContext = Depends(require_admin)):
    source = db.get(KnowledgeSource, source_id)
    if not source:
        raise HTTPException(404, "Register the knowledge source before assessing or importing it")
    if source.version != data.source_version:
        raise HTTPException(409, "Assessment must pin the registered source version")
    if not source.publisher or not source.license_type or not (source.source_url or source.local_file_path):
        raise HTTPException(422, "Publisher, licence and source location are required")
    if db.scalar(select(DiagnosticSourceAssessment).where(DiagnosticSourceAssessment.source_id == source_id)):
        raise HTTPException(409, "Source assessment is immutable; register a new source version for a new decision")
    row = DiagnosticSourceAssessment(source_id=source_id, assessed_by_user_id=auth.user_id, **data.model_dump())
    db.add(row)
    db.commit()
    return _serialize(row)


@router.get("/source-assessments")
def list_source_assessments(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
        db: Session = Depends(get_db), auth: AuthContext = Depends(require_admin)):
    rows = db.scalars(select(DiagnosticSourceAssessment).order_by(DiagnosticSourceAssessment.id).offset((page-1)*page_size).limit(page_size)).all()
    return {"items": [_serialize(r) for r in rows], "total": db.scalar(select(func.count()).select_from(DiagnosticSourceAssessment)), "page": page, "page_size": page_size}


@router.post("/sources/{source_id}/revoke")
def revoke_source(source_id: str, data: DatasetActionInput, db: Session = Depends(get_db), auth: AuthContext = Depends(require_admin)):
    row = db.scalar(select(DiagnosticSourceAssessment).where(DiagnosticSourceAssessment.source_id == source_id))
    if not row:
        raise HTTPException(404, "Source assessment not found")
    if row.status != "revoked":
        row.status, row.revocation_reason = "revoked", data.reason
        row.revoked_by_user_id, row.revoked_at = auth.user_id, now()
        db.commit()
    return _serialize(row)


@router.post("/datasets/{dataset_id}/{action}")
def dataset_action(dataset_id: str, action: Literal["revoke", "restore"], data: DatasetActionInput,
        db: Session = Depends(get_db), auth: AuthContext = Depends(require_admin)):
    dataset = db.get(DiagnosticDataset, dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    try:
        handler = revoke_dataset if action == "revoke" else restore_dataset
        return _serialize(handler(db, dataset, auth.user_id, data.reason))
    except PromotionError as exc:
        db.rollback()
        raise HTTPException(409, str(exc))


@router.get("/dataset-events")
def dataset_events(dataset_id: str, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
        db: Session = Depends(get_db), auth: AuthContext = Depends(require_admin)):
    query = select(DiagnosticDatasetEvent).where(DiagnosticDatasetEvent.dataset_id == dataset_id)
    rows = db.scalars(query.order_by(DiagnosticDatasetEvent.created_at, DiagnosticDatasetEvent.id).offset((page-1)*page_size).limit(page_size)).all()
    return {"items": [_serialize(r) for r in rows], "page": page, "page_size": page_size}


@router.get("/conflicts")
def conflicts(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
        db: Session = Depends(get_db), auth: AuthContext = Depends(require_admin)):
    rows = db.scalars(select(DiagnosticDataConflict).order_by(DiagnosticDataConflict.id).offset((page-1)*page_size).limit(page_size)).all()
    return {"items": [_serialize(r) for r in rows], "total": db.scalar(select(func.count()).select_from(DiagnosticDataConflict)), "page": page, "page_size": page_size}


@router.post("/conflicts/{conflict_id}/resolve")
def resolve_conflict(conflict_id: str, data: ConflictResolutionInput,
        db: Session = Depends(get_db), auth: AuthContext = Depends(require_admin)):
    row = db.get(DiagnosticDataConflict, conflict_id)
    if not row:
        raise HTTPException(404, "Conflict not found")
    if row.status != "open":
        raise HTTPException(409, "Conflict already resolved")
    if data.status == "resolved_by_revocation":
        definitions = [db.get(DiagnosticDefinitionVariant, key) for key in (row.left_definition_id, row.right_definition_id)]
        if not any(db.get(DiagnosticDataset, item.dataset_id).status == "revoked" for item in definitions):
            raise HTTPException(409, "Revoke the rejected dataset first")
    row.status, row.resolution_reason, row.resolved_by_user_id = data.status, data.reason, auth.user_id
    db.commit()
    return _serialize(row)


@router.post("/imports", status_code=201)
def import_diagnostic_dataset(
    data: DiagnosticDatasetImport,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_admin),
):
    try:
        row = ingest_dataset(db, data, auth.user_id)
    except DatasetAdapterUnavailable as exc:
        db.rollback()
        raise HTTPException(422, str(exc))
    except DatasetIngestionError as exc:
        db.rollback()
        raise HTTPException(409, str(exc))
    return _serialize(row)


@router.get("/datasets")
def list_datasets(
    page: int = Query(1, ge=1),
    page_size: int = Query(settings.default_page_size, ge=1, le=settings.max_page_size),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_admin),
):
    query = select(DiagnosticDataset).order_by(DiagnosticDataset.created_at.desc())
    total = db.scalar(select(func.count()).select_from(DiagnosticDataset)) or 0
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_serialize(row) for row in rows], "page": page, "page_size": page_size, "total": total}


@router.get("/definitions")
def list_definitions(
    stage: Literal["quarantined", "source_matched", "verified", "production"] | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(settings.default_page_size, ge=1, le=settings.max_page_size),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_admin),
):
    query = select(DiagnosticDefinitionVariant)
    if stage:
        query = query.where(DiagnosticDefinitionVariant.promotion_stage == stage)
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = db.scalars(
        query.order_by(DiagnosticDefinitionVariant.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {"items": [_serialize(row) for row in rows], "page": page, "page_size": page_size, "total": total}


@router.post("/definitions/{definition_id}/promote")
def promote_definition_route(
    definition_id: str,
    data: PromotionInput,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_admin),
):
    row = db.get(DiagnosticDefinitionVariant, definition_id)
    if not row:
        raise HTTPException(404, "Diagnostic definition not found")
    try:
        return _serialize(promote_definition(db, row, data.target_stage, auth.user_id, data.reason))
    except PromotionError as exc:
        db.rollback()
        raise HTTPException(409, str(exc))


@router.post("/aliases/{alias_id}/promote")
def promote_alias_route(
    alias_id: str,
    data: PromotionInput,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_admin),
):
    row = db.get(DiagnosticCodeAlias, alias_id)
    if not row:
        raise HTTPException(404, "Diagnostic alias not found")
    try:
        return _serialize(promote_alias(db, row, data.target_stage, auth.user_id, data.reason))
    except PromotionError as exc:
        db.rollback()
        raise HTTPException(409, str(exc))


@router.get("/aliases")
def list_aliases(
    stage: Literal["quarantined", "source_matched", "verified", "production"] | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(settings.default_page_size, ge=1, le=settings.max_page_size),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_admin),
):
    query = select(DiagnosticCodeAlias)
    if stage:
        query = query.where(DiagnosticCodeAlias.promotion_stage == stage)
    total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = db.scalars(
        query.order_by(DiagnosticCodeAlias.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {"items": [_serialize(row) for row in rows], "page": page, "page_size": page_size, "total": total}


@router.get("/coverage")
def diagnostic_coverage(
    group_by: Literal["namespace", "manufacturer", "brand", "ecu_module", "code_type"] = "namespace",
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_admin),
):
    return coverage_report(db, group_by)
