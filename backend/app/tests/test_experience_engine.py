"""ORVECT Experience Engine: learning from workshop outcomes, safely.

These tests exist because the Experience Engine is the one component allowed to
turn opinion into evidence. What matters is not that it learns, but that it
refuses to learn the wrong things: unknown outcomes, one workshop's repeated
submissions, incompatible vehicles, and anything a language model claims about
its own sources.
"""

import json

import pytest
from sqlalchemy import select

from app.database.models import (
    DiagnosticCompletion,
    DiagnosticDataConsent,
    DiagnosticHypothesis,
    DiagnosticObservation,
    DiagnosticSession,
    DiagnosticStep,
    ExperienceCase,
    ExperiencePattern,
    ExperiencePatternCase,
    Garage,
    GarageMembership,
    HypothesisStateEvent,
    User,
    VehicleConfiguration,
    VehicleProfile,
    now,
)
from app.core.config import settings as settings_module
from app.database.session import SessionLocal
from app.modules.diagnostic_ai.providers import AIInvalidResponse
from app.modules.experience import (
    aggregation,
    capture,
    compatibility,
    metrics,
    next_check,
    retrieval,
    signature,
    taxonomy,
    trust,
)

GOLF = {
    "manufacturer": "Volkswagen",
    "make": "Volkswagen",
    "model": "Golf VII",
    "platform": "MQB",
    "engine_code": "CZCA",
    "fuel_type": "gasoline",
    "ecu_model": "MED17.5.5",
}
BMW = {
    "manufacturer": "BMW",
    "make": "BMW",
    "model": "320d",
    "platform": "F30",
    "engine_code": "N47D20C",
    "fuel_type": "diesel",
    "ecu_model": "DDE7.3",
}


# --- fixtures -----------------------------------------------------------------

def make_garage(db, name):
    garage = Garage(name=name)
    db.add(garage)
    db.flush()
    user = User(
        garage_id=garage.id, email=f"{garage.id[:8]}@example.test",
        display_name=name, role="technician", password_hash=None,
    )
    db.add(user)
    db.flush()
    db.add(GarageMembership(user_id=user.id, garage_id=garage.id, role="technician"))
    return garage, user


def make_completed_case(
    db, garage, user, vehicle_spec, codes, *, cause="bobine cylindre 1",
    outcome="confirmed", consent=True, mileage=120000, symptoms="ralenti irregulier",
    tests=(("Permuter les bobines 1 et 2", "positive"),),
):
    """Build a finished diagnosis and run it through the Experience Engine."""
    vehicle = VehicleProfile(
        garage_id=garage.id, make=vehicle_spec["make"], model=vehicle_spec["model"],
        year=2018, market="EU", engine_name="test", engine_code=vehicle_spec["engine_code"],
        fuel_type=vehicle_spec["fuel_type"], transmission="manual", notes="",
    )
    db.add(vehicle)
    db.flush()
    db.add(VehicleConfiguration(
        vehicle_id=vehicle.id, manufacturer=vehicle_spec["manufacturer"],
        make=vehicle_spec["make"], model=vehicle_spec["model"],
        platform=vehicle_spec["platform"], model_year=2018,
        engine_code=vehicle_spec["engine_code"], fuel_type=vehicle_spec["fuel_type"],
        engine_ecu_model=vehicle_spec.get("ecu_model"), confirmed_by_user=True,
        precision_level="confirmed", confidence_score=1.0,
    ))
    case = DiagnosticSession(
        garage_id=garage.id, technician_id=user.id, vehicle_profile_id=vehicle.id,
        status="completed", mileage=mileage, observed_symptoms=symptoms,
        appearance_circumstances="moteur chaud", completed_at=now(),
    )
    db.add(case)
    db.flush()
    for code in codes:
        db.add(DiagnosticObservation(
            session_id=case.id, observation_type="DTC", key=code,
            value={"namespace": "sae_obd2", "status": "active", "freeze_frame": {"rpm": 2000}},
            source="manual",
        ))
    for order, (title, state) in enumerate(tests, start=1):
        db.add(DiagnosticStep(
            session_id=case.id, step_order=order, title=title, objective="Durée estimée : 10 min.",
            instructions=[], required_tools=["Multimètre"], expected_results=[],
            safety_notes=[], source_ids=[], source_references=[],
            verification_status="unverified", status="completed",
            result={"state": state, "outcome": "", "comment": ""}, completed_at=now(),
        ))
    hypothesis = DiagnosticHypothesis(
        session_id=case.id, title=cause, suspected_component=cause,
        probability_score=70.0, confidence_label="medium", reasoning="",
        supporting_evidence=[], contradicting_evidence=[], source_ids=[],
        source_references=[], verification_status="unverified", status="likely",
    )
    db.add(hypothesis)
    db.flush()

    variants = {
        "confirmed": {"post_repair_result": "resolved", "dtc_after_repair": "cleared_no_return",
                      "root_cause_confidence": "successful_repair", "resolution_status": "problem_repaired"},
        "supported": {"post_repair_result": "partially_resolved", "dtc_after_repair": "not_checked",
                      "root_cause_confidence": "strongly_suspected", "resolution_status": "problem_repaired"},
        "contradicted": {"post_repair_result": "not_resolved", "dtc_after_repair": "returned",
                         "root_cause_confidence": "not_confirmed", "resolution_status": "problem_repaired"},
        "unknown": {"post_repair_result": "unknown_not_tested", "dtc_after_repair": "not_checked",
                    "root_cause_confidence": "strongly_suspected", "resolution_status": "repair_pending"},
        "unresolved": {"post_repair_result": "unknown_not_tested", "dtc_after_repair": "not_checked",
                       "root_cause_confidence": "not_confirmed", "resolution_status": "inconclusive"},
    }[outcome]
    completion = DiagnosticCompletion(
        session_id=case.id, garage_id=garage.id, user_id=user.id,
        confirmed_cause=cause, selected_hypothesis_id=hypothesis.id,
        repair_action_type="component_replaced", repair_action_details="",
        components_involved=[cause], technician_notes="", **variants,
    )
    db.add(completion)
    db.flush()
    consent_row = None
    if consent:
        consent_row = DiagnosticDataConsent(
            session_id=case.id, garage_id=garage.id, user_id=user.id,
            consent=True, consent_version="v1",
        )
        db.add(consent_row)
        db.flush()
    recorded = capture.capture(db, case, completion, consent_row)
    db.commit()
    return case, recorded


def seeded_network(db, garages=2, outcome="confirmed", spec=None, cause="bobine cylindre 1", codes=("P0301",)):
    """N independent workshops reporting the same finding."""
    cases = []
    for index in range(garages):
        garage, user = make_garage(db, f"Atelier {index}")
        cases.append(
            make_completed_case(db, garage, user, spec or GOLF, list(codes), cause=cause, outcome=outcome)
        )
    return cases


# --- outcome classification ---------------------------------------------------

@pytest.mark.parametrize(
    "outcome,expected",
    [
        ("confirmed", capture.CONFIRMED),
        ("supported", capture.SUPPORTED),
        ("contradicted", capture.CONTRADICTED),
        ("unknown", capture.UNKNOWN),
        ("unresolved", capture.UNRESOLVED),
    ],
)
def test_outcome_classification_is_deterministic(client, outcome, expected):
    with SessionLocal() as db:
        garage, user = make_garage(db, "Atelier")
        _case, recorded = make_completed_case(db, garage, user, GOLF, ["P0301"], outcome=outcome)
        assert recorded.outcome_class == expected


def test_unknown_repair_outcome_is_never_a_confirmation(client):
    """A repair nobody verified cannot support anything, however sure the technician is."""
    with SessionLocal() as db:
        garage, user = make_garage(db, "Atelier")
        _case, recorded = make_completed_case(db, garage, user, GOLF, ["P0301"], outcome="unknown")
        assert recorded.outcome_class == capture.UNKNOWN
        assert recorded.shareable is False
        assert "repair_outcome_not_observed" in recorded.quality_flags
        assert db.scalars(select(ExperiencePattern)).all() == []


