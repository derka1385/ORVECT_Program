"""Nebius reasoning + Tavily evidence: wiring, provenance and failure modes."""

import json

import httpx
import pytest

from app.core.config import settings
from app.modules.diagnostic_ai.confidence import assess as assess_confidence
from app.modules.diagnostic_ai.nebius import NebiusAutomotiveAIProvider, _model_facing_schema
from app.modules.diagnostic_ai.providers import AIInvalidResponse, AIProviderUnavailable, canonical_source
from app.modules.diagnostic_ai.schemas import LLMDiagnosticAnalysis
from app.modules.research import tavily
from app.modules.research.decision import build_queries, decide_research
from app.modules.research.retriever import build_evidence


EXTERNAL_SOURCE = {
    "source_id": "tavily:abc123",
    "source_type": "technical_documentation",
    "source_version": "2026-09-18",
    "vehicle_compatibility": {"scope": "external_research_unverified", "query": "q"},
    "timestamp": "2026-09-18T10:00:00+00:00",
    "verified": False,
    "url": "https://bosch-automotive.example/p0301",
    "title": "Misfire diagnosis",
    "domain": "bosch-automotive.example",
}


CATALOG_SOURCE = {
    "source_id": "catalog-1",
    "source_type": "open_source_dataset",
    "source_version": "1.0",
    "vehicle_compatibility": {"scope": "generic_standardized"},
    "timestamp": "2026-01-01T00:00:00+00:00",
    "verified": False,
}


def _context(**overrides):
    base = {
        "vehicle": {
            "make": "Volkswagen",
            "model": "Golf VII",
            "model_year": 2018,
            "engine_code": "CZCA",
            "engine_name": "1.4 TSI",
            "configuration_confirmed": True,
        },
        "fault_codes": [{"code": "P0301", "namespace": "sae_obd2", "ecu": None, "freeze_frame": {}}],
        "technical_definitions": [
            {
                "namespace": "sae_obd2",
                "code": "P0301",
                "ecu": None,
                "description": "Cylinder 1 Misfire Detected",
                "definition_type": "generic_standardized",
                "documented": True,
                "source": CATALOG_SOURCE,
            }
        ],
        "technical_excerpts": [{"source": EXTERNAL_SOURCE}],
        "measurements": [],
        "previous_steps": [],
        "images": [],
        "untrusted_user_data": {"symptoms": "ralenti irrégulier", "circumstances": ""},
        "diagnostic_engine": {"hypotheses_allowed": True, "required_status": None, "reasons": []},
    }
    base.update(overrides)
    return base


def _valid_payload(with_source=True, expanded=False):
    """A minimal schema-valid analysis.

    `expanded=False` mirrors what the model emits (a bare source_id);
    `expanded=True` mirrors what the server has rebuilt, for tests that
    validate the payload directly.
    """
    reference = EXTERNAL_SOURCE if expanded else {"source_id": EXTERNAL_SOURCE["source_id"]}
    citation = [reference] if with_source else []
    return {
        "schemaVersion": "2.0",
        "caseSummary": "Raté d’allumage isolé sur le cylindre 1.",
        "reasoningApproach": "Corrélation DTC, symptômes et preuves externes.",
        "interpretedFaultCodes": [
            {
                "namespace": "sae_obd2",
                "code": "P0301",
                "ecu": None,
                "meaning": "Cylinder 1 Misfire Detected",
                "definitionType": "generic_standardized",
                "sourceStatus": "provided_by_database",
                "sources": [CATALOG_SOURCE] if expanded else [{"source_id": CATALOG_SOURCE["source_id"]}],
                "relevance": "primary",
            }
        ],
        "correlations": [],
        "hypotheses": [
            {
                "id": "h1",
                "label": "Bobine d’allumage cylindre 1",
                "component": "ignition_coil_1",
                "confidence": 0.7,
                "supportingEvidence": ["Raté isolé sur un seul cylindre"],
                "contradictingEvidence": [],
                "requiredConfirmation": ["Permutation contrôlée des bobines 1 et 2"],
                "status": "possible",
                "verificationStatus": "partially_verified" if with_source else "unverified",
                "sources": citation,
            }
        ],
        "imageEvidence": [],
        "missingInformation": [],
        "nextChecks": [
            {
                "id": "c1",
                "order": 1,
                "title": "Permuter les bobines 1 et 2",
                "objective": "Durée estimée : 5–10 min. Déterminer si le raté suit la bobine.",
                "prerequisites": ["Moteur froid"],
                "instructions": ["Permuter la bobine 1 avec la bobine 2."],
                "safetyWarnings": ["Contact coupé."],
                "expectedResults": [
                    {
                        "outcome": "Le raté suit la bobine",
                        "interpretation": "Défaut de bobine fortement indiqué.",
                        "nextAction": "Poursuivre sur le circuit d’allumage.",
                    }
                ],
                "requiredTools": ["Outillage à main"],
                "estimatedDifficulty": "easy",
                "verificationStatus": "partially_verified" if with_source else "unverified",
                "manufacturerProcedure": False,
                "sources": citation,
            }
        ],
        "finalConclusion": {"status": "testing_required", "summary": "Contrôles à réaliser."},
        "warnings": ["Ne pas remplacer l’injecteur avant les contrôles simples."],
    }


