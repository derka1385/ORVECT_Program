"""Aggregate individual experience cases into reusable patterns.

Every counter here is recomputed from the link rows rather than incremented, so
a pattern is always reproducible from the cases behind it. That property is
what makes an aggregate auditable: it can be rebuilt and compared.
"""

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import ExperienceCase, ExperiencePattern, ExperiencePatternCase, now

from . import capture, signature, trust
from .capture import _aware

MAX_SYMPTOMS = 8
MAX_TESTS = 8
MAX_COMPONENTS = 5


def _pattern_rows(case: ExperienceCase) -> list[dict]:
    """Every (level, dtc scope) a case may legitimately be learned under."""
    dims = signature.dimensions(
        {
            "manufacturer": case.manufacturer,
            "make": case.make,
            "model": case.model,
            "generation": case.generation,
            "platform": case.platform,
            "engine_code": case.engine_code,
            "engine_family": case.engine_family,
            "fuel_type": case.fuel_type,
            "transmission_type": case.transmission_type,
            "drivetrain": case.drivetrain,
            "ecu_manufacturer": case.ecu_manufacturer,
            "ecu_model": case.ecu_model,
        }
    )
    rows = []
    for level, scope, _weight in signature.scope_signatures(dims):
        for dtc_scope, sig in signature.dtc_variants(case.dtc_codes):
            rows.append(
                {
                    "level": level,
                    "scope": scope,
                    "dtc_scope": dtc_scope,
                    "dtc_signature": sig,
                    "pattern_key": signature.pattern_key(
                        level, scope, dtc_scope, sig,
                        case.root_cause_component, case.repair_action_type,
                    ),
                }
            )
    return rows


def index_case(db: Session, case: ExperienceCase) -> list[ExperiencePattern]:
    """Attach one case to its patterns and recompute them.

    A case that is not shareable stays in its own workshop: it is recorded and
    counted for that garage's metrics, but it never reaches a shared pattern.
    """
    if case.revoked_at:
        return []
    if not case.shareable or case.outcome_class not in capture.PATTERN_ELIGIBLE_OUTCOMES:
        return []
    if not case.root_cause_component or not case.dtc_signature:
        return []

    touched = []
    for descriptor in _pattern_rows(case):
        pattern = db.scalar(
            select(ExperiencePattern).where(ExperiencePattern.pattern_key == descriptor["pattern_key"])
        )
        if not pattern:
            pattern = ExperiencePattern(
                pattern_key=descriptor["pattern_key"],
                scope_level=descriptor["level"],
                scope=descriptor["scope"],
                dtc_scope=descriptor["dtc_scope"],
                dtc_signature=descriptor["dtc_signature"],
                root_cause_component=case.root_cause_component,
                repair_action_type=case.repair_action_type,
                first_seen_at=_aware(case.created_at) or now(),
            )
            db.add(pattern)
            db.flush()
        link = db.scalar(
            select(ExperiencePatternCase).where(
                ExperiencePatternCase.pattern_id == pattern.id,
                ExperiencePatternCase.case_id == case.id,
            )
        )
        if not link:
            db.add(
                ExperiencePatternCase(
                    pattern_id=pattern.id,
                    case_id=case.id,
                    garage_id=case.garage_id,
                    outcome_class=case.outcome_class,
                )
            )
            db.flush()
        recompute(db, pattern)
        touched.append(pattern)
    return touched


def unindex_case(db: Session, case: ExperienceCase) -> int:
    """Detach a revoked case and recompute every pattern it fed."""
    links = db.scalars(
        select(ExperiencePatternCase).where(ExperiencePatternCase.case_id == case.id)
    ).all()
    patterns = [db.get(ExperiencePattern, link.pattern_id) for link in links]
    for link in links:
        db.delete(link)
    db.flush()
    for pattern in patterns:
        if pattern:
            recompute(db, pattern)
    return len(links)


def recompute(db: Session, pattern: ExperiencePattern) -> ExperiencePattern:
    """Rebuild every counter of a pattern from its linked cases."""
    cases = db.scalars(
        select(ExperienceCase)
        .join(ExperiencePatternCase, ExperiencePatternCase.case_id == ExperienceCase.id)
        .where(ExperiencePatternCase.pattern_id == pattern.id)
    ).all()
    # A duplicate submission keeps its row but stops counting, so one workshop
    # cannot inflate a pattern by closing the same job repeatedly.
    # A duplicate or revoked case keeps its row and stops counting.
    counted = [item for item in cases if not item.duplicate_of and not item.revoked_at]
    outcomes = Counter(item.outcome_class for item in counted)
    garages = {item.garage_id for item in counted}
    mileages = [item.mileage for item in counted if item.mileage]
    symptoms = Counter(word for item in counted for word in (item.symptom_keywords or []))
    tests = Counter(
        test.get("title", "")[:200]
        for item in counted
        for test in (item.discriminating_tests or [])
        if test.get("title")
    )
    components = Counter(
        component for item in counted for component in (item.components_involved or [])
    )
    # SQLite returns naive datetimes; a freshly flushed row is aware. Comparing
    # the two raises, so both are normalized before min/max.
    seen = [_aware(item.created_at) for item in counted if item.created_at]

    pattern.case_count = len(counted)
    pattern.garage_count = len(garages)
    pattern.confirmed_count = outcomes.get(capture.CONFIRMED, 0)
    pattern.supported_count = outcomes.get(capture.SUPPORTED, 0)
    pattern.contradicting_count = outcomes.get(capture.CONTRADICTED, 0)
    pattern.unresolved_count = outcomes.get(capture.UNRESOLVED, 0)
    pattern.unknown_count = outcomes.get(capture.UNKNOWN, 0)
    pattern.mileage_min = min(mileages) if mileages else None
    pattern.mileage_max = max(mileages) if mileages else None
    pattern.common_symptoms = [word for word, _ in symptoms.most_common(MAX_SYMPTOMS)]
    pattern.discriminating_tests = [
        {"title": title, "cases": count} for title, count in tests.most_common(MAX_TESTS)
    ]
    pattern.component_examples = [name for name, _ in components.most_common(MAX_COMPONENTS)]
    pattern.support_label = trust.support_label(
        pattern.confirmed_count, pattern.garage_count, pattern.contradicting_count
    )
    if seen:
        pattern.first_seen_at = min(seen)
        pattern.last_seen_at = max(seen)
    pattern.updated_at = now()
    return pattern


def rebuild_all(db: Session) -> int:
    """Recompute every pattern. Used by admin tooling and by the tests."""
    patterns = db.scalars(select(ExperiencePattern)).all()
    for pattern in patterns:
        recompute(db, pattern)
    return len(patterns)


def repair_success_rate(pattern: ExperiencePattern) -> float | None:
    """Share of outcomes that held, or None when the sample is too small.

    Returned only for a corroborated pattern: a rate computed on one or two
    cases reads like a statistic without being one.
    """
    observed = pattern.confirmed_count + pattern.supported_count + pattern.contradicting_count
    if not trust.shareable_support(pattern.support_label) or observed < trust.CORROBORATED_MIN_CONFIRMED:
        return None
    return round((pattern.confirmed_count + pattern.supported_count) / observed, 3)