def test_consent_is_required_before_a_case_leaves_the_workshop(client):
    with SessionLocal() as db:
        garage, user = make_garage(db, "Atelier")
        _case, recorded = make_completed_case(db, garage, user, GOLF, ["P0301"], consent=False)
        assert recorded.outcome_class == capture.CONFIRMED
        assert recorded.shareable is False
        assert db.scalars(select(ExperiencePattern)).all() == []


# --- aggregation --------------------------------------------------------------

def test_one_workshop_alone_never_reaches_corroborated(client):
    """A single garage fixing cars does not establish a rule for anyone else."""
    with SessionLocal() as db:
        garage, user = make_garage(db, "Atelier unique")
        for _ in range(4):
            make_completed_case(db, garage, user, GOLF, ["P0301"])
        patterns = db.scalars(select(ExperiencePattern)).all()
        assert patterns, "the cases should still be indexed"
        assert {item.support_label for item in patterns} == {trust.EMERGING}
        assert all(item.garage_count == 1 for item in patterns)


def test_two_independent_workshops_corroborate_a_pattern(client):
    with SessionLocal() as db:
        seeded_network(db, garages=2)
        engine = db.scalar(
            select(ExperiencePattern).where(ExperiencePattern.scope_level == "engine_ecu")
        )
        assert engine.garage_count == 2
        assert engine.confirmed_count == 2
        assert engine.support_label == trust.CORROBORATED
        assert trust.shareable_support(engine.support_label)


def test_established_support_requires_volume_and_independence(client):
    with SessionLocal() as db:
        seeded_network(db, garages=5)
        engine = db.scalar(
            select(ExperiencePattern).where(ExperiencePattern.scope_level == "engine_ecu")
        )
        assert engine.support_label == trust.ESTABLISHED
        assert aggregation.repair_success_rate(engine) == 1.0


def test_contradicting_outcomes_demote_a_pattern(client):
    with SessionLocal() as db:
        seeded_network(db, garages=2)
        # Three workshops then report the same repair failing.
        for index in range(3):
            garage, user = make_garage(db, f"Contradiction {index}")
            make_completed_case(db, garage, user, GOLF, ["P0301"], outcome="contradicted")
        engine = db.scalar(
            select(ExperiencePattern).where(ExperiencePattern.scope_level == "engine_ecu")
        )
        assert engine.contradicting_count == 3
        assert engine.confirmed_count == 2
        assert engine.support_label == trust.EMERGING, "contradiction must be able to demote"


def test_duplicate_submissions_do_not_inflate_a_pattern(client):
    """One workshop closing the same job repeatedly must not manufacture support."""
    with SessionLocal() as db:
        seeded_network(db, garages=2)
        garage, user = make_garage(db, "Atelier bavard")
        first = make_completed_case(db, garage, user, GOLF, ["P0301"])[1]
        repeats = [make_completed_case(db, garage, user, GOLF, ["P0301"])[1] for _ in range(4)]
        assert first.duplicate_of is None
        assert all(item.duplicate_of for item in repeats)
        assert all("duplicate_submission" in item.quality_flags for item in repeats)
        engine = db.scalar(
            select(ExperiencePattern).where(ExperiencePattern.scope_level == "engine_ecu")
        )
        assert engine.garage_count == 3
        assert engine.confirmed_count == 3, "the four repeats must count once"


def test_patterns_are_reproducible_from_their_raw_cases(client):
    """An aggregate that cannot be rebuilt from its cases is not auditable."""
    with SessionLocal() as db:
        seeded_network(db, garages=3)
        before = {
            item.pattern_key: (item.case_count, item.confirmed_count, item.garage_count, item.support_label)
            for item in db.scalars(select(ExperiencePattern)).all()
        }
        for pattern in db.scalars(select(ExperiencePattern)).all():
            pattern.case_count = pattern.confirmed_count = pattern.garage_count = 0
            pattern.support_label = trust.EMERGING
        db.flush()
        aggregation.rebuild_all(db)
        after = {
            item.pattern_key: (item.case_count, item.confirmed_count, item.garage_count, item.support_label)
            for item in db.scalars(select(ExperiencePattern)).all()
        }
        assert after == before


def test_raw_cases_are_never_destroyed_by_aggregation(client):
    with SessionLocal() as db:
        seeded_network(db, garages=2)
        cases = db.scalars(select(ExperienceCase)).all()
        links = db.scalars(select(ExperiencePatternCase)).all()
        assert len(cases) == 2
        assert links, "every pattern must stay traceable to its cases"
        assert {item.case_id for item in links} <= {item.id for item in cases}


# --- compatibility ------------------------------------------------------------

def test_a_different_manufacturer_is_not_evidence(client):
    """A Golf finding must not become evidence for a BMW with the same code."""
    with SessionLocal() as db:
        seeded_network(db, garages=3)
        evidence = retrieval.field_evidence(db, BMW, [{"code": "P0301"}], garage_id=None)
        assert evidence == []


def test_same_manufacturer_different_engine_matches_only_weakly(client):
    with SessionLocal() as db:
        seeded_network(db, garages=3)
        other_engine = {**GOLF, "engine_code": "DADA", "ecu_model": "MED17.9"}
        evidence = retrieval.field_evidence(db, other_engine, [{"code": "P0301"}], garage_id=None)
        levels = {item["field_evidence"]["compatibility_level"] for item in evidence}
        assert "engine" not in levels and "engine_ecu" not in levels
        assert levels <= {"model", "brand", "platform"}
        assert len(evidence) == 1
        strong = retrieval.field_evidence(db, GOLF, [{"code": "P0301"}], garage_id=None)
        assert max(item["field_evidence"]["compatibility_score"] for item in strong) > max(
            item["field_evidence"]["compatibility_score"] for item in evidence
        )


def test_one_finding_yields_one_evidence_item(client):
    """The same cases are indexed at several scope levels; the reader sees one."""
    with SessionLocal() as db:
        seeded_network(db, garages=3)
        evidence = retrieval.field_evidence(db, GOLF, [{"code": "P0301"}], garage_id=None)
        assert len(evidence) == 1
        summary = retrieval.summarize(evidence)
        assert summary["confirmed_cases"] == 3, "counts must not be summed across levels"
        assert summary["best_level"] == "engine_ecu"


def test_compatibility_explains_why_a_case_was_matched(client):
    with SessionLocal() as db:
        seeded_network(db, garages=3)
        evidence = retrieval.field_evidence(db, GOLF, [{"code": "P0301"}], garage_id=None)
        best = max(evidence, key=lambda item: item["field_evidence"]["compatibility_score"])
        detail = best["field_evidence"]
        assert detail["compatibility_level"] == "engine_ecu"
        assert set(detail["matched_on"]) == {"brand", "engine_code", "ecu_model", "dtc_set"}


def test_a_partial_vehicle_match_is_not_a_weak_match(client):
    """Missing a dimension of a scope means no match at that level, not a low score."""
    with SessionLocal() as db:
        seeded_network(db, garages=3)
        pattern = db.scalar(
            select(ExperiencePattern).where(ExperiencePattern.scope_level == "engine_ecu")
        )
        dims = signature.dimensions({**GOLF, "ecu_model": None})
        assert compatibility.evaluate(dims, [{"code": "P0301"}], pattern) is None


def test_a_single_code_still_finds_a_multi_code_case(client):
    with SessionLocal() as db:
        seeded_network(db, garages=3, codes=("P0301", "P0171"))
        evidence = retrieval.field_evidence(db, GOLF, [{"code": "P0301"}], garage_id=None)
        assert evidence, "a shared code should still surface the experience"
        assert all(item["field_evidence"]["matched_on"][-1] == "dtc_code" for item in evidence)


def test_no_brand_means_no_compatibility_claim(client):
    with SessionLocal() as db:
        seeded_network(db, garages=3)
        assert retrieval.field_evidence(db, {"model": "Golf VII"}, [{"code": "P0301"}], None) == []


# --- privacy and tenant isolation ---------------------------------------------

