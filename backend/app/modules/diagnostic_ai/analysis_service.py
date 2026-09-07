import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.models import AICall, DiagnosticEvent, DiagnosticHypothesis, DiagnosticSession, DiagnosticStep, now

from .context_builder import DiagnosticContextBuilder
from .diagnostic_engine import DiagnosticEngine
from .providers import AIInvalidResponse, AIProviderUnavailable, PROMPT_VERSION, get_ai_provider, selected_model, validate_provider_sources
from .safety_engine import SafetyEngine
from .schemas import DiagnosticAnalysis, LLMDiagnosticAnalysis, NON_INFORMATIVE_RESULT_STATES


class AnalysisInProgress(Exception):
    pass


def _event(db, case, kind, payload):
    db.add(
        DiagnosticEvent(
            session_id=case.id,
            event_type=kind,
            payload=payload,
            actor_type="system",
            actor_id=None,
        )
    )


def _source_payloads(items) -> tuple[list[str], list[dict]]:
    references = [source.model_dump(mode="json") for source in items]
    return list(dict.fromkeys(source["source_id"] for source in references)), references


def _validate_dtc_interpretations(analysis: LLMDiagnosticAnalysis, context: dict) -> None:
    expected = {
        (item.get("namespace", "sae_obd2"), item["code"], item.get("ecu")): item
        for item in context.get("technical_definitions", [])
    }
    actual = {(item.namespace, item.code, item.ecu): item for item in analysis.interpretedFaultCodes}
    if set(actual) != set(expected):
        raise AIInvalidResponse("The explanation layer must return each input DTC exactly once")
    for identity, definition in expected.items():
        item = actual[identity]
        expected_status = "provided_by_database" if definition["documented"] else "not_found"
        expected_sources = [definition["source"]] if definition["documented"] else []
        if (
            item.definitionType != definition["definition_type"]
            or item.meaning != definition["description"]
            or item.sourceStatus != expected_status
            or [source.model_dump(mode="json") for source in item.sources] != expected_sources
        ):
            raise AIInvalidResponse(
                f"The explanation layer altered the authoritative DTC resolution for {identity[0]}:{identity[1]}:{identity[2] or 'unknown-ecu'}"
            )


def _persist(db, case, result, safety, context, context_hash, operation):
    validate_provider_sources(result.analysis, context)
    _validate_dtc_interpretations(result.analysis, context)
    analysis = DiagnosticAnalysis.model_validate(
        {**result.analysis.model_dump(mode="json"), "safetyAssessment": safety.model_dump(mode="json")}
    )
    payload = analysis.model_dump(mode="json")
    body = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    run = AICall(
        session_id=case.id,
        provider=result.provider,
        model=result.model,
        operation_type=operation,
        status="completed",
        schema_version="2.0",
        prompt_version=PROMPT_VERSION,
        request_id=str(uuid.uuid4()),
        input_hash=context_hash,
        output_hash=hashlib.sha256(body.encode()).hexdigest(),
        output_payload=payload,
        validation_status="repaired" if result.repaired else "valid",
        error_safe=None,
        latency_ms=result.latency_ms,
        token_usage=result.token_usage,
    )
    db.add(run)
    db.flush()
    for old in db.scalars(
        select(DiagnosticHypothesis).where(
            DiagnosticHypothesis.session_id == case.id,
            DiagnosticHypothesis.status.in_(["active", "possible", "likely", "unlikely"]),
        )
    ).all():
        old.status = "superseded"
    for hypothesis in analysis.hypotheses:
        source_ids, references = _source_payloads(hypothesis.sources)
        reasoning = "; ".join(hypothesis.requiredConfirmation) or "Hypothesis requires confirmation"
        if hypothesis.verificationStatus == "unverified":
            reasoning = f"UNVERIFIED GENERAL KNOWLEDGE. {reasoning}"
        db.add(
            DiagnosticHypothesis(
                session_id=case.id,
                title=hypothesis.label,
                suspected_component=hypothesis.component or "not_determined",
                probability_score=hypothesis.confidence * 100,
                confidence_label="high" if hypothesis.confidence >= 0.75 else "medium" if hypothesis.confidence >= 0.4 else "low",
                reasoning=reasoning,
                supporting_evidence=hypothesis.supportingEvidence,
                contradicting_evidence=hypothesis.contradictingEvidence,
                source_ids=source_ids,
                source_references=references,
                verification_status=hypothesis.verificationStatus,
                status=hypothesis.status,
            )
        )
    for old_step in db.scalars(
        select(DiagnosticStep).where(
            DiagnosticStep.session_id == case.id,
            DiagnosticStep.status.in_(["current", "pending"]),
        )
    ).all():
        old_step.status = "superseded"
    base = db.scalar(
        select(DiagnosticStep.step_order)
        .where(DiagnosticStep.session_id == case.id)
        .order_by(DiagnosticStep.step_order.desc())
    ) or 0
    for index, check in enumerate(analysis.nextChecks):
        source_ids, references = _source_payloads(check.sources)
        db.add(
            DiagnosticStep(
                session_id=case.id,
                step_order=base + index + 1,
                title=check.title,
                objective=check.objective,
                instructions=check.instructions,
                required_tools=check.requiredTools,
                expected_results=[
                    {
                        "result_id": f"{check.id}:{result_index}",
                        "label": expected.outcome,
                        "meaning": expected.interpretation,
                        "next_action": expected.nextAction,
                    }
                    for result_index, expected in enumerate(check.expectedResults)
                ],
                safety_notes=check.safetyWarnings,
                source_ids=source_ids,
                source_references=references,
                verification_status=check.verificationStatus,
                status="current" if index == 0 else "pending",
                result=None,
                technician_comment=None,
                hypotheses_before=[item.model_dump(mode="json") for item in analysis.hypotheses],
                hypotheses_after=[],
            )
        )
    case.status = "in_progress"
    case.analysis_started_at = None
    case.analysis_context_hash = context_hash
    case.urgency_level = safety.status
    case.current_summary = analysis.caseSummary
    case.prompt_version = PROMPT_VERSION
    case.ai_model = result.model
    _event(
        db,
        case,
        "ai_explanation_completed",
        {
            "ai_run_id": run.id,
            "provider": result.provider,
            "model": result.model,
            "operation": operation,
            "validation_status": run.validation_status,
            "safety_decision_source": "safety_engine",
        },
    )
    db.commit()
    return payload