def _nebius_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://nebius.test/v1")


def _completion(payload, usage=None):
    return httpx.Response(
        200,
        json={
            "model": "Qwen/Qwen3-235B-A22B",
            "choices": [{"message": {"content": json.dumps(payload)}}],
            "usage": usage or {"prompt_tokens": 1200, "completion_tokens": 800, "total_tokens": 2000},
        },
    )


# --- Nebius -------------------------------------------------------------

def test_model_facing_schema_asks_only_for_a_source_id():
    """The model may never supply a URL, timestamp or verification flag."""
    schema = _model_facing_schema()
    assert schema["$defs"]["SourceReference"]["properties"] == {"source_id": {"type": "string"}}
    assert "url" not in schema["$defs"]["SourceReference"]["properties"]


@pytest.mark.anyio
async def test_nebius_expands_citations_and_reports_token_usage():
    context = _context()
    provider = NebiusAutomotiveAIProvider(_nebius_client(lambda request: _completion(_valid_payload())))
    result = await provider.analyze_initial_case(context, [])
    assert result.provider == "nebius"
    assert result.token_usage["total_tokens"] == 2000
    # The bare {source_id} citation is rebuilt into the full canonical source.
    assert result.analysis.hypotheses[0].sources[0].model_dump(mode="json") == canonical_source(EXTERNAL_SOURCE)
    assert result.analysis.hypotheses[0].sources[0].url == EXTERNAL_SOURCE["url"]


@pytest.mark.anyio
async def test_nebius_drops_a_citation_the_context_never_contained():
    """An invented source_id is removed, and the claim falls back to unverified."""
    payload = _valid_payload()
    payload["hypotheses"][0]["sources"] = [{"source_id": "tavily:fabricated"}]
    provider = NebiusAutomotiveAIProvider(_nebius_client(lambda request: _completion(payload)))
    result = await provider.analyze_initial_case(_context(), [])
    assert result.analysis.hypotheses[0].sources == []
    assert result.analysis.hypotheses[0].verificationStatus == "unverified"
    # Dropping it is normalization, not a repair: no second call was needed.
    assert result.normalized is True
    assert result.repaired is False


@pytest.mark.anyio
async def test_nebius_invalid_json_is_repaired_once_then_fails_cleanly():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "not json at all"}}]})

    provider = NebiusAutomotiveAIProvider(_nebius_client(handler))
    with pytest.raises(AIInvalidResponse):
        await provider.analyze_initial_case(_context(), [])
    assert calls["n"] == 2, "exactly one repair attempt, never an unbounded retry loop"


