"""Diagnostic performance metrics.

ORVECT measures itself from what actually happened: confirmed outcomes, tests
performed, how often external research was needed and what each diagnosis cost.
Every figure here is computed from stored rows, and a figure that cannot be
computed honestly is returned as None rather than as a zero.
"""

import statistics
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.models import (
    AICall,
    DiagnosticSession,
    ExperienceCase,
    ExperiencePattern,
    HypothesisOutcome,
    now,
)

from . import capture, trust

DEFAULT_WINDOW_DAYS = 90
# Below this, a rate is noise dressed up as a measurement.
MIN_SAMPLE = 5


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator < MIN_SAMPLE:
        return None
    return round(numerator / denominator, 3)


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return round(ordered[index], 1)


def _token_cost(input_tokens: int, output_tokens: int) -> float | None:
    """Money only when prices are configured. No invented tariff."""
    if not settings.nebius_price_input_per_mtok and not settings.nebius_price_output_per_mtok:
        return None
    return round(
        input_tokens / 1_000_000 * settings.nebius_price_input_per_mtok
        + output_tokens / 1_000_000 * settings.nebius_price_output_per_mtok,
        6,
    )


def diagnostic_quality(db: Session, garage_id: str | None, since) -> dict:
    """How well the diagnostic path performed, measured on confirmed outcomes."""
    query = select(ExperienceCase).where(ExperienceCase.created_at >= since)
    if garage_id:
        query = query.where(ExperienceCase.garage_id == garage_id)
    cases = [item for item in db.scalars(query).all() if not item.duplicate_of]

    confirmed = [item for item in cases if item.outcome_class == capture.CONFIRMED]
    ranked = [item for item in confirmed if item.confirmed_hypothesis_rank]
    resolved = [
        item for item in cases
        if item.outcome_class in {capture.CONFIRMED, capture.SUPPORTED}
    ]
    observed = [
        item for item in cases
        if item.outcome_class in {capture.CONFIRMED, capture.SUPPORTED, capture.CONTRADICTED}
    ]
    tests = [item.test_count for item in confirmed if item.test_count]
    durations = [
        item.time_to_outcome_seconds for item in confirmed if item.time_to_outcome_seconds
    ]
    verdicts = db.scalars(
        select(HypothesisOutcome).where(HypothesisOutcome.recorded_at >= since)
        if not garage_id
        else select(HypothesisOutcome).where(
            HypothesisOutcome.recorded_at >= since, HypothesisOutcome.garage_id == garage_id
        )
    ).all()
    decided = [item for item in verdicts if item.verdict in {"confirmed", "rejected"}]

    return {
        "cases": len(cases),
        "confirmed_cases": len(confirmed),
        "first_hypothesis_confirmation_rate": _rate(
            sum(1 for item in ranked if item.confirmed_hypothesis_rank == 1), len(ranked)
        ),
        "top3_hypothesis_confirmation_rate": _rate(
            sum(1 for item in ranked if item.confirmed_hypothesis_rank <= 3), len(ranked)
        ),
        "hypothesis_rejection_rate": _rate(
            sum(1 for item in decided if item.verdict == "rejected"), len(decided)
        ),
        "mean_tests_before_confirmed_cause": round(statistics.mean(tests), 2) if tests else None,
        "median_seconds_to_confirmed_cause": round(statistics.median(durations)) if durations else None,
        "repair_success_rate": _rate(len(resolved), len(observed)),
        "unresolved_case_rate": _rate(
            sum(1 for item in cases if item.outcome_class == capture.UNRESOLVED), len(cases)
        ),
        "unknown_outcome_rate": _rate(
            sum(1 for item in cases if item.outcome_class == capture.UNKNOWN), len(cases)
        ),
    }