def test_field_evidence_never_exposes_another_garage_raw_data(client):
    """Aggregates cross workshops; raw cases never do."""
    with SessionLocal() as db:
        cases = seeded_network(db, garages=3)
        garage_ids = {db.get(DiagnosticSession, case.id).garage_id for case, _ in cases}
        evidence = retrieval.field_evidence(db, GOLF, [{"code": "P0301"}], garage_id=None)
        assert evidence
        blob = str(evidence)
        for garage_id in garage_ids:
            assert garage_id not in blob
        for case, recorded in cases:
            assert case.id not in blob
            assert recorded.id not in blob
        for item in evidence:
            assert "garage_id" not in item["field_evidence"]
            assert "session_id" not in item["field_evidence"]
            assert item["field_evidence"]["garage_count"] >= 1


def test_own_workshop_history_stays_inside_the_workshop(client):
    """A garage sees its own unshared cases; nobody else does."""
    with SessionLocal() as db:
        garage, user = make_garage(db, "Atelier privé")
        make_completed_case(db, garage, user, GOLF, ["P0301"], consent=False)
        mine = retrieval.field_evidence(db, GOLF, [{"code": "P0301"}], garage_id=garage.id)
        assert mine, "a workshop must benefit from its own history"
        assert all(item["field_evidence"]["evidence_scope"] == retrieval.OWN_WORKSHOP for item in mine)

        other, _other_user = make_garage(db, "Autre atelier")
        assert retrieval.field_evidence(db, GOLF, [{"code": "P0301"}], garage_id=other.id) == []
        assert retrieval.field_evidence(db, GOLF, [{"code": "P0301"}], garage_id=None) == []


def test_network_evidence_requires_corroboration_before_it_travels(client):
    with SessionLocal() as db:
        garage, user = make_garage(db, "Premier atelier")
        make_completed_case(db, garage, user, GOLF, ["P0301"])
        other, _ = make_garage(db, "Second atelier")
        assert retrieval.field_evidence(db, GOLF, [{"code": "P0301"}], garage_id=other.id) == []

        second_garage, second_user = make_garage(db, "Troisième atelier")
        make_completed_case(db, second_garage, second_user, GOLF, ["P0301"])
        shared = retrieval.field_evidence(db, GOLF, [{"code": "P0301"}], garage_id=other.id)
        assert shared and all(
            item["field_evidence"]["evidence_scope"] == retrieval.NETWORK for item in shared
        )


def test_evidence_text_is_aggregated_not_narrative(client):
    with SessionLocal() as db:
        seeded_network(db, garages=3)
        evidence = retrieval.field_evidence(db, GOLF, [{"code": "P0301"}], garage_id=None)
        excerpt = evidence[0]["excerpt"]
        assert "ateliers indépendants" in excerpt
        assert "Association observée" in excerpt, "causality must not be claimed"
        assert "Atelier 0" not in excerpt


# --- provenance and the model boundary ----------------------------------------

def _field_context(db):
    evidence = retrieval.field_evidence(db, GOLF, [{"code": "P0301"}], garage_id=None)
    assert evidence
    return evidence[0]


def test_field_evidence_carries_provenance_and_is_never_verified(client):
    with SessionLocal() as db:
        seeded_network(db, garages=3)
        source = _field_context(db)["source"]
        assert source["source_id"].startswith("orvect:")
        assert source["source_type"] == trust.FIELD_EVIDENCE_SOURCE_TYPE
        assert source["verified"] is False, "field evidence is not verified documentation"
        assert source["vehicle_compatibility"]["scope"] == "orvect_field_evidence"
        assert source["vehicle_compatibility"]["matched_on"]


def test_field_evidence_is_traceable_back_to_its_cases(client):
    with SessionLocal() as db:
        seeded_network(db, garages=3)
        source_id = _field_context(db)["source"]["source_id"]
        pattern = next(
            item for item in db.scalars(select(ExperiencePattern)).all()
            if signature.field_source_id(item.pattern_key) == source_id
        )
        links = db.scalars(
            select(ExperiencePatternCase).where(ExperiencePatternCase.pattern_id == pattern.id)
        ).all()
        assert len(links) == pattern.case_count


def test_model_cannot_fabricate_a_field_source_id(client):
    from app.modules.diagnostic_ai.providers import validate_provider_sources
    from app.modules.diagnostic_ai.schemas import LLMDiagnosticAnalysis
    from test_orvect_research import _context, _valid_payload

    forged = dict(
        source_id="orvect:0000000000000000",
        source_type=trust.FIELD_EVIDENCE_SOURCE_TYPE,
        source_version="2026-09-19",
        vehicle_compatibility={"scope": "orvect_field_evidence"},
        timestamp="2026-09-19T00:00:00+00:00",
        verified=False,
    )
    payload = _valid_payload(expanded=True)
    payload["hypotheses"][0]["sources"] = [forged]
    with pytest.raises(AIInvalidResponse):
        validate_provider_sources(LLMDiagnosticAnalysis.model_validate(payload), _context())


def test_model_cannot_elevate_field_evidence_into_oem_evidence(client):
    """Citing a real field id while claiming OEM authority is overwritten by the server."""
    from app.modules.diagnostic_ai.providers import _normalize_provider_payload, validate_provider_sources
    from app.modules.diagnostic_ai.schemas import LLMDiagnosticAnalysis
    from test_orvect_research import _context, _valid_payload

    with SessionLocal() as db:
        seeded_network(db, garages=3)
        item = _field_context(db)

    context = _context(technical_excerpts=[item])
    payload = _valid_payload()
    payload["hypotheses"][0]["sources"] = [{"source_id": item["source"]["source_id"]}]
    payload["hypotheses"][0]["verificationStatus"] = "verified"
    normalized, _changed = _normalize_provider_payload(payload, context)
    rebuilt = normalized["hypotheses"][0]["sources"][0]
    assert rebuilt["source_type"] == trust.FIELD_EVIDENCE_SOURCE_TYPE
    assert rebuilt["verified"] is False
    validate_provider_sources(LLMDiagnosticAnalysis.model_validate(normalized), context)

    # The same citation with an OEM claim attached is rebuilt, never honoured.
    claimed = dict(item["source"], source_type="oem_manufacturer", verified=True)
    payload2 = _valid_payload(expanded=True)
    payload2["hypotheses"][0]["sources"] = [claimed]
    with pytest.raises(AIInvalidResponse):
        validate_provider_sources(LLMDiagnosticAnalysis.model_validate(payload2), context)


def test_field_evidence_cannot_unlock_a_manufacturer_procedure(client):
    from app.modules.diagnostic_ai.schemas import NextCheck

    with SessionLocal() as db:
        seeded_network(db, garages=3)
        source = _field_context(db)["source"]
    with pytest.raises(ValueError):
        NextCheck.model_validate({
            "id": "c1", "order": 1, "title": "Contrôle", "objective": "o",
            "prerequisites": [], "instructions": [], "safetyWarnings": [],
            "expectedResults": [], "requiredTools": [], "estimatedDifficulty": "easy",
            "verificationStatus": "verified", "manufacturerProcedure": True,
            "sources": [source],
        })


def test_authoritative_dtc_definitions_remain_immutable(client):
    """Field evidence changes ranking, never a catalogue definition."""
    from app.modules.diagnostic_ai.analysis_service import _validate_dtc_interpretations
    from app.modules.diagnostic_ai.schemas import LLMDiagnosticAnalysis
    from test_orvect_research import _context, _valid_payload

    payload = _valid_payload(expanded=True)
    payload["interpretedFaultCodes"][0]["meaning"] = "Observé 17 fois : bobine défaillante"
    with pytest.raises(AIInvalidResponse):
        _validate_dtc_interpretations(LLMDiagnosticAnalysis.model_validate(payload), _context())


