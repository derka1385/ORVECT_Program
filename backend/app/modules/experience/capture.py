"""Turn a completed diagnosis into a structured experience case.

This is the write side of the Experience Engine. It reads only structured
technician input and never asks a model whether something is true. Its second
job is admission control: a workshop submission is not automatically trusted,
and an unknown outcome is never read as a confirmation.
"""

from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.database.models import (
    DiagnosticCompletion,
    DiagnosticDataConsent,
    DiagnosticHypothesis,
    DiagnosticObservation,
    DiagnosticSession,
    DiagnosticStep,
    ExperienceCase,
    VehicleConfiguration,
    VehicleProfile,
    now,
)
from app.modules.diagnostic_ai.schemas import NON_INFORMATIVE_RESULT_STATES
from app.modules.research.decision import keywords

from . import signature, taxonomy

# Outcome classes, from strongest to weakest evidence value.
CONFIRMED = "confirmed"          # repaired, verified resolved, codes did not come back
SUPPORTED = "supported"          # repaired and improved, but not verified to that standard
CONTRADICTED = "contradicted"    # the repair did not hold: demotes a pattern
UNRESOLVED = "unresolved"        # diagnosis ended without a cause
UNKNOWN = "unknown"              # outcome never observed; carries no confirmation

CONFIRMING_RESOLUTIONS = {"problem_repaired", "no_repair_required"}
STRONG_CONFIDENCE = {"successful_repair", "measurement_test"}
CLEARED_STATES = {"cleared_no_return", "not_applicable"}

# Minimum quality for a case to be allowed to influence other workshops.
SHAREABLE_MIN_QUALITY = 5
DUPLICATE_WINDOW_DAYS = 30
PATTERN_ELIGIBLE_OUTCOMES = {CONFIRMED, SUPPORTED, CONTRADICTED}


