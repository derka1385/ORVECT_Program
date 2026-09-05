import gzip
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.database.models import (
    DiagnosticCodeAlias,
    DiagnosticDataset,
    DiagnosticDefinitionVariant,
    DiagnosticIdentifier,
    DiagnosticNamespace,
    KnowledgeSource,
    DiagnosticSourceAssessment,
)
from app.database.session import SessionLocal
from app.modules.diagnostic_data.ingestion import ADAPTERS, DatasetAdapterUnavailable, calculate_dataset_checksum
from app.modules.diagnostic_data.resolver import DiagnosticDataResolver
from app.modules.diagnostic_data.schemas import DiagnosticDatasetImport
from app.seed import ADMIN_USER_ID, VEHICLE_ID
from app.modules.diagnostic_data.admission import assertion_hash, required_claims


TEST_SOURCE_ID = "10000000-0000-0000-0000-000000000001"


def _test_evidence(db, row):
    row.provenance = {**row.provenance, "admission_tier": "A", "claims": {
        key: [{"source_id": row.source_id, "source_version": row.source_version,
               "document_reference": "synthetic-test-fixture", "confidence": "supported",
               "assertion_sha256": assertion_hash(value)}]
        for key, value in required_claims(db, row).items()
    }}


def _test_source(db):
    source = KnowledgeSource(
        id=TEST_SOURCE_ID,
        title="Synthetic VAG resolver test fixture — contains no real automotive definitions",
        source_type="internal_test",
        publisher="DiagPilot tests",
        version="test-v1",
        license_type="internal_test",
        checksum=hashlib.sha256(b"synthetic-vag-resolver-test-v1").hexdigest(),
        trust_level="test_only",
        review_status="reviewed",
        local_file_path="backend/app/tests/test_diagnostic_data.py",
    )
    db.add(source)
    db.flush()
    db.add(DiagnosticSourceAssessment(source_id=source.id, source_version=source.version,
        category="open_data", authority_level="authoritative", commercial_use="allowed",
        redistribution="allowed", attribution_requirements="Synthetic tests only",
        licence_evidence="Synthetic fixture authored by the test suite; NOT automotive data",
        provenance_notes="Never included in production seed", independent_origin="diagpilot-test-fixture",
        content_rights_confirmed=True, status="approved", assessed_by_user_id=ADMIN_USER_ID))
    db.flush()
    return source


