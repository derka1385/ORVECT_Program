import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.models import (
    AICall, DiagnosticEvent, DiagnosticHypothesis, DiagnosticSession, DiagnosticStep,
    HypothesisStateEvent, now,
)

from app.modules.experience import next_check, trust
from app.modules.research.retriever import build_evidence

from . import progress
from .confidence import assess as assess_confidence
from .context_builder import DiagnosticContextBuilder
from .diagnostic_engine import DiagnosticEngine
from .providers import AIInvalidResponse, AIProviderUnavailable, EXPLORATORY_MEANING_PREFIX, PROMPT_VERSION, canonical_source, get_ai_provider, selected_model, validate_provider_sources
from .safety_engine import SafetyEngine
from .schemas import CARRIED_OUT_STEP_STATES, DiagnosticAnalysis, LLMDiagnosticAnalysis, NON_INFORMATIVE_RESULT_STATES, NextBestCheck, ResearchMetadata


class AnalysisInProgress(Exception):
    pass


def _evidence_sections(excerpts: list[dict]) -> dict:
    """Group retrieved evidence by trust class, most authoritative first."""
    sections: dict[str, list[str]] = {name: [] for name in trust.TRUST_CLASSES}
    for item in excerpts:
        source_type = (item.get("source") or {}).get("source_type")
        label = item.get("trust_class") or trust.trust_class(source_type)
        sections.setdefault(label, []).append(item.get("id") or (item.get("source") or {}).get("source_id"))
    return {
        name: [value for value in ids if value]
        for name, ids in sections.items()
    }


def _record_hypothesis_ranking(db, case, analysis) -> None:
    """Append the ranking to the hypothesis history. Prior states are kept."""
    for position, hypothesis in enumerate(analysis.hypotheses, start=1):
        db.add(
            HypothesisStateEvent(
                session_id=case.id,
                hypothesis_label=hypothesis.label[:200],
                event_type="ranked",
                strength_after=hypothesis.confidence,
                status_after=hypothesis.status,
                rank_position=position,
                decision_source="orvect_analysis",
                detail={
                    "verificationStatus": hypothesis.verificationStatus,
                    "component": hypothesis.component,
                },
            )
        )


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
        if (context.get("exploration_mode") and not definition["documented"]
            and item.sourceStatus == "ai_general_knowledge_unverified"):
            if (item.definitionType != definition["definition_type"] or item.sources
                or not item.meaning.startswith(EXPLORATORY_MEANING_PREFIX)):
                raise AIInvalidResponse("An exploratory DTC meaning must remain explicitly unverified and source-free")
            continue
        expected_status = "provided_by_database" if definition["documented"] else "not_found"
        expected_sources = [canonical_source(definition["source"])] if definition["documented"] else []
        if (
            item.definitionType != definition["definition_type"]
            or item.meaning != definition["description"]
            or item.sourceStatus != expected_status
            or [source.model_dump(mode="json") for source in item.sources] != expected_sources
        ):
            raise AIInvalidResponse(
                f"The explanation layer altered the authoritative DTC resolution for {identity[0]}:{identity[1]}:{identity[2] or 'unknown-ecu'}"
            )


def _persist(db, case, result, safety, context, context_hash, operation, research=None):
    validate_provider_sources(result.analysis, context)
    _validate_dtc_interpretations(result.analysis, context)
    research = research or {}
    telemetry = ResearchMetadata.model_validate(
        {
            **{key: value for key, value in research.items() if key in ResearchMetadata.model_fields},
            "provider": result.provider,
            "model": result.model,
            "durationMs": result.latency_ms,
            "tokenUsage": result.token_usage,
        }
    )
    analysis = DiagnosticAnalysis.model_validate(
        {
            **result.analysis.model_dump(mode="json"),
            "safetyAssessment": safety.model_dump(mode="json"),
            "confidence": assess_confidence(result.analysis, context, research).model_dump(mode="json"),
            "researchMetadata": telemetry.model_dump(mode="json"),
        }
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
        validation_status="repaired" if result.repaired else "normalized" if result.normalized else "valid",
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
    plan = [item.model_dump(mode="json") for item in analysis.nextChecks]
    ranked = next_check.rank(
        plan,
        [item.model_dump(mode="json") for item in analysis.hypotheses],
        {
            row.title
            for row in db.scalars(
                select(DiagnosticStep).where(
                    DiagnosticStep.session_id == case.id, DiagnosticStep.status.in_(CARRIED_OUT_STEP_STATES)
                )
            ).all()
        },
        context.get("orvect_field_evidence") or [],
    )
    # The report keeps the reasoning layer's full plan; ORVECT decides on its own
    # which of those checks the workshop should actually do next.
    current_id = ranked[0]["check"]["id"] if ranked else (plan[0]["id"] if plan else None)
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
                # Persisted so the check can be re-ranked later without asking
                # the reasoning layer again.
                estimated_difficulty=check.estimatedDifficulty,
                estimated_minutes=next_check.parse_minutes(check.objective),
                source_ids=source_ids,
                source_references=references,
                verification_status=check.verificationStatus,
                status="current" if check.id == current_id else "pending",
                result=None,
                technician_comment=None,
                hypotheses_before=[item.model_dump(mode="json") for item in analysis.hypotheses],
                hypotheses_after=[],
            )
        )
    if ranked:
        analysis.nextBestCheck = NextBestCheck(
            checkId=ranked[0]["check"]["id"],
            title=ranked[0]["check"]["title"],
            planOrder=ranked[0]["plan_order"],
            score=ranked[0]["score"],
            rationale=ranked[0]["rationale"],
            selectionMethod=ranked[0]["selectionMethod"],
        )
        payload = analysis.model_dump(mode="json")
    _record_hypothesis_ranking(db, case, analysis)
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
            "research_triggered": telemetry.researchTriggered,
            "search_count": telemetry.searchCount,
            "external_sources": telemetry.externalSources,
            "from_cache": telemetry.fromCache,
            "latency_ms": result.latency_ms,
            "token_usage": result.token_usage,
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