@pytest.mark.anyio
async def test_nebius_falls_back_to_json_object_when_schema_mode_is_rejected():
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body["response_format"]["type"])
        if body["response_format"]["type"] == "json_schema":
            return httpx.Response(400, json={"error": "response_format not supported"})
        return _completion(_valid_payload())

    provider = NebiusAutomotiveAIProvider(_nebius_client(handler))
    result = await provider.analyze_initial_case(_context(), [])
    assert seen[:2] == ["json_schema", "json_object"]
    assert result.analysis.hypotheses


@pytest.mark.anyio
async def test_nebius_rejects_a_bad_key_without_leaking_it(monkeypatch):
    secret = "nbk-super-secret-value"
    monkeypatch.setattr(settings, "nebius_api_key", secret)
    provider = NebiusAutomotiveAIProvider(
        _nebius_client(lambda request: httpx.Response(401, json={"error": f"invalid api key {secret}"}))
    )
    with pytest.raises(AIProviderUnavailable) as raised:
        await provider.analyze_initial_case(_context(), [])
    assert "clé" in str(raised.value)
    assert secret not in str(raised.value), "the provider error must never carry the key"


# --- Research decision --------------------------------------------------

def test_queries_are_vehicle_specific_and_never_the_bare_code():
    queries = build_queries(_context())
    assert queries, "a query must be built for a known vehicle"
    assert all(query.strip() != "P0301" for query in queries)
    assert any("Volkswagen" in query and "P0301" in query for query in queries)
    assert any("CZCA" in query for query in queries), "engine code must drive one query"


def test_research_is_skipped_when_internal_knowledge_covers_the_case(monkeypatch):
    monkeypatch.setattr(settings, "tavily_api_key", "test-key")
    context = _context()
    context["internal_excerpts"] = [{"id": f"k{i}"} for i in range(4)]
    plan = decide_research(context)
    assert plan.needed is False
    assert plan.reasons == ["internal_knowledge_sufficient"]


def test_research_is_triggered_for_multiple_codes(monkeypatch):
    monkeypatch.setattr(settings, "tavily_api_key", "test-key")
    context = _context(
        fault_codes=[{"code": "P0301"}, {"code": "P0171"}, {"code": "P0507"}]
    )
    context["internal_excerpts"] = [{"id": f"k{i}"} for i in range(4)]
    plan = decide_research(context)
    assert plan.needed is True
    assert "multiple_codes_need_shared_cause_evidence" in plan.reasons


def test_research_never_runs_without_a_configured_key(monkeypatch):
    monkeypatch.setattr(settings, "tavily_api_key", "")
    assert decide_research(_context()).needed is False


def test_domain_classification_ranks_oem_above_forums():
    assert tavily.classify_domain("erwin.volkswagen.de") == "oem_manufacturer"
    assert tavily.classify_domain("nhtsa.gov") == "safety_authority"
    assert tavily.classify_domain("golfmk7.com") == "specialist_community"
    assert (
        tavily.SOURCE_RANK[tavily.classify_domain("erwin.volkswagen.de")]
        > tavily.SOURCE_RANK[tavily.classify_domain("golfmk7.com")]
    )


# --- Failure modes ------------------------------------------------------

@pytest.mark.anyio
async def test_tavily_outage_degrades_instead_of_failing_the_diagnosis(monkeypatch, db_session):
    async def unavailable(queries):
        raise tavily.TavilyUnavailable("Tavily is down")

    monkeypatch.setattr(settings, "tavily_api_key", "test-key")
    monkeypatch.setattr(tavily, "search", unavailable)
    excerpts, metadata = await build_evidence(db_session, _context(), [])
    assert metadata["researchTriggered"] is True
    assert metadata["externalResearchAvailable"] is False
    assert metadata["researchError"]
    assert excerpts == [], "no external excerpt is invented when research fails"


