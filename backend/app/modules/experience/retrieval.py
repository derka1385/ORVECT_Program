"""Retrieve ORVECT's own field evidence for a live diagnosis.

This is what makes the platform progressively less dependent on external
search: before spending a Tavily query, the pipeline asks what ORVECT already
observed on compatible vehicles.

Two rules govern everything here. Aggregates leave the workshop, raw cases
never do. And field evidence is always labelled as field evidence: it informs
a ranking, it does not become manufacturer documentation.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import ExperienceCase, ExperiencePattern, now

from . import aggregation, capture, compatibility, signature, taxonomy, trust

# Context budget. More evidence items cost tokens on every diagnosis and add
# little once the strongest compatible patterns are present.
MAX_FIELD_EVIDENCE = 6
OWN_WORKSHOP = "own_workshop"
NETWORK = "network"


@dataclass
class _OwnGroup:
    """A garage's own cases grouped like a pattern, for one scope level."""
    scope_level: str
    scope: dict
    dtc_scope: str
    dtc_signature: str
    root_cause_component: str
    repair_action_type: str
    case_count: int
    garage_count: int
    confirmed_count: int
    supported_count: int
    contradicting_count: int
    unresolved_count: int
    unknown_count: int
    mileage_min: int | None
    mileage_max: int | None
    common_symptoms: list
    discriminating_tests: list
    component_examples: list
    support_label: str
    last_seen_at: datetime
    pattern_key: str


def _live_signatures(codes) -> list[str]:
    return [sig for _scope, sig in signature.dtc_variants(codes)]


def _candidate_patterns(db: Session, signatures: list[str]) -> list[ExperiencePattern]:
    if not signatures:
        return []
    return db.scalars(
        select(ExperiencePattern).where(
            ExperiencePattern.dtc_signature.in_(signatures),
            ExperiencePattern.support_label.in_([trust.CORROBORATED, trust.ESTABLISHED]),
            ExperiencePattern.review_state != "rejected",
        )
    ).all()


def _own_groups(db: Session, garage_id: str, signatures: list[str]) -> list[_OwnGroup]:
    """Aggregate this garage's own history, including cases it never shared."""
    if not signatures or not garage_id:
        return []
    cases = db.scalars(
        select(ExperienceCase).where(
            ExperienceCase.garage_id == garage_id,
            ExperienceCase.duplicate_of.is_(None),
            ExperienceCase.revoked_at.is_(None),
            ExperienceCase.outcome_class.in_(sorted(capture.PATTERN_ELIGIBLE_OUTCOMES)),
        )
    ).all()
    grouped: dict[tuple, list[ExperienceCase]] = {}
    for case in cases:
        if not case.root_cause_component:
            continue
        dims = signature.dimensions(
            {
                "manufacturer": case.manufacturer, "make": case.make, "model": case.model,
                "generation": case.generation, "platform": case.platform,
                "engine_code": case.engine_code, "engine_family": case.engine_family,
                "fuel_type": case.fuel_type, "transmission_type": case.transmission_type,
                "drivetrain": case.drivetrain, "ecu_manufacturer": case.ecu_manufacturer,
                "ecu_model": case.ecu_model,
            }
        )
        for level, scope, _weight in signature.scope_signatures(dims):
            for dtc_scope, sig in signature.dtc_variants(case.dtc_codes):
                if sig not in signatures:
                    continue
                key = (level, tuple(sorted(scope.items())), dtc_scope, sig,
                       case.root_cause_component, case.repair_action_type)
                grouped.setdefault(key, []).append(case)

    groups = []
    for key, members in grouped.items():
        level, scope_items, dtc_scope, sig, component, repair = key
        outcomes = Counter(item.outcome_class for item in members)
        mileages = [item.mileage for item in members if item.mileage]
        symptoms = Counter(word for item in members for word in (item.symptom_keywords or []))
        tests = Counter(
            test.get("title", "")[:200]
            for item in members for test in (item.discriminating_tests or []) if test.get("title")
        )
        components = Counter(name for item in members for name in (item.components_involved or []))
        stamps = [item.created_at for item in members if item.created_at]
        scope = dict(scope_items)
        groups.append(
            _OwnGroup(
                scope_level=level, scope=scope, dtc_scope=dtc_scope, dtc_signature=sig,
                root_cause_component=component, repair_action_type=repair,
                case_count=len(members), garage_count=1,
                confirmed_count=outcomes.get(capture.CONFIRMED, 0),
                supported_count=outcomes.get(capture.SUPPORTED, 0),
                contradicting_count=outcomes.get(capture.CONTRADICTED, 0),
                unresolved_count=outcomes.get(capture.UNRESOLVED, 0),
                unknown_count=outcomes.get(capture.UNKNOWN, 0),
                mileage_min=min(mileages) if mileages else None,
                mileage_max=max(mileages) if mileages else None,
                common_symptoms=[word for word, _ in symptoms.most_common(aggregation.MAX_SYMPTOMS)],
                discriminating_tests=[
                    {"title": title, "cases": count} for title, count in tests.most_common(aggregation.MAX_TESTS)
                ],
                component_examples=[name for name, _ in components.most_common(aggregation.MAX_COMPONENTS)],
                # Own history is shown whatever its support level: it is the
                # workshop's own record, not a claim about other vehicles.
                support_label=trust.support_label(
                    outcomes.get(capture.CONFIRMED, 0), 1, outcomes.get(capture.CONTRADICTED, 0)
                ),
                last_seen_at=max(stamps) if stamps else now(),
                pattern_key=signature.pattern_key(level, scope, dtc_scope, sig, component, repair),
            )
        )
    return groups