def pipeline_efficiency(db: Session, garage_id: str | None, since) -> dict:
    """Research behaviour, model reliability, latency and cost inputs."""
    query = (
        select(AICall)
        .join(DiagnosticSession, DiagnosticSession.id == AICall.session_id)
        .where(AICall.created_at >= since, AICall.status == "completed")
    )
    if garage_id:
        query = query.where(DiagnosticSession.garage_id == garage_id)
    runs = db.scalars(query).all()

    research_triggered = cache_hits = field_backed = avoided = 0
    searches = input_tokens = output_tokens = 0
    latencies: list[float] = []
    for run in runs:
        telemetry = (run.output_payload or {}).get("researchMetadata") or {}
        if telemetry.get("researchTriggered"):
            research_triggered += 1
            if telemetry.get("fromCache"):
                cache_hits += 1
        if telemetry.get("fieldEvidenceUsed"):
            field_backed += 1
        if telemetry.get("researchAvoidedByFieldEvidence"):
            avoided += 1
        searches += telemetry.get("searchCount") or 0
        usage = run.token_usage or {}
        input_tokens += usage.get("prompt_tokens") or 0
        output_tokens += usage.get("completion_tokens") or 0
        if run.latency_ms:
            latencies.append(run.latency_ms)

    repaired = sum(1 for run in runs if run.validation_status == "repaired")
    total = len(runs)
    return {
        "analyses": total,
        "research_trigger_rate": _rate(research_triggered, total),
        "research_cache_hit_rate": _rate(cache_hits, research_triggered),
        "resolved_without_external_research_rate": _rate(total - research_triggered, total),
        "field_evidence_usage_rate": _rate(field_backed, total),
        "research_avoided_by_field_evidence_rate": _rate(avoided, total),
        "ai_repair_rate": _rate(repaired, total),
        "latency_ms_p50": _percentile(latencies, 0.5),
        "latency_ms_p95": _percentile(latencies, 0.95),
        "tavily_queries": searches,
        "cost_inputs": {
            "models": sorted({run.model for run in runs if run.model}),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "tokens_per_analysis": round((input_tokens + output_tokens) / total, 1) if total else None,
            "tavily_queries_per_analysis": round(searches / total, 2) if total else None,
            "repair_retries": repaired,
            "estimated_cost_usd": _token_cost(input_tokens, output_tokens),
            "estimated_cost_per_analysis_usd": (
                round(_token_cost(input_tokens, output_tokens) / total, 6)
                if total and _token_cost(input_tokens, output_tokens) is not None
                else None
            ),
            "pricing_configured": bool(
                settings.nebius_price_input_per_mtok or settings.nebius_price_output_per_mtok
            ),
        },
    }


def knowledge_growth(db: Session, garage_id: str | None) -> dict:
    """Size and maturity of ORVECT's own accumulated intelligence."""
    patterns = db.scalars(select(ExperiencePattern)).all()
    shareable = db.scalars(select(ExperienceCase).where(ExperienceCase.shareable.is_(True))).all()
    own = (
        db.scalars(select(ExperienceCase).where(ExperienceCase.garage_id == garage_id)).all()
        if garage_id
        else []
    )
    return {
        "experience_cases_total": len(db.scalars(select(ExperienceCase)).all()),
        "experience_cases_shareable": len(shareable),
        "experience_cases_own_workshop": len(own) if garage_id else None,
        "patterns_total": len(patterns),
        "patterns_corroborated": sum(
            1 for item in patterns if item.support_label == trust.CORROBORATED
        ),
        "patterns_established": sum(
            1 for item in patterns if item.support_label == trust.ESTABLISHED
        ),
        "contributing_workshops": len({item.garage_id for item in shareable}),
    }


def report(db: Session, garage_id: str | None, window_days: int = DEFAULT_WINDOW_DAYS) -> dict:
    since = now() - timedelta(days=window_days)
    return {
        "scope": "garage" if garage_id else "network",
        "window_days": window_days,
        "generated_at": now().isoformat(),
        "minimum_sample_for_rates": MIN_SAMPLE,
        "diagnostic_quality": diagnostic_quality(db, garage_id, since),
        "pipeline_efficiency": pipeline_efficiency(db, garage_id, since),
        "knowledge_growth": knowledge_growth(db, garage_id),
    }