def test_safety_engine_authority_is_untouched_by_experience(client):
    """No volume of field cases can move a safety decision."""
    from app.modules.diagnostic_ai.safety_engine import SafetyEngine

    with SessionLocal() as db:
        seeded_network(db, garages=5)
        evidence = retrieval.field_evidence(db, GOLF, [{"code": "P0301"}], garage_id=None)
    assessment = SafetyEngine().assess({
        "fault_codes": [{"code": "P0301", "status": "active"}],
        "untrusted_user_data": {"symptoms": "ralenti irregulier"},
        "orvect_field_evidence": evidence,
        "field_evidence_summary": retrieval.summarize(evidence),
    })
    assert assessment.status == "UNKNOWN"
    assert assessment.humanReviewRequired is True
    assert assessment.decisionSource == "safety_engine"


# --- research decision --------------------------------------------------------

def _research_context(summary, **overrides):
    base = {
        "technical_definitions": [
            {"definition_type": "generic_standardized", "documented": True}
        ],
        "fault_codes": [{"code": "P0301"}],
        "internal_excerpts": [{"id": 1}, {"id": 2}, {"id": 3}],
        "vehicle": {"make": "Volkswagen", "model": "Golf VII", "model_year": 2018, "engine_code": "CZCA"},
        "untrusted_user_data": {"symptoms": ""},
        "field_evidence_summary": summary,
    }
    base.update(overrides)
    return base


def _strong_summary(**changes):
    summary = {
        "available": True, "items": 2, "best_level": "engine_ecu", "best_score": 118,
        "strongest_support": trust.ESTABLISHED, "confirmed_cases": 5,
        "independent_garages": 3, "contradicted": False, "distinct_root_causes": 1,
        "network_backed": True,
    }
    summary.update(changes)
    return summary


def test_strong_field_evidence_can_avoid_an_external_search(client, monkeypatch):
    from app.modules.research.decision import decide_research

    monkeypatch.setattr(settings_module, "tavily_api_key", "test-key")
    context = _research_context(_strong_summary(), internal_excerpts=[{"id": 1}])
    plan = decide_research(context)
    assert plan.needed is False
    assert "orvect_field_evidence_sufficient" in plan.reasons


def test_contradictory_field_evidence_always_triggers_research(client, monkeypatch):
    from app.modules.research.decision import decide_research

    monkeypatch.setattr(settings_module, "tavily_api_key", "test-key")
    plan = decide_research(_research_context(_strong_summary(contradicted=True)))
    assert plan.needed is True
    assert "field_evidence_contradictory" in plan.reasons


def test_diverging_field_evidence_triggers_research(client, monkeypatch):
    from app.modules.research.decision import decide_research

    monkeypatch.setattr(settings_module, "tavily_api_key", "test-key")
    plan = decide_research(_research_context(_strong_summary(distinct_root_causes=3)))
    assert plan.needed is True
    assert "field_evidence_diverges_on_root_cause" in plan.reasons


def test_field_evidence_never_replaces_a_missing_definition(client, monkeypatch):
    """Experience cannot stand in for a manufacturer definition ORVECT lacks."""
    from app.modules.research.decision import decide_research

    monkeypatch.setattr(settings_module, "tavily_api_key", "test-key")
    plan = decide_research(_research_context(
        _strong_summary(),
        technical_definitions=[{"definition_type": "manufacturer_specific", "documented": False}],
    ))
    assert plan.needed is True
    assert "manufacturer_specific_code" in plan.reasons
    assert "orvect_field_evidence_sufficient" not in plan.reasons


def test_weak_field_evidence_does_not_suppress_research(client, monkeypatch):
    from app.modules.research.decision import decide_research

    monkeypatch.setattr(settings_module, "tavily_api_key", "test-key")
    plan = decide_research(_research_context(
        _strong_summary(confirmed_cases=1, independent_garages=1, network_backed=False),
        internal_excerpts=[{"id": 1}],
    ))
    assert plan.needed is True
    assert "orvect_field_evidence_sufficient" not in plan.reasons


# --- iterative diagnosis ------------------------------------------------------

def _check(identifier, title, difficulty="easy", minutes=10, tools=("Multimètre",), outcomes=()):
    return {
        "id": identifier, "order": 1, "title": title,
        "objective": f"Durée estimée : {minutes} min. Vérifier.",
        "requiredTools": list(tools), "estimatedDifficulty": difficulty,
        "expectedResults": [
            {"outcome": item, "interpretation": item, "nextAction": ""} for item in outcomes
        ],
    }


def test_next_check_prefers_cheap_fast_discriminating_work(client):
    hypotheses = [
        {"label": "Bobine allumage cylindre 1", "component": "bobine"},
        {"label": "Bougie encrassée", "component": "bougie"},
    ]
    cheap = _check("cheap", "Permuter bobine et bougie", "easy", 10, ("Multimètre",),
                   ("bobine defaillante", "bougie encrassee"))
    costly = _check("costly", "Démonter la culasse", "advanced", 180,
                    ("Pont", "Outillage spécifique", "Clé dynamométrique", "Joint"), ())
    ranked = next_check.rank([costly, cheap], hypotheses, set())
    assert ranked[0]["check"]["id"] == "cheap"
    assert ranked[0]["selectionMethod"] == next_check.SELECTION_METHOD
    assert any("départage" in line for line in ranked[0]["rationale"])


def test_next_check_never_repeats_completed_work(client):
    hypotheses = [{"label": "Bobine", "component": "bobine"}]
    done = _check("done", "Permuter les bobines")
    todo = _check("todo", "Inspecter la bougie")
    ranked = next_check.rank([done, todo], hypotheses, {"Permuter les bobines"})
    assert [item["check"]["id"] for item in ranked] == ["todo"]


def test_next_check_ranking_is_stable(client):
    hypotheses = [{"label": "Bobine", "component": "bobine"}]
    checks = [_check("a", "Contrôle A"), _check("b", "Contrôle B")]
    assert [item["check"]["id"] for item in next_check.rank(checks, hypotheses, set())] == \
           [item["check"]["id"] for item in next_check.rank(checks, hypotheses, set())]


def test_submitting_a_result_promotes_the_next_check(client, monkeypatch):
    """The loop: a result immediately produces the next action, with no model call."""
    case_id = _analysed_case(client, monkeypatch, checks=2)
    detail = client.get(f"/api/diagnostics/{case_id}").json()
    current = next(item for item in detail["steps"] if item["status"] == "current")
    pending = [item for item in detail["steps"] if item["status"] == "pending"]
    assert pending, "the plan should hold more than one check"

    response = client.post(
        f"/api/diagnostics/{case_id}/steps/{current['id']}/result",
        json={"state": "negative", "outcome": "Rien d’anormal", "comment": ""},
    )
    assert response.status_code == 200, response.text
    assert response.json()["next_step_id"] in {item["id"] for item in pending}
    after = client.get(f"/api/diagnostics/{case_id}").json()["steps"]
    assert sum(1 for item in after if item["status"] == "current") == 1


def test_hypothesis_history_is_appended_never_overwritten(client, monkeypatch):
    case_id = _analysed_case(client, monkeypatch, checks=2)
    detail = client.get(f"/api/diagnostics/{case_id}").json()
    hypothesis = detail["hypotheses"][0]
    current = next(item for item in detail["steps"] if item["status"] == "current")

    assert client.post(
        f"/api/diagnostics/{case_id}/hypotheses/{hypothesis['id']}/verdict",
        json={"verdict": "rejected", "evidence_note": "Permutation sans effet"},
    ).status_code == 201
    # The verdict re-selects the recommended check, so the current step is read
    # again rather than reused from before.
    current = next(
        item for item in client.get(f"/api/diagnostics/{case_id}").json()["steps"]
        if item["status"] == "current"
    )
    assert client.post(
        f"/api/diagnostics/{case_id}/steps/{current['id']}/result",
        json={"state": "negative", "outcome": "Aucune variation constatée", "comment": ""},
    ).status_code == 200

    evolution = client.get(f"/api/diagnostics/{case_id}/evolution").json()
    kinds = [item["event"] for item in evolution["timeline"]]
    assert "ranked" in kinds and "technician_verdict" in kinds and "test_result" in kinds
    assert evolution["timeline"] == sorted(evolution["timeline"], key=lambda item: item["at"])
    verdict_event = next(item for item in evolution["timeline"] if item["event"] == "technician_verdict")
    assert verdict_event["status_before"] == "likely"
    assert verdict_event["status_after"] == "rejected"
    assert verdict_event["strength_before"] is not None, "the prior strength must survive"