def _aware(value):
    """SQLite hands back naive datetimes; comparing them to an aware `now()` raises."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def classify_outcome(completion: DiagnosticCompletion) -> str:
    """Deterministic evidence value of a completed case.

    Conservative on purpose: `unknown_not_tested` and a pending repair can only
    ever produce UNKNOWN, whatever the technician believes the cause to be.
    """
    if completion.post_repair_result == "not_resolved" or completion.dtc_after_repair == "returned":
        return CONTRADICTED
    if completion.resolution_status == "inconclusive":
        return UNRESOLVED
    if completion.post_repair_result == "unknown_not_tested":
        return UNKNOWN
    if completion.resolution_status not in CONFIRMING_RESOLUTIONS:
        return UNKNOWN
    if (
        completion.post_repair_result == "resolved"
        and completion.dtc_after_repair in CLEARED_STATES
        and completion.root_cause_confidence in STRONG_CONFIDENCE
    ):
        return CONFIRMED
    if completion.post_repair_result in {"resolved", "partially_resolved"}:
        return SUPPORTED
    return UNKNOWN


def canonical_cause(completion: DiagnosticCompletion) -> taxonomy.CanonicalCause:
    """Structured identity of what was actually found.

    Delegated to the taxonomy so that four wordings of one finding, in four
    languages, produce one key, while an unrecognised or ambiguous cause keeps
    an identity of its own instead of being forced onto a neighbour.
    """
    return taxonomy.resolve(completion.components_involved, completion.confirmed_cause or "")


def _vehicle_dimensions(db: Session, vehicle: VehicleProfile | None) -> dict:
    if not vehicle:
        return {}
    config = db.scalar(select(VehicleConfiguration).where(VehicleConfiguration.vehicle_id == vehicle.id))
    engine_code = None
    if config:
        engine_code = config.engine_code_confirmed_by_user or config.engine_code
    elif vehicle.engine_code and vehicle.engine_code != "UNKNOWN":
        engine_code = vehicle.engine_code
    return {
        "manufacturer": (config.manufacturer if config and config.manufacturer else vehicle.make),
        "make": (config.make if config and config.make else vehicle.make),
        "model": (config.model if config and config.model else vehicle.model),
        "generation": config.generation if config else None,
        "platform": config.platform if config else None,
        "model_year": (config.model_year if config and config.model_year else vehicle.year),
        "engine_code": engine_code,
        "engine_family": config.engine_family if config else None,
        "fuel_type": (config.fuel_type if config and config.fuel_type else vehicle.fuel_type),
        "transmission_type": (config.transmission_type if config and config.transmission_type else vehicle.transmission),
        "drivetrain": config.drivetrain if config else None,
        "ecu_manufacturer": config.engine_ecu_manufacturer if config else None,
        "ecu_model": config.engine_ecu_model if config else None,
    }


def _quality(case_fields: dict, outcome: str) -> tuple[int, list[str]]:
    """Admission score and the explicit reasons behind it."""
    score, flags = 0, []
    if case_fields["engine_code"]:
        score += 2
    else:
        flags.append("vehicle_configuration_incomplete")
    if case_fields["informative_test_count"] > 0:
        score += 2
    else:
        flags.append("no_informative_test_recorded")
    if outcome in {CONFIRMED, SUPPORTED, CONTRADICTED}:
        score += 2
    else:
        flags.append("repair_outcome_not_observed")
    if case_fields["root_cause_component"] and case_fields["root_cause_component"] != taxonomy.UNRESOLVED:
        score += 2
    else:
        flags.append("root_cause_not_identified")
    if case_fields["cause_canonical"]:
        score += 1
    else:
        # Still admissible: it simply groups with nothing else until the
        # vocabulary covers it, which is the safe failure direction.
        flags.append(f"cause_{case_fields['cause_resolution']}")
    if case_fields["dtc_after_repair"] != "not_checked":
        score += 1
    else:
        flags.append("post_repair_codes_not_checked")
    if case_fields["mileage"]:
        score += 1
    if not case_fields["dtc_signature"]:
        flags.append("no_fault_code_recorded")
    return score, flags


def _duplicate_of(db: Session, case_fields: dict, garage_id: str, session_id: str) -> str | None:
    """Same workshop re-submitting the same finding on the same vehicle.

    Kept as a row, excluded from counting, so a single garage cannot inflate a
    pattern by closing the same job several times.
    """
    if not case_fields["dtc_signature"] or not case_fields["root_cause_component"]:
        return None
    prior = db.scalars(
        select(ExperienceCase)
        .where(
            ExperienceCase.garage_id == garage_id,
            ExperienceCase.session_id != session_id,
            ExperienceCase.dtc_signature == case_fields["dtc_signature"],
            ExperienceCase.root_cause_component == case_fields["root_cause_component"],
            ExperienceCase.duplicate_of.is_(None),
        )
        .order_by(ExperienceCase.created_at.desc())
    ).all()
    for candidate in prior:
        if candidate.engine_code == case_fields["engine_code"] and candidate.model == case_fields["model"]:
            return candidate.id
    return None


def build_case(
    db: Session,
    case: DiagnosticSession,
    completion: DiagnosticCompletion,
    consent: DiagnosticDataConsent | None,
) -> ExperienceCase:
    """Normalize one completed diagnosis. Raw history is never modified."""
    vehicle = db.get(VehicleProfile, case.vehicle_profile_id)
    dims = _vehicle_dimensions(db, vehicle)
    observations = db.scalars(
        select(DiagnosticObservation).where(DiagnosticObservation.session_id == case.id)
    ).all()
    dtcs = [item for item in observations if item.observation_type == "DTC"]
    measurements = [item for item in observations if item.observation_type == "measurement"]
    steps = db.scalars(
        select(DiagnosticStep).where(DiagnosticStep.session_id == case.id).order_by(DiagnosticStep.step_order)
    ).all()
    hypotheses = db.scalars(
        select(DiagnosticHypothesis)
        .where(DiagnosticHypothesis.session_id == case.id)
        .order_by(DiagnosticHypothesis.probability_score.desc())
    ).all()

    completed = [item for item in steps if item.result]
    informative = [
        item for item in completed
        if (item.result or {}).get("state") not in NON_INFORMATIVE_RESULT_STATES
    ]
    ranked = [item for item in hypotheses if item.status != "superseded"] or hypotheses
    confirmed_rank = None
    if completion.selected_hypothesis_id:
        for position, item in enumerate(ranked, start=1):
            if item.id == completion.selected_hypothesis_id:
                confirmed_rank = position
                break

    cause = canonical_cause(completion)
    code_entries = [
        {"code": item.key, "namespace": (item.value or {}).get("namespace") or "sae_obd2"}
        for item in dtcs
    ]
    started, finished = _aware(case.created_at), _aware(case.completed_at)
    elapsed = max(0, int((finished - started).total_seconds())) if started and finished else None

    fields = {
        **{key: dims.get(key) for key in (
            "manufacturer", "make", "model", "generation", "platform", "model_year",
            "engine_code", "engine_family", "fuel_type", "transmission_type",
            "drivetrain", "ecu_manufacturer", "ecu_model",
        )},
        "mileage": case.mileage,
        "dtc_signature": signature.dtc_signature(code_entries),
        "dtc_codes": [f"{item['namespace']}:{signature.normalize(item['code']).upper()}" for item in code_entries],
        "symptom_keywords": keywords(f"{case.observed_symptoms} {case.appearance_circumstances}", 12),
        "measurement_names": sorted({signature.normalize(item.key)[:80] for item in measurements if item.key}),
        "had_freeze_frame": any((item.value or {}).get("freeze_frame") for item in dtcs),
        "root_cause_component": cause.key,
        # The technician's own wording is never rewritten: it is the audit trail
        # behind every canonical key.
        "root_cause_text": (completion.confirmed_cause or "")[:2000],
        "cause_system": cause.system,
        "cause_component": cause.component,
        "cause_position": cause.position,
        "cause_failure_mode": cause.failure_mode,
        "cause_canonical": cause.canonical,
        "cause_resolution": cause.reason,
        "repair_action_type": completion.repair_action_type,
        "components_involved": [str(item)[:120] for item in (completion.components_involved or [])][:50],
        "resolution_status": completion.resolution_status,
        "post_repair_result": completion.post_repair_result,
        "dtc_after_repair": completion.dtc_after_repair,
        "root_cause_confidence": completion.root_cause_confidence,
        "discriminating_tests": [
            {
                "title": item.title[:200],
                "state": (item.result or {}).get("state"),
                "order": item.step_order,
            }
            for item in informative
        ][:20],
        "test_count": len(completed),
        "informative_test_count": len(informative),
        "confirmed_hypothesis_rank": confirmed_rank,
        "hypothesis_count": len(ranked),
        "time_to_outcome_seconds": elapsed,
    }

    outcome = classify_outcome(completion)
    quality_score, quality_flags = _quality(fields, outcome)
    duplicate = _duplicate_of(db, fields, case.garage_id, case.id)
    if duplicate:
        quality_flags.append("duplicate_submission")

    shareable = bool(
        consent
        and consent.consent
        and not duplicate
        and quality_score >= SHAREABLE_MIN_QUALITY
        and outcome in PATTERN_ELIGIBLE_OUTCOMES
        and fields["root_cause_component"]
        and fields["root_cause_component"] != taxonomy.UNRESOLVED
        and fields["dtc_signature"]
    )
    row = ExperienceCase(
        session_id=case.id,
        garage_id=case.garage_id,
        completion_id=completion.id,
        consent_id=consent.id if consent else None,
        outcome_class=outcome,
        quality_score=quality_score,
        quality_flags=sorted(set(quality_flags)),
        review_state="needs_review" if duplicate else "auto_accepted",
        shareable=shareable,
        duplicate_of=duplicate,
        **fields,
    )
    return row


def revoke(db: Session, session_id: str) -> bool:
    """Withdraw a case from the shared intelligence.

    Called when a workshop revokes its contribution. The row is kept for audit
    but stops counting anywhere, and every pattern it fed is recomputed at once
    so no stale aggregate survives the withdrawal.
    """
    from . import aggregation

    row = db.scalar(select(ExperienceCase).where(ExperienceCase.session_id == session_id))
    if not row or row.revoked_at:
        return False
    row.revoked_at = now()
    row.shareable = False
    row.review_state = "revoked"
    db.flush()
    aggregation.unindex_case(db, row)
    return True


def capture(
    db: Session,
    case: DiagnosticSession,
    completion: DiagnosticCompletion,
    consent: DiagnosticDataConsent | None,
) -> ExperienceCase | None:
    """Record the case and refresh the patterns it belongs to.

    Never fatal: failing to learn from a diagnosis must not fail the technician's
    completion, which is the operation they actually asked for.
    """
    from . import aggregation

    try:
        if db.scalar(select(ExperienceCase).where(ExperienceCase.session_id == case.id)):
            return None
        row = build_case(db, case, completion, consent)
        db.add(row)
        db.flush()
        aggregation.index_case(db, row)
        return row
    except Exception as exc:
        logger.warning(
            "experience_capture_failed",
            error_type=type(exc).__name__,
            error=str(exc)[:300],
            session_id=case.id,
        )
        return None