def _cause_label(item) -> str:
    """Readable cause for the report; the key itself stays a machine identifier."""
    system, component, position = None, None, None
    key = item.root_cause_component or ""
    if key.count("/") >= 1:
        pieces = key.split("/")
        system, component = pieces[0], pieces[1]
        position = pieces[2] if len(pieces) > 2 else None
    return taxonomy.label(system, component, position, fallback=key)


def _excerpt(item, scope: str) -> str:
    """Aggregate wording. No garage name, no date of intervention, no free text."""
    origin = (
        f"{item.case_count} cas ORVECT compatibles dans cet atelier"
        if scope == OWN_WORKSHOP
        else f"{item.case_count} cas ORVECT compatibles répartis sur {item.garage_count} ateliers indépendants"
    )
    parts = [
        f"Cause racine constatée : {_cause_label(item)}.",
        f"Observation : {origin}.",
        f"Issues : {item.confirmed_count} confirmée(s), {item.supported_count} corroborée(s), "
        f"{item.contradicting_count} contredite(s).",
    ]
    rate = (
        aggregation.repair_success_rate(item)
        if isinstance(item, ExperiencePattern)
        else None
    )
    if rate is not None:
        parts.append(f"Taux de résolution observé : {round(rate * 100)} %.")
    if item.discriminating_tests:
        titles = ", ".join(test["title"] for test in item.discriminating_tests[:3])
        parts.append(f"Contrôles ayant départagé les hypothèses : {titles}.")
    if item.mileage_min and item.mileage_max:
        parts.append(f"Kilométrage observé : {item.mileage_min}–{item.mileage_max} km.")
    if item.contradicting_count:
        parts.append("Des cas contredisent cette cause : à confirmer par les contrôles.")
    parts.append(
        "Évidence de terrain ORVECT agrégée et anonymisée. Association observée, "
        "pas une causalité établie ni une procédure constructeur."
    )
    return " ".join(parts)


