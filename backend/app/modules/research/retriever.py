"""Merge internal Orvect knowledge with external Tavily evidence.

Every excerpt handed to the reasoning layer carries a `source` object in the
exact shape the existing provenance validator enforces, so an externally
sourced claim is subject to the same rules as a catalogue definition: the model
may cite it, but it cannot alter it and cannot invent one.
"""

import hashlib
import json
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import logger
from app.database.models import ResearchCache, now

from . import tavily
from .decision import ResearchPlan, decide_research

EXTERNAL_SCOPE = "external_research_unverified"


def _cache_key(context: dict, queries: list[str]) -> str:
    """make + model + year + engine + DTCs + queries — not the free-text symptoms."""
    vehicle = context.get("vehicle", {})
    signature = {
        "make": vehicle.get("make"),
        "model": vehicle.get("model"),
        "year": vehicle.get("model_year"),
        "engine": vehicle.get("engine_code") or vehicle.get("engine_name"),
        "codes": sorted(item.get("code") for item in context.get("fault_codes", []) if item.get("code")),
        "queries": sorted(queries),
    }
    return hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()


def _source_reference(item: dict) -> dict:
    """An external evidence item rendered as a citable source.

    `verified` stays False: web evidence is never OEM-reviewed documentation,
    which is what keeps it from unlocking `manufacturerProcedure`.
    """
    return {
        "source_id": "tavily:" + hashlib.sha1(item["url"].encode()).hexdigest()[:16],
        "source_type": item["source_type"],
        "source_version": item["retrieved_at"][:10],
        "vehicle_compatibility": {"scope": EXTERNAL_SCOPE, "query": item["query"]},
        "timestamp": item["retrieved_at"],
        "verified": False,
        "url": item["url"],
        "title": item["title"],
        "domain": item["domain"],
    }


def _read_cache(db: Session, key: str) -> dict | None:
    row = db.scalar(select(ResearchCache).where(ResearchCache.cache_key == key))
    if not row:
        return None
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=now().tzinfo)
    if expires <= now():
        return None
    return {"evidence": row.evidence, "queries": row.queries, "search_count": row.search_count}


def _write_cache(db: Session, key: str, queries: list[str], evidence: list[dict], searches: int) -> None:
    db.merge(
        ResearchCache(
            id=db.scalar(select(ResearchCache.id).where(ResearchCache.cache_key == key)) or None,
            cache_key=key,
            queries=queries,
            evidence=evidence,
            provider="tavily",
            search_count=searches,
            expires_at=now() + timedelta(hours=settings.tavily_cache_ttl_hours),
        )
    )
    db.commit()


async def gather_external_evidence(db: Session, context: dict, plan: ResearchPlan) -> dict:
    """Run (or reuse) external research. Never raises: failure is reported, not fatal."""
    outcome = {
        "evidence": [],
        "excerpts": [],
        "search_count": 0,
        "cached": False,
        "available": False,
        "failed_queries": [],
        "error": None,
    }
    if not plan.needed:
        return outcome

    key = _cache_key(context, plan.queries)
    cached = _read_cache(db, key)
    if cached:
        outcome.update(
            evidence=cached["evidence"],
            cached=True,
            available=bool(cached["evidence"]),
            search_count=0,
        )
    else:
        try:
            items, failed = await tavily.search(plan.queries)
        except tavily.TavilyUnavailable as exc:
            outcome["error"] = str(exc)
            return outcome
        except Exception as exc:
            logger.warning("tavily_unexpected_error", error_type=type(exc).__name__)
            outcome["error"] = "External research is temporarily unavailable"
            return outcome
        stamp = now().isoformat()
        items = [{**item, "retrieved_at": stamp} for item in items]
        outcome.update(
            evidence=items,
            failed_queries=failed,
            search_count=len(plan.queries) - len(failed),
            available=bool(items),
        )
        if items:
            _write_cache(db, key, plan.queries, items, outcome["search_count"])

    outcome["excerpts"] = [
        {
            "id": _source_reference(item)["source_id"],
            "title": item["title"],
            "excerpt": item["snippet"],
            "origin": "external_research",
            "vehicle_scope": {"scope": EXTERNAL_SCOPE},
            "source": _source_reference(item),
        }
        for item in outcome["evidence"]
    ]
    return outcome


async def build_evidence(db: Session, context: dict, internal: list[dict]) -> tuple[list[dict], dict]:
    """Return (excerpts for the model, research metadata for telemetry/UI)."""
    marked_internal = [{**item, "origin": "orvect_knowledge"} for item in internal]
    plan = decide_research({**context, "internal_excerpts": marked_internal})
    research = await gather_external_evidence(db, context, plan)
    metadata = {
        "researchTriggered": plan.needed,
        "researchReasons": plan.reasons,
        "queries": plan.queries if plan.needed else [],
        "searchCount": research["search_count"],
        "fromCache": research["cached"],
        "externalSources": len(research["evidence"]),
        "internalSources": len(marked_internal),
        "externalResearchAvailable": research["available"],
        "failedQueries": research["failed_queries"],
        "researchError": research["error"],
        "sourceMix": _source_mix(research["evidence"]),
    }
    return marked_internal + research["excerpts"], metadata


def _source_mix(evidence: list[dict]) -> dict:
    mix: dict[str, int] = {}
    for item in evidence:
        mix[item["source_type"]] = mix.get(item["source_type"], 0) + 1
    return mix