def test_a_rejected_hypothesis_is_marked_not_deleted(client, monkeypatch):
    case_id = _analysed_case(client, monkeypatch, checks=2)
    hypothesis = client.get(f"/api/diagnostics/{case_id}").json()["hypotheses"][0]
    client.post(
        f"/api/diagnostics/{case_id}/hypotheses/{hypothesis['id']}/verdict",
        json={"verdict": "rejected"},
    )
    with SessionLocal() as db:
        row = db.get(DiagnosticHypothesis, hypothesis["id"])
        assert row is not None, "history must survive a rejection"
        assert row.status == "rejected"
        assert row.title == hypothesis["title"]


def test_undetermined_verdict_is_not_a_confirmation(client, monkeypatch):
    case_id = _analysed_case(client, monkeypatch, checks=2)
    hypothesis = client.get(f"/api/diagnostics/{case_id}").json()["hypotheses"][0]
    client.post(
        f"/api/diagnostics/{case_id}/hypotheses/{hypothesis['id']}/verdict",
        json={"verdict": "undetermined"},
    )
    with SessionLocal() as db:
        row = db.get(DiagnosticHypothesis, hypothesis["id"])
        assert row.verification_status != "verified"
        assert row.status != "rejected"


# --- API surface --------------------------------------------------------------

def _rich_provider(monkeypatch):
    """A provider that actually ranks hypotheses and plans several checks.

    The built-in mock returns neither, so the iterative loop and the hypothesis
    history have nothing to exercise without this.
    """
    from app.modules.diagnostic_ai import analysis_service
    from app.modules.diagnostic_ai.providers import ProviderResult, _mock_analysis
    from app.modules.diagnostic_ai.schemas import Hypothesis, NextCheck

    def hypothesis(identifier, label, component, score, status):
        return Hypothesis(
            id=identifier, label=label, component=component, confidence=score,
            supportingEvidence=["Constat atelier"], contradictingEvidence=[],
            requiredConfirmation=["Contrôle à réaliser"], status=status,
            verificationStatus="unverified", sources=[],
        )

    def check(identifier, order, title, difficulty, minutes, tools):
        return NextCheck(
            id=identifier, order=order, title=title,
            objective=f"Durée estimée : {minutes} min. Départager les pistes.",
            prerequisites=[], instructions=["Étape"], safetyWarnings=[],
            expectedResults=[
                {"outcome": "bobine defaillante", "interpretation": "bobine defaillante",
                 "nextAction": "Poursuivre"},
                {"outcome": "bougie encrassee", "interpretation": "bougie encrassee",
                 "nextAction": "Poursuivre"},
            ],
            requiredTools=tools, estimatedDifficulty=difficulty,
            verificationStatus="unverified", manufacturerProcedure=False, sources=[],
        )

    class RichProvider:
        async def analyze_initial_case(self, context, images):
            analysis = _mock_analysis(context)
            analysis.hypotheses = [
                hypothesis("h1", "Bobine allumage cylindre 1", "bobine", 0.7, "likely"),
                hypothesis("h2", "Bougie encrassée cylindre 1", "bougie", 0.4, "possible"),
            ]
            analysis.nextChecks = [
                check("check-slow", 1, "Déposer et inspecter la culasse", "advanced", 180,
                      ["Pont", "Endoscope", "Clé dynamométrique", "Joint"]),
                check("check-fast", 2, "Permuter bobine et bougie du cylindre 1", "easy", 10,
                      ["Multimètre"]),
            ]
            analysis.finalConclusion.status = "testing_required"
            return ProviderResult(
                analysis, settings_module.llm_provider,
                analysis_service.selected_model(context, False), 1,
            )

        async def analyze_follow_up(self, context, images):
            return await self.analyze_initial_case(context, images)

    monkeypatch.setattr(analysis_service, "get_ai_provider", lambda: RichProvider())


def _analysed_case(client, monkeypatch=None, checks=1):
    if checks > 1:
        _rich_provider(monkeypatch)
    response = client.post("/api/diagnostics", json={
        "vehicle_id": client.get("/api/vehicles").json()["items"][0]["id"],
        "mileage": 125000, "symptoms": "Ratés moteur", "circumstances": "Moteur chaud",
    })
    assert response.status_code == 201, response.text
    case_id = response.json()["id"]
    assert client.post(f"/api/diagnostics/{case_id}/fault-codes", json={"fault_codes": [
        {"code": "P0301", "ecu": "ECU moteur", "status": "active", "freeze_frame": {},
         "technician_verification": "confirmed"}
    ]}).status_code == 201
    assert client.post(f"/api/diagnostics/{case_id}/analyze").status_code == 200
    return case_id


def test_evolution_endpoint_enforces_tenant_isolation(client):
    with SessionLocal() as db:
        garage, user = make_garage(db, "Ailleurs")
        case, _ = make_completed_case(db, garage, user, GOLF, ["P0301"])
        foreign_id = case.id
    assert client.get(f"/api/diagnostics/{foreign_id}/evolution").status_code == 404
    assert client.get(f"/api/diagnostics/{foreign_id}/field-evidence").status_code == 404
    assert client.post(
        f"/api/diagnostics/{foreign_id}/hypotheses/{foreign_id}/verdict",
        json={"verdict": "confirmed"},
    ).status_code == 404


def test_case_field_evidence_endpoint_returns_aggregates_only(client):
    with SessionLocal() as db:
        seeded_network(db, garages=3)
    case_id = _analysed_case(client)
    body = client.get(f"/api/diagnostics/{case_id}/field-evidence").json()
    assert "summary" in body
    for item in body["evidence"]:
        assert item["source_id"].startswith("orvect:")
        assert "garage_id" not in item
        assert item["trust_class"] == trust.ORVECT_FIELD


def test_intelligence_metrics_require_admin(client):
    response = client.get("/api/intelligence/metrics")
    assert response.status_code == 200, "the seeded session is the administrator"
    body = response.json()
    assert body["scope"] == "garage"
    assert set(body) >= {"diagnostic_quality", "pipeline_efficiency", "knowledge_growth"}


def test_metrics_decline_rates_below_the_minimum_sample(client):
    """A rate computed on two cases is noise; ORVECT returns nothing instead."""
    with SessionLocal() as db:
        garage, user = make_garage(db, "Petit atelier")
        for _ in range(2):
            make_completed_case(db, garage, user, GOLF, ["P0301"])
        report = metrics.report(db, garage.id)
    quality = report["diagnostic_quality"]
    assert quality["cases"] == 1, "the second submission is a duplicate"
    assert quality["repair_success_rate"] is None
    assert quality["first_hypothesis_confirmation_rate"] is None


def test_metrics_report_real_rates_once_the_sample_is_large_enough(client):
    with SessionLocal() as db:
        seeded_network(db, garages=6)
        report = metrics.report(db, None)
    quality = report["diagnostic_quality"]
    assert quality["confirmed_cases"] == 6
    assert quality["repair_success_rate"] == 1.0
    assert quality["first_hypothesis_confirmation_rate"] == 1.0
    growth = report["knowledge_growth"]
    assert growth["contributing_workshops"] == 6
    assert growth["patterns_established"] >= 1


def test_cost_is_measured_not_invented(client):
    """Without a configured tariff, ORVECT reports tokens and no price."""
    _analysed_case(client)
    with SessionLocal() as db:
        report = metrics.report(db, None)
    costs = report["pipeline_efficiency"]["cost_inputs"]
    assert costs["pricing_configured"] is False
    assert costs["estimated_cost_usd"] is None
    assert report["pipeline_efficiency"]["analyses"] >= 1
    assert "tavily_queries_per_analysis" in costs