def _evidence_item(item, match: compatibility.Match, scope: str) -> dict:
    source_id = signature.field_source_id(item.pattern_key)
    seen = item.last_seen_at or now()
    # Network evidence is coarsened to the month: an exact date would say when a
    # specific vehicle passed through a specific workshop.
    if scope == NETWORK:
        seen = seen.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    stamp = seen.isoformat()
    return {
        "id": source_id,
        "title": f"Expérience ORVECT · {_cause_label(item)}",
        "excerpt": _excerpt(item, scope),
        "origin": "orvect_field_evidence",
        "trust_class": trust.ORVECT_FIELD,
        "vehicle_scope": {
            "scope": "orvect_field_evidence",
            "level": match.level,
            "matched_on": match.matched_on,
            **item.scope,
        },
        "field_evidence": {
            "evidence_scope": scope,
            "support_label": item.support_label,
            "compatibility_level": match.level,
            "compatibility_score": match.score,
            "matched_on": match.matched_on,
            "case_count": item.case_count,
            "garage_count": item.garage_count,
            "confirmed_count": item.confirmed_count,
            "supported_count": item.supported_count,
            "contradicting_count": item.contradicting_count,
            "root_cause_component": item.root_cause_component,
            "repair_action_type": item.repair_action_type,
            "discriminating_tests": item.discriminating_tests,
            "notes": match.notes,
        },
        "source": {
            "source_id": source_id,
            "source_type": trust.FIELD_EVIDENCE_SOURCE_TYPE,
            "source_version": stamp[:10],
            # Compatibility is carried in the source itself so the server can
            # rebuild the exact citation the model is allowed to make.
            "vehicle_compatibility": {
                "scope": "orvect_field_evidence",
                "level": match.level,
                "matched_on": match.matched_on,
                "support_label": item.support_label,
            },
            "timestamp": stamp,
            # Field evidence is never verified documentation. This is what stops
            # it from unlocking a manufacturer procedure downstream.
            "verified": False,
            "title": f"Expérience ORVECT · {_cause_label(item)}",
            "domain": None,
            "url": None,
        },
    }


def field_evidence(db: Session, vehicle: dict, codes, garage_id: str | None) -> list[dict]:
    """Compatible ORVECT field evidence, strongest match first."""
    signatures = _live_signatures(codes)
    if not signatures:
        return []
    dims = signature.dimensions(vehicle)
    if not dims.get("brand"):
        # Without a brand there is no defensible compatibility claim.
        return []

    # One finding, one evidence item. The same cases are indexed at several
    # scope levels, so without this the technician would read the same
    # observation four times and the counters would be silently multiplied.
    found: dict[tuple[str, str], tuple[int, dict]] = {}
    for scope, items in (
        (NETWORK, _candidate_patterns(db, signatures)),
        (OWN_WORKSHOP, _own_groups(db, garage_id, signatures)),
    ):
        for item in items:
            match = compatibility.evaluate(dims, codes, item)
            if not compatibility.acceptable(match):
                continue
            key = (item.root_cause_component, item.repair_action_type)
            current = found.get(key)
            # Most specific compatible match wins; a network-backed finding wins
            # a tie because it rests on more than one workshop.
            weight = (match.score, scope == NETWORK)
            if not current or weight > current[0]:
                found[key] = (weight, _evidence_item(item, match, scope))

    ordered = sorted(
        found.values(),
        key=lambda entry: (entry[0], entry[1]["field_evidence"]["confirmed_count"]),
        reverse=True,
    )
    return [payload for _weight, payload in ordered][:MAX_FIELD_EVIDENCE]


def summarize(evidence: list[dict]) -> dict:
    """Compact view used by the deterministic research decision."""
    if not evidence:
        return {
            "available": False, "items": 0, "best_level": None, "best_score": 0,
            "strongest_support": None, "confirmed_cases": 0, "independent_garages": 0,
            "contradicted": False, "distinct_root_causes": 0, "network_backed": False,
        }
    details = [item["field_evidence"] for item in evidence]
    best = max(details, key=lambda item: item["compatibility_score"])
    network = [item for item in details if item["evidence_scope"] == NETWORK]
    return {
        "available": True,
        "items": len(details),
        "best_level": best["compatibility_level"],
        "best_score": best["compatibility_score"],
        "strongest_support": max(
            (item["support_label"] for item in details),
            key=lambda label: trust.SUPPORT_ORDER.get(label, 0),
        ),
        # Counted from the best-matched finding, never summed across findings:
        # the research gate reads this number and an inflated count would
        # suppress an external search that was actually needed.
        "confirmed_cases": best["confirmed_count"],
        "independent_garages": best["garage_count"],
        "contradicted": any(item["contradicting_count"] for item in details),
        "distinct_root_causes": len({item["root_cause_component"] for item in details}),
        "network_backed": bool(network),
    }