RESPONSE_LANGUAGES = {"fr", "en", "sv", "de"}


async def analyze_case(db: Session, case: DiagnosticSession, follow_up=False, language="fr"):
    """Orchestrate the Orvect diagnostic pipeline.

    Deterministic context and DTC resolution, then the knowledge-first research
    gate, then one strong Nebius reasoning call over internal + external
    evidence. Stages are published as they actually happen.
    """
    if case.status == "analyzing":
        raise AnalysisInProgress("Une analyse est déjà en cours")
    progress.start(case.id)
    progress.set_stage(case.id, "context")
    context, images = DiagnosticContextBuilder().build(db, case)
    if not context["fault_codes"]:
        progress.clear(case.id)
        raise ValueError("Ajoutez au moins un code défaut")
    progress.set_stage(
        case.id, "codes", f"{len(context['fault_codes'])} code(s) défaut"
    )
    context["exploration_mode"] = settings.diagnostic_exploration_enabled and settings.llm_provider in {"gemini", "nebius"}
    context["diagnostic_engine"] = DiagnosticEngine().evaluate(context).as_dict()

    # The site language is part of the analysis identity: switching it and
    # re-running must produce a report in that language, never a cache hit.
    context["response_language"] = language if language in RESPONSE_LANGUAGES else "fr"
    # Hashed before external evidence is merged: retrieval timestamps would
    # otherwise make every run a cache miss.
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
            progress.finish(case.id)
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
        progress.finish(case.id)
        return DiagnosticAnalysis.model_validate(cached.output_payload).model_dump(mode="json")

    previous = case.status
    case.status = "analyzing"
    case.analysis_started_at = now()
    db.commit()
    try:
        progress.set_stage(case.id, "knowledge", f"{len(context['technical_excerpts'])} élément(s) interne(s)")
        progress.set_stage(case.id, "research_decision")
        excerpts, research = await build_evidence(db, context, context["technical_excerpts"])
        if research["researchTriggered"]:
            progress.set_stage(
                case.id,
                "research",
                f"{research['externalSources']} source(s) externe(s)"
                + (" (cache)" if research["fromCache"] else ""),
            )
        context["technical_excerpts"] = excerpts
        # The model must never blend evidence classes. Sections are derived from
        # the trust class each item already carries, so the grouping cannot drift
        # from the provenance the server will reconstruct afterwards.
        context["evidence_sections"] = _evidence_sections(excerpts)
        # Tell the model what the research layer decided, so it can say so too.
        context["research_status"] = {
            "external_research_performed": research["researchTriggered"],
            "external_research_available": research["externalResearchAvailable"],
            "external_source_count": research["externalSources"],
            "source_mix": research["sourceMix"],
            "note": research["researchError"] or "",
        }

        progress.set_stage(case.id, "reasoning")
        provider = get_ai_provider()
        result = await (
            provider.analyze_follow_up(context, images)
            if follow_up
            else provider.analyze_initial_case(context, images)
        )
        progress.set_stage(case.id, "test_plan", f"{len(result.analysis.nextChecks)} contrôle(s)")
        safety = SafetyEngine().assess(context)
        payload = _persist(db, case, result, safety, context, context_hash, operation, research)
        progress.finish(case.id)
        return payload
    except Exception as exc:
        db.rollback()
        fresh = db.get(DiagnosticSession, case.id)
        fresh.status = previous if previous != "analyzing" else "draft"
        fresh.analysis_started_at = None
        safe = str(exc) if isinstance(exc, (AIProviderUnavailable, AIInvalidResponse, ValueError)) else "Erreur interne du fournisseur IA"
        progress.fail(case.id, safe[:200])
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