def _latest_result_is_non_informative(db: Session, case: DiagnosticSession) -> bool:
    step = db.scalar(
        select(DiagnosticStep)
        .where(DiagnosticStep.session_id == case.id, DiagnosticStep.completed_at.is_not(None))
        .order_by(DiagnosticStep.completed_at.desc())
    )
    return bool(step and (step.result or {}).get("state") in NON_INFORMATIVE_RESULT_STATES)


def _effective_context_hash(context: dict) -> str:
    """Hash only evidence that may legitimately change the diagnostic state."""
    effective = {
        **context,
        "previous_steps": [
            item for item in context.get("previous_steps", []) if item.get("diagnostic_effect") == "informative"
        ],
    }
    canonical = DiagnosticContextBuilder.canonical(effective)
    return hashlib.sha256(canonical.encode()).hexdigest()


async def analyze_case(db: Session, case: DiagnosticSession, follow_up=False):
    if case.status == "analyzing":
        raise AnalysisInProgress("Une analyse est déjà en cours")
    context, images = DiagnosticContextBuilder().build(db, case)
    if not context["fault_codes"]:
        raise ValueError("Ajoutez au moins un code défaut")
    context["diagnostic_engine"] = DiagnosticEngine().evaluate(context).as_dict()
    context_hash = _effective_context_hash(context)
    if follow_up and _latest_result_is_non_informative(db, case) and case.analysis_context_hash == context_hash:
        latest = db.scalar(
            select(AICall)
            .where(
                AICall.session_id == case.id,
                AICall.status == "completed",
                AICall.schema_version == "2.0",
                AICall.output_payload.is_not(None),
            )
            .order_by(AICall.created_at.desc())
        )
        if latest:
            return DiagnosticAnalysis.model_validate(latest.output_payload).model_dump(mode="json")
    operation = "follow_up" if follow_up else "initial_analysis"
    cached = db.scalar(
        select(AICall)
        .where(
            AICall.session_id == case.id,
            AICall.input_hash == context_hash,
            AICall.operation_type == operation,
            AICall.status == "completed",
            AICall.schema_version == "2.0",
            AICall.provider == settings.llm_provider,
            AICall.model == selected_model(context, follow_up),
            AICall.prompt_version == PROMPT_VERSION,
            AICall.output_payload.is_not(None),
        )
        .order_by(AICall.created_at.desc())
    )
    if cached:
        return DiagnosticAnalysis.model_validate(cached.output_payload).model_dump(mode="json")
    previous = case.status
    case.status = "analyzing"
    case.analysis_started_at = now()
    db.commit()
    provider = get_ai_provider()
    try:
        result = await (
            provider.analyze_follow_up(context, images)
            if follow_up
            else provider.analyze_initial_case(context, images)
        )
        safety = SafetyEngine().assess(context)
        return _persist(db, case, result, safety, context, context_hash, operation)
    except Exception as exc:
        db.rollback()
        fresh = db.get(DiagnosticSession, case.id)
        fresh.status = previous if previous != "analyzing" else "draft"
        fresh.analysis_started_at = None
        safe = str(exc) if isinstance(exc, (AIProviderUnavailable, AIInvalidResponse, ValueError)) else "Erreur interne du fournisseur IA"
        db.add(
            AICall(
                session_id=case.id,
                provider=settings.llm_provider,
                model="unavailable",
                operation_type=operation,
                status="failed",
                schema_version="2.0",
                prompt_version=PROMPT_VERSION,
                request_id=str(uuid.uuid4()),
                input_hash=context_hash,
                output_hash=None,
                output_payload=None,
                validation_status="failed",
                error_safe=safe[:300],
                latency_ms=0,
                token_usage=None,
            )
        )
        db.commit()
        raise