def _catalog(db, variants, aliases=(), documented_available=None):
    source = _test_source(db)
    vag = db.scalar(select(DiagnosticNamespace).where(DiagnosticNamespace.key == "vag_uds"))
    sae = db.scalar(select(DiagnosticNamespace).where(DiagnosticNamespace.key == "sae_obd2"))
    dataset = DiagnosticDataset(
        namespace_id=vag.id,
        source_id=source.id,
        name=f"synthetic-vag-test-{uuid4()}",
        version="test-v1",
        adapter_type="structured_json",
        checksum=hashlib.sha256(str(uuid4()).encode()).hexdigest(),
        status="active",
        legal_use_confirmed=True,
        documented_available_count=documented_available if documented_available is not None else len(variants),
        imported_definition_count=len(variants),
        rejected_definition_count=0,
        imported_by_user_id=ADMIN_USER_ID,
        dataset_metadata={"test_only": True},
    )
    db.add(dataset)
    db.flush()
    identifiers = {}
    definitions = []
    for index, item in enumerate(variants):
        code = item["code"]
        identifier = identifiers.get(code)
        if not identifier:
            identifier = DiagnosticIdentifier(
                namespace_id=vag.id,
                normalized_code=code,
                canonical_display_code=item.get("display", code),
                code_type="manufacturer_specific",
                manufacturer_specific_code=code,
            )
            db.add(identifier)
            db.flush()
            identifiers[code] = identifier
        scope = item.get("scope", {})
        definition = DiagnosticDefinitionVariant(
            identifier_id=identifier.id,
            dataset_id=dataset.id,
            source_id=source.id,
            external_record_id=f"synthetic-record-{index}",
            description=item["description"],
            failure_mode=item.get("failure_mode"),
            subtype=item.get("subtype"),
            provenance={
                "record_id": f"synthetic-record-{index}",
                "document_reference": "synthetic-test-fixture",
                "section": "resolver behavior",
                "retrieved_at": "2026-01-01T00:00:00+00:00",
            },
            source_version=source.version,
            verification_status="verified" if item.get("stage", "production") in {"verified", "production"} else "unreviewed",
            promotion_stage=item.get("stage", "production"),
            is_generated=item.get("generated", False),
            **scope,
        )
        db.add(definition)
        definitions.append(definition)
    db.flush()
    alias_rows = []
    for row in definitions:
        _test_evidence(db, row)
    for source_code, target_code, stage in aliases:
        target = db.scalar(
            select(DiagnosticIdentifier).where(
                DiagnosticIdentifier.namespace_id == sae.id,
                DiagnosticIdentifier.normalized_code == target_code,
            )
        )
        if not target:
            target = DiagnosticIdentifier(
                namespace_id=sae.id,
                normalized_code=target_code,
                canonical_display_code=target_code,
                code_type="generic_standardized",
            )
            db.add(target)
            db.flush()
        row = DiagnosticCodeAlias(
            source_identifier_id=identifiers[source_code].id,
            target_identifier_id=target.id,
            dataset_id=dataset.id,
            relationship_type="generic_obd_equivalent",
            source_id=source.id,
            source_version=source.version,
            provenance={
                "record_id": f"alias-{source_code}-{target_code}",
                "document_reference": "synthetic-test-fixture",
                "retrieved_at": "2026-01-01T00:00:00+00:00",
            },
            verification_status="verified" if stage == "production" else "unreviewed",
            promotion_stage=stage,
            is_generated=False,
        )
        db.add(row)
        db.flush()
        _test_evidence(db, row)
        alias_rows.append(row)
    db.commit()
    return definitions, alias_rows


