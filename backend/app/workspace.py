import re
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import AuthContext, active_garage_id, authenticated_user_id, require_admin
from app.database.models import (
    AccountPreference,
    DiagnosticCompletion,
    DiagnosticContribution,
    DiagnosticDataConsent,
    DiagnosticEvent,
    DiagnosticHypothesis,
    DiagnosticObservation,
    DiagnosticSession,
    DiagnosticStep,
    DiagnosticTroubleCode,
    DTCSubmission,
    ProductAnalyticsEvent,
    VehicleProfile,
    now,
)
from app.database.session import get_db


router = APIRouter(tags=["workspace"])
CONSENT_VERSION = "diagnostic-sharing-v1"
ORVECT_VERSION = "beta-2026.09"
COMPLETION_STATUSES = {
    "problem_repaired", "repair_pending", "no_repair_required",
    "inconclusive", "referred_elsewhere", "other",
}
REVIEW_STATUSES = {"PENDING_REVIEW", "NEEDS_INFORMATION", "ACCEPTED", "REJECTED", "CONFLICT", "REVOKED"}
DTC_REVIEW_STATUSES = {"PENDING_REVIEW", "ACCEPTED", "REJECTED", "DUPLICATE", "CONFLICT", "NEEDS_INFORMATION"}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConsentInput(Strict):
    consent: bool = False
    consent_version: str = Field(default=CONSENT_VERSION, pattern=r"^[a-zA-Z0-9._-]{1,30}$")


class CompletionInput(Strict):
    resolution_status: Literal["problem_repaired", "repair_pending", "no_repair_required", "inconclusive", "referred_elsewhere", "other"]
    confirmed_cause: str = Field(default="", max_length=5000)
    selected_hypothesis_id: str | None = None
    repair_action_type: Literal["component_replaced", "wiring_repaired", "cleaning", "software_update", "coding_adaptation", "no_repair", "other"]
    repair_action_details: str = Field(default="", max_length=5000)
    components_involved: list[str] = Field(default_factory=list, max_length=50)
    root_cause_confidence: Literal["successful_repair", "measurement_test", "strongly_suspected", "not_confirmed"]
    post_repair_result: Literal["resolved", "partially_resolved", "not_resolved", "unknown_not_tested"]
    dtc_after_repair: Literal["cleared_no_return", "returned", "not_checked", "not_applicable"]
    technician_notes: str = Field(default="", max_length=5000)


class AmendmentInput(Strict):
    reason: str = Field(min_length=3, max_length=1000)
    correction: str = Field(min_length=1, max_length=5000)


class PreferenceInput(Strict):
    data_sharing_preference: Literal["ASK_EVERY_TIME", "DO_NOT_SHARE_BY_DEFAULT"]


class DTCSubmissionInput(Strict):
    code: str = Field(min_length=2, max_length=80)
    manufacturer: str = Field(min_length=1, max_length=120)
    ecu_module: str = Field(default="", max_length=120)
    description: str = Field(min_length=3, max_length=5000)
    vehicle: str = Field(default="", max_length=160)
    engine: str = Field(default="", max_length=120)
    platform: str = Field(default="", max_length=120)
    subcode: str = Field(default="", max_length=80)
    source_reference: str = Field(default="", max_length=2000)
    notes: str = Field(default="", max_length=5000)
    attested: bool

    @field_validator("code")
    @classmethod
    def normalized_code(cls, value: str) -> str:
        return re.sub(r"\s+", "", value).upper()


class ReviewInput(Strict):
    status: str
    notes: str = Field(default="", max_length=5000)