def test_admin_can_review_and_reject_a_learned_pattern(client):
    with SessionLocal() as db:
        seeded_network(db, garages=5)
    listing = client.get("/api/intelligence/patterns", params={"support": "established"}).json()
    assert listing["patterns"], listing
    pattern = listing["patterns"][0]
    assert pattern["source_id"].startswith("orvect:")
    assert client.post(
        f"/api/intelligence/patterns/{pattern['id']}/review", params={"state": "rejected"}
    ).status_code == 200
    with SessionLocal() as db:
        assert retrieval.field_evidence(db, GOLF, [{"code": "P0301"}], None) == [] or all(
            item["source"]["source_id"] != pattern["source_id"]
            for item in retrieval.field_evidence(db, GOLF, [{"code": "P0301"}], None)
        )


def test_completion_endpoint_records_an_experience_case(client, monkeypatch):
    """The outcome workflow end to end, through the public API."""
    case_id = _analysed_case(client, monkeypatch, checks=2)
    detail = client.get(f"/api/diagnostics/{case_id}").json()
    current = next(item for item in detail["steps"] if item["status"] == "current")
    client.post(f"/api/diagnostics/{case_id}/steps/{current['id']}/result",
                json={"state": "positive", "outcome": "Défaut suit la bobine", "comment": ""})
    assert client.post(f"/api/diagnostics/{case_id}/consent", json={"consent": True}).status_code == 201
    response = client.post(f"/api/diagnostics/{case_id}/complete", json={
        "resolution_status": "problem_repaired",
        "confirmed_cause": "Bobine d’allumage cylindre 1",
        "selected_hypothesis_id": detail["hypotheses"][0]["id"],
        "repair_action_type": "component_replaced", "repair_action_details": "Bobine remplacée",
        "components_involved": ["Bobine cylindre 1"], "root_cause_confidence": "successful_repair",
        "post_repair_result": "resolved", "dtc_after_repair": "cleared_no_return",
        "technician_notes": "",
    })
    assert response.status_code == 201, response.text
    experience = response.json()["experience"]
    assert experience["recorded"] is True
    assert experience["outcome_class"] == capture.CONFIRMED
    with SessionLocal() as db:
        row = db.scalar(select(ExperienceCase).where(ExperienceCase.session_id == case_id))
        assert row.informative_test_count == 1
        assert row.confirmed_hypothesis_rank == 1
        assert row.dtc_signature == "sae_obd2:P0301"


def test_learning_failure_never_breaks_a_completion(client, monkeypatch):
    """Recording experience is secondary to the technician finishing their job."""
    def explode(*args, **kwargs):
        raise RuntimeError("aggregation exploded")

    monkeypatch.setattr(aggregation, "index_case", explode)
    case_id = _analysed_case(client)
    client.post(f"/api/diagnostics/{case_id}/consent", json={"consent": True})
    response = client.post(f"/api/diagnostics/{case_id}/complete", json={
        "resolution_status": "problem_repaired", "confirmed_cause": "Bobine",
        "selected_hypothesis_id": None, "repair_action_type": "component_replaced",
        "repair_action_details": "", "components_involved": ["Bobine"],
        "root_cause_confidence": "successful_repair", "post_repair_result": "resolved",
        "dtc_after_repair": "cleared_no_return", "technician_notes": "",
    })
    assert response.status_code == 201
    assert response.json()["experience"]["recorded"] is False


# --- caching and migrations ---------------------------------------------------

def test_analysis_cache_is_invalidated_by_the_new_prompt_version(client):
    from app.database.models import AICall
    from app.modules.diagnostic_ai.providers import PROMPT_VERSION

    case_id = _analysed_case(client)
    assert client.post(f"/api/diagnostics/{case_id}/analyze").status_code == 200
    with SessionLocal() as db:
        runs = db.scalars(
            select(AICall).where(AICall.session_id == case_id, AICall.status == "completed")
        ).all()
        assert len(runs) == 1, "an identical context must reuse the cached analysis"
        assert runs[0].prompt_version == PROMPT_VERSION


def test_migrations_have_a_single_head(client):
    """Asked of Alembic itself rather than parsed from the files."""
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    assert list(heads) == ["0014"], f"expected one head, found {heads}"


# --- review 2: adaptive next check --------------------------------------------

def _adaptive_provider(monkeypatch):
    """Three checks, each tied to a different hypothesis, plus one generic.

    Built so that eliminating a hypothesis genuinely changes which check is
    worth doing next; otherwise the loop cannot be shown to be adaptive.
    """
    from app.modules.diagnostic_ai import analysis_service
    from app.modules.diagnostic_ai.providers import ProviderResult, _mock_analysis
    from app.modules.diagnostic_ai.schemas import Hypothesis, NextCheck

    def hypothesis(identifier, label, component, score):
        return Hypothesis(
            id=identifier, label=label, component=component, confidence=score,
            supportingEvidence=["Constat"], contradictingEvidence=[],
            requiredConfirmation=["Contrôle"], status="likely",
            verificationStatus="unverified", sources=[],
        )

    def check(identifier, order, title, difficulty, minutes, tools, mentions):
        return NextCheck(
            id=identifier, order=order, title=title,
            objective=f"Durée estimée : {minutes} min. {mentions}",
            prerequisites=[], instructions=["Étape"], safetyWarnings=[],
            expectedResults=[
                {"outcome": mentions, "interpretation": mentions, "nextAction": "Poursuivre"},
            ],
            requiredTools=tools, estimatedDifficulty=difficulty,
            verificationStatus="unverified", manufacturerProcedure=False, sources=[],
        )

    class AdaptiveProvider:
        async def analyze_initial_case(self, context, images):
            analysis = _mock_analysis(context)
            analysis.hypotheses = [
                hypothesis("h-coil", "Bobine allumage cylindre 1", "bobine", 0.6),
                hypothesis("h-plug", "Bougie encrassée cylindre 1", "bougie", 0.5),
                hypothesis("h-inject", "Injecteur cylindre 1", "injecteur", 0.4),
            ]
            analysis.nextChecks = [
                check("c-coil", 1, "Mesurer la bobine", "easy", 10, ["Multimètre"], "bobine"),
                check("c-plug", 2, "Inspecter la bougie", "easy", 12, ["Clé"], "bougie"),
                check("c-inject", 3, "Tester l’injecteur", "intermediate", 25,
                      ["Manomètre", "Adaptateur"], "injecteur"),
            ]
            analysis.finalConclusion.status = "testing_required"
            return ProviderResult(
                analysis, settings_module.llm_provider,
                analysis_service.selected_model(context, False), 1,
            )

        async def analyze_follow_up(self, context, images):
            return await self.analyze_initial_case(context, images)

    monkeypatch.setattr(analysis_service, "get_ai_provider", lambda: AdaptiveProvider())


def _adaptive_case(client, monkeypatch):
    _adaptive_provider(monkeypatch)
    response = client.post("/api/diagnostics", json={
        "vehicle_id": client.get("/api/vehicles").json()["items"][0]["id"],
        "mileage": 125000, "symptoms": "Ratés moteur", "circumstances": "Moteur chaud",
    })
    case_id = response.json()["id"]
    client.post(f"/api/diagnostics/{case_id}/fault-codes", json={"fault_codes": [
        {"code": "P0301", "ecu": "ECU moteur", "status": "active", "freeze_frame": {},
         "technician_verification": "confirmed"}
    ]})
    assert client.post(f"/api/diagnostics/{case_id}/analyze").status_code == 200
    return case_id


def _current_step(client, case_id):
    steps = client.get(f"/api/diagnostics/{case_id}").json()["steps"]
    return next(item for item in steps if item["status"] == "current")


def _hypothesis_id(client, case_id, needle):
    for item in client.get(f"/api/diagnostics/{case_id}").json()["hypotheses"]:
        if needle in item["title"].casefold():
            return item["id"]
    raise AssertionError(f"hypothesis {needle} not found")


