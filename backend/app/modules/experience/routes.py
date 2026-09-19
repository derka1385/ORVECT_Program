"""API for the outcome workflow and ORVECT's accumulated intelligence.

Tenant isolation follows the existing pattern: the active garage comes from the
server-side membership, never from the client. Cross-workshop knowledge is only
ever returned as an aggregate.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import AuthContext, active_garage_id, authenticated_user_id, require_admin
from app.database.models import (
    DiagnosticHypothesis,
    DiagnosticSession,
    DiagnosticStep,
    ExperienceCase,
    ExperiencePattern,
    ExperiencePatternCase,
    HypothesisOutcome,
    HypothesisStateEvent,
    VehicleProfile,
    now,
)
from app.database.session import get_db

from . import aggregation, capture, metrics, retrieval, signature

router = APIRouter(tags=["orvect-intelligence"])

MAX_WINDOW_DAYS = 365


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HypothesisVerdictInput(Strict):
    # `undetermined` exists so a technician can say "not settled" without that
    # being stored as either a confirmation or a rejection.
    verdict: Literal["confirmed", "rejected", "undetermined"]
    evidence_note: str = Field(default="", max_length=2000)


def _owned_case(db: Session, case_id: str, garage_id: str) -> DiagnosticSession:
    row = db.scalar(
        select(DiagnosticSession).where(
            DiagnosticSession.id == case_id, DiagnosticSession.garage_id == garage_id
        )
    )
    if not row:
        raise HTTPException(404, "Dossier diagnostic introuvable")
    return row


@router.post("/api/diagnostics/{case_id}/hypotheses/{hypothesis_id}/verdict", status_code=201)
def record_verdict(
    case_id: str,
    hypothesis_id: str,
    data: HypothesisVerdictInput,
    db: Session = Depends(get_db),
    garage_id: str = Depends(active_garage_id),
    user_id: str = Depends(authenticated_user_id),
):
    """Technician verdict on one hypothesis, with its history entry."""
    case = _owned_case(db, case_id, garage_id)
    hypothesis = db.scalar(
        select(DiagnosticHypothesis).where(
            DiagnosticHypothesis.id == hypothesis_id, DiagnosticHypothesis.session_id == case.id
        )
    )
    if not hypothesis:
        raise HTTPException(404, "Hypothèse introuvable dans ce dossier")
    existing = db.scalar(
        select(HypothesisOutcome).where(HypothesisOutcome.hypothesis_id == hypothesis.id)
    )
    previous = existing.verdict if existing else None
    if existing:
        existing.verdict = data.verdict
        existing.evidence_note = data.evidence_note
        existing.recorded_at = now()
        outcome = existing
    else:
        outcome = HypothesisOutcome(
            session_id=case.id,
            hypothesis_id=hypothesis.id,
            garage_id=garage_id,
            user_id=user_id,
            verdict=data.verdict,
            evidence_note=data.evidence_note,
        )
        db.add(outcome)
    db.add(
        HypothesisStateEvent(
            session_id=case.id,
            hypothesis_id=hypothesis.id,
            hypothesis_label=hypothesis.title[:200],
            event_type="technician_verdict",
            strength_before=hypothesis.probability_score,
            status_before=hypothesis.status,
            status_after=data.verdict,
            decision_source="technician",
            detail={"previous_verdict": previous, "note": data.evidence_note[:500]},
        )
    )
    # The ranking row records the verdict, but a rejected hypothesis is never
    # deleted: the case must stay reconstructable exactly as it was reasoned.
    if data.verdict == "rejected":
        hypothesis.status = "rejected"
    elif data.verdict == "confirmed":
        hypothesis.verification_status = "verified"
    db.commit()
    db.refresh(outcome)
    return {
        "hypothesis_id": hypothesis.id,
        "verdict": outcome.verdict,
        "recorded_at": outcome.recorded_at.isoformat(),
    }


@router.get("/api/diagnostics/{case_id}/evolution")
def diagnostic_evolution(
    case_id: str,
    db: Session = Depends(get_db),
    garage_id: str = Depends(active_garage_id),
):
    """Full auditable history of how this diagnosis moved."""
    case = _owned_case(db, case_id, garage_id)
    events = db.scalars(
        select(HypothesisStateEvent)
        .where(HypothesisStateEvent.session_id == case.id)
        .order_by(HypothesisStateEvent.created_at)
    ).all()
    steps = db.scalars(
        select(DiagnosticStep)
        .where(DiagnosticStep.session_id == case.id)
        .order_by(DiagnosticStep.step_order)
    ).all()
    verdicts = db.scalars(
        select(HypothesisOutcome).where(HypothesisOutcome.session_id == case.id)
    ).all()
    return {
        "case_id": case.id,
        "status": case.status,
        "timeline": [
            {
                "at": item.created_at.isoformat(),
                "event": item.event_type,
                "hypothesis": item.hypothesis_label,
                "hypothesis_id": item.hypothesis_id,
                "rank": item.rank_position,
                "strength_before": item.strength_before,
                "strength_after": item.strength_after,
                "status_before": item.status_before,
                "status_after": item.status_after,
                "result_state": item.result_state,
                "step_id": item.step_id,
                "decision_source": item.decision_source,
                "detail": item.detail,
            }
            for item in events
        ],
        "steps": [
            {
                "id": item.id,
                "order": item.step_order,
                "title": item.title,
                "status": item.status,
                "result": item.result,
                "completed_at": item.completed_at.isoformat() if item.completed_at else None,
            }
            for item in steps
        ],
        "verdicts": [
            {
                "hypothesis_id": item.hypothesis_id,
                "verdict": item.verdict,
                "recorded_at": item.recorded_at.isoformat(),
            }
            for item in verdicts
        ],
    }


@router.get("/api/diagnostics/{case_id}/field-evidence")
def case_field_evidence(
    case_id: str,
    db: Session = Depends(get_db),
    garage_id: str = Depends(active_garage_id),
):
    """Compatible ORVECT experience for this case, aggregated only."""
    from app.modules.diagnostic_ai.context_builder import DiagnosticContextBuilder

    case = _owned_case(db, case_id, garage_id)
    context, _images = DiagnosticContextBuilder().build(db, case)
    evidence = context.get("orvect_field_evidence") or []
    return {
        "case_id": case.id,
        "summary": context.get("field_evidence_summary"),
        # Only the aggregated view is ever serialized: no raw case, no garage
        # identity, no intervention date leaves this endpoint.
        "evidence": [
            {
                "source_id": item["source"]["source_id"],
                "title": item["title"],
                "excerpt": item["excerpt"],
                "trust_class": item["trust_class"],
                **item["field_evidence"],
            }
            for item in evidence
        ],
    }


@router.get("/api/intelligence/field-evidence")
def lookup_field_evidence(
    code: str = Query(..., min_length=2, max_length=80),
    make: str = Query("", max_length=100),
    model: str = Query("", max_length=100),
    engine_code: str = Query("", max_length=80),
    ecu_model: str = Query("", max_length=120),
    db: Session = Depends(get_db),
    garage_id: str = Depends(active_garage_id),
):
    """Ad-hoc lookup of ORVECT experience for a vehicle and a code."""
    vehicle = {
        "manufacturer": make,
        "make": make,
        "model": model,
        "engine_code": engine_code,
        "ecu_model": ecu_model,
    }
    evidence = retrieval.field_evidence(db, vehicle, [{"code": code}], garage_id)
    return {
        "query": {**vehicle, "code": code},
        "summary": retrieval.summarize(evidence),
        "evidence": [
            {
                "source_id": item["source"]["source_id"],
                "title": item["title"],
                "excerpt": item["excerpt"],
                **item["field_evidence"],
            }
            for item in evidence
        ],
    }


@router.get("/api/intelligence/metrics")
def intelligence_metrics(
    scope: Literal["garage", "network"] = Query("garage"),
    window_days: int = Query(metrics.DEFAULT_WINDOW_DAYS, ge=1, le=MAX_WINDOW_DAYS),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_admin),
):
    """Diagnostic performance. Network scope returns aggregates only."""
    garage_id = None if scope == "network" else auth.garage_id
    return metrics.report(db, garage_id, window_days)


@router.get("/api/intelligence/patterns")
def list_patterns(
    limit: int = Query(50, ge=1, le=200),
    support: Literal["all", "corroborated", "established"] = Query("all"),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_admin),
):
    """Admin review of learned patterns, with their raw-case counts."""
    query = select(ExperiencePattern).order_by(ExperiencePattern.last_seen_at.desc())
    if support != "all":
        query = query.where(ExperiencePattern.support_label == support)
    patterns = db.scalars(query.limit(limit)).all()
    return {
        "patterns": [
            {
                "id": item.id,
                "source_id": signature.field_source_id(item.pattern_key),
                "scope_level": item.scope_level,
                "scope": item.scope,
                "dtc_scope": item.dtc_scope,
                "dtc_signature": item.dtc_signature,
                "root_cause_component": item.root_cause_component,
                "repair_action_type": item.repair_action_type,
                "case_count": item.case_count,
                "garage_count": item.garage_count,
                "confirmed_count": item.confirmed_count,
                "supported_count": item.supported_count,
                "contradicting_count": item.contradicting_count,
                "support_label": item.support_label,
                "review_state": item.review_state,
                "repair_success_rate": aggregation.repair_success_rate(item),
                "discriminating_tests": item.discriminating_tests,
                "last_seen_at": item.last_seen_at.isoformat(),
            }
            for item in patterns
        ]
    }


@router.post("/api/intelligence/patterns/{pattern_id}/review")
def review_pattern(
    pattern_id: str,
    state: Literal["auto", "approved", "rejected"] = Query(...),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_admin),
):
    """Human override on a learned pattern. Rejection removes it from retrieval."""
    pattern = db.get(ExperiencePattern, pattern_id)
    if not pattern:
        raise HTTPException(404, "Motif introuvable")
    pattern.review_state = state
    db.commit()
    return {"id": pattern.id, "review_state": pattern.review_state}


@router.post("/api/intelligence/patterns/rebuild")
def rebuild_patterns(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_admin),
):
    """Recompute every aggregate from its raw cases. Aggregates stay reproducible."""
    count = aggregation.rebuild_all(db)
    db.commit()
    return {"patterns_recomputed": count}