def serialize(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def owned_case(db: Session, session_id: str, garage_id: str) -> DiagnosticSession:
    case = db.scalar(select(DiagnosticSession).where(
        DiagnosticSession.id == session_id,
        DiagnosticSession.garage_id == garage_id,
    ))
    if not case:
        raise HTTPException(404, "Dossier diagnostic introuvable")
    return case


def analytics(db: Session, name: str, garage_id: str, user_id: str | None, session_id: str | None = None, metadata: dict | None = None):
    db.add(ProductAnalyticsEvent(
        garage_id=garage_id,
        user_id=user_id,
        session_id=session_id,
        event_name=name,
        event_metadata=metadata or {},
    ))


_SENSITIVE_KEYS = {
    "vin", "license_plate", "licence_plate", "plate", "registration", "registration_number",
    "customer", "customer_name", "name", "email", "phone", "telephone", "payment",
    "payment_information", "card", "card_number", "address",
}
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d .()-]{7,}\d)(?!\w)")
_VIN = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b", re.I)
_PLATE = re.compile(r"\b[A-Z]{2}[- ]?\d{3}[- ]?[A-Z]{2}\b", re.I)
_CARD = re.compile(r"\b(?:\d[ -]*?){13,19}\b")


def sanitize(value):
    if isinstance(value, dict):
        return {key: sanitize(item) for key, item in value.items() if key.lower() not in _SENSITIVE_KEYS}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        clean = value
        for pattern in (_EMAIL, _PHONE, _VIN, _PLATE, _CARD):
            clean = pattern.sub("[REDACTED]", clean)
        return clean
    return value


def latest_consent(db: Session, case_id: str) -> DiagnosticDataConsent | None:
    return db.scalar(select(DiagnosticDataConsent).where(
        DiagnosticDataConsent.session_id == case_id,
    ).order_by(DiagnosticDataConsent.recorded_at.desc()))


def build_contribution(db: Session, case: DiagnosticSession, completion: DiagnosticCompletion, consent: DiagnosticDataConsent) -> DiagnosticContribution:
    observations = db.scalars(select(DiagnosticObservation).where(DiagnosticObservation.session_id == case.id)).all()
    steps = db.scalars(select(DiagnosticStep).where(DiagnosticStep.session_id == case.id).order_by(DiagnosticStep.step_order)).all()
    hypotheses = db.scalars(select(DiagnosticHypothesis).where(DiagnosticHypothesis.session_id == case.id)).all()
    vehicle = db.get(VehicleProfile, case.vehicle_profile_id)
    dtcs = [item for item in observations if item.observation_type == "DTC"]
    measurements = [item for item in observations if item.observation_type == "measurement"]
    payload = {
        "vehicle": {
            "brand": vehicle.make, "model": vehicle.model, "year": vehicle.year,
            "platform": vehicle.market, "engine_code": vehicle.engine_code,
            "engine_family": vehicle.engine_name, "gearbox": vehicle.transmission,
        },
        "dtcs": [{"code": item.key, "ecu": item.value.get("ecu"), "subcode": item.value.get("sub_code"), "status": item.value.get("status"), "freeze_frame": item.value.get("freeze_frame", {})} for item in dtcs],
        "symptoms": case.observed_symptoms,
        "circumstances": case.appearance_circumstances,
        "measurements": [{"name": item.key, "value": item.value, "unit": item.unit, "source": item.source} for item in measurements],
        "tests": [{"title": item.title, "objective": item.objective, "result": item.result, "status": item.status} for item in steps],
        "hypotheses": [{"title": item.title, "component": item.suspected_component, "confidence": item.probability_score, "status": item.status, "verification": item.verification_status} for item in hypotheses],
        "confirmed_root_cause": completion.confirmed_cause,
        "repair": {"type": completion.repair_action_type, "details": completion.repair_action_details, "components": completion.components_involved},
        "post_repair_result": completion.post_repair_result,
        "dtc_after_repair": completion.dtc_after_repair,
        "confidence": completion.root_cause_confidence,
        "orvect_version": ORVECT_VERSION,
        "diagnostic_engine_version": case.prompt_version or case.ai_model or "unknown",
        "source_type": "WORKSHOP_CASE",
    }
    source_refs = sorted({ref.get("source_id") for item in hypotheses for ref in (item.source_references or []) if ref.get("source_id")})
    signature = sorted((item.key, (item.value or {}).get("ecu") or "") for item in dtcs)
    similar = db.scalars(select(DiagnosticContribution).where(DiagnosticContribution.status != "REVOKED")).all()
    conflicts = []
    for prior in similar:
        prior_dtcs = sorted((item.get("code"), item.get("ecu") or "") for item in prior.sanitized_payload.get("dtcs", []))
        if prior_dtcs == signature and prior.sanitized_payload.get("confirmed_root_cause") != completion.confirmed_cause:
            conflicts.append(prior.id)
    return DiagnosticContribution(
        session_id=case.id, consent_id=consent.id, garage_id=case.garage_id,
        submitted_by_user_id=completion.user_id, source_type="WORKSHOP_CASE",
        status="CONFLICT" if conflicts else "PENDING_REVIEW",
        sanitized_payload=sanitize(payload), provenance_references=source_refs,
        conflict_summary={"conflicting_contribution_ids": conflicts},
    )