def test_next_check_reacts_to_what_the_result_eliminated(client, monkeypatch):
    """The same first test, two readings, two different next actions."""
    outcomes = {}
    for excluded, label in (("h-plug", "bougie"), ("h-inject", "injecteur")):
        case_id = _adaptive_case(client, monkeypatch)
        current = _current_step(client, case_id)
        target = _hypothesis_id(client, case_id, label)
        response = client.post(
            f"/api/diagnostics/{case_id}/steps/{current['id']}/result",
            json={"state": "negative", "outcome": "Valeur hors plage",
                  "excludes_hypothesis_ids": [target]},
        )
        assert response.status_code == 200, response.text
        outcomes[excluded] = _current_step(client, case_id)["title"]
    assert outcomes["h-plug"] != outcomes["h-inject"], outcomes
    assert "bougie" not in outcomes["h-plug"].casefold()
    assert "injecteur" not in outcomes["h-inject"].casefold()


def test_a_completed_check_is_never_recommended_again(client, monkeypatch):
    case_id = _adaptive_case(client, monkeypatch)
    seen = set()
    for _ in range(3):
        current = _current_step(client, case_id)
        assert current["id"] not in seen, "a completed check came back as current"
        seen.add(current["id"])
        response = client.post(
            f"/api/diagnostics/{case_id}/steps/{current['id']}/result",
            json={"state": "negative", "outcome": "Rien d’anormal"},
        )
        assert response.status_code == 200
        if not response.json()["next_step_id"]:
            break
    steps = client.get(f"/api/diagnostics/{case_id}").json()["steps"]
    assert all(item["status"] != "current" or not item["result"] for item in steps)


def test_rejecting_a_hypothesis_changes_the_recommended_check(client, monkeypatch):
    """A verdict outside the test loop still re-selects the next action."""
    case_id = _adaptive_case(client, monkeypatch)
    before = _current_step(client, case_id)
    target = _hypothesis_id(client, case_id, before["title"].split()[-1].casefold()[:6])
    response = client.post(
        f"/api/diagnostics/{case_id}/hypotheses/{target}/verdict",
        json={"verdict": "rejected", "evidence_note": "Écartée par mesure"},
    )
    assert response.status_code == 201, response.text
    after = _current_step(client, case_id)
    assert after["id"] != before["id"], "the check that targeted the rejected cause stayed current"
    assert response.json()["current_step_id"] == after["id"]


def test_an_irrelevant_check_sinks_below_a_discriminating_one(client):
    """Scoring, in isolation: no live hypothesis to separate means not next."""
    live = [{"label": "Bobine allumage cylindre 1", "component": "bobine"}]
    relevant = _check("relevant", "Mesurer la bobine", "advanced", 120, ("A", "B", "C", "D"))
    irrelevant = _check("irrelevant", "Contrôler le circuit de freinage", "easy", 5, ("A",))
    ranked = next_check.rank([irrelevant, relevant], live, set())
    assert ranked[0]["check"]["id"] == "relevant"
    assert any("ne départage plus" in line for line in ranked[-1]["rationale"])


def test_ranking_uses_the_persisted_cost_of_a_step(client, monkeypatch):
    """Difficulty and duration survive persistence, so re-ranking stays honest."""
    case_id = _adaptive_case(client, monkeypatch)
    with SessionLocal() as db:
        steps = db.scalars(
            select(DiagnosticStep).where(DiagnosticStep.session_id == case_id)
        ).all()
        assert {item.estimated_difficulty for item in steps} == {"easy", "intermediate"}
        assert all(item.estimated_minutes for item in steps)


def test_hypothesis_elimination_is_recorded_and_reversible_in_history(client, monkeypatch):
    case_id = _adaptive_case(client, monkeypatch)
    current = _current_step(client, case_id)
    target = _hypothesis_id(client, case_id, "injecteur")
    client.post(
        f"/api/diagnostics/{case_id}/steps/{current['id']}/result",
        json={"state": "positive", "outcome": "Débit conforme",
              "excludes_hypothesis_ids": [target],
              "supports_hypothesis_ids": [_hypothesis_id(client, case_id, "bobine")]},
    )
    timeline = client.get(f"/api/diagnostics/{case_id}/evolution").json()["timeline"]
    excluded = [item for item in timeline if item["event"] == "excluded_by_test"]
    supported = [item for item in timeline if item["event"] == "supported_by_test"]
    assert len(excluded) == 1 and excluded[0]["status_after"] == "rejected"
    assert excluded[0]["strength_before"] is not None
    assert len(supported) == 1
    assert supported[0]["detail"]["verification_after"] == "partially_verified"
    with SessionLocal() as db:
        assert db.get(DiagnosticHypothesis, target).status == "rejected"
        assert db.get(DiagnosticHypothesis, target).title


def test_an_unknown_hypothesis_id_is_refused(client, monkeypatch):
    case_id = _adaptive_case(client, monkeypatch)
    current = _current_step(client, case_id)
    response = client.post(
        f"/api/diagnostics/{case_id}/steps/{current['id']}/result",
        json={"state": "negative", "outcome": "x", "excludes_hypothesis_ids": ["not-a-real-id"]},
    )
    assert response.status_code == 422


# --- review 2: canonical root causes ------------------------------------------

@pytest.mark.parametrize("components,text", [
    (["Injecteur cylindre 1"], "injecteur cylindre 1 défectueux"),
    (["injecteur #1"], ""),
    (["Fuel injector cylinder 1"], ""),
    ([], "injector fault cyl. 1"),
    (["Insprutare cylinder 1"], ""),
    (["Einspritzventil Zylinder 1"], ""),
])
def test_equivalent_wordings_map_to_one_canonical_cause(client, components, text):
    """Four languages, six wordings, one finding."""
    resolved = taxonomy.resolve(components, text)
    assert resolved.canonical is True
    assert resolved.key == "fuel_system/injector/cylinder_1"


def test_distinct_components_are_never_merged(client):
    keys = {
        taxonomy.resolve(["Bobine cylindre 1"], "").key,
        taxonomy.resolve(["Bougie cylindre 1"], "").key,
        taxonomy.resolve(["Injecteur cylindre 1"], "").key,
        taxonomy.resolve(["Injecteur cylindre 2"], "").key,
    }
    assert len(keys) == 4


def test_an_ambiguous_cause_stays_unmerged(client):
    resolved = taxonomy.resolve(["Bobine cylindre 1", "Bougie cylindre 1"], "")
    assert resolved.canonical is False
    assert resolved.reason == taxonomy.AMBIGUOUS
    assert resolved.component is None
    assert resolved.key != taxonomy.resolve(["Bobine cylindre 1"], "").key


def test_an_unknown_cause_stays_unknown(client):
    resolved = taxonomy.resolve([], "quelque chose que le vocabulaire ne couvre pas")
    assert resolved.canonical is False
    assert resolved.reason == taxonomy.UNRESOLVED
    other = taxonomy.resolve([], "une autre chose non couverte")
    assert resolved.key != other.key, "two unknown causes must not merge with each other"


def test_the_failure_mode_is_recorded_but_does_not_split_the_cause(client):
    with_mode = taxonomy.resolve(["Injecteur cylindre 1"], "injecteur défectueux")
    without = taxonomy.resolve(["Injecteur cylindre 1"], "")
    assert with_mode.key == without.key
    assert with_mode.failure_mode == "malfunction"
    assert without.failure_mode is None


def test_technician_wording_is_preserved_verbatim(client):
    with SessionLocal() as db:
        garage, user = make_garage(db, "Atelier")
        _case, recorded = make_completed_case(
            db, garage, user, GOLF, ["P0301"], cause="Injecteur cylindre 1 HS (constaté au banc)",
        )
        assert recorded.root_cause_text == "Injecteur cylindre 1 HS (constaté au banc)"
        assert recorded.components_involved == ["Injecteur cylindre 1 HS (constaté au banc)"]
        assert recorded.root_cause_component == "fuel_system/injector/cylinder_1"
        assert recorded.cause_component == "injector"
        assert recorded.cause_position == "cylinder_1"
        assert recorded.cause_canonical is True