@pytest.mark.anyio
async def test_one_failing_query_does_not_lose_the_other_results(monkeypatch):
    monkeypatch.setattr(settings, "tavily_api_key", "test-key")

    def handler(request):
        if "recall" in json.loads(request.content)["query"]:
            return httpx.Response(500, json={"error": "upstream"})
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://nhtsa.gov/a",
                        "title": "Recall notice",
                        "content": "text",
                        "score": 0.9,
                    }
                ]
            },
        )

    async def patched(queries):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="https://tavily.test"
        ) as client:
            results, failed = [], []
            for query in queries:
                try:
                    results.extend(await tavily._one_search(client, query))
                except Exception:
                    failed.append(query)
            return tavily._dedupe(results), failed

    monkeypatch.setattr(tavily, "search", patched)
    evidence, failed = await tavily.search(["P0301 causes", "Golf recall bulletin"])
    assert failed == ["Golf recall bulletin"]
    assert len(evidence) == 1 and evidence[0]["source_type"] == "safety_authority"


def test_results_without_a_real_url_are_discarded():
    """A citation Orvect cannot link to is not evidence."""
    import asyncio

    def handler(request):
        return httpx.Response(
            200,
            json={
                "results": [
                    {"url": "", "title": "No link", "content": "x", "score": 1},
                    {"url": "https://ok.example/a", "title": "Linked", "content": "y", "score": 1},
                ]
            },
        )

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="https://tavily.test"
        ) as client:
            return await tavily._one_search(client, "query")

    items = asyncio.run(run())
    assert [item["url"] for item in items] == ["https://ok.example/a"]


# --- Confidence ---------------------------------------------------------

def test_confidence_is_zero_without_hypotheses():
    analysis = LLMDiagnosticAnalysis.model_validate({**_valid_payload(expanded=True), "hypotheses": []})
    result = assess_confidence(analysis, _context(), {})
    assert result.score == 0 and result.label == "low"
    assert result.improvedBy


def test_confidence_rises_with_independent_good_sources_and_measurements():
    analysis = LLMDiagnosticAnalysis.model_validate(_valid_payload(expanded=True))
    bare = assess_confidence(analysis, _context(), {"researchTriggered": False})
    richer = assess_confidence(
        analysis,
        _context(measurements=[{"name": "fuel_trim", "value": 12}]),
        {"researchTriggered": True, "externalResearchAvailable": True},
    )
    assert richer.score > bare.score
    assert richer.decisionSource == "confidence_heuristic"
    assert 0 <= richer.score <= 95


def test_confidence_drops_when_external_verification_was_wanted_but_unavailable():
    analysis = LLMDiagnosticAnalysis.model_validate(_valid_payload(expanded=True))
    context = _context()
    available = assess_confidence(analysis, context, {"researchTriggered": True, "externalResearchAvailable": True})
    missing = assess_confidence(analysis, context, {"researchTriggered": True, "externalResearchAvailable": False})
    assert missing.score < available.score


# --- Decision boundary --------------------------------------------------

def test_do_not_replace_warnings_survive_the_replacement_boundary():
    """Telling a technician NOT to replace a part is the point, not a violation."""
    from app.modules.diagnostic_ai.providers import boundary_violation

    for allowed in (
        "Ne pas remplacer l’injecteur ni le calculateur avant les contrôles simples.",
        "Do not replace the injector before the simple checks.",
        "Éviter de remplacer la bobine sans contrôle.",
        "No part replacement is recommended.",
    ):
        assert boundary_violation(allowed) is None, allowed


def test_affirmative_replacement_recommendations_are_still_blocked():
    from app.modules.diagnostic_ai.providers import boundary_violation

    for blocked in (
        "La bobine doit être remplacée.",
        "The coil should be replaced.",
        "Pièce à remplacer : bobine 1.",
        "Le véhicule peut rouler sans risque.",
    ):
        assert boundary_violation(blocked) is not None, blocked