@router.post("/api/diagnostics/{session_id}/consent", status_code=201)
def record_consent(session_id: str, data: ConsentInput, db: Session = Depends(get_db), garage_id: str = Depends(active_garage_id), user_id: str = Depends(authenticated_user_id)):
    owned_case(db, session_id, garage_id)
    row = DiagnosticDataConsent(session_id=session_id, garage_id=garage_id, user_id=user_id, consent=data.consent, consent_version=data.consent_version)
    db.add(row); db.commit(); db.refresh(row)
    return serialize(row)


@router.post("/api/diagnostics/{session_id}/complete", status_code=201)
def complete_diagnostic(session_id: str, data: CompletionInput, db: Session = Depends(get_db), garage_id: str = Depends(active_garage_id), user_id: str = Depends(authenticated_user_id)):
    case = owned_case(db, session_id, garage_id)
    if db.scalar(select(DiagnosticCompletion).where(DiagnosticCompletion.session_id == case.id)):
        raise HTTPException(409, "Ce diagnostic est déjà terminé. Ajoutez un amendement pour le corriger.")
    if data.selected_hypothesis_id and not db.scalar(select(DiagnosticHypothesis).where(DiagnosticHypothesis.id == data.selected_hypothesis_id, DiagnosticHypothesis.session_id == case.id)):
        raise HTTPException(422, "L’hypothèse sélectionnée n’appartient pas à ce diagnostic")
    completion = DiagnosticCompletion(session_id=case.id, garage_id=garage_id, user_id=user_id, **data.model_dump())
    case.status = "completed"; case.completed_at = now()
    db.add(completion)
    db.add(DiagnosticEvent(session_id=case.id, event_type="DiagnosticCompleted", payload=sanitize(data.model_dump()), actor_type="user", actor_id=user_id))
    analytics(db, "diagnostic_completed", garage_id, user_id, case.id, {"resolution_status": data.resolution_status})
    if data.post_repair_result == "resolved": analytics(db, "diagnostic_resolved", garage_id, user_id, case.id)
    if data.resolution_status == "inconclusive": analytics(db, "diagnostic_inconclusive", garage_id, user_id, case.id)
    db.flush()
    consent = latest_consent(db, case.id)
    contribution = None
    if consent and consent.consent:
        contribution = build_contribution(db, case, completion, consent)
        db.add(contribution); db.flush()
        analytics(db, "contribution_created", garage_id, user_id, case.id, {"status": contribution.status})
    db.commit(); db.refresh(completion)
    return {"completion": serialize(completion), "contribution": serialize(contribution) if contribution else None}


@router.post("/api/diagnostics/{session_id}/amendments", status_code=201)
def amend_diagnostic(session_id: str, data: AmendmentInput, db: Session = Depends(get_db), garage_id: str = Depends(active_garage_id), user_id: str = Depends(authenticated_user_id)):
    case = owned_case(db, session_id, garage_id)
    if case.status != "completed": raise HTTPException(409, "Les amendements concernent les diagnostics terminés")
    event = DiagnosticEvent(session_id=case.id, event_type="DiagnosticAmended", payload=sanitize(data.model_dump()), actor_type="user", actor_id=user_id)
    db.add(event); db.commit(); db.refresh(event)
    return serialize(event)