def test_generic_sae_dtc_resolution_uses_safe_legacy_catalog(client):
    response = client.post("/api/diagnostic-data/resolve", json={"namespace": "sae_obd2", "code": "P0301"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "resolved"
    assert body["definition_type"] == "generic_standardized"
    assert body["documented"] is True and body["source"]["source_id"]
    assert body["source_details"]["licensing"]["license_type"]
    assert body["source_details"]["provenance"]["checksum"]
    coverage = client.get("/api/diagnostic-data/coverage?group_by=namespace").json()
    sae = next(item for item in coverage["items"] if item["group"] == "sae_obd2")
    vag = next(item for item in coverage["items"] if item["group"] == "vag_uds")
    assert sae["covered"] == sae["legacy_active_unreviewed"] == 8_920
    assert vag["documented_available"] == 0 and vag["coverage_ratio"] is None


def test_vag_manufacturer_identifier_with_documented_generic_alias(client):
    db = SessionLocal()
    try:
        _catalog(
            db,
            [{"code": "VAG-TEST-ALIAS", "description": "Synthetic test definition; not automotive data."}],
            aliases=[("VAG-TEST-ALIAS", "P0301", "production")],
        )
    finally:
        db.close()
    body = client.post(
        "/api/diagnostic-data/resolve", json={"namespace": "vag_uds", "code": "VAG-TEST-ALIAS"}
    ).json()
    assert body["status"] == "resolved"
    assert body["generic_obd_equivalent"] == {
        "namespace": "sae_obd2",
        "code": "P0301",
        "canonical_display_code": "P0301",
    }
    generic = client.post(
        "/api/diagnostic-data/resolve", json={"namespace": "sae_obd2", "code": "P0301"}
    ).json()
    assert generic["status"] == "resolved" and generic["definition_type"] == "generic_standardized"


def test_vag_manufacturer_identifier_without_generic_alias(client):
    db = SessionLocal()
    try:
        _catalog(db, [{"code": "VAG-TEST-NO-ALIAS", "description": "Synthetic no-alias definition."}])
    finally:
        db.close()
    body = client.post(
        "/api/diagnostic-data/resolve", json={"namespace": "vag_uds", "code": "VAG-TEST-NO-ALIAS"}
    ).json()
    assert body["status"] == "resolved" and body["generic_obd_equivalent"] is None


def test_same_identifier_can_resolve_to_different_ecu_variants():
    db = SessionLocal()
    try:
        _catalog(
            db,
            [
                {"code": "VAG-TEST-VARIANT", "description": "Synthetic ECU A meaning.", "scope": {"ecu_identifiers": ["ECU-A"]}},
                {"code": "VAG-TEST-VARIANT", "description": "Synthetic ECU B meaning.", "scope": {"ecu_identifiers": ["ECU-B"]}},
            ],
        )
        resolver = DiagnosticDataResolver()
        first = resolver.resolve(db, "vag_uds", "VAG-TEST-VARIANT", {"ecu_identifiers": ["ECU-A"]})
        second = resolver.resolve(db, "vag_uds", "VAG-TEST-VARIANT", {"ecu_identifiers": ["ECU-B"]})
        assert first["description"] == "Synthetic ECU A meaning."
        assert second["description"] == "Synthetic ECU B meaning."
    finally:
        db.close()


def test_insufficient_vehicle_configuration_returns_candidates_and_missing_fields(client):
    db = SessionLocal()
    try:
        _catalog(
            db,
            [
                {"code": "VAG-TEST-MISSING", "description": "Synthetic ECU A meaning.", "scope": {"ecu_identifiers": ["ECU-A"]}},
                {"code": "VAG-TEST-MISSING", "description": "Synthetic ECU B meaning.", "scope": {"ecu_identifiers": ["ECU-B"]}},
            ],
        )
    finally:
        db.close()
    body = client.post(
        "/api/diagnostic-data/resolve", json={"namespace": "vag_uds", "code": "VAG-TEST-MISSING"}
    ).json()
    assert body["status"] == "insufficient_vehicle_configuration"
    assert body["missing_information"] == ["ecu_identifiers"] and len(body["candidates"]) == 2


def test_unknown_vag_manufacturer_identifier_is_not_invented(client):
    body = client.post(
        "/api/diagnostic-data/resolve", json={"namespace": "vag_uds", "code": "VAG-UNLISTED-GENUINE-SHAPE"}
    ).json()
    assert body["status"] == "unknown"
    assert body["definition_type"] == "manufacturer_specific"
    assert body["description"] == "Definition unavailable for this vehicle configuration."


def test_quarantined_definition_and_alias_never_leak_into_production_resolution(client):
    db = SessionLocal()
    try:
        _catalog(
            db,
            [{"code": "VAG-TEST-QUARANTINE", "description": "Must remain isolated.", "stage": "quarantined"}],
            aliases=[("VAG-TEST-QUARANTINE", "P0301", "quarantined")],
        )
    finally:
        db.close()
    body = client.post(
        "/api/diagnostic-data/resolve", json={"namespace": "vag_uds", "code": "VAG-TEST-QUARANTINE"}
    ).json()
    assert body["status"] == "unknown" and body["candidates"] == [] and body["aliases"] == []
    assert "Must remain isolated" not in json.dumps(body)


def test_provenance_and_licensing_are_preserved_through_resolver_api(client):
    db = SessionLocal()
    try:
        _catalog(db, [{"code": "VAG-TEST-PROVENANCE", "description": "Synthetic provenance definition."}])
    finally:
        db.close()
    body = client.post(
        "/api/diagnostic-data/resolve", json={"namespace": "vag_uds", "code": "VAG-TEST-PROVENANCE"}
    ).json()
    candidate = body["candidates"][0]
    assert candidate["provenance"]["document_reference"] == "synthetic-test-fixture"
    assert candidate["source"]["source_id"] == TEST_SOURCE_ID
    assert candidate["source"]["source_version"] == "test-v1"
    assert candidate["source"]["licensing"] == {
        "license_type": "internal_test",
        "publisher": "DiagPilot tests",
        "legal_use_confirmed": True,
    }
    assert candidate["source"]["dataset"]["checksum"]


def test_equally_applicable_definitions_are_returned_as_ambiguous_candidates(client):
    db = SessionLocal()
    try:
        _catalog(
            db,
            [
                {"code": "VAG-TEST-AMBIGUOUS", "description": "Synthetic candidate one."},
                {"code": "VAG-TEST-AMBIGUOUS", "description": "Synthetic candidate two."},
            ],
        )
    finally:
        db.close()
    body = client.post(
        "/api/diagnostic-data/resolve", json={"namespace": "vag_uds", "code": "VAG-TEST-AMBIGUOUS"}
    ).json()
    assert body["status"] == "ambiguous" and body["documented"] is False
    assert {item["description"] for item in body["candidates"]} == {
        "Synthetic candidate one.",
        "Synthetic candidate two.",
    }


def test_exact_ecu_specific_resolution_when_metadata_is_sufficient(client):
    db = SessionLocal()
    try:
        _catalog(
            db,
            [
                {"code": "VAG-TEST-EXACT", "description": "Synthetic ECU A exact meaning.", "scope": {"ecu_module": "engine", "ecu_identifiers": ["PART-A"]}},
                {"code": "VAG-TEST-EXACT", "description": "Synthetic ECU B exact meaning.", "scope": {"ecu_module": "engine", "ecu_identifiers": ["PART-B"]}},
            ],
        )
    finally:
        db.close()
    body = client.post(
        "/api/diagnostic-data/resolve",
        json={
            "namespace": "vag_uds",
            "code": "VAG-TEST-EXACT",
            "vehicle_id": VEHICLE_ID,
            "ecu_module": "engine",
            "ecu_identifiers": ["PART-B"],
        },
    ).json()
    assert body["status"] == "resolved"
    assert body["description"] == "Synthetic ECU B exact meaning."
    assert len(body["candidates"]) == 1


def test_structured_ingestion_starts_in_quarantine_and_uses_manifest_denominator(client):
    db = SessionLocal()
    try:
        _test_source(db)
        db.commit()
    finally:
        db.close()
    raw = {
        "schema_version": "1.0",
        "source_id": TEST_SOURCE_ID,
        "namespace": {
            "key": "vag_uds",
            "manufacturer": "Volkswagen Group",
            "brand_group": "VAG",
            "code_system": "UDS_OEM",
            "description": "VAG manufacturer diagnostic identifiers; definitions require licensed source data",
        },
        "dataset": {
            "name": "synthetic-ingestion-test",
            "version": "test-v1",
            "format": "structured_json",
            "legal_use_confirmed": True,
            "documented_available_count": 2,
            "content_checksum_sha256": "0" * 64,
            "metadata": {"test_only": True},
        },
        "definitions": [
            {
                "code": "VAG-TEST-INGEST",
                "canonical_display_code": "VAG-TEST-INGEST",
                "code_type": "manufacturer_specific",
                "manufacturer_specific_code": "VAG-TEST-INGEST",
                "description": "Synthetic imported definition.",
                "applicability": {"ecu_module": "engine"},
                "provenance": {
                    "record_id": "synthetic-ingest-1",
                    "document_reference": "synthetic-test-fixture",
                    "retrieved_at": "2026-01-01T00:00:00Z",
                },
                "source_version": "test-v1",
                "origin": "source_extract",
            }
        ],
        "aliases": [],
    }
    payload = DiagnosticDatasetImport.model_validate(raw)
    raw["dataset"]["content_checksum_sha256"] = calculate_dataset_checksum(payload)
    response = client.post("/api/diagnostic-data/imports", json=raw)
    assert response.status_code == 201
    db = SessionLocal()
    try:
        row = db.scalar(select(DiagnosticDefinitionVariant).where(DiagnosticDefinitionVariant.description == "Synthetic imported definition."))
        assert row.promotion_stage == "quarantined" and row.verification_status == "unreviewed"
    finally:
        db.close()
    coverage = client.get("/api/diagnostic-data/coverage?group_by=namespace").json()
    vag = next(item for item in coverage["items"] if item["group"] == "vag_uds")
    assert vag["documented_available"] == 2 and vag["production"] == 0 and vag["unavailable"] == 1


def test_generated_definition_cannot_enter_promotion_workflow(client):
    db = SessionLocal()
    try:
        definitions, _ = _catalog(
            db,
            [{"code": "VAG-TEST-GENERATED", "description": "Generated test row.", "stage": "quarantined", "generated": True}],
        )
        definition_id = definitions[0].id
    finally:
        db.close()
    response = client.post(
        f"/api/diagnostic-data/definitions/{definition_id}/promote",
        json={"target_stage": "source_matched", "reason": "Synthetic promotion rejection test"},
    )
    assert response.status_code == 409 and "never be promoted" in response.json()["detail"]


def test_verified_definition_must_follow_every_promotion_stage(client):
    db = SessionLocal()
    try:
        definitions, _ = _catalog(
            db,
            [{"code": "VAG-TEST-PROMOTION", "description": "Synthetic promotion workflow row.", "stage": "quarantined"}],
        )
        definition_id = definitions[0].id
    finally:
        db.close()
    reason = "Synthetic human review for lifecycle test"
    for stage in ("source_matched", "verified", "production"):
        response = client.post(
            f"/api/diagnostic-data/definitions/{definition_id}/promote",
            json={"target_stage": stage, "reason": reason},
        )
        assert response.status_code == 200 and response.json()["promotion_stage"] == stage
    resolved = client.post(
        "/api/diagnostic-data/resolve", json={"namespace": "vag_uds", "code": "VAG-TEST-PROMOTION"}
    ).json()
    assert resolved["status"] == "resolved"


def test_documented_alias_follows_the_same_reviewed_promotion_sequence(client):
    db = SessionLocal()
    try:
        _, aliases = _catalog(
            db,
            [{"code": "VAG-TEST-ALIAS-PROMOTION", "description": "Synthetic alias promotion row."}],
            aliases=[("VAG-TEST-ALIAS-PROMOTION", "P0301", "quarantined")],
        )
        alias_id = aliases[0].id
    finally:
        db.close()
    listing = client.get("/api/diagnostic-data/aliases?stage=quarantined&page_size=1")
    assert listing.status_code == 200 and listing.json()["items"][0]["id"] == alias_id
    reason = "Synthetic human alias review lifecycle test"
    for stage in ("source_matched", "verified", "production"):
        response = client.post(
            f"/api/diagnostic-data/aliases/{alias_id}/promote",
            json={"target_stage": stage, "reason": reason},
        )
        assert response.status_code == 200 and response.json()["promotion_stage"] == stage
    resolved = client.post(
        "/api/diagnostic-data/resolve",
        json={"namespace": "vag_uds", "code": "VAG-TEST-ALIAS-PROMOTION"},
    ).json()
    assert resolved["generic_obd_equivalent"]["code"] == "P0301"


def test_oem_namespace_flows_through_diagnostic_engine_and_llm_explanation(client):
    db = SessionLocal()
    try:
        _catalog(db, [{"code": "VAG-TEST-PIPELINE", "description": "Synthetic pipeline definition."}])
    finally:
        db.close()
    case = client.post("/api/diagnostics", json={"vehicle_id": VEHICLE_ID}).json()
    added = client.post(
        f"/api/diagnostics/{case['id']}/fault-codes",
        json={"fault_codes": [{"namespace": "vag_uds", "code": "VAG-TEST-PIPELINE", "technician_verification": "confirmed"}]},
    )
    assert added.status_code == 201
    assert added.json()[0]["value"]["resolution_status"] == "resolved"
    analysis = client.post(f"/api/diagnostics/{case['id']}/analyze")
    assert analysis.status_code == 200
    interpreted = analysis.json()["interpretedFaultCodes"][0]
    assert interpreted["namespace"] == "vag_uds"
    assert interpreted["meaning"] == "Synthetic pipeline definition."
    assert interpreted["sourceStatus"] == "provided_by_database"


def test_vag_coverage_reports_codes_without_documented_generic_equivalent(client):
    db = SessionLocal()
    try:
        _catalog(
            db,
            [
                {"code": "VAG-TEST-COVERED-ALIAS", "description": "Synthetic alias coverage row."},
                {"code": "VAG-TEST-COVERED-NATIVE", "description": "Synthetic native coverage row."},
            ],
            aliases=[("VAG-TEST-COVERED-ALIAS", "P0301", "production")],
        )
    finally:
        db.close()
    report = client.get("/api/diagnostic-data/coverage?group_by=brand").json()
    assert report["vag"] == {
        "production_manufacturer_identifiers": 2,
        "with_documented_generic_obd_equivalent": 1,
        "without_generic_obd_equivalent": 1,
    }


def test_same_identifier_from_two_ecus_is_not_collapsed_in_explanation_layer(client):
    db = SessionLocal()
    try:
        _catalog(
            db,
            [
                {"code": "VAG-TEST-TWO-ECUS", "description": "Synthetic engine ECU meaning.", "scope": {"ecu_module": "engine"}},
                {"code": "VAG-TEST-TWO-ECUS", "description": "Synthetic gearbox ECU meaning.", "scope": {"ecu_module": "gearbox"}},
            ],
        )
    finally:
        db.close()
    case = client.post("/api/diagnostics", json={"vehicle_id": VEHICLE_ID}).json()
    response = client.post(
        f"/api/diagnostics/{case['id']}/fault-codes",
        json={
            "fault_codes": [
                {"namespace": "vag_uds", "code": "VAG-TEST-TWO-ECUS", "ecu": "engine", "technician_verification": "confirmed"},
                {"namespace": "vag_uds", "code": "VAG-TEST-TWO-ECUS", "ecu": "gearbox", "technician_verification": "confirmed"},
            ]
        },
    )
    assert response.status_code == 201
    analysis_response = client.post(f"/api/diagnostics/{case['id']}/analyze")
    assert analysis_response.status_code == 200, analysis_response.text
    analysis = analysis_response.json()
    assert {(item["ecu"], item["meaning"]) for item in analysis["interpretedFaultCodes"]} == {
        ("engine", "Synthetic engine ECU meaning."),
        ("gearbox", "Synthetic gearbox ECU meaning."),
    }


def test_legacy_quarantine_archive_is_complete_and_runtime_inert():
    archive_path = Path(__file__).parents[3] / "quarantine" / "dtc_catalog_legacy_quarantine.json.gz"
    if not archive_path.exists():
        pytest.skip("The quarantine archive is intentionally excluded from runtime container images")
    with gzip.open(archive_path, "rt") as handle:
        archive = json.load(handle)
    assert archive["entry_count"] == 56_220
    assert archive["runtime_policy"] == "NEVER_LOADED_BY_PRODUCTION_RESOLVER"
    assert all(item["promotion_stage"] == "quarantined" for item in archive["entries"])
    canonical = json.dumps(archive["entries"], sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    assert hashlib.sha256(canonical).hexdigest() == archive["entries_checksum_sha256"]
    runtime = Path(__file__).parents[1] / "modules" / "diagnostic_data" / "resolver.py"
    assert "dtc_catalog_legacy_quarantine" not in runtime.read_text()


def test_odx_and_pdx_adapters_are_registered_but_fail_closed_without_a_licensed_profile():
    assert {"structured_json", "sae_structured", "oem_structured", "odx", "pdx"} <= set(ADAPTERS)
    for name in ("odx", "pdx"):
        with pytest.raises(DatasetAdapterUnavailable, match="no licensed, profile-specific parser"):
            ADAPTERS[name].parse(b"not-imported")