def test_patterns_group_on_canonical_identity_not_wording(client):
    """Two workshops, two languages, one pattern."""
    with SessionLocal() as db:
        first, first_user = make_garage(db, "Atelier FR")
        make_completed_case(db, first, first_user, GOLF, ["P0301"],
                            cause="Injecteur cylindre 1 défectueux")
        second, second_user = make_garage(db, "Verkstad SE")
        make_completed_case(db, second, second_user, GOLF, ["P0301"],
                            cause="Insprutare cylinder 1")
        patterns = db.scalars(
            select(ExperiencePattern).where(ExperiencePattern.scope_level == "engine_ecu")
        ).all()
        assert len(patterns) == 1, "different wordings produced different patterns"
        assert patterns[0].garage_count == 2
        assert patterns[0].support_label == trust.CORROBORATED
        assert patterns[0].root_cause_component == "fuel_system/injector/cylinder_1"


def test_an_unresolved_cause_is_not_shareable(client):
    with SessionLocal() as db:
        garage, user = make_garage(db, "Atelier")
        _case, recorded = make_completed_case(db, garage, user, GOLF, ["P0301"], cause="")
        assert recorded.cause_canonical is False
        assert recorded.shareable is False


# --- review 3: cross-garage trust and authority -------------------------------

def test_many_cases_from_one_workshop_are_not_many_workshops(client):
    """Volume from a single garage can never look like independent corroboration."""
    with SessionLocal() as db:
        garage, user = make_garage(db, "Atelier prolifique")
        for index in range(6):
            make_completed_case(db, garage, user, GOLF, ["P0301"], mileage=100000 + index * 7000)
        patterns = db.scalars(select(ExperiencePattern)).all()
        assert patterns
        assert {item.garage_count for item in patterns} == {1}
        assert {item.support_label for item in patterns} == {trust.EMERGING}
        other, _ = make_garage(db, "Atelier tiers")
        assert retrieval.field_evidence(db, GOLF, [{"code": "P0301"}], other.id) == []


def test_confirmations_must_exceed_contradictions_to_stay_shareable(client):
    with SessionLocal() as db:
        seeded_network(db, garages=2)
        pattern = db.scalar(
            select(ExperiencePattern).where(ExperiencePattern.scope_level == "engine_ecu")
        )
        assert trust.shareable_support(pattern.support_label)
        for index in range(2):
            garage, user = make_garage(db, f"Contre {index}")
            make_completed_case(db, garage, user, GOLF, ["P0301"], outcome="contradicted")
        db.refresh(pattern)
        assert pattern.contradicting_count == 2 and pattern.confirmed_count == 2
        assert not trust.shareable_support(pattern.support_label)
        other, _ = make_garage(db, "Tiers")
        assert retrieval.field_evidence(db, GOLF, [{"code": "P0301"}], other.id) == []


def test_revoking_a_contribution_removes_what_was_learned(client):
    with SessionLocal() as db:
        cases = seeded_network(db, garages=3)
        before = db.scalar(
            select(ExperiencePattern).where(ExperiencePattern.scope_level == "engine_ecu")
        )
        assert before.confirmed_count == 3 and before.garage_count == 3
        session_id = cases[0][0].id
        assert capture.revoke(db, session_id) is True
        db.commit()
        after = db.scalar(
            select(ExperiencePattern).where(ExperiencePattern.scope_level == "engine_ecu")
        )
        assert after.confirmed_count == 2 and after.garage_count == 2
        revoked = db.scalar(select(ExperienceCase).where(ExperienceCase.session_id == session_id))
        assert revoked.revoked_at is not None and revoked.shareable is False
        assert revoked.root_cause_text, "the raw record is kept for audit"
        assert db.scalars(
            select(ExperiencePatternCase).where(ExperiencePatternCase.case_id == revoked.id)
        ).all() == []


def test_revocation_is_idempotent(client):
    with SessionLocal() as db:
        cases = seeded_network(db, garages=3)
        session_id = cases[0][0].id
        assert capture.revoke(db, session_id) is True
        assert capture.revoke(db, session_id) is False


def test_a_revoked_case_leaves_no_stale_field_evidence(client):
    with SessionLocal() as db:
        cases = seeded_network(db, garages=2)
        other, _ = make_garage(db, "Tiers")
        assert retrieval.field_evidence(db, GOLF, [{"code": "P0301"}], other.id)
        capture.revoke(db, cases[0][0].id)
        db.commit()
        assert retrieval.field_evidence(db, GOLF, [{"code": "P0301"}], other.id) == []


def test_shared_evidence_exposes_no_identifying_field(client):
    """Nothing that could point at a vehicle, a workshop or a person."""
    with SessionLocal() as db:
        cases = seeded_network(db, garages=3)
        vins = set()
        for case, recorded in cases:
            session = db.get(DiagnosticSession, case.id)
            vehicle = db.get(VehicleProfile, session.vehicle_profile_id)
            vins.update({vehicle.id, session.id, recorded.id, session.garage_id,
                         session.technician_id})
        evidence = retrieval.field_evidence(db, GOLF, [{"code": "P0301"}], garage_id=None)
        blob = json.dumps(evidence, default=str)
        for identifier in vins:
            assert identifier not in blob
        for banned in ("vin", "registration", "technician_notes", "user_id", "garage_id",
                       "session_id"):
            assert banned not in blob.casefold()
        # The month is enough to date a pattern; the day would date a visit.
        assert evidence[0]["source"]["source_version"].endswith("-01")


def test_field_evidence_keeps_its_class_whatever_the_volume(client):
    """A hundred agreeing workshops still do not make manufacturer evidence."""
    with SessionLocal() as db:
        seeded_network(db, garages=12)
        evidence = retrieval.field_evidence(db, GOLF, [{"code": "P0301"}], garage_id=None)
        assert evidence
        detail = evidence[0]
        assert detail["trust_class"] == trust.ORVECT_FIELD
        assert detail["source"]["source_type"] == trust.FIELD_EVIDENCE_SOURCE_TYPE
        assert detail["source"]["verified"] is False
        assert trust.trust_class(detail["source"]["source_type"]) != trust.AUTHORITATIVE
        pattern = db.scalar(
            select(ExperiencePattern).where(ExperiencePattern.scope_level == "engine_ecu")
        )
        assert pattern.support_label == trust.ESTABLISHED
        assert pattern.garage_count == 12


def test_field_evidence_never_becomes_a_dtc_definition(client, monkeypatch):
    """Even well-supported experience cannot fill a definition ORVECT lacks."""
    from app.modules.research.decision import decide_research

    monkeypatch.setattr(settings_module, "tavily_api_key", "test-key")
    plan = decide_research(_research_context(
        _strong_summary(confirmed_cases=40, independent_garages=12),
        technical_definitions=[{"definition_type": "manufacturer_specific", "documented": False}],
    ))
    assert plan.needed is True
    assert "internal_definition_missing" in plan.reasons


def test_field_evidence_never_becomes_a_safety_rule(client):
    from app.modules.diagnostic_ai.safety_engine import SafetyEngine

    with SessionLocal() as db:
        seeded_network(db, garages=12)
        evidence = retrieval.field_evidence(db, GOLF, [{"code": "P0301"}], garage_id=None)
    assessment = SafetyEngine().assess({
        "fault_codes": [{"code": "P0301", "status": "active"}],
        "untrusted_user_data": {"symptoms": "ralenti irregulier"},
        "orvect_field_evidence": evidence,
    })
    assert assessment.status == "UNKNOWN"
    assert assessment.ruleIds == ["safety-rules-v1:no-matching-rule"]


def test_aggregation_is_reproducible_after_revocation(client):
    with SessionLocal() as db:
        cases = seeded_network(db, garages=4)
        capture.revoke(db, cases[0][0].id)
        db.commit()
        snapshot = {
            item.pattern_key: (item.case_count, item.confirmed_count, item.garage_count,
                               item.contradicting_count, item.support_label)
            for item in db.scalars(select(ExperiencePattern)).all()
        }
        aggregation.rebuild_all(db)
        again = {
            item.pattern_key: (item.case_count, item.confirmed_count, item.garage_count,
                               item.contradicting_count, item.support_label)
            for item in db.scalars(select(ExperiencePattern)).all()
        }
        assert again == snapshot
        assert all(counts[2] == 3 for counts in again.values())