def history_rows(db: Session, garage_id: str):
    sessions = db.scalars(select(DiagnosticSession).where(DiagnosticSession.garage_id == garage_id).order_by(DiagnosticSession.created_at.desc())).all()
    rows = []
    for case in sessions:
        vehicle = db.get(VehicleProfile, case.vehicle_profile_id)
        completion = db.scalar(select(DiagnosticCompletion).where(DiagnosticCompletion.session_id == case.id))
        dtcs = [row.key for row in db.scalars(select(DiagnosticObservation).where(DiagnosticObservation.session_id == case.id, DiagnosticObservation.observation_type == "DTC")).all()]
        rows.append({"id": case.id, "status": case.status, "started_at": case.created_at, "completed_at": case.completed_at, "vehicle": {"id": vehicle.id, "make": vehicle.make, "model": vehicle.model, "year": vehicle.year}, "dtcs": dtcs, "outcome": completion.post_repair_result if completion else None, "resolution_status": completion.resolution_status if completion else None})
    return rows


def utc_value(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


@router.get("/api/workspace/dashboard")
def dashboard(db: Session = Depends(get_db), garage_id: str = Depends(active_garage_id), user_id: str = Depends(authenticated_user_id)):
    rows = history_rows(db, garage_id)
    started_this_month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    dtcs = {code for row in rows for code in row["dtcs"]}
    shared = db.scalar(select(func.count()).select_from(DiagnosticContribution).where(DiagnosticContribution.garage_id == garage_id)) or 0
    completed = [row for row in rows if row["status"] == "completed"]
    resolved = [row for row in rows if row["outcome"] == "resolved"]
    inconclusive = [row for row in rows if row["resolution_status"] == "inconclusive"]
    vehicle_count = len({row["vehicle"]["id"] for row in rows})
    preference = db.get(AccountPreference, user_id)
    return {"account": {"product": "ORVECT Beta", "plan": preference.plan if preference else "FREE", "monthly_price_eur": 0}, "metrics": {"total_diagnostics": len(rows), "completed_diagnostics": len(completed), "active_diagnostics": len(rows) - len(completed), "resolved_diagnostics": len(resolved), "inconclusive_diagnostics": len(inconclusive), "vehicles_diagnosed": vehicle_count, "unique_dtcs": len(dtcs), "diagnostics_this_month": sum(1 for row in rows if row["started_at"] and utc_value(row["started_at"]) >= started_this_month), "cases_shared": shared, "completion_rate": round(len(completed) / len(rows) * 100, 1) if rows else 0}, "recent_diagnostics": rows[:10]}


@router.get("/api/workspace/history")
def diagnostic_history(status: str | None = None, vehicle: str | None = None, dtc: str | None = None, date_from: datetime | None = None, date_to: datetime | None = None, db: Session = Depends(get_db), garage_id: str = Depends(active_garage_id)):
    rows = history_rows(db, garage_id)
    if status:
        if status == "active": rows = [r for r in rows if r["status"] != "completed"]
        elif status == "resolved": rows = [r for r in rows if r["outcome"] == "resolved"]
        elif status == "inconclusive": rows = [r for r in rows if r["resolution_status"] == "inconclusive"]
        else: rows = [r for r in rows if r["status"] == status]
    if vehicle:
        needle = vehicle.casefold(); rows = [r for r in rows if needle in f'{r["vehicle"]["make"]} {r["vehicle"]["model"]}'.casefold()]
    if dtc: rows = [r for r in rows if dtc.upper() in {code.upper() for code in r["dtcs"]}]
    if date_from: rows = [r for r in rows if utc_value(r["started_at"]) >= utc_value(date_from)]
    if date_to: rows = [r for r in rows if utc_value(r["started_at"]) <= utc_value(date_to)]
    return {"items": rows, "count": len(rows)}


@router.get("/api/workspace/settings")
def get_settings(db: Session = Depends(get_db), garage_id: str = Depends(active_garage_id), user_id: str = Depends(authenticated_user_id)):
    preference = db.get(AccountPreference, user_id)
    if not preference:
        preference = AccountPreference(user_id=user_id, garage_id=garage_id)
        db.add(preference); db.commit(); db.refresh(preference)
    total = db.scalar(select(func.count()).select_from(DiagnosticSession).where(DiagnosticSession.garage_id == garage_id)) or 0
    shared = db.scalar(select(func.count()).select_from(DiagnosticContribution).where(DiagnosticContribution.garage_id == garage_id)) or 0
    return {**serialize(preference), "diagnostics_performed": total, "cases_contributed": shared}


@router.put("/api/workspace/settings")
def update_settings(data: PreferenceInput, db: Session = Depends(get_db), garage_id: str = Depends(active_garage_id), user_id: str = Depends(authenticated_user_id)):
    preference = db.get(AccountPreference, user_id) or AccountPreference(user_id=user_id, garage_id=garage_id)
    preference.data_sharing_preference = data.data_sharing_preference
    db.add(preference); db.commit(); db.refresh(preference)
    return serialize(preference)


def duplicate_check(db: Session, data: DTCSubmissionInput):
    trusted = db.scalar(select(DiagnosticTroubleCode).where(func.upper(DiagnosticTroubleCode.code) == data.code))
    submissions = db.scalars(select(DTCSubmission).where(func.upper(DTCSubmission.code) == data.code, func.lower(DTCSubmission.manufacturer) == data.manufacturer.lower())).all()
    candidates = ([{"type": "trusted_dtc", "id": trusted.id, "description": trusted.generic_description}] if trusted else []) + [{"type": "submission", "id": row.id, "description": row.description, "status": row.status} for row in submissions]
    descriptions = [item["description"].strip().casefold() for item in candidates]
    exact = data.description.strip().casefold() in descriptions
    conflict = bool(candidates) and not exact
    return {"possible_duplicate": bool(candidates), "exact_description": exact, "conflict_detected": conflict, "candidates": candidates}


@router.post("/api/dtc-submissions/check")
def check_dtc_submission(data: DTCSubmissionInput, db: Session = Depends(get_db), garage_id: str = Depends(active_garage_id)):
    return duplicate_check(db, data)


@router.post("/api/dtc-submissions", status_code=201)
def submit_dtc(data: DTCSubmissionInput, db: Session = Depends(get_db), garage_id: str = Depends(active_garage_id), user_id: str = Depends(authenticated_user_id)):
    if not data.attested: raise HTTPException(422, "La confirmation de provenance ou d’observation réelle est obligatoire")
    check = duplicate_check(db, data)
    row = DTCSubmission(garage_id=garage_id, submitted_by_user_id=user_id, status="PENDING_REVIEW", duplicate_candidates=check["candidates"], conflict_detected=check["conflict_detected"], **sanitize(data.model_dump()))
    db.add(row); analytics(db, "dtc_submission_created", garage_id, user_id, metadata={"code": data.code, "possible_duplicate": check["possible_duplicate"]})
    db.commit(); db.refresh(row)
    return {"submission": serialize(row), "duplicate_check": check}


@router.get("/api/admin/review")
def review_queue(db: Session = Depends(get_db), auth: AuthContext = Depends(require_admin)):
    contributions = db.scalars(select(DiagnosticContribution).where(DiagnosticContribution.garage_id == auth.garage_id, DiagnosticContribution.status.in_(REVIEW_STATUSES)).order_by(DiagnosticContribution.created_at.desc())).all()
    submissions = db.scalars(select(DTCSubmission).where(DTCSubmission.garage_id == auth.garage_id, DTCSubmission.status.in_(DTC_REVIEW_STATUSES)).order_by(DTCSubmission.created_at.desc())).all()
    return {"contributions": [serialize(row) for row in contributions], "dtc_submissions": [serialize(row) for row in submissions]}


@router.patch("/api/admin/review/{kind}/{item_id}")
def review_item(kind: Literal["contribution", "dtc"], item_id: str, data: ReviewInput, db: Session = Depends(get_db), auth: AuthContext = Depends(require_admin)):
    model, statuses = (DiagnosticContribution, REVIEW_STATUSES) if kind == "contribution" else (DTCSubmission, DTC_REVIEW_STATUSES)
    if data.status not in statuses: raise HTTPException(422, "Statut de revue invalide")
    row = db.scalar(select(model).where(model.id == item_id, model.garage_id == auth.garage_id))
    if not row: raise HTTPException(404, "Contribution introuvable")
    row.status = data.status; row.review_notes = data.notes; row.reviewed_by_user_id = auth.user_id; row.reviewed_at = now()
    db.commit(); db.refresh(row)
    return serialize(row)