def test_long_tail_domains_are_ranked_not_dumped_into_general_web():
    """Real Tavily results are mostly sites absent from any allowlist."""
    observed = {
        "autosafety.org": "safety_authority",
        "justanswer.com": "specialist_community",
        "go-parts.com": "repair_technical_resource",
        "bobsmechanicalrepairs.co.uk": "repair_technical_resource",
        "carista.com": "repair_technical_resource",
    }
    for domain, expected in observed.items():
        assert tavily.classify_domain(domain) == expected, domain
    # Non-automotive domains must still fall through to general_web.
    for domain in ("bbc.co.uk", "wikipedia.org", "au7o.io"):
        assert tavily.classify_domain(domain) == "general_web", domain


def test_ranked_hypotheses_cannot_coexist_with_insufficient_evidence():
    """A report that ranks causes has not found the evidence insufficient."""
    from app.modules.diagnostic_ai.providers import _normalize_provider_payload

    payload = _valid_payload()
    payload["finalConclusion"] = {"status": "insufficient_evidence", "summary": "x"}
    normalized, changed = _normalize_provider_payload(payload, _context())
    assert normalized["finalConclusion"]["status"] == "testing_required"
    assert changed is True


def test_engine_stop_status_is_never_rewritten():
    """When the gate forbids hypotheses, its required status stands."""
    from app.modules.diagnostic_ai.providers import _normalize_provider_payload

    payload = {**_valid_payload(), "hypotheses": []}
    payload["finalConclusion"] = {"status": "insufficient_evidence", "summary": "x"}
    context = _context(
        diagnostic_engine={
            "hypotheses_allowed": False,
            "required_status": "insufficient_evidence",
            "reasons": [],
        }
    )
    normalized, _ = _normalize_provider_payload(payload, context)
    assert normalized["finalConclusion"]["status"] == "insufficient_evidence"


def test_an_all_zero_ranking_is_rejected_as_a_model_failure():
    """Proposing causes while scoring every one at zero ranks nothing."""
    from app.modules.diagnostic_ai.providers import validate_provider_sources

    payload = _valid_payload(with_source=False, expanded=True)
    for item in payload["hypotheses"]:
        item["confidence"] = 0.0
    analysis = LLMDiagnosticAnalysis.model_validate(payload)
    with pytest.raises(AIInvalidResponse):
        validate_provider_sources(analysis, _context())


def test_a_normal_ranking_still_passes():
    from app.modules.diagnostic_ai.providers import validate_provider_sources

    analysis = LLMDiagnosticAnalysis.model_validate(_valid_payload(with_source=False, expanded=True))
    validate_provider_sources(analysis, _context())


def test_citation_ids_are_scrubbed_from_prose():
    """Ids belong in `sources`; the exact phrasing seen in a live run is tidied."""
    from app.modules.diagnostic_ai.providers import strip_source_ids

    live = ("Symptômes typiques de misfire : ralenti irrégulier, vibrations à l’arrêt "
            "(sources externes non vérifiées, ex. tavily:ebee7e9b45367ff0, tavily:5caf748950c71f01).")
    assert strip_source_ids(live) == "Symptômes typiques de misfire : ralenti irrégulier, vibrations à l’arrêt (sources externes non vérifiées)."
    assert strip_source_ids("Voir tavily:0123456789ab pour le détail.") == "Voir pour le détail."
    assert strip_source_ids("Aucun identifiant ici.") == "Aucun identifiant ici."
    # The sources array itself is untouched: only free text is scrubbed.
    payload = _valid_payload()
    payload["hypotheses"][0]["supportingEvidence"] = ["Raté isolé (tavily:abc123def456)"]
    from app.modules.diagnostic_ai.providers import _normalize_provider_payload
    normalized, changed = _normalize_provider_payload(payload, _context())
    assert changed is True
    assert normalized["hypotheses"][0]["supportingEvidence"] == ["Raté isolé"]
    assert normalized["hypotheses"][0]["sources"][0]["source_id"] == EXTERNAL_SOURCE["source_id"]
